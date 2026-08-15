"""Celery tasks for workflow processing.

Handles async workflow operations and SLA monitoring.
"""

from __future__ import annotations

from typing import Any

from app.core.celery import celery_app
from app.db.session import AsyncSessionLocal
from app.services.document.processing.approval import ApprovalWorkflowEngine
from app.services.notifications import NotificationOutbox, notification_outbox


async def enqueue_workflow_notification(
    *,
    outbox: NotificationOutbox,
    workflow_id: str,
    step_id: str,
    action: str,
    approver_id: str,
    workspace_id: str = "default",
    db: Any | None = None,
) -> dict[str, Any]:
    """Enqueue the worker facade's notification in the local outbox."""
    notification = await outbox.enqueue(
        workspace_id=workspace_id,
        event_type=f"workflow.{action}",
        recipient=approver_id,
        payload={"workflow_id": workflow_id, "step_id": step_id},
        deduplication_key=f"{workflow_id}:{step_id}:{approver_id}:{action}:worker",
        db=db,
    )
    return {
        "notification_id": notification.id,
        "delivery_mode": "local_outbox",
    }


@celery_app.task
async def check_workflow_slas() -> dict[str, Any]:
    """Check for workflows that have exceeded SLA.

    Runs periodically via Celery beat schedule.

    Returns:
        Dict with count of escalated workflows.
    """
    async with AsyncSessionLocal() as db:
        engine = ApprovalWorkflowEngine(db)
        escalated = await engine.check_slas()

        return {
            "escalated_count": len(escalated),
            "workflow_ids": [str(w.id) for w in escalated],
        }


@celery_app.task
async def process_document_workflow(
    workflow_definition_id: str,
    document_id: str,
    triggered_by: str,
    trigger_type: str = "document_upload",
    metadata: dict | None = None,
) -> dict[str, str]:
    """Start a workflow for a document asynchronously.

    Args:
        workflow_definition_id: Workflow template ID.
        document_id: Document being processed.
        triggered_by: User ID.
        trigger_type: Type of trigger.
        metadata: Additional metadata.

    Returns:
        Dict with workflow instance ID.
    """
    async with AsyncSessionLocal() as db:
        engine = ApprovalWorkflowEngine(db)

        from app.services.document.processing.approval import WorkflowTrigger

        try:
            trigger = WorkflowTrigger(trigger_type)
        except ValueError:
            trigger = WorkflowTrigger.MANUAL

        workflow = await engine.start_workflow(
            workflow_definition_id=workflow_definition_id,
            document_id=document_id,
            triggered_by=triggered_by,
            trigger_type=trigger,
            metadata=metadata,
        )

        return {
            "workflow_id": str(workflow.id),
            "status": workflow.status,
        }


@celery_app.task
async def send_workflow_notifications(
    workflow_id: str,
    step_id: str,
    action: str,
    approver_id: str,
) -> dict[str, Any]:
    """Send notifications for workflow actions.

    Args:
        workflow_id: Workflow instance ID.
        step_id: Step ID.
        action: Approval action taken.
        approver_id: User who took action.

    Returns:
        Dict with notification results.
    """
    async with AsyncSessionLocal() as db:
        delivery = await enqueue_workflow_notification(
            outbox=notification_outbox,
            workflow_id=workflow_id,
            step_id=step_id,
            action=action,
            approver_id=approver_id,
            db=db,
        )
        return {
            "workflow_id": workflow_id,
            "step_id": step_id,
            "action": action,
            "notifications_processed": True,
            "channels": ["in_app", "email"],  # Future: actual channel list
            **delivery,
        }
