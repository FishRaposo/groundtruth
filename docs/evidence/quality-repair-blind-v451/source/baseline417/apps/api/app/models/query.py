import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import JSON, Boolean, DateTime, Float, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.utils.time import utc_now


class BoundedMemoryPolicy(str, Enum):
    """Additive query memory modes; disabled preserves legacy behavior."""

    DISABLED = "disabled"
    RECENT = "recent"


class Query(Base):
    """SQLAlchemy model for storing query history and retrieval traces."""

    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True, index=True
    )
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    refusal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    retrieval_trace: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    refused: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class SourceCitation(BaseModel):
    """Schema for a single source citation attached to an answer."""

    chunk_id: uuid.UUID = Field(description="Identifier of the source chunk")
    document_id: uuid.UUID = Field(description="Identifier of the parent document")
    document_title: str = Field(description="Title of the source document")
    content_preview: str = Field(description="Preview of the chunk content")
    relevance_score: float = Field(description="Relevance score from retrieval")
    citation_index: int = Field(description="Numeric citation index in the answer")
    document_version: int | None = None
    content_hash: str | None = None
    quoted_text: str | None = None
    source_status: str = "unknown"


class RetrievalTrace(BaseModel):
    """Schema for the full retrieval trace recorded per query."""

    query_embedding_dim: int = Field(
        description="Dimensionality of the query embedding"
    )
    vector_results: int = Field(description="Number of results from vector search")
    keyword_results: int = Field(description="Number of results from keyword search")
    reranked_results: int = Field(description="Number of results after reranking")
    final_context_chunks: int = Field(
        description="Number of chunks used for generation"
    )
    confidence: float = Field(description="Overall confidence score")
    latency_ms: int = Field(description="Total retrieval latency in milliseconds")
    scores: list[dict[str, Any]] = Field(
        default_factory=list, description="Detailed score breakdown per chunk"
    )
    method: str = "legacy"
    execution_mode: str = "legacy"
    request_id: str | None = None
    provenance: dict[str, Any] | None = None
    refusal_threshold: float | None = None
    retrieval_latency_ms: float | None = None


class QueryRequest(BaseModel):
    """Schema for submitting a new question."""

    question: str = Field(
        min_length=1, max_length=2048, description="The question to answer"
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        le=50,
        description="Override default number of results to retrieve",
    )
    document_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    collection_ids: list[uuid.UUID] | None = Field(default=None, max_length=100)
    retrieval_method: Literal["keyword", "vector", "hybrid", "reranked"] = "reranked"
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Optional persisted conversation to continue"
    )
    memory_policy: BoundedMemoryPolicy = Field(
        default=BoundedMemoryPolicy.DISABLED,
        description="Conversation memory policy; disabled preserves legacy behavior",
    )
    memory_max_tokens: int = Field(
        default=1000,
        ge=1,
        le=8000,
        description="Maximum estimated tokens selected from recent conversation turns",
    )


class QueryResponse(BaseModel):
    """Schema for the full answer including citations and trace."""

    id: uuid.UUID = Field(description="Unique query identifier")
    question: str = Field(description="The original question")
    answer: str | None = Field(description="The generated answer, or null if refused")
    sources: list[SourceCitation] = Field(
        default_factory=list, description="Source citations"
    )
    retrieval_trace: RetrievalTrace | None = Field(
        default=None, description="Full retrieval trace for debugging"
    )
    refused: bool = Field(description="Whether the system refused to answer")
    confidence: float | None = Field(description="Overall confidence score")
    token_usage: dict[str, Any] | None = Field(description="Token usage statistics")
    created_at: datetime = Field(description="Timestamp when the query was processed")
    conversation_id: uuid.UUID | None = None
    outcome: str | None = None
    refusal_reason: str | None = None
    execution_mode: str = "legacy"
    evidence_access: str = "unknown"
    provenance: dict[str, Any] | None = None

    model_config = {"from_attributes": True}


class QueryListItem(BaseModel):
    """Schema for a query item in a listing response."""

    id: uuid.UUID = Field(description="Unique query identifier")
    question: str = Field(description="The original question")
    refused: bool = Field(description="Whether the system refused to answer")
    confidence: float | None = Field(description="Overall confidence score")
    created_at: datetime = Field(description="Timestamp when the query was processed")
    conversation_id: uuid.UUID | None = None
    outcome: str | None = None
    evidence_access: str = "unknown"

    model_config = {"from_attributes": True}


class QueryListResponse(BaseModel):
    """Schema for paginated query history listing."""

    queries: list[QueryListItem] = Field(description="List of query records")
    total: int = Field(description="Total number of queries matching the query")
