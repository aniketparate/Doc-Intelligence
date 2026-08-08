import fnmatch
import hashlib
import os
import re
import sys
import types
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


# Test-safe environment defaults before importing app modules.
os.environ.setdefault("SECRET_KEY", "test-secret-key-with-32-characters")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "dociq")
os.environ.setdefault("POSTGRES_USER", "dociq")
os.environ.setdefault("POSTGRES_PASSWORD", "changeme")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("LLM_BACKEND", "ollama")
os.environ.setdefault("LLM_MODEL", "llama3.2:3b")


# Stub sentence-transformers so tests do not download or load heavy models.
if "sentence_transformers" not in sys.modules:
    st_mod = types.ModuleType("sentence_transformers")

    class FakeSentenceTransformer:
        def __init__(self, model_name: str, device: str = "cpu"):
            self.model_name = model_name
            self.device = device

        def encode(
            self,
            texts,
            batch_size: int = 32,
            convert_to_numpy: bool = True,
            normalize_embeddings: bool = False,
            show_progress_bar: bool = False,
        ):
            _ = (batch_size, show_progress_bar)
            if isinstance(texts, str):
                texts = [texts]

            vectors = []
            for text in texts:
                seed = int(hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:8], 16)
                rng = np.random.default_rng(seed)
                vectors.append(rng.random(1024, dtype=np.float32))

            matrix = np.stack(vectors, axis=0)
            if normalize_embeddings:
                norms = np.linalg.norm(matrix, axis=1, keepdims=True)
                norms[norms == 0.0] = 1.0
                matrix = matrix / norms
            return matrix if convert_to_numpy else matrix.tolist()

    class FakeCrossEncoder:
        def __init__(self, model_name: str):
            self.model_name = model_name

        def predict(self, pairs, convert_to_numpy: bool = True, show_progress_bar: bool = False):
            _ = show_progress_bar
            scores = []
            for query, text in pairs:
                q_terms = set(re.findall(r"[a-z0-9]+", str(query).lower()))
                t_terms = set(re.findall(r"[a-z0-9]+", str(text).lower()))
                overlap = len(q_terms & t_terms)
                score = float(overlap) / max(1, len(q_terms))
                scores.append(score)
            arr = np.array(scores, dtype=np.float32)
            return arr if convert_to_numpy else arr.tolist()

    st_mod.SentenceTransformer = FakeSentenceTransformer
    st_mod.CrossEncoder = FakeCrossEncoder
    sys.modules["sentence_transformers"] = st_mod


# Patch NLTK tokenization/stopwords to avoid network downloads in tests.
import nltk  # noqa: E402
from nltk import tokenize  # noqa: E402
from nltk.corpus import stopwords  # noqa: E402


def _simple_word_tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9]+", text)


def _simple_sent_tokenize(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


tokenize.word_tokenize = _simple_word_tokenize
nltk.word_tokenize = _simple_word_tokenize
tokenize.sent_tokenize = _simple_sent_tokenize
nltk.sent_tokenize = _simple_sent_tokenize
stopwords.words = lambda language: ["a", "an", "the", "and", "or", "is", "are", "to", "of", "in"]


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, object] = {}

    async def set(self, key: str, value, ex: int | None = None, nx: bool = False):
        _ = ex
        if nx and key in self._store:
            return False
        self._store[key] = value
        return True

    async def get(self, key: str):
        return self._store.get(key)

    async def delete(self, *keys: str):
        deleted = 0
        for key in keys:
            if key in self._store:
                del self._store[key]
                deleted += 1
        return deleted

    async def scan_iter(self, match: str = "*"):
        for key in list(self._store.keys()):
            if fnmatch.fnmatch(key, match):
                yield key

    async def ping(self):
        return True

    async def flushdb(self):
        self._store.clear()

    async def aclose(self):
        return None


@pytest.fixture(scope="session")
def integration_enabled() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS", "0") == "1"


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: marks tests that require real services")


def pytest_collection_modifyitems(config, items):
    _ = config
    if os.getenv("RUN_INTEGRATION_TESTS", "0") == "1":
        return

    skip_integration = pytest.mark.skip(reason="integration tests disabled (set RUN_INTEGRATION_TESTS=1)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest_asyncio.fixture
async def test_redis(integration_enabled: bool) -> AsyncIterator[FakeRedis]:
    if integration_enabled:
        from redis.asyncio import Redis

        redis_url = os.getenv("TEST_REDIS_URL", os.environ["REDIS_URL"])
        redis = Redis.from_url(redis_url, decode_responses=True)
        await redis.flushdb()
        yield redis
        await redis.flushdb()
        await redis.aclose()
        return

    redis = FakeRedis()
    yield redis


@pytest_asyncio.fixture(scope="session")
async def _integration_engine(integration_enabled: bool):
    if not integration_enabled:
        yield None
        return

    from app.models.database import Base

    db_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://dociq:changeme@localhost:5432/dociq",
    )
    engine = create_async_engine(db_url, future=True)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(_integration_engine, integration_enabled: bool) -> AsyncIterator[AsyncSession]:
    if not integration_enabled:
        pytest.skip("test_db requires RUN_INTEGRATION_TESTS=1")

    assert _integration_engine is not None
    session_maker = async_sessionmaker(_integration_engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        await session.execute(
            text(
                "TRUNCATE chat_messages, chat_sessions, bm25_indexes, documents, otp_codes, projects, users "
                "RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
        yield session


@pytest.fixture
def mock_qdrant():
    class MockQdrant:
        def __init__(self):
            self.created = []
            self.deleted = []

        async def create_collection(self, **kwargs):
            self.created.append(kwargs)

        async def delete_collection(self, **kwargs):
            self.deleted.append(kwargs)

        async def search(self, **kwargs):
            _ = kwargs
            return []

        async def get_collections(self):
            return {"collections": []}

    return MockQdrant()


@pytest.fixture
def mock_ollama(monkeypatch):
    async def _mock_complete(system: str, messages: list[dict], temperature: float | None = None) -> str:
        _ = (system, messages, temperature)
        return "mock-ollama-response"

    from app.core import llm_client as llm_client_module

    monkeypatch.setattr(llm_client_module.llm_client, "complete", _mock_complete)
    return _mock_complete


@pytest_asyncio.fixture
async def authenticated_client(test_redis):
    from app.main import app
    from app.models.database import User, get_db_session
    from app.services.auth_service import create_access_token, get_current_user, get_redis

    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        email="authed@example.com",
        full_name="Authed User",
        hashed_password="hashed",
        is_verified=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    async def _override_current_user():
        return user

    async def _override_get_db():
        yield None

    async def _override_get_redis():
        return test_redis

    token = create_access_token(user)

    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_db_session] = _override_get_db
    app.dependency_overrides[get_redis] = _override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as client:
        yield client, user, token

    app.dependency_overrides.clear()
