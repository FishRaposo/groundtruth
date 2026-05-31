"""API key model for service-to-service authentication."""

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ApiKey(Base):
    """SQLAlchemy model for API keys used for programmatic access."""

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rate_limit: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)


def generate_api_key() -> tuple[str, str, str]:
    raw_key = f"gt_{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:8]
    return raw_key, key_hash, key_prefix


class ApiKeyCreate(BaseModel):
    """Schema for creating a new API key."""

    name: str = Field(min_length=1, max_length=256, description="Human-readable name for the API key")
    is_admin: bool = Field(default=False, description="Whether this key has admin privileges")
    rate_limit: int = Field(default=60, description="Requests per minute allowed for this key")


class ApiKeyUpdate(BaseModel):
    """Schema for updating an existing API key."""

    name: str | None = Field(default=None, description="Updated name for the API key")
    rate_limit: int | None = Field(default=None, description="Updated rate limit")


class ApiKeyResponse(BaseModel):
    """Schema returned when reading an API key (never includes the raw key)."""

    id: uuid.UUID = Field(description="Unique API key identifier")
    name: str = Field(description="Human-readable name for the API key")
    key_prefix: str = Field(description="First 8 characters of the raw key for identification")
    is_active: bool = Field(description="Whether the API key is currently active")
    is_admin: bool = Field(description="Whether this key has admin privileges")
    created_at: datetime = Field(description="Timestamp when the API key was created")
    last_used_at: datetime | None = Field(default=None, description="Timestamp of last usage")
    rate_limit: int = Field(description="Requests per minute allowed for this key")

    model_config = {"from_attributes": True}


class ApiKeyCreateResponse(ApiKeyResponse):
    """Schema returned once at creation time including the raw key value."""

    key: str = Field(description="The raw API key (shown only once)")


class ApiKeyListResponse(BaseModel):
    """Schema for paginated API key listing."""

    keys: list[ApiKeyResponse] = Field(description="List of API key records")
    total: int = Field(description="Total number of API keys")
