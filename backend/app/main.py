from __future__ import annotations

import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.limiter import limiter
from app.api.routes.ask import router as ask_router
from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.extract import router as extract_router
from app.api.routes.health import router as health_router
from app.api.routes.projects import router as projects_router
from app.api.routes.sessions import router as sessions_router
from app.config import settings


def configure_structured_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start = time.perf_counter()
        client_ip = request.client.host if request.client else None
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "request_failed",
                request_id=request_id,
                method=method,
                path=path,
                client_ip=client_ip,
                duration_ms=duration_ms,
            )
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)
        response.headers["x-request-id"] = request_id
        logger.info(
            "request_completed",
            request_id=request_id,
            method=method,
            path=path,
            status_code=response.status_code,
            client_ip=client_ip,
            duration_ms=duration_ms,
        )
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_structured_logging()
    logger.info("app_starting", app_name="Ultra Doc-Intelligence", debug=settings.DEBUG)
    yield
    logger.info("app_stopping")


app = FastAPI(
    title="Ultra Doc-Intelligence API",
    version="0.1.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# SlowAPI wiring
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Prometheus instrumentation
Instrumentator().instrument(app)

# Routers
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(sessions_router)
app.include_router(ask_router)
app.include_router(extract_router)
app.include_router(projects_router)
app.include_router(health_router)


@app.get("/", include_in_schema=False)
async def root() -> Response:
    return Response(content="Ultra Doc-Intelligence API", media_type="text/plain")

