from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import User, get_db_session
from app.models.schemas import (
    MessageResponse,
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
)
from app.services.auth_service import get_current_user
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ProjectListResponse:
    projects = await ProjectService.list_projects(db=db, user=current_user)
    return ProjectListResponse(projects=[ProjectResponse.model_validate(project) for project in projects])


@router.post("", response_model=ProjectCreateResponse)
async def create_project(
    payload: ProjectCreateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ProjectCreateResponse:
    project = await ProjectService.create_project(
        db=db,
        user=current_user,
        name=payload.name,
        description=payload.description,
    )
    return ProjectCreateResponse(
        project_id=project.id,
        name=project.name,
        qdrant_namespace=project.qdrant_namespace,
        doc_count=project.doc_count,
        chunk_count=project.chunk_count,
        created_at=project.created_at,
    )


@router.get("/{id}", response_model=ProjectResponse)
async def get_project(
    id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    project = await ProjectService.get_project(db=db, user=current_user, project_id=str(id))
    return ProjectResponse.model_validate(project)


@router.patch("/{id}", response_model=ProjectResponse)
async def update_project(
    id: UUID,
    payload: ProjectUpdateRequest,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> ProjectResponse:
    project = await ProjectService.update_project(
        db=db,
        user=current_user,
        project_id=str(id),
        name=payload.name,
        description=payload.description,
    )
    return ProjectResponse.model_validate(project)


@router.delete("/{id}", response_model=MessageResponse)
async def delete_project(
    id: UUID,
    db: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    await ProjectService.delete_project(db=db, user=current_user, project_id=str(id))
    return MessageResponse(message="Project deleted")
