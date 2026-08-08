from __future__ import annotations

import pickle
from datetime import timedelta
from typing import Any
from uuid import UUID

import nltk
from nltk.tokenize import word_tokenize
from rank_bm25 import BM25Okapi
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import BM25Index


BM25_CACHE_TTL_SECONDS = int(timedelta(hours=24).total_seconds())


class BM25IndexService:
    def __init__(self) -> None:
        self._redis: Redis | None = None

    def build(self, chunks: list[Any]) -> BM25Okapi:
        self._ensure_nltk_tokenizer()

        tokenized_corpus: list[list[str]] = []
        for chunk in chunks:
            text = (getattr(chunk, "text", "") or "").strip().lower()
            tokens = word_tokenize(text) if text else []
            tokenized_corpus.append(tokens)

        return BM25Okapi(tokenized_corpus)

    def search(self, index: BM25Okapi, query: str, all_chunks: list[Any], top_n: int) -> list[Any]:
        self._ensure_nltk_tokenizer()
        query_tokens = word_tokenize((query or "").lower())
        if not query_tokens or not all_chunks:
            return []
        return index.get_top_n(query_tokens, all_chunks, n=top_n)

    @staticmethod
    def serialize(index: BM25Okapi) -> bytes:
        return pickle.dumps(index, protocol=pickle.HIGHEST_PROTOCOL)

    @staticmethod
    def deserialize(data: bytes) -> BM25Okapi:
        return pickle.loads(data)

    async def cache_after_build(self, doc_id: str | UUID, index: BM25Okapi) -> None:
        redis = await self._get_redis()
        key = self._cache_key(doc_id)
        await redis.set(key, self.serialize(index), ex=BM25_CACHE_TTL_SECONDS)

    async def save_to_db_and_cache(self, db: AsyncSession, doc_id: str | UUID, index: BM25Okapi) -> None:
        serialized = self.serialize(index)

        stmt = select(BM25Index).where(BM25Index.document_id == UUID(str(doc_id)))
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.index_data = serialized
        else:
            db.add(BM25Index(document_id=UUID(str(doc_id)), index_data=serialized))

        await db.commit()

        redis = await self._get_redis()
        await redis.set(self._cache_key(doc_id), serialized, ex=BM25_CACHE_TTL_SECONDS)

    async def load(self, db: AsyncSession, doc_id: str | UUID) -> BM25Okapi | None:
        redis = await self._get_redis()
        cache_key = self._cache_key(doc_id)

        cached = await redis.get(cache_key)
        if cached:
            return self.deserialize(cached)

        stmt = select(BM25Index).where(BM25Index.document_id == UUID(str(doc_id)))
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()
        if not row:
            return None

        await redis.set(cache_key, row.index_data, ex=BM25_CACHE_TTL_SECONDS)
        return self.deserialize(row.index_data)

    async def delete_cache(self, doc_id: str | UUID) -> None:
        redis = await self._get_redis()
        await redis.delete(self._cache_key(doc_id))

    async def _get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(settings.REDIS_URL)
        return self._redis

    @staticmethod
    def _cache_key(doc_id: str | UUID) -> str:
        return f"bm25:{doc_id}"

    @staticmethod
    def _ensure_nltk_tokenizer() -> None:
        try:
            nltk.data.find("tokenizers/punkt_tab/english")
        except LookupError:
            try:
                nltk.download("punkt_tab", quiet=True)
            except Exception:
                pass

        try:
            nltk.data.find("tokenizers/punkt/english.pickle")
        except LookupError:
            try:
                nltk.download("punkt", quiet=True)
            except Exception:
                pass


bm25_service = BM25IndexService()
