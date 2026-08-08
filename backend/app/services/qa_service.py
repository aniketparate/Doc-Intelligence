from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.guardrails import confidence_scorer
from app.core.llm_client import llm_client
from app.core.retriever import retriever
from app.core.session_memory import session_memory_manager
from app.models.database import ChatMessage, ChatSession, User
from app.services.project_service import get_project_or_403


class QAService:
    async def ask(
        self,
        db: AsyncSession,
        user: User,
        project_id: str,
        session_id: str | UUID,
        question: str,
        top_k: int,
        retrieval_mode: str,
        use_hyde: bool,
    ) -> dict:
        started = time.perf_counter()

        project = await get_project_or_403(project_id=project_id, user=user, db=db)
        session = await self._get_session_or_404(db=db, session_id=session_id, project_id=str(project.id), user_id=str(user.id))

        # 1) Load session history + summary.
        history_messages, summary = await session_memory_manager.build_context_for_llm(
            db=db,
            session_id=session.id,
            current_question=question,
        )

        # 2) Rewrite follow-up question.
        rewritten_question = await session_memory_manager.rewrite_followup(question=question, history=history_messages)

        # 3) Retrieve chunks.
        retrieved_chunks = await retriever.retrieve(
            db=db,
            collection_name=project.qdrant_namespace,
            project_id=project.id,
            query=rewritten_question,
            use_hyde=use_hyde,
            filters=None,
        )
        retrieved_chunks = retrieved_chunks[: max(1, top_k)]

        # 4) Build LLM prompt with history + retrieved context.
        retrieved_context = self._build_retrieved_context(retrieved_chunks)
        summary_block = f"Conversation Summary:\n{summary}\n" if summary else ""
        system_prompt = llm_client.build_qa_system_prompt(summary_block=summary_block, retrieved_context=retrieved_context)

        llm_messages = history_messages + [{"role": "user", "content": question.strip()}]

        # 5) Call llm_client.complete().
        llm_answer = await llm_client.complete(system=system_prompt, messages=llm_messages)

        # 6) Score confidence.
        scored = confidence_scorer.score(answer=llm_answer, chunks=retrieved_chunks)

        # 7) Apply refusal / low-confidence logic (via guardrails.score result).
        final_answer = scored.answer

        # 8) Persist user and assistant messages.
        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            content=question.strip(),
        )
        db.add(user_message)

        sources_payload = [
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "page": chunk.page_num,
                "source_filename": chunk.source_filename,
                "reranker_score": chunk.reranker_score,
            }
            for chunk in retrieved_chunks
        ]

        retrieval_meta = {
            "rewritten_question": rewritten_question,
            "retrieval_mode": retrieval_mode,
            "use_hyde": use_hyde,
            "top_k": top_k,
        }

        assistant_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=final_answer,
            sources=sources_payload,
            confidence=scored.confidence,
            retrieval_meta=retrieval_meta,
        )
        db.add(assistant_message)

        # 9) Auto-generate title when missing.
        if not session.title:
            session.title = self._generate_title(question)
        session.updated_at = datetime.now(timezone.utc)

        await db.commit()

        latency_ms = int((time.perf_counter() - started) * 1000)

        # 10) Return response matching Section 8.5 schema.
        return {
            "answer": final_answer,
            "confidence": scored.confidence,
            "confidence_breakdown": scored.confidence_breakdown,
            "sources": sources_payload,
            "refused": scored.refused,
            "latency_ms": latency_ms,
        }

    @staticmethod
    async def _get_session_or_404(db: AsyncSession, session_id: str | UUID, project_id: str, user_id: str) -> ChatSession:
        session = await db.get(ChatSession, UUID(str(session_id)))
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        if str(session.project_id) != project_id or str(session.user_id) != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return session

    @staticmethod
    def _build_retrieved_context(chunks: list) -> str:
        blocks: list[str] = []
        for chunk in chunks:
            body = (chunk.llm_context_text or chunk.window_text or chunk.text or "").strip()
            if not body:
                continue
            blocks.append(f"{chunk.context_prefix}{body}")
        return "\n\n".join(blocks)

    @staticmethod
    def _generate_title(question: str) -> str:
        clean = " ".join(question.split())
        if len(clean) <= 80:
            return clean
        return clean[:77].rstrip() + "..."


qa_service = QAService()
