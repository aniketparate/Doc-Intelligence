from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.vector_store import vector_store
from app.models.database import get_db_session
from app.services.auth_service import get_redis
from app.utils.storage import storage

try:
    from prometheus_fastapi_instrumentator import Instrumentator
except ImportError:  # pragma: no cover
    Instrumentator = None  # type: ignore[assignment]


router = APIRouter(tags=["health"])
_instrumentator = Instrumentator() if Instrumentator is not None else None
_instrumented = False


def setup_metrics(app: FastAPI) -> None:
    global _instrumented
    if _instrumentator is None or _instrumented:
        return
    _instrumentator.instrument(app)
    _instrumented = True


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db_session)) -> dict:
    checks: dict[str, bool] = {
        "postgres": False,
        "qdrant": False,
        "redis": False,
        "minio": False,
        "ollama": False,
    }

    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:
        checks["postgres"] = False

    try:
        await vector_store._client.get_collections()
        checks["qdrant"] = True
    except Exception:
        checks["qdrant"] = False

    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = True
    except Exception:
        checks["redis"] = False

    try:
        await storage.exists("healthcheck")
        checks["minio"] = True
    except Exception:
        checks["minio"] = False

    try:
        timeout = httpx.Timeout(10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags")
            response.raise_for_status()
        checks["ollama"] = True
    except Exception:
        checks["ollama"] = False

    status_value = "ok" if all(checks.values()) else "degraded"
    return {"status": status_value, "checks": checks}


@router.get("/metrics")
async def metrics() -> Response:
    payload = generate_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)
