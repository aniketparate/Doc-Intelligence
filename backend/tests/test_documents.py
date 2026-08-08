from __future__ import annotations

from io import BytesIO
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile

from app.models.database import Project, User
from app.services.upload_service import upload_service


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _make_upload(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=filename, headers=Headers({"content-type": content_type}))


async def _create_user_project(test_db):
    user = User(email="docs@example.com", full_name="Docs", hashed_password="x", is_verified=True, is_active=True)
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    project = Project(user_id=user.id, name="Docs Project", qdrant_namespace=f"project_{user.id}")
    test_db.add(project)
    await test_db.commit()
    await test_db.refresh(project)
    return user, project


async def test_upload_returns_pending_status_immediately(test_db, test_redis, monkeypatch):
    user, project = await _create_user_project(test_db)

    monkeypatch.setattr("app.services.upload_service.storage.save", AsyncMock())
    ingest_delay = Mock()
    monkeypatch.setattr("app.services.upload_service.ingest_document.delay", ingest_delay)

    async def _mock_get_redis():
        return test_redis

    monkeypatch.setattr("app.services.upload_service.get_redis", _mock_get_redis)

    files = [_make_upload("a.txt", b"hello world", "text/plain")]
    result = await upload_service.upload_documents(db=test_db, user=user, project_id=str(project.id), files=files)

    assert len(result) == 1
    assert result[0]["status"] == "pending"
    ingest_delay.assert_called_once()


async def test_add_on_upload_appends_to_existing_project(test_db, test_redis, monkeypatch):
    user, project = await _create_user_project(test_db)

    monkeypatch.setattr("app.services.upload_service.storage.save", AsyncMock())
    monkeypatch.setattr("app.services.upload_service.ingest_document.delay", Mock())

    async def _mock_get_redis():
        return test_redis

    monkeypatch.setattr("app.services.upload_service.get_redis", _mock_get_redis)

    first = [_make_upload("first.txt", b"first", "text/plain")]
    second = [_make_upload("second.txt", b"second", "text/plain")]

    await upload_service.upload_documents(db=test_db, user=user, project_id=str(project.id), files=first)

    ask_key = f"ask:{project.id}:deadbeef"
    await test_redis.set(ask_key, "cached")

    result = await upload_service.upload_documents(db=test_db, user=user, project_id=str(project.id), files=second)

    assert len(result) == 1
    assert result[0]["status"] == "pending"
    assert await test_redis.get(ask_key) is None


async def test_unsupported_file_type_is_rejected(test_db):
    user, project = await _create_user_project(test_db)

    files = [_make_upload("malware.exe", b"MZ", "application/octet-stream")]

    with pytest.raises(HTTPException) as exc:
        await upload_service.upload_documents(db=test_db, user=user, project_id=str(project.id), files=files)

    assert exc.value.status_code == 400
    assert "unsupported file type" in exc.value.detail.lower()
