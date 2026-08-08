from __future__ import annotations

from typing import Any
from uuid import uuid4

from qdrant_client import AsyncQdrantClient
from qdrant_client import models as qdrant_models

from app.config import settings


class VectorStore:
    def __init__(self) -> None:
        self._client = AsyncQdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

    async def upsert(self, collection_name: str, chunks: list[Any], embeddings: list[list[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")

        points: list[qdrant_models.PointStruct] = []
        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = str(getattr(chunk, "chunk_id", "") or uuid4())

            payload = {
                "doc_id": str(getattr(chunk, "doc_id", "")),
                "project_id": str(getattr(chunk, "project_id", "")),
                "user_id": str(getattr(chunk, "user_id", "")),
                "chunk_id": chunk_id,
                "text": str(getattr(chunk, "text", "")),
                "window_text": str(getattr(chunk, "window_text", "")),
                "context_prefix": str(getattr(chunk, "context_prefix", "")),
                "page_num": getattr(chunk, "page_num", None),
                "chunk_index": int(getattr(chunk, "chunk_index", 0)),
                "total_chunks": int(getattr(chunk, "total_chunks", 0)),
                "doc_type": str(getattr(chunk, "doc_type", "")),
                "source_filename": str(getattr(chunk, "source_filename", "")),
            }

            points.append(
                qdrant_models.PointStruct(
                    id=chunk_id,
                    vector=embedding,
                    payload=payload,
                )
            )

        await self._client.upsert(
            collection_name=collection_name,
            points=points,
            wait=True,
        )

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int,
        filters: Any = None,
    ) -> list[dict[str, Any]]:
        query_filter = self._to_query_filter(filters)
        results = await self._client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            query_filter=query_filter,
            search_params=qdrant_models.SearchParams(hnsw_ef=128),
            with_payload=True,
        )

        return [
            {
                "id": str(hit.id),
                "score": float(hit.score),
                "payload": hit.payload,
            }
            for hit in results.points
        ]

    async def delete_by_doc(self, collection_name: str, doc_id: str) -> None:
        delete_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="doc_id",
                    match=qdrant_models.MatchValue(value=str(doc_id)),
                )
            ]
        )

        await self._client.delete(
            collection_name=collection_name,
            points_selector=delete_filter,
            wait=True,
        )

    async def scroll_by_doc(self, collection_name: str, doc_id: str, limit: int = 256) -> list[dict[str, Any]]:
        scroll_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="doc_id",
                    match=qdrant_models.MatchValue(value=str(doc_id)),
                )
            ]
        )

        results: list[dict[str, Any]] = []
        offset = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                results.append(
                    {
                        "id": str(record.id),
                        "payload": record.payload or {},
                    }
                )
            if offset is None:
                break

        return results

    async def scroll_by_project(self, collection_name: str, project_id: str, limit: int = 256) -> list[dict[str, Any]]:
        scroll_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="project_id",
                    match=qdrant_models.MatchValue(value=str(project_id)),
                )
            ]
        )

        results: list[dict[str, Any]] = []
        offset = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                limit=limit,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for record in records:
                results.append(
                    {
                        "id": str(record.id),
                        "payload": record.payload or {},
                    }
                )
            if offset is None:
                break

        return results

    async def delete_collection(self, collection_name: str) -> None:
        if await self.collection_exists(collection_name):
            await self._client.delete_collection(collection_name=collection_name)

    async def collection_exists(self, collection_name: str) -> bool:
        return bool(await self._client.collection_exists(collection_name=collection_name))

    @staticmethod
    def _to_query_filter(filters: Any) -> qdrant_models.Filter | None:
        if filters is None:
            return None

        if isinstance(filters, qdrant_models.Filter):
            return filters

        if isinstance(filters, dict):
            must_conditions: list[qdrant_models.FieldCondition] = []
            for key, value in filters.items():
                must_conditions.append(
                    qdrant_models.FieldCondition(
                        key=str(key),
                        match=qdrant_models.MatchValue(value=value),
                    )
                )
            return qdrant_models.Filter(must=must_conditions)

        raise ValueError("Unsupported filters type")


vector_store = VectorStore()
