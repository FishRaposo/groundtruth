"""Webhook models for event notifications.

Manages webhook subscriptions, deliveries, and retry logic.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from sqlalchemy import Column, DateTime, String, Text, JSON, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID

from app.db.session import Base
from app.utils.time import utc_now


class WebhookEventType(str, Enum):
    """Types of webhook events."""
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    DOCUMENT_PROCESSED = "document.processed"
    CHUNK_CREATED = "chunk.created"
    QUERY_PERFORMED = "query.performed"
    CONVERSATION_CREATED = "conversation.created"
    CONVERSATION_MESSAGE = "conversation.message"


class WebhookStatus(str, Enum):
    """Webhook subscription status."""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class WebhookSubscription(Base):
    """A webhook subscription for event notifications."""
    
    __tablename__ = "webhook_subscriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Endpoint configuration
    url = Column(String(2048), nullable=False)
    secret = Column(String(255), nullable=False)  # For HMAC signature
    
    # Event filtering
    events = Column(JSON, default=list)  # List of event types to subscribe to
    document_filter = Column(JSON, nullable=True)  # Optional document ID filter
    
    # Status
    status = Column(SQLEnum(WebhookStatus), default=WebhookStatus.ACTIVE)
    
    # Metadata
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    
    # Delivery stats
    delivery_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    last_delivered_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "url": self.url,
            "events": self.events or [],
            "status": self.status.value if self.status else None,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "delivery_count": self.delivery_count,
            "failure_count": self.failure_count,
        }


class WebhookDelivery(Base):
    """Record of a webhook delivery attempt."""
    
    __tablename__ = "webhook_deliveries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    
    # Event details
    event_type = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=False)
    
    # Delivery details
    attempted_at = Column(DateTime(timezone=True), default=utc_now)
    response_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    
    # Retry tracking
    attempt_number = Column(Integer, default=1)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    
    # Status
    success = Column(Integer, default=0)  # 0 = pending/failed, 1 = success
    error_message = Column(Text, nullable=True)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "subscription_id": str(self.subscription_id),
            "event_type": self.event_type,
            "attempted_at": self.attempted_at.isoformat() if self.attempted_at else None,
            "response_status": self.response_status,
            "attempt_number": self.attempt_number,
            "success": bool(self.success),
            "error_message": self.error_message,
        }
