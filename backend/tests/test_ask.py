from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.routes import ask as ask_route
from app.models import database as models_db
from app.models.database import ChatSession, User
from app.services import auth_service
from app.services.qa_service import qa_service


pytestmark = pytest.mark.asyncio


class FakeDB:
    def __init__(self, session: ChatSession):
        self._session = session
        self.added = []
        self.committed = False

    async def get(self, model, value):
        if model is ChatSession and str(value) == str(self._session.id):
            return self._session
        return None

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


@dataclass
class ScoreResult:
    answer: str
    confidence: float
    confidence_breakdown: dict
    refused: bool


def _make_chunk(chunk_id: str, text: str, score: float = 0.9):
    return SimpleNamespace(
        chunk_id=chunk_id,
        text=text,
        window_text=text,
        context_prefix="[doc] file.pdf | Page 1 | ",
        page_num=1,
        source_filename="file.pdf",
        reranker_score=score,
        llm_context_text=text,
    )


def _make_user() -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid4(),
        email="qa@example.com",
        full_name="QA",
        hashed_password="x",
        is_verified=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


async def test_full_ask_pipeline_returns_answer_with_sources(monkeypatch):
    user = _make_user()
    project_id = str(uuid4())
    session = ChatSession(id=uuid4(), project_id=uuid4(), user_id=user.id, title=None)
    db = FakeDB(session)

    monkeypatch.setattr("app.services.qa_service.get_project_or_403", AsyncMock(return_value=SimpleNamespace(id=project_id, qdrant_namespace="project_ns")))
    monkeypatch.setattr(
        "app.services.qa_service.session_memory_manager.build_context_for_llm",
        AsyncMock(return_value=([{"role": "assistant", "content": "Previous answer"}], "")),
    )
    monkeypatch.setattr(
        "app.services.qa_service.session_memory_manager.rewrite_followup",
        AsyncMock(return_value="rewritten question"),
    )
    monkeypatch.setattr(
        "app.services.qa_service.retriever.retrieve",
        AsyncMock(return_value=[_make_chunk("c1", "Penalty is 5000"), _make_chunk("c2", "Section 234F")]),
    )
    monkeypatch.setattr("app.services.qa_service.llm_client.complete", AsyncMock(return_value="Penalty is 5000 under Section 234F."))
    monkeypatch.setattr(
        "app.services.qa_service.confidence_scorer.score",
        lambda answer, chunks: ScoreResult(
            answer=answer,
            confidence=0.88,
            confidence_breakdown={
                "retrieval_score": 0.9,
                "chunk_agreement": 0.8,
                "answer_coverage": 0.85,
                "source_count": 0.5,
            },
            refused=False,
        ),
    )

    result = await qa_service.ask(
        db=db,
        user=user,
        project_id=project_id,
        session_id=session.id,
        question="What is the late filing penalty?",
        top_k=2,
        retrieval_mode="hybrid",
        use_hyde=True,
    )

    assert result["answer"].startswith("Penalty is 5000")
    assert result["sources"]
    assert result["refused"] is False
    assert db.committed is True
    assert len(db.added) == 2


async def test_session_history_is_included_in_context(monkeypatch):
    user = _make_user()
    session = ChatSession(id=uuid4(), project_id=uuid4(), user_id=user.id, title="T")
    db = FakeDB(session)

    history = [{"role": "assistant", "content": "Earlier context"}]
    captured = {}

    monkeypatch.setattr("app.services.qa_service.get_project_or_403", AsyncMock(return_value=SimpleNamespace(id=str(session.project_id), qdrant_namespace="project_ns")))
    monkeypatch.setattr("app.services.qa_service.session_memory_manager.build_context_for_llm", AsyncMock(return_value=(history, "")))
    monkeypatch.setattr("app.services.qa_service.session_memory_manager.rewrite_followup", AsyncMock(return_value="standalone question"))
    monkeypatch.setattr("app.services.qa_service.retriever.retrieve", AsyncMock(return_value=[_make_chunk("c1", "x")]))

    async def _complete(system, messages, temperature=None):
        _ = (system, temperature)
        captured["messages"] = messages
        return "answer"

    monkeypatch.setattr("app.services.qa_service.llm_client.complete", _complete)
    monkeypatch.setattr(
        "app.services.qa_service.confidence_scorer.score",
        lambda answer, chunks: ScoreResult(answer=answer, confidence=0.9, confidence_breakdown={"retrieval_score": 1.0, "chunk_agreement": 1.0, "answer_coverage": 1.0, "source_count": 1.0}, refused=False),
    )

    await qa_service.ask(
        db=db,
        user=user,
        project_id=str(session.project_id),
        session_id=session.id,
        question="follow up?",
        top_k=1,
        retrieval_mode="hybrid",
        use_hyde=False,
    )

    assert captured["messages"][0]["content"] == "Earlier context"
    assert captured["messages"][-1]["content"] == "follow up?"


async def test_followup_rewriting_changes_retrieval_query(monkeypatch):
    user = _make_user()
    session = ChatSession(id=uuid4(), project_id=uuid4(), user_id=user.id, title="T")
    db = FakeDB(session)

    captured = {}

    monkeypatch.setattr("app.services.qa_service.get_project_or_403", AsyncMock(return_value=SimpleNamespace(id=str(session.project_id), qdrant_namespace="project_ns")))
    monkeypatch.setattr("app.services.qa_service.session_memory_manager.build_context_for_llm", AsyncMock(return_value=([], "")))
    monkeypatch.setattr("app.services.qa_service.session_memory_manager.rewrite_followup", AsyncMock(return_value="rewritten retrieval query"))

    async def _retrieve(**kwargs):
        captured["query"] = kwargs["query"]
        return [_make_chunk("c1", "answer text")]

    monkeypatch.setattr("app.services.qa_service.retriever.retrieve", _retrieve)
    monkeypatch.setattr("app.services.qa_service.llm_client.complete", AsyncMock(return_value="answer"))
    monkeypatch.setattr(
        "app.services.qa_service.confidence_scorer.score",
        lambda answer, chunks: ScoreResult(answer=answer, confidence=0.9, confidence_breakdown={"retrieval_score": 1.0, "chunk_agreement": 1.0, "answer_coverage": 1.0, "source_count": 1.0}, refused=False),
    )

    await qa_service.ask(
        db=db,
        user=user,
        project_id=str(session.project_id),
        session_id=session.id,
        question="what about it?",
        top_k=1,
        retrieval_mode="hybrid",
        use_hyde=True,
    )

    assert captured["query"] == "rewritten retrieval query"


async def test_cache_hit_returns_without_calling_llm(test_redis, monkeypatch):
    app = FastAPI()
    app.include_router(ask_route.router)

    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        email="cache@example.com",
        full_name="Cache",
        hashed_password="x",
        is_verified=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    async def _override_current_user():
        return user

    async def _override_db():
        yield None

    async def _override_redis():
        return test_redis

    app.dependency_overrides[auth_service.get_current_user] = _override_current_user
    app.dependency_overrides[models_db.get_db_session] = _override_db
    app.dependency_overrides[auth_service.get_redis] = _override_redis

    project = SimpleNamespace(id=str(uuid4()), qdrant_namespace="project_ns")
    monkeypatch.setattr(ask_route, "get_project_or_403", AsyncMock(return_value=project))

    qa_ask = AsyncMock(side_effect=AssertionError("qa_service.ask should not be called on cache hit"))
    monkeypatch.setattr(ask_route.qa_service, "ask", qa_ask)

    payload = {
        "answer": "cached answer",
        "confidence": 0.9,
        "confidence_breakdown": {
            "retrieval_score": 0.9,
            "chunk_agreement": 0.9,
            "answer_coverage": 0.9,
            "source_count": 1.0,
        },
        "sources": [{"chunk_id": "c1", "text": "x", "page": 1, "source_filename": "a.pdf", "reranker_score": 0.7}],
        "refused": False,
        "latency_ms": 1,
    }
    cache_key = f"ask:{project.id}:" + __import__("hashlib").sha256("cached question".encode("utf-8")).hexdigest()
    await test_redis.set(cache_key, json.dumps(payload))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            f"/projects/{project.id}/ask",
            json={
                "session_id": str(uuid4()),
                "question": "cached question",
                "top_k": 5,
                "retrieval_mode": "hybrid",
                "use_hyde": True,
            },
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "cached answer"
    qa_ask.assert_not_called()

    app.dependency_overrides.clear()
