from __future__ import annotations
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "dociq"
    POSTGRES_USER: str = "dociq"
    POSTGRES_PASSWORD: str = "changeme"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: str = "minioadmin123"
    MINIO_BUCKET: str = "dociq-uploads"
    MINIO_USE_SSL: bool = False

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-large-en-v1.5"
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_DEVICE: str = "cpu"

    # Reranker
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_DEVICE: str = "cpu"

    # LLM
    LLM_BACKEND: Literal["ollama", "vllm"] = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    VLLM_BASE_URL: str = "http://localhost:8000"
    LLM_MODEL: str = "llama3.2:3b"
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 1024
    LLM_REQUEST_TIMEOUT_SECONDS: int = 60

    # RAG
    DENSE_TOP_N: int = 20
    SPARSE_TOP_N: int = 20
    RERANK_TOP_K: int = 5
    RRF_K: int = 60
    HYDE_ENABLED: bool = True
    CONFIDENCE_REFUSAL_THRESHOLD: float = 0.25
    CONFIDENCE_LOW_THRESHOLD: float = 0.45
    SEMANTIC_SIMILARITY_THRESHOLD: float = 0.7
    SEMANTIC_CHUNK_MIN_TOKENS: int = 256
    SEMANTIC_CHUNK_MAX_TOKENS: int = 512
    FALLBACK_CHUNK_SIZE: int = 400
    FALLBACK_CHUNK_OVERLAP: int = 80
    BM25_CACHE_TTL_SECONDS: int = 86400
    SESSION_MAX_HISTORY_TURNS: int = 10
    SESSION_SUMMARY_TRIGGER_TURNS: int = 15
    SESSION_SUMMARY_TTL_SECONDS: int = 3600

    # Upload
    MAX_FILE_SIZE_MB: int = 100
    MAX_FILES_PER_UPLOAD: int = 50
    ALLOWED_EXTENSIONS: str = "pdf,docx,doc,txt,md,xlsx,pptx,html,epub"

    # Auth
    SECRET_KEY: str = "changeme-generate-random-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    LOGIN_MODE: str = "password"

    # SSO
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    SSO_REDIRECT_BASE: str = "http://localhost"

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "noreply@localhost"

    # App
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost"

    # ── Computed properties ──────────────────────────────────────

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def QDRANT_URL(self) -> str:
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"

    @property
    def ALLOWED_EXTENSIONS_LIST(self) -> list[str]:
        return [s.strip() for s in self.ALLOWED_EXTENSIONS.split(",") if s.strip()]

    @property
    def CORS_ORIGINS_LIST(self) -> list[str]:
        return [s.strip() for s in self.CORS_ORIGINS.split(",") if s.strip()]
    
    @property
    def EFFECTIVE_EMBEDDING_DEVICE(self) -> str:
        try:
            import torch
            if self.EMBEDDING_DEVICE == "cuda" and torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"
    
    @property
    def EFFECTIVE_RERANKER_DEVICE(self) -> str:
        try:
            import torch
            if self.RERANKER_DEVICE == "cuda" and torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass
        return "cpu"


# No lru_cache — instantiate fresh so .env is always read
settings = Settings()