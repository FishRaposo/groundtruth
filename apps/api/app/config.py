from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator

from app.evidence_policy import (
    ProcedureVerificationProfile,
    ProposalProfile,
    RoleScopePolicy,
    SourceContextPolicy,
    validate_evidence_engines,
)
from app.internal.vendor_core.config import BaseAppConfig
from app.support_catalog import NLI


class Settings(BaseAppConfig):
    """Application settings, extending the internal vendor configuration.

    Inherits infrastructure fields (REDIS_URL, LOG_LEVEL, CELERY_BROKER_URL,
    DB_POOL_*, ...) from the vendor ``BaseAppConfig`` and adds GroundTruth's domain
    knobs. ``OPENAI_API_KEY`` is overridden back to a plain ``str`` (the base
    declares it as ``Optional[SecretStr]``) to preserve GroundTruth's call sites.
    """

    DATABASE_URL: str = (
        "postgresql+asyncpg://groundtruth:groundtruth_dev@localhost:5432/groundtruth"
    )
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
    LOG_FORMAT: str = "text"

    AUTH_ENABLED: bool = True
    RATE_LIMIT_ENABLED: bool = True

    CORS_ORIGINS: str = "http://localhost:3000"
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_FILE_TYPES: str = ".pdf,.md,.html,.docx,.txt"

    EMBEDDING_BATCH_SIZE: int = 100
    EMBEDDING_CACHE_ENABLED: bool = True

    CELERY_RESULT_URL: str = "redis://localhost:6379/0"

    OFFLINE_MODE: bool = False

    # Legacy is an explicit compatibility profile for the published golden demo.
    EMBEDDING_MODE: str = "legacy"
    GENERATION_MODE: str = "legacy"
    INGESTION_MODE: str = "inline"
    SOURCE_CONTEXT_MODE: Literal["body", "versioned_title"] = "body"
    LOCAL_MODEL_PATH: str = ""
    LOCAL_MODEL_REVISION: str = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    STORAGE_ROOT: str = "data/uploads"
    CONNECTED_REFUSAL_THRESHOLD: float = 0.35
    ANSWER_SELECTION_MODE: Literal["lexical", "reader"] = "lexical"
    ANSWER_PROPOSAL_PROFILE: ProposalProfile = "qa_only_v1"
    ROLE_SCOPE_POLICY: RoleScopePolicy = "literal_v1"
    PROCEDURE_VERIFICATION_PROFILE: ProcedureVerificationProfile = "all_units_nli_v1"
    SOURCE_CONTEXT_POLICY: SourceContextPolicy = "explicit_target_v1"
    READER_MODEL_PATH: str = ""
    READER_MODEL_REVISION: str = "934656cdda79824eabf503ed56e15c01ddbdbe3f"
    READER_NULL_THRESHOLD: float = Field(default=0.0, allow_inf_nan=False)
    READER_MAX_LENGTH: int = Field(default=384, ge=128, le=512)
    READER_STRIDE: int = Field(default=128, ge=0, le=256)
    READER_N_BEST: int = Field(default=20, ge=1, le=100)
    READER_MAX_SPAN_TOKENS: int = Field(default=96, ge=1, le=128)
    ANSWER_SUPPORT_MODE: Literal["disabled", "local_nli"] = "disabled"
    SUPPORT_MODEL_PATH: str = ""
    SUPPORT_MODEL_REVISION: str = NLI.revision
    SUPPORT_MIN_MARGIN: float = Field(default=4.0, ge=0, le=4, allow_inf_nan=False)

    @model_validator(mode="after")
    def evidence_profile_requires_its_engines(self) -> "Settings":
        validate_evidence_engines(
            self.ANSWER_PROPOSAL_PROFILE,
            self.ROLE_SCOPE_POLICY,
            self.ANSWER_SELECTION_MODE,
            self.ANSWER_SUPPORT_MODE,
            procedure=self.PROCEDURE_VERIFICATION_PROFILE,
            generation=self.GENERATION_MODE,
            context=self.SOURCE_CONTEXT_POLICY,
        )
        return self

    @property
    def connected(self) -> bool:
        return self.EMBEDDING_MODE != "legacy" or self.GENERATION_MODE != "legacy"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
