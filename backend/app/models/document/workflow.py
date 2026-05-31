"""Workflow models for document processing.

Defines workflow definitions, instances, and steps for approval workflows.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import Column, DateTime, String, Text, JSON, Integer, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


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
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Steps configuration (JSON with approvers, conditions, SLA)
    steps_config = Column(JSON, default=list, nullable=False)
    
    # Ownership
    owner_id = Column(String(100), nullable=False, index=True)
    organization_id = Column(String(100), nullable=True, index=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # Built-in vs custom
    
    # Metadata
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    instances = relationship("WorkflowInstance", backref="definition", cascade="all, delete-orphan")
    
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
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_definition_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Status tracking
    status = Column(String(50), default="pending")  # pending, in_progress, approved, rejected, cancelled, escalated, expired
    current_step_index = Column(Integer, default=0)
    
    # Trigger info
    triggered_by = Column(String(100), nullable=False)
    trigger_type = Column(String(50), default="manual")  # manual, upload, form, scheduled, webhook
    
    # Metadata and context
    metadata = Column(JSON, default=dict)
    context = Column(JSON, default=dict)  # Extracted form data, etc.
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    steps = relationship("WorkflowStep", backref="workflow", cascade="all, delete-orphan", order_by="WorkflowStep.step_index")
    
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
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class WorkflowStep(Base):
    """Individual step in a workflow instance."""
    
    __tablename__ = "workflow_steps"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    # Step configuration
    step_index = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Approvers (can be users or roles)
    approver_ids = Column(JSON, default=list)  # List of user IDs
    approver_role = Column(String(100), nullable=True)  # Role-based approval
    
    # Approval configuration
    is_parallel = Column(Boolean, default=False)  # All approvers at once vs sequential
    min_approvals = Column(Integer, default=1)  # Minimum approvals needed
    
    # Conditional routing
    approval_route = Column(String(100), nullable=True)  # Next step on approval
    rejection_route = Column(String(100), nullable=True)  # Next step on rejection
    
    # Status
    status = Column(String(50), default="waiting")  # waiting, pending, approved, rejected, expired
    
    # Decisions recorded
    decisions = Column(JSON, default=dict)  # {approver_id: {action, comment, timestamp}}
    
    # SLA
    sla_hours = Column(Integer, default=24)
    due_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Notifications
    notifications_sent = Column(JSON, default=list)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
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
