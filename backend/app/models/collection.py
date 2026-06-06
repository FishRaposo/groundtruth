"""Document collection models for access control.

Collections group documents and control access permissions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON, Table, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.utils.time import utc_now

if TYPE_CHECKING:
    from app.models.document.base import Document


# Association table for collection-document many-to-many
collection_documents = Table(
    "collection_documents",
    Base.metadata,
    Column("collection_id", UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE")),
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")),
)


class Collection(Base):
    """A document collection with access control."""
    
    __tablename__ = "collections"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Ownership
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    
    # Permissions
    is_public: Mapped[str] = mapped_column(String(20), default="private")  # private, organization, public
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    
    # Stats
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    documents: Mapped[list[Document]] = relationship("Document", secondary=collection_documents, backref="collections")
    shares: Mapped[list[CollectionShare]] = relationship("CollectionShare", back_populates="collection", cascade="all, delete-orphan")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
            "organization_id": self.organization_id,
            "is_public": self.is_public,
            "document_count": self.document_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CollectionShare(Base):
    """Share record for collection access."""
    
    __tablename__ = "collection_shares"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Shared with
    user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    group_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    
    # Permission level
    permission: Mapped[str] = mapped_column(String(20), default="read")  # read, write, admin
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    collection: Mapped[Collection] = relationship("Collection", back_populates="shares")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "collection_id": str(self.collection_id),
            "user_id": self.user_id,
            "group_id": self.group_id,
            "permission": self.permission,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class AuditLog(Base):
    """Audit log for document and collection access."""
    
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Who
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    api_key_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    
    # What
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # read, write, delete, share, query
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)  # document, collection, query
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Details
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # When
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "user_id": self.user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
