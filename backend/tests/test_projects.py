from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.database import ChatSession, Document, Project, User
from app.services.project_service import ProjectService, get_project_or_403


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _create_user(test_db, email: str) -> User:
    user = User(email=email, full_name="Project User", hashed_password="x", is_verified=True, is_active=True)
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    return user


async def test_create_project_also_creates_qdrant_collection(test_db, monkeypatch):
    user = await _create_user(test_db, "proj-owner@example.com")
    create_collection = AsyncMock()
    monkeypatch.setattr("app.services.project_service.qdrant_client.create_collection", create_collection)

    project = await ProjectService.create_project(db=test_db, user=user, name="Income Tax Law", description="desc")

    assert project.qdrant_namespace == f"project_{project.id}"
    create_collection.assert_awaited_once()


async def test_user_cannot_access_another_users_project(test_db):
    owner = await _create_user(test_db, "owner@example.com")
    intruder = await _create_user(test_db, "intruder@example.com")

    project = Project(user_id=owner.id, name="Private", qdrant_namespace="project_private")
    test_db.add(project)
    await test_db.commit()
    await test_db.refresh(project)

    with pytest.raises(HTTPException) as exc:
        await get_project_or_403(project_id=str(project.id), user=intruder, db=test_db)

    assert exc.value.status_code == 403


async def test_delete_project_cleans_up_all_data(test_db, monkeypatch):
    user = await _create_user(test_db, "cleanup@example.com")
    project = Project(user_id=user.id, name="Cleanup", qdrant_namespace="project_cleanup")
    test_db.add(project)
    await test_db.commit()
    await test_db.refresh(project)

    document = Document(
        project_id=project.id,
        user_id=user.id,
        filename="file.txt",
        original_path=f"uploads/{user.id}/{project.id}/x/file.txt",
        mime_type="text/plain",
        status="ready",
        num_chunks=3,
    )
    session = ChatSession(project_id=project.id, user_id=user.id, title="S1")
    test_db.add_all([document, session])
    await test_db.commit()

    monkeypatch.setattr("app.services.project_service._delete_project_minio_objects", AsyncMock())
    monkeypatch.setattr("app.services.project_service._delete_project_cache_keys", AsyncMock())
    monkeypatch.setattr("app.services.project_service.qdrant_client.delete_collection", AsyncMock())

    await ProjectService.delete_project(db=test_db, user=user, project_id=str(project.id))

    assert await test_db.get(Project, project.id) is None

    docs = list((await test_db.execute(select(Document).where(Document.project_id == project.id))).scalars().all())
    sessions = list((await test_db.execute(select(ChatSession).where(ChatSession.project_id == project.id))).scalars().all())

    assert docs == []
    assert sessions == []
