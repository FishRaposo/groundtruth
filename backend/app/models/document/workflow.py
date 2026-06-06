"""Workflow models for document processing.

Defines workflow definitions, instances, and steps for approval workflows.
"""

from __future__ import annotations

import uuid
from enum import Enum
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, String, Text, JSON, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.utils.time import utc_now


class WorkflowStepStatus(Enum):
    """Status of a workflow step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAITING = "waiting"
    SKIPPED = "skipped"
    EXPIRED = "expired"


class ApprovalAction(Enum):
    """Possible approval actions."""
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    DELEGATE = "delegate"


class WorkflowDefinition(Base):
    """Template for a workflow (approval process definition)."""
    
    __tablename__ = "workflow_definitions"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Steps configuration (JSON with approvers, conditions, SLA)
    steps_config: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    
    # Ownership
    owner_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)  # Built-in vs custom
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    
    # Relationships
    instances: Mapped[list[WorkflowInstance]] = relationship("WorkflowInstance", back_populates="definition", cascade="all, delete-orphan")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "steps_count": len(self.steps_config) if self.steps_config else 0,
            "owner_id": self.owner_id,
            "organization_id": self.organization_id,
            "is_active": self.is_active,
            "is_system": self.is_system,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class WorkflowInstance(Base):
    """Running instance of a workflow (approval process)."""
    
    __tablename__ = "workflow_instances"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_definition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Status tracking
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, in_progress, approved, rejected, cancelled, escalated, expired
    current_step_index: Mapped[int] = mapped_column(Integer, default=0)
    
    # Trigger info
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), default="manual")  # manual, upload, form, scheduled, webhook
    
    # Metadata and context
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # Extracted form data, etc.
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    definition: Mapped[WorkflowDefinition] = relationship("WorkflowDefinition", back_populates="instances")
    steps: Mapped[list[WorkflowStep]] = relationship("WorkflowStep", back_populates="workflow", cascade="all, delete-orphan", order_by="WorkflowStep.step_index")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "workflow_definition_id": str(self.workflow_definition_id),
            "document_id": str(self.document_id),
            "status": self.status,
            "current_step_index": self.current_step_index,
            "triggered_by": self.triggered_by,
            "trigger_type": self.trigger_type,
            "metadata": self.metadata_,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class WorkflowStep(Base):
    """Individual step in a workflow instance."""
    
    __tablename__ = "workflow_steps"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Step configuration
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Approvers (can be users or roles)
    approver_ids: Mapped[list[str]] = mapped_column(JSON, default=list)  # List of user IDs
    approver_role: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Role-based approval
    
    # Approval configuration
    is_parallel: Mapped[bool] = mapped_column(Boolean, default=False)  # All approvers at once vs sequential
    min_approvals: Mapped[int] = mapped_column(Integer, default=1)  # Minimum approvals needed
    
    # Conditional routing
    approval_route: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Next step on approval
    rejection_route: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Next step on rejection
    
    # Status
    status: Mapped[str] = mapped_column(String(50), default="waiting")  # waiting, pending, approved, rejected, expired
    
    # Decisions recorded
    decisions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {approver_id: {action, comment, timestamp}}
    
    # SLA
    sla_hours: Mapped[int] = mapped_column(Integer, default=24)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Notifications
    notifications_sent: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    
    # Relationships
    workflow: Mapped[WorkflowInstance] = relationship("WorkflowInstance", back_populates="steps")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "workflow_id": str(self.workflow_id),
            "step_index": self.step_index,
            "name": self.name,
            "description": self.description,
            "approver_ids": self.approver_ids,
            "approver_role": self.approver_role,
            "is_parallel": self.is_parallel,
            "min_approvals": self.min_approvals,
            "status": self.status,
            "decisions": self.decisions,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
