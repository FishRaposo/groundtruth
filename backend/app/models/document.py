import enum
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import JSON, DateTime, Enum, Float, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SourceType(str, enum.Enum):
    """Supported document source formats."""

    PDF = "pdf"
    MARKDOWN = "md"
    HTML = "html"
    DOCX = "docx"


class DocumentStatus(str, enum.Enum):
    """Document processing lifecycle states."""

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class Document(Base):
    """SQLAlchemy model for uploaded documents."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus), default=DocumentStatus.PENDING, nullable=False
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class DocumentCreate(BaseModel):
    """Schema for creating a new document reference."""

    title: str = Field(description="Document title or filename")
    source_type: SourceType = Field(description="File format of the source document")
    source_url: str | None = Field(default=None, description="Optional URL to the source file")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")


class DocumentResponse(BaseModel):
    """Schema returned when reading a single document."""

    id: uuid.UUID = Field(description="Unique document identifier")
    title: str = Field(description="Document title")
    source_type: SourceType = Field(description="Source file format")
    source_url: str | None = Field(description="URL to source file if available")
    status: DocumentStatus = Field(description="Current processing status")
    metadata: dict[str, Any] | None = Field(description="Attached metadata")
    file_size: int | None = Field(default=None, description="File size in bytes")
    page_count: int | None = Field(default=None, description="Number of pages")
    chunk_count: int | None = Field(default=None, description="Number of chunks")
    processing_time_ms: float | None = Field(default=None, description="Total processing time in milliseconds")
    created_at: datetime = Field(description="Timestamp when document was created")
    updated_at: datetime = Field(description="Timestamp when document was last updated")

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    """Schema for paginated document listing."""

    documents: list[DocumentResponse] = Field(description="List of documents")
    total: int = Field(description="Total number of documents matching the query")
    limit: int = Field(description="Maximum results per page")
    offset: int = Field(description="Pagination offset")
