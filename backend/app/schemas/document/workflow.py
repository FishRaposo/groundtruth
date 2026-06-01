"""Workflow schemas for API requests and responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class WorkflowStepDefinition(BaseModel):
    """Definition of a step in a workflow."""
    name: str
    description: str | None = None
    approvers: list[str] = Field(default_factory=list)
    approver_role: str | None = None
    is_parallel: bool = False
    min_approvals: int = 1
    sla_hours: int = 24
    approval_route: str | None = None
    rejection_route: str | None = None


class WorkflowDefinitionCreate(BaseModel):
    """Request to create a workflow definition."""
    name: str
    description: str | None = None
    steps: list[WorkflowStepDefinition]
    is_active: bool = True


class WorkflowDefinitionResponse(BaseModel):
    """Response for a workflow definition."""
    id: str
    name: str
    description: str | None = None
    steps_count: int
    owner_id: str
    organization_id: str | None = None
    is_active: bool
    is_system: bool
    created_at: str | None = None


class WorkflowInstanceCreate(BaseModel):
    """Request to start a workflow instance."""
    workflow_definition_id: str
    document_id: str
    trigger_type: str = "manual"
    metadata: dict[str, Any] | None = None


class WorkflowStepResponse(BaseModel):
    """Response for a workflow step."""
    id: str
    step_index: int
    name: str
    description: str | None = None
    approver_ids: list[str]
    approver_role: str | None = None
    is_parallel: bool
    min_approvals: int
    status: str
    decisions: dict[str, Any] | None = None
    due_at: str | None = None
    completed_at: str | None = None


class WorkflowInstanceResponse(BaseModel):
    """Response for a workflow instance."""
    id: str
    workflow_definition_id: str
    document_id: str
    status: str
    current_step_index: int
    triggered_by: str
    trigger_type: str
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    completed_at: str | None = None
    expires_at: str | None = None
    steps: list[WorkflowStepResponse] | None = None


class ApprovalActionRequest(BaseModel):
    """Request to process an approval action."""
    step_id: str
    action: str  # approve, reject, request_changes, delegate
    comment: str | None = None


class ApprovalResultResponse(BaseModel):
    """Response for an approval action."""
    success: bool
    workflow_id: str
    step_id: str
    action: str
    new_status: str
    next_step: str | None = None
    notifications_sent: list[str]
