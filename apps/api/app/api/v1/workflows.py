"""Workflow API endpoints for document processing.

Provides REST endpoints for workflow management and approvals.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.schemas.document.workflow import (
    ApprovalActionRequest,
    ApprovalResultResponse,
    WorkflowDefinitionCreate,
    WorkflowDefinitionResponse,
    WorkflowInstanceCreate,
    WorkflowInstanceResponse,
)
from app.services.audit import audit_trail
from app.services.document.processing.approval import (
    ApprovalWorkflowEngine,
    WorkflowTrigger,
)
from app.services.workflow_events import workflow_event_broker

router = APIRouter(prefix="/workflows", tags=["workflows"])


def workflow_definition_visibility(current_user: dict[str, Any]):
    """Return the owner/organization/system visibility predicate."""
    from app.models.document.workflow import WorkflowDefinition

    workspace_id = current_user.get("workspace_id", "default")
    predicates = [WorkflowDefinition.owner_id == current_user["id"]]
    if organization_id := current_user.get("organization_id"):
        predicates.append(WorkflowDefinition.organization_id == organization_id)
    return or_(
        WorkflowDefinition.is_system.is_(True),
        and_(WorkflowDefinition.workspace_id == workspace_id, or_(*predicates)),
    )


def workflow_instance_visibility(current_user: dict[str, Any]):
    """Keep workflow instances private to their workspace and initiating owner."""
    from app.models.document.workflow import WorkflowInstance

    return and_(
        WorkflowInstance.workspace_id == current_user.get("workspace_id", "default"),
        WorkflowInstance.triggered_by == current_user["id"],
    )


@router.post("/definitions", response_model=WorkflowDefinitionResponse)
async def create_workflow_definition(
    data: WorkflowDefinitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new workflow definition (template)."""
    engine = ApprovalWorkflowEngine(db)

    workflow_def = await engine.create_workflow_definition(
        name=data.name,
        description=data.description,
        steps=[step.dict() for step in data.steps],
        owner_id=current_user["id"],
        is_active=data.is_active,
        workspace_id=current_user.get("workspace_id", "default"),
        organization_id=current_user.get("organization_id"),
    )
    await audit_trail.record(
        actor_id=current_user["id"],
        action="create_definition",
        resource_type="workflow",
        resource_id=str(workflow_def.id),
    )

    return workflow_def.to_dict()


@router.get("/definitions", response_model=list[WorkflowDefinitionResponse])
async def list_workflow_definitions(
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List workflow definitions."""
    from sqlalchemy import select

    from app.models.document.workflow import WorkflowDefinition

    result = await db.execute(
        select(WorkflowDefinition)
        .where(
            WorkflowDefinition.is_active.is_(True),
            workflow_definition_visibility(current_user),
        )
        .offset(skip)
        .limit(limit)
    )

    return [wd.to_dict() for wd in result.scalars().all()]


@router.post("/instances", response_model=WorkflowInstanceResponse)
async def start_workflow(
    data: WorkflowInstanceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Start a new workflow instance."""
    engine = ApprovalWorkflowEngine(db)

    try:
        trigger_type = WorkflowTrigger(data.trigger_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid trigger_type: {data.trigger_type}",
        ) from None

    workflow = await engine.start_workflow(
        workflow_definition_id=data.workflow_definition_id,
        document_id=data.document_id,
        triggered_by=current_user["id"],
        trigger_type=trigger_type,
        metadata=data.metadata,
        workspace_id=current_user.get("workspace_id", "default"),
    )
    await audit_trail.record(
        actor_id=current_user["id"],
        action="start",
        resource_type="workflow",
        resource_id=str(workflow.id),
    )

    return workflow.to_dict()


@router.post("/{workflow_id}/approve", response_model=ApprovalResultResponse)
async def process_approval(
    workflow_id: str,
    data: ApprovalActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Process an approval/rejection action."""
    engine = ApprovalWorkflowEngine(db)

    try:
        from app.models.document.workflow import ApprovalAction

        action = ApprovalAction(data.action)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action: {data.action}",
        ) from None

    result = await engine.process_approval(
        workflow_id=workflow_id,
        step_id=data.step_id,
        approver_id=current_user["id"],
        action=action,
        comment=data.comment,
        workspace_id=current_user.get("workspace_id", "default"),
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": result.errors},
        )

    await audit_trail.record(
        actor_id=current_user["id"],
        action=data.action,
        resource_type="approval",
        resource_id=workflow_id,
        metadata={"step_id": data.step_id},
    )

    return {
        "success": result.success,
        "workflow_id": result.workflow_id,
        "step_id": result.step_id,
        "action": result.action,
        "new_status": result.new_status,
        "next_step": result.next_step,
        "notifications_sent": result.notifications_sent,
    }


@router.get("/instances/{workflow_id}", response_model=WorkflowInstanceResponse)
async def get_workflow_instance(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get workflow instance details."""
    from sqlalchemy import select

    from app.models.document.workflow import WorkflowInstance

    result = await db.execute(
        select(WorkflowInstance).where(
            WorkflowInstance.id == uuid.UUID(workflow_id),
            workflow_instance_visibility(current_user),
        )
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found",
        )

    workflow_dict = workflow.to_dict()
    workflow_dict["steps"] = [step.to_dict() for step in workflow.steps]

    return workflow_dict


@router.get("/documents/{document_id}/history")
async def get_document_workflow_history(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Get workflow history for a document."""
    engine = ApprovalWorkflowEngine(db)
    return await engine.get_workflow_history(
        document_id,
        workspace_id=current_user.get("workspace_id", "default"),
        owner_id=current_user["id"],
    )


@router.post("/instances/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
    reason: str | None = None,
) -> dict[str, Any]:
    """Cancel a workflow instance."""
    engine = ApprovalWorkflowEngine(db)

    success = await engine.cancel_workflow(
        workflow_id=workflow_id,
        cancelled_by=current_user["id"],
        reason=reason,
        workspace_id=current_user.get("workspace_id", "default"),
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found or already completed",
        )

    await audit_trail.record(
        actor_id=current_user["id"],
        action="cancel",
        resource_type="workflow",
        resource_id=workflow_id,
        metadata={"reason": reason},
    )

    return {"success": True, "message": "Workflow cancelled"}


@router.get("/instances/{workflow_id}/events")
async def stream_workflow_events(
    workflow_id: str,
    request: Request,
    after_event_id: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """Stream additive ordered workflow status events over standard SSE."""
    from sqlalchemy import select

    from app.models.document.workflow import WorkflowInstance

    result = await db.execute(
        select(WorkflowInstance).where(
            WorkflowInstance.id == uuid.UUID(workflow_id),
            workflow_instance_visibility(current_user),
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    async def events():
        iterator = workflow_event_broker.subscribe(workflow_id, after_event_id)
        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(anext(iterator), timeout=15)
            except TimeoutError:
                yield ": heartbeat\n\n"
                continue
            yield (
                f"id: {event.event_id}\n"
                f"event: {event.event_type}\n"
                f"data: {json.dumps(event.data, sort_keys=True)}\n\n"
            )

    return StreamingResponse(events(), media_type="text/event-stream")
