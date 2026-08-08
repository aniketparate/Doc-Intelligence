from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.middleware import limit_ask
from app.models.database import User, get_db_session
from app.models.schemas import AskRequest, AskResponse
from app.services.auth_service import get_current_user, get_redis
from app.services.project_service import get_project_or_403
from app.services.qa_service import qa_service

router = APIRouter(prefix="/projects", tags=["ask"])


@router.post("/{id}/ask", response_model=AskResponse)
@limit_ask
async def ask(
    request: Request,
    id: str,
    payload: AskRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> AskResponse:
    _ = request
    project = await get_project_or_403(project_id=id, user=current_user, db=db)

    redis = await get_redis()
    question_hash = hashlib.sha256(payload.question.encode("utf-8")).hexdigest()
    cache_key = f"ask:{project.id}:{question_hash}"

    cached = await redis.get(cache_key)
    if cached:
        return AskResponse(**json.loads(cached))

    result = await qa_service.ask(
        db=db,
        user=current_user,
        project_id=str(project.id),
        session_id=payload.session_id,
        question=payload.question,
        top_k=payload.top_k,
        retrieval_mode=payload.retrieval_mode.value,
        use_hyde=payload.use_hyde,
    )

    await redis.set(cache_key, json.dumps(result), ex=3600)
    return AskResponse(**result)
