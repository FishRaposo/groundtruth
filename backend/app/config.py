from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    DATABASE_URL: str = "postgresql+asyncpg://groundtruth:groundtruth_dev@localhost:5432/groundtruth"
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = "groundtruth"
    DATABASE_USER: str = "groundtruth"
    DATABASE_PASSWORD: str = "groundtruth_dev"

    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536
    LOCAL_EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64

    RETRIEVAL_TOP_K: int = 5
    SIMILARITY_THRESHOLD: float = 0.7

    REFUSAL_CONFIDENCE_THRESHOLD: float = 0.5

    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "text"

    AUTH_ENABLED: bool = True
    RATE_LIMIT_ENABLED: bool = True

    CORS_ORIGINS: str = "http://localhost:3000"
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_FILE_TYPES: str = ".pdf,.md,.html,.docx,.txt"

    EMBEDDING_BATCH_SIZE: int = 100
    EMBEDDING_CACHE_ENABLED: bool = True

    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_URL: str = "redis://localhost:6379/0"

    OFFLINE_MODE: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
