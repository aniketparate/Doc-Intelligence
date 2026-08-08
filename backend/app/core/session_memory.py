from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm_client import llm_client
from app.models.database import ChatMessage
from app.services.auth_service import get_redis


SUMMARY_PROMPT = (
    "Summarize this conversation concisely, preserving all key "
    "facts, numbers, names, and decisions mentioned."
)

REWRITE_PROMPT = (
    "Given this conversation history, rewrite the follow-up question "
    "as a complete standalone question. Return ONLY the rewritten "
    "question, nothing else."
)

SUMMARY_TTL_SECONDS = 3600


class SessionMemoryManager:
    async def build_context_for_llm(
        self,
        db: AsyncSession,
        session_id: str | UUID,
        current_question: str,
    ) -> tuple[list[dict[str, str]], str]:
        _ = current_question
        messages = await self._load_session_messages(db=db, session_id=session_id)

        if len(messages) <= 10:
            return self._format_messages(messages), ""

        old_messages = messages[:-10]
        recent_messages = messages[-10:]
        summary = await self.get_or_create_summary(session_id=session_id, messages=old_messages)
        return self._format_messages(recent_messages), summary

    async def get_or_create_summary(self, session_id: str | UUID, messages: list[ChatMessage]) -> str:
        if not messages:
            return ""

        cache_key = self._summary_cache_key(session_id=session_id, msg_count=len(messages))
        redis = await get_redis()

        cached = await redis.get(cache_key)
        if cached:
            return cached

        transcript = self._format_transcript(messages)
        summary = await llm_client.complete(
            system=SUMMARY_PROMPT,
            messages=[{"role": "user", "content": transcript}],
        )

        summary = summary.strip()
        await redis.set(cache_key, summary, ex=SUMMARY_TTL_SECONDS)
        return summary

    async def rewrite_followup(self, question: str, history: list[dict[str, str]]) -> str:
        if not history:
            return question

        history_slice = history[-4:]
        history_text = "\n".join(
            f"{item.get('role', 'user').upper()}: {item.get('content', '').strip()}" for item in history_slice
        ).strip()

        if not history_text:
            return question

        user_prompt = f"Conversation History:\n{history_text}\n\nFollow-up Question:\n{question.strip()}"
        rewritten = await llm_client.complete(
            system=REWRITE_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        rewritten = rewritten.strip()
        return rewritten or question

    async def _load_session_messages(self, db: AsyncSession, session_id: str | UUID) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == UUID(str(session_id)))
            .order_by(asc(ChatMessage.created_at))
        )
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    def _format_messages(messages: list[ChatMessage]) -> list[dict[str, str]]:
        return [
            {
                "role": str(message.role),
                "content": message.content,
            }
            for message in messages
        ]

    @staticmethod
    def _format_transcript(messages: list[ChatMessage]) -> str:
        lines: list[str] = []
        for message in messages:
            lines.append(f"{str(message.role).upper()}: {message.content.strip()}")
        return "\n".join(lines)

    @staticmethod
    def _summary_cache_key(session_id: str | UUID, msg_count: int) -> str:
        return f"summary:{session_id}:{msg_count}"


session_memory_manager = SessionMemoryManager()
