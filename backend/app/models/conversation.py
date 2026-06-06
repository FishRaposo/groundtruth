"""Conversation models for multi-turn RAG chat.

Manages conversation state, context window, and history for
multi-turn question answering with memory.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.utils.time import utc_now


class Conversation(Base):
    """A conversation session with multiple messages."""
    
    __tablename__ = "conversations"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Auto-generated or user-set
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    
    # Context management
    document_ids: Mapped[list[str]] = mapped_column(JSON, default=list)  # List of document IDs in context
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)  # Custom system prompt
    
    # Configuration
    max_context_length: Mapped[int] = mapped_column(Integer, default=4000)  # Max tokens for context
    context_strategy: Mapped[str] = mapped_column(String(50), default="recent")  # recent, relevant, summary
    
    # Statistics
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    messages: Mapped[list[Message]] = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    contexts: Mapped[list[ConversationContext]] = relationship("ConversationContext", back_populates="conversation", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "document_ids": self.document_ids or [],
            "message_count": self.message_count,
            "total_tokens": self.total_tokens,
        }


class Message(Base):
    """A single message in a conversation."""
    
    __tablename__ = "messages"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Message content
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant, system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    
    # Token usage
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # RAG context (for assistant messages)
    retrieved_chunks: Mapped[list[str]] = mapped_column(JSON, default=list)  # List of chunk IDs used
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # Source documents
    generation_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Time to generate response
    
    # Metadata
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)  # Additional metadata
    
    # Relationships
    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="messages")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "sources": self.sources or [],
        }


class ConversationContext(Base):
    """Context window management for conversations.
    
    Tracks which chunks/documents are in the active context
    and their relevance scores.
    """
    
    __tablename__ = "conversation_contexts"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Context entries
    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False)
    relevance_score: Mapped[int] = mapped_column(Integer, default=0)  # 0-100 relevance score
    
    # Context lifecycle
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    access_count: Mapped[int] = mapped_column(Integer, default=1)
    
    # Why was this added to context?
    added_reason: Mapped[str] = mapped_column(String(50), default="retrieval")  # retrieval, user_add, auto_expand
    
    # Relationships
    conversation: Mapped[Conversation] = relationship("Conversation", back_populates="contexts")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "conversation_id": str(self.conversation_id),
            "chunk_id": str(self.chunk_id),
            "relevance_score": self.relevance_score,
            "access_count": self.access_count,
        }
