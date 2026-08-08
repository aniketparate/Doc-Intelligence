from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.document_processor import SUPPORTED_MIME_TO_SUFFIX
from app.models.database import Document, User
from app.services.auth_service import get_redis
from app.services.project_service import get_project_or_403
from app.utils.storage import storage
from app.workers.ingest_task import ingest_document


class UploadService:
    async def upload_documents(
        self,
        db: AsyncSession,
        user: User,
        project_id: str,
        files: list[UploadFile],
    ) -> list[dict[str, str]]:
        project = await get_project_or_403(project_id=project_id, user=user, db=db)

        if not files:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

        if len(files) > settings.MAX_FILES_PER_UPLOAD:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum files per upload is {settings.MAX_FILES_PER_UPLOAD}",
            )

        existing_count = await self._existing_project_document_count(db=db, project_id=str(project.id))
        is_add_on_upload = existing_count > 0

        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        created_docs: list[Document] = []

        for upload in files:
            mime = self._validate_mime(upload.content_type)
            file_bytes = await upload.read()

            if len(file_bytes) > max_bytes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"File too large: {upload.filename}",
                )

            safe_filename = Path(upload.filename or f"file-{uuid4()}").name

            document = Document(
                project_id=project.id,
                user_id=user.id,
                filename=safe_filename,
                original_path="",
                mime_type=mime,
                file_size_bytes=len(file_bytes),
                status="pending",
            )
            db.add(document)
            await db.flush()

            key = f"uploads/{user.id}/{project.id}/{document.id}/{safe_filename}"
            await storage.save(key=key, data=file_bytes, content_type=mime)
            document.original_path = key

            created_docs.append(document)

        await db.commit()

        for document in created_docs:
            ingest_document.delay(str(document.id))

        if is_add_on_upload:
            await self._invalidate_project_ask_cache(str(project.id))

        return [{"doc_id": str(doc.id), "status": "pending"} for doc in created_docs]

    @staticmethod
    def _validate_mime(content_type: str | None) -> str:
        if not content_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing file content type")

        normalized = content_type.split(";", 1)[0].strip().lower()
        if normalized not in SUPPORTED_MIME_TO_SUFFIX:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type: {content_type}")

        return normalized

    @staticmethod
    async def _existing_project_document_count(db: AsyncSession, project_id: str) -> int:
        stmt = select(func.count(Document.id)).where(Document.project_id == UUID(str(project_id)))
        result = await db.execute(stmt)
        return int(result.scalar_one() or 0)

    @staticmethod
    async def _invalidate_project_ask_cache(project_id: str) -> None:
        redis = await get_redis()
        pattern = f"ask:{project_id}:*"

        keys: list[str] = []
        async for key in redis.scan_iter(match=pattern):
            keys.append(str(key))

        if keys:
            await redis.delete(*keys)


upload_service = UploadService()
