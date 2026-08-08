from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.bm25_index import bm25_service
from app.core.embedder import embedder
from app.core.hyde import hyde
from app.core.reranker import reranker
from app.core.vector_store import vector_store
from app.models.database import Document


@dataclass
class RetrievedChunk:
    doc_id: str
    project_id: str
    user_id: str
    chunk_id: str
    text: str
    window_text: str
    context_prefix: str
    page_num: int | None
    chunk_index: int
    total_chunks: int
    doc_type: str
    source_filename: str
    dense_score: float | None = None
    sparse_score: float | None = None
    rrf_score: float | None = None
    reranker_score: float | None = None
    llm_context_text: str | None = None


class Retriever:
    async def retrieve(
        self,
        db: AsyncSession,
        collection_name: str,
        project_id: str | UUID,
        query: str,
        use_hyde: bool = True,
        filters: Any = None,
    ) -> list[RetrievedChunk]:
        raw_query = (query or "").strip()
        if not raw_query:
            return []

        # Layer 1 — HyDE
        retrieval_query = raw_query
        if use_hyde and settings.HYDE_ENABLED:
            retrieval_query = await hyde.generate_hypothesis(raw_query)

        # Layer 2 — Dense retrieval
        dense_results = await self._dense_retrieval(
            collection_name=collection_name,
            retrieval_query=retrieval_query,
            filters=filters,
        )

        # Layer 3 — Sparse retrieval (BM25)
        sparse_results = await self._sparse_retrieval(
            db=db,
            collection_name=collection_name,
            project_id=project_id,
            raw_query=raw_query,
        )

        # Layer 4 — Reciprocal Rank Fusion
        merged_candidates = self._rrf_merge(
            dense_results=dense_results,
            sparse_results=sparse_results,
            k=settings.RRF_K,
            merged_limit=20,
        )

        # Layer 5 — Cross-encoder re-ranking
        reranked = reranker.rerank(raw_query, merged_candidates)
        final_chunks = reranked[: settings.RERANK_TOP_K]

        # Expand each final chunk to window_text for LLM context.
        for chunk in final_chunks:
            chunk.llm_context_text = chunk.window_text

        return final_chunks

    async def _dense_retrieval(
        self,
        collection_name: str,
        retrieval_query: str,
        filters: Any,
    ) -> list[RetrievedChunk]:
        query_vector = embedder.embed(retrieval_query)
        hits = await vector_store.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=settings.DENSE_TOP_N,
            filters=filters,
        )

        chunks: list[RetrievedChunk] = []
        for hit in hits:
            payload = hit.get("payload") or {}
            chunk = self._payload_to_chunk(payload)
            chunk.dense_score = float(hit.get("score", 0.0))
            chunks.append(chunk)
        return chunks

    async def _sparse_retrieval(
        self,
        db: AsyncSession,
        collection_name: str,
        project_id: str | UUID,
        raw_query: str,
    ) -> list[RetrievedChunk]:
        project_uuid = UUID(str(project_id))
        docs_stmt = select(Document).where(Document.project_id == project_uuid, Document.status == "ready")
        docs = list((await db.execute(docs_stmt)).scalars().all())

        sparse_map: dict[str, tuple[RetrievedChunk, float]] = {}
        for doc in docs:
            index = await bm25_service.load(db, doc.id)
            if index is None:
                continue

            doc_chunks = await self._load_doc_chunks(collection_name=collection_name, doc_id=str(doc.id))
            if not doc_chunks:
                continue

            doc_chunks.sort(key=lambda c: c.chunk_index)
            corpus_size = int(getattr(index, "corpus_size", len(doc_chunks)))

            if len(doc_chunks) < corpus_size:
                continue
            if len(doc_chunks) > corpus_size:
                doc_chunks = doc_chunks[:corpus_size]

            ranked = bm25_service.search(index=index, query=raw_query, all_chunks=doc_chunks, top_n=settings.SPARSE_TOP_N)
            for rank, chunk in enumerate(ranked, start=1):
                score = 1.0 / rank
                chunk.sparse_score = score

                existing = sparse_map.get(chunk.chunk_id)
                if existing is None:
                    sparse_map[chunk.chunk_id] = (chunk, score)
                else:
                    old_chunk, old_score = existing
                    if score > old_score:
                        sparse_map[chunk.chunk_id] = (chunk, score)
                    else:
                        old_chunk.sparse_score = old_score

        ranked_sparse = sorted((item[0] for item in sparse_map.values()), key=lambda c: c.sparse_score or 0.0, reverse=True)
        return ranked_sparse[: settings.SPARSE_TOP_N]

    async def _load_doc_chunks(self, collection_name: str, doc_id: str) -> list[RetrievedChunk]:
        chunks: list[RetrievedChunk] = []
        records = await vector_store.scroll_by_doc(collection_name=collection_name, doc_id=doc_id, limit=256)
        for record in records:
            payload = record.get("payload") or {}
            chunks.append(self._payload_to_chunk(payload))

        return chunks

    def _rrf_merge(
        self,
        dense_results: list[RetrievedChunk],
        sparse_results: list[RetrievedChunk],
        k: int,
        merged_limit: int,
    ) -> list[RetrievedChunk]:
        merged_scores: dict[str, float] = {}
        merged_chunks: dict[str, RetrievedChunk] = {}

        self._add_rrf_scores(merged_scores, merged_chunks, dense_results, k)
        self._add_rrf_scores(merged_scores, merged_chunks, sparse_results, k)

        ranked_ids = sorted(merged_scores, key=lambda cid: merged_scores[cid], reverse=True)

        out: list[RetrievedChunk] = []
        for chunk_id in ranked_ids[:merged_limit]:
            chunk = merged_chunks[chunk_id]
            chunk.rrf_score = merged_scores[chunk_id]
            out.append(chunk)
        return out

    @staticmethod
    def _add_rrf_scores(
        merged_scores: dict[str, float],
        merged_chunks: dict[str, RetrievedChunk],
        ranked_list: list[RetrievedChunk],
        k: int,
    ) -> None:
        for rank, chunk in enumerate(ranked_list, start=1):
            merged_scores[chunk.chunk_id] = merged_scores.get(chunk.chunk_id, 0.0) + (1.0 / (k + rank))
            if chunk.chunk_id not in merged_chunks:
                merged_chunks[chunk.chunk_id] = chunk

    @staticmethod
    def _payload_to_chunk(payload: dict[str, Any]) -> RetrievedChunk:
        return RetrievedChunk(
            doc_id=str(payload.get("doc_id", "")),
            project_id=str(payload.get("project_id", "")),
            user_id=str(payload.get("user_id", "")),
            chunk_id=str(payload.get("chunk_id", "")),
            text=str(payload.get("text", "")),
            window_text=str(payload.get("window_text", "")),
            context_prefix=str(payload.get("context_prefix", "")),
            page_num=payload.get("page_num"),
            chunk_index=int(payload.get("chunk_index", 0) or 0),
            total_chunks=int(payload.get("total_chunks", 0) or 0),
            doc_type=str(payload.get("doc_type", "")),
            source_filename=str(payload.get("source_filename", "")),
        )


retriever = Retriever()
