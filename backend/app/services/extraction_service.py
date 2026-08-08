from __future__ import annotations

import json
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.extractor import extractor
from app.core.vector_store import vector_store
from app.models.database import User
from app.services.auth_service import get_redis
from app.services.project_service import get_project_or_403


class ExtractionService:
    async def extract(self, db: AsyncSession, user: User, project_id: str) -> dict:
        return await self.extract_project(db=db, user=user, project_id=project_id)

    async def extract_project(self, db: AsyncSession, user: User, project_id: str) -> dict:
        project = await get_project_or_403(project_id=project_id, user=user, db=db)
        redis = await get_redis()

        cache_key = self._cache_key(str(project.id))
        cached = await redis.get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                pass

        records = await vector_store.scroll_by_project(
            collection_name=project.qdrant_namespace,
            project_id=str(project.id),
            limit=256,
        )

        chunks = [SimpleNamespace(**(record.get("payload") or {})) for record in records]
        result = await extractor.extract(chunks)

        # Persistent cache (no TTL) until explicit invalidation/deletion.
        await redis.set(cache_key, json.dumps(result))
        return result

    @staticmethod
    def _cache_key(project_id: str) -> str:
        return f"extract:{project_id}"


extraction_service = ExtractionService()
