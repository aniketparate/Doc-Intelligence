from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import ChatMessage, ChatSession, User, get_db_session
from app.models.schemas import (
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatSessionCreateRequest,
    ChatSessionDeleteResponse,
    ChatSessionListResponse,
    ChatSessionResponse,
    ChatSessionUpdateRequest,
)
from app.services.auth_service import get_current_user
from app.services.project_service import get_project_or_403

router = APIRouter(prefix="/projects", tags=["sessions"])


@router.post("/{id}/sessions", response_model=ChatSessionResponse)
async def create_session(
    id: UUID,
    payload: ChatSessionCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    project = await get_project_or_403(project_id=str(id), user=current_user, db=db)

    session = ChatSession(
        project_id=project.id,
        user_id=current_user.id,
        title=payload.title,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ChatSessionResponse.model_validate(session)


@router.get("/{id}/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatSessionListResponse:
    project = await get_project_or_403(project_id=str(id), user=current_user, db=db)

    stmt = (
        select(ChatSession)
        .where(ChatSession.project_id == project.id, ChatSession.user_id == current_user.id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = list((await db.execute(stmt)).scalars().all())
    return ChatSessionListResponse(sessions=[ChatSessionResponse.model_validate(s) for s in sessions])


@router.get("/{id}/sessions/{sid}", response_model=ChatSessionResponse)
async def get_session(
    id: UUID,
    sid: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    project = await get_project_or_403(project_id=str(id), user=current_user, db=db)

    session = await db.get(ChatSession, sid)
    if not session or session.project_id != project.id or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return ChatSessionResponse.model_validate(session)


@router.get("/{id}/sessions/{sid}/messages", response_model=ChatMessageListResponse)
async def get_session_messages(
    id: UUID,
    sid: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatMessageListResponse:
    project = await get_project_or_403(project_id=str(id), user=current_user, db=db)

    session = await db.get(ChatSession, sid)
    if not session or session.project_id != project.id or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    stmt = select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.asc())
    messages = list((await db.execute(stmt)).scalars().all())
    return ChatMessageListResponse(messages=[ChatMessageResponse.model_validate(m) for m in messages])


@router.delete("/{id}/sessions/{sid}", response_model=ChatSessionDeleteResponse)
async def delete_session(
    id: UUID,
    sid: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatSessionDeleteResponse:
    project = await get_project_or_403(project_id=str(id), user=current_user, db=db)

    session = await db.get(ChatSession, sid)
    if not session or session.project_id != project.id or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    await db.delete(session)
    await db.commit()
    return ChatSessionDeleteResponse(message="Session deleted")


@router.patch("/{id}/sessions/{sid}", response_model=ChatSessionResponse)
async def update_session(
    id: UUID,
    sid: UUID,
    payload: ChatSessionUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ChatSessionResponse:
    project = await get_project_or_403(project_id=str(id), user=current_user, db=db)

    session = await db.get(ChatSession, sid)
    if not session or session.project_id != project.id or session.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if payload.title is not None:
        session.title = payload.title
    if payload.is_archived is not None:
        session.is_archived = payload.is_archived
    session.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(session)
    return ChatSessionResponse.model_validate(session)
