"""Document collection models for access control.

Collections group documents and control access permissions.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, String, Text, JSON, Table, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


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
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Ownership
    owner_id = Column(String(100), nullable=False, index=True)
    organization_id = Column(String(100), nullable=True, index=True)
    
    # Permissions
    is_public = Column(String(20), default="private")  # private, organization, public
    
    # Metadata
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Stats
    document_count = Column(Integer, default=0)
    
    # Relationships
    documents = relationship("Document", secondary=collection_documents, backref="collections")
    shares = relationship("CollectionShare", backref="collection", cascade="all, delete-orphan")
    
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
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_id = Column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Shared with
    user_id = Column(String(100), nullable=True, index=True)
    group_id = Column(String(100), nullable=True, index=True)
    
    # Permission level
    permission = Column(String(20), default="read")  # read, write, admin
    
    # Metadata
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    created_by = Column(String(100), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
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
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Who
    user_id = Column(String(100), nullable=False, index=True)
    api_key_id = Column(String(100), nullable=True, index=True)
    
    # What
    action = Column(String(50), nullable=False)  # read, write, delete, share, query
    resource_type = Column(String(50), nullable=False)  # document, collection, query
    resource_id = Column(String(100), nullable=True)
    
    # Details
    details = Column(JSON, default=dict)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    
    # When
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    
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
