from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware import limit_extract
from app.models.database import User, get_db_session
from app.models.schemas import ExtractRequest, ExtractResponse
from app.services.auth_service import get_current_user
from app.services.extraction_service import extraction_service
from app.services.project_service import get_project_or_403

router = APIRouter(prefix="/projects", tags=["extract"])


@router.post("/{id}/extract", response_model=ExtractResponse)
@limit_extract
async def extract(
    request: Request,
    id: UUID,
    payload: ExtractRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ExtractResponse:
    _ = request
    _ = payload
    await get_project_or_403(project_id=str(id), user=current_user, db=db)
    data = await extraction_service.extract(db=db, user=current_user, project_id=str(id))
    return ExtractResponse(data=data, confidence=None, sources=[])
