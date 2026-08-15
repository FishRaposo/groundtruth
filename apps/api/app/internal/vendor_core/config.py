# Vendored from FishRaposo/operator-shared-core v1.3.0.
# Source commit: dbf276a7708da65b55e1f10b35af634b300d1f07.
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseAppConfig(BaseSettings):
    """Base Configuration model for all repositories.

    Imports settings from environment variables or .env files.
    """

    APP_NAME: str = "operator-showcase"
    ENV: str = "development"
    DEBUG: bool = True

    # Database Settings
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"

    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379/0"

    # Observability
    LOG_LEVEL: str = "INFO"

    # External APIs
    OPENAI_API_KEY: Optional[SecretStr] = None
    ANTHROPIC_API_KEY: Optional[SecretStr] = None
    GITHUB_TOKEN: Optional[SecretStr] = None

    # LLM Settings
    LLM_FAST_MODEL: str = "gpt-4o-mini"
    LLM_SMART_MODEL: str = "gpt-4o"
    LLM_EMBEDDING_MODEL: str = "text-embedding-3-small"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4096

    # Celery Settings
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # CORS Settings
    CORS_ALLOWED_ORIGINS: str = "*"

    # Connection Pool Settings
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @classmethod
    def validate_config(cls, config_dict: dict | None = None) -> list[dict]:
        """Validate configuration and return list of issues.

        Returns empty list if configuration is valid.
        Each issue is {"field": str, "message": str, "severity": "error"|"warning"}.
        """
        issues = []
        data = config_dict or cls().model_dump()

        if not data.get("DATABASE_URL"):
            issues.append(
                {
                    "field": "DATABASE_URL",
                    "message": "Missing database URL",
                    "severity": "error",
                }
            )

        log_level = (data.get("LOG_LEVEL") or "").upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if log_level and log_level not in valid_levels:
            issues.append(
                {
                    "field": "LOG_LEVEL",
                    "message": f"Invalid log level. Must be one of {valid_levels}",
                    "severity": "warning",
                }
            )

        temp = data.get("LLM_TEMPERATURE", 0.7)
        if not 0.0 <= temp <= 2.0:
            issues.append(
                {
                    "field": "LLM_TEMPERATURE",
                    "message": "Temperature must be between 0.0 and 2.0",
                    "severity": "warning",
                }
            )

        return issues
