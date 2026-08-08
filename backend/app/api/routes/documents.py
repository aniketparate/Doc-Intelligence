from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.bm25_index import bm25_service
from app.core.vector_store import vector_store
from app.api.middleware import limit_documents
from app.models.database import Document, Project, User, get_db_session
from app.models.schemas import DocumentListResponse, DocumentResponse, DocumentUploadResponse, MessageResponse
from app.services.auth_service import get_current_user, get_redis
from app.services.project_service import get_project_or_403
from app.services.upload_service import upload_service
from app.utils.storage import storage

router = APIRouter(prefix="/projects", tags=["documents"])


@router.post("/{id}/documents", response_model=DocumentUploadResponse)
@limit_documents
async def upload_documents(
    request: Request,
    id: UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> DocumentUploadResponse:
    _ = request
    await get_project_or_403(project_id=str(id), user=current_user, db=db)
    uploaded = await upload_service.upload_documents(db=db, user=current_user, project_id=str(id), files=files)
    return DocumentUploadResponse(documents=uploaded)


@router.get("/{id}/documents", response_model=DocumentListResponse)
async def list_documents(
    id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> DocumentListResponse:
    project = await get_project_or_403(project_id=str(id), user=current_user, db=db)

    stmt = select(Document).where(Document.project_id == project.id).order_by(Document.created_at.desc())
    docs = list((await db.execute(stmt)).scalars().all())
    return DocumentListResponse(documents=[DocumentResponse.model_validate(doc) for doc in docs])


@router.get("/{id}/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(
    id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:
    project = await get_project_or_403(project_id=str(id), user=current_user, db=db)

    document = await db.get(Document, doc_id)
    if not document or document.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    return DocumentResponse.model_validate(document)


@router.delete("/{id}/documents/{doc_id}", response_model=MessageResponse)
async def delete_document(
    id: UUID,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    project = await get_project_or_403(project_id=str(id), user=current_user, db=db)

    document = await db.get(Document, doc_id)
    if not document or document.project_id != project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if document.original_path:
        try:
            await storage.delete(document.original_path)
        except Exception:
            pass

    try:
        await vector_store.delete_by_doc(collection_name=project.qdrant_namespace, doc_id=str(document.id))
    except Exception:
        pass

    try:
        await bm25_service.delete_cache(document.id)
    except Exception:
        pass

    project.doc_count = max(0, int(project.doc_count or 0) - 1)
    project.chunk_count = max(0, int(project.chunk_count or 0) - int(document.num_chunks or 0))

    await db.delete(document)
    await db.commit()

    redis = await get_redis()

    ask_keys: list[str] = []
    async for key in redis.scan_iter(match=f"ask:{project.id}:*"):
        ask_keys.append(str(key))
    if ask_keys:
        await redis.delete(*ask_keys)

    await redis.delete(f"extract:{project.id}")

    return MessageResponse(message="Document deleted")
