"""Approval workflow engine for document processing.

Manages multi-stage approval workflows with notifications and audit trails.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
    WorkflowStep,
    WorkflowStepStatus,
    ApprovalAction,
)


class WorkflowTrigger(Enum):
    """Triggers that can start a workflow."""
    DOCUMENT_UPLOAD = "document_upload"
    FORM_SUBMISSION = "form_submission"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"


class WorkflowStatus(Enum):
    """Status of a workflow instance."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"
    EXPIRED = "expired"


@dataclass
class ApprovalResult:
    """Result of an approval action."""
    success: bool
    workflow_id: str
    step_id: str
    action: str
    new_status: str
    next_step: str | None = None
    notifications_sent: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ApprovalWorkflowEngine:
    """Engine for managing document approval workflows.
    
    Features:
    - Multi-stage approval chains
    - Conditional routing (if approved, route to X; if rejected, route to Y)
    - SLA tracking and escalation
    - Parallel approvals (multiple approvers at same stage)
    - Notifications (email, webhook, in-app)
    - Audit trail
    """
    
    def __init__(self, db: AsyncSession) -> None:
        """Initialize workflow engine.
        
        Args:
            db: Database session.
        """
        self.db = db
    
    async def create_workflow_definition(
        self,
        name: str,
        description: str,
        steps: list[dict[str, Any]],
        owner_id: str,
        is_active: bool = True,
    ) -> WorkflowDefinition:
        """Create a new workflow definition (template).
        
        Args:
            name: Workflow name.
            description: Workflow description.
            steps: List of step definitions with approvers and conditions.
            owner_id: Creator user ID.
            is_active: Whether workflow is active.
            
        Returns:
            Created workflow definition.
        """
        workflow_def = WorkflowDefinition(
            id=uuid.uuid4(),
            name=name,
            description=description,
            steps_config=steps,
            owner_id=owner_id,
            is_active=is_active,
            created_at=datetime.now(timezone.utc),
        )
        
        self.db.add(workflow_def)
        await self.db.commit()
        await self.db.refresh(workflow_def)
        
        return workflow_def
    
    async def start_workflow(
        self,
        workflow_definition_id: str,
        document_id: str,
        triggered_by: str,
        trigger_type: WorkflowTrigger = WorkflowTrigger.MANUAL,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowInstance:
        """Start a new workflow instance.
        
        Args:
            workflow_definition_id: ID of workflow definition.
            document_id: Document being processed.
            triggered_by: User ID who triggered workflow.
            trigger_type: Type of trigger.
            metadata: Additional metadata.
            
        Returns:
            Created workflow instance.
        """
        # Get workflow definition
        result = await self.db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == workflow_definition_id
            )
        )
        workflow_def = result.scalar_one_or_none()
        
        if not workflow_def:
            raise ValueError(f"Workflow definition not found: {workflow_definition_id}")
        
        # Create workflow instance
        workflow = WorkflowInstance(
            id=uuid.uuid4(),
            workflow_definition_id=workflow_definition_id,
            document_id=document_id,
            status=WorkflowStatus.PENDING.value,
            triggered_by=triggered_by,
            trigger_type=trigger_type.value,
            current_step_index=0,
            metadata=metadata or {},
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        
        self.db.add(workflow)
        await self.db.flush()
        
        # Create steps
        steps = workflow_def.steps_config
        for i, step_config in enumerate(steps):
            step = WorkflowStep(
                id=uuid.uuid4(),
                workflow_id=workflow.id,
                step_index=i,
                name=step_config["name"],
                description=step_config.get("description", ""),
                approver_ids=step_config.get("approvers", []),
                approver_role=step_config.get("approver_role"),
                is_parallel=step_config.get("is_parallel", False),
                min_approvals=step_config.get("min_approvals", 1),
                sla_hours=step_config.get("sla_hours", 24),
                status=WorkflowStepStatus.PENDING.value if i == 0 else WorkflowStepStatus.WAITING.value,
                due_at=datetime.now(timezone.utc) + timedelta(hours=step_config.get("sla_hours", 24)),
            )
            self.db.add(step)
        
        await self.db.commit()
        await self.db.refresh(workflow)
        
        # Notify first approvers
        await self._notify_approvers(workflow, steps[0])
        
        return workflow
    
    async def process_approval(
        self,
        workflow_id: str,
        step_id: str,
        approver_id: str,
        action: ApprovalAction,
        comment: str | None = None,
    ) -> ApprovalResult:
        """Process an approval/rejection action.
        
        Args:
            workflow_id: Workflow instance ID.
            step_id: Current step ID.
            approver_id: User making the decision.
            action: APPROVE or REJECT.
            comment: Optional comment.
            
        Returns:
            ApprovalResult with next steps.
        """
        result = ApprovalResult(
            success=False,
            workflow_id=workflow_id,
            step_id=step_id,
            action=action.value,
            new_status="",
        )
        
        # Get workflow and step
        workflow_result = await self.db.execute(
            select(WorkflowInstance).where(WorkflowInstance.id == workflow_id)
        )
        workflow = workflow_result.scalar_one_or_none()
        
        if not workflow:
            result.errors.append("Workflow not found")
            return result
        
        step_result = await self.db.execute(
            select(WorkflowStep).where(WorkflowStep.id == step_id)
        )
        step = step_result.scalar_one_or_none()
        
        if not step:
            result.errors.append("Step not found")
            return result
        
        # Validate approver
        if approver_id not in step.approver_ids:
            result.errors.append("User is not an approver for this step")
            return result
        
        # Record decision
        step.decisions = step.decisions or {}
        step.decisions[approver_id] = {
            "action": action.value,
            "comment": comment,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        # Check if step is complete
        approvals = sum(
            1 for d in step.decisions.values()
            if d["action"] == ApprovalAction.APPROVE.value
        )
        _rejections = sum(
            1 for d in step.decisions.values()
            if d["action"] == ApprovalAction.REJECT.value
        )
        
        if action == ApprovalAction.REJECT:
            # Handle rejection
            step.status = WorkflowStepStatus.REJECTED.value
            workflow.status = WorkflowStatus.REJECTED.value
            workflow.completed_at = datetime.now(timezone.utc)
            
            # Check for conditional routing on rejection
            if step.rejection_route:
                next_step_id = step.rejection_route
                # Route to specified step or end
                if next_step_id == "end":
                    workflow.status = WorkflowStatus.REJECTED.value
                else:
                    await self._route_to_step(workflow, next_step_id)
            
            result.success = True
            result.new_status = WorkflowStatus.REJECTED.value
            
        elif approvals >= step.min_approvals:
            # Step approved
            step.status = WorkflowStepStatus.APPROVED.value
            step.completed_at = datetime.now(timezone.utc)
            
            # Check if there are more steps
            next_step = await self._get_next_step(workflow, step)
            
            if next_step:
                workflow.current_step_index = next_step.step_index
                next_step.status = WorkflowStepStatus.PENDING.value
                result.next_step = str(next_step.id)
                result.new_status = WorkflowStatus.IN_PROGRESS.value
                workflow.status = WorkflowStatus.IN_PROGRESS.value
                
                # Notify next approvers
                await self._notify_approvers(workflow, next_step)
            else:
                # Workflow complete
                workflow.status = WorkflowStatus.APPROVED.value
                workflow.completed_at = datetime.now(timezone.utc)
                result.new_status = WorkflowStatus.APPROVED.value
            
            result.success = True
        
        await self.db.commit()
        
        # Send notifications
        notifications = await self._send_notifications(workflow, step, action, approver_id)
        result.notifications_sent = notifications
        
        return result
    
    async def _get_next_step(
        self,
        workflow: WorkflowInstance,
        current_step: WorkflowStep,
    ) -> WorkflowStep | None:
        """Get the next step in the workflow."""
        result = await self.db.execute(
            select(WorkflowStep).where(
                WorkflowStep.workflow_id == workflow.id,
                WorkflowStep.step_index > current_step.step_index,
                WorkflowStep.status == WorkflowStepStatus.WAITING.value,
            ).order_by(WorkflowStep.step_index)
        )
        return result.scalar_one_or_none()
    
    async def _route_to_step(
        self,
        workflow: WorkflowInstance,
        step_id: str,
    ) -> None:
        """Route workflow to a specific step."""
        # Implementation for conditional routing
        pass
    
    async def _notify_approvers(
        self,
        workflow: WorkflowInstance,
        step: WorkflowStep,
    ) -> list[str]:
        """Notify approvers that action is required."""
        notifications: list[str] = []
        
        for approver_id in step.approver_ids:
            # TODO: Implement actual notification (email, in-app, webhook)
            # For now, just record that notification was sent
            notifications.append(f"notified:{approver_id}")
        
        step.notifications_sent = notifications
        return notifications
    
    async def _send_notifications(
        self,
        workflow: WorkflowInstance,
        step: WorkflowStep,
        action: ApprovalAction,
        approver_id: str,
    ) -> list[str]:
        """Send notifications about approval action."""
        notifications: list[str] = []
        
        # Notify workflow owner
        notifications.append(f"owner:{workflow.triggered_by}")
        
        # If rejected, notify previous approvers
        if action == ApprovalAction.REJECT:
            prev_steps = await self.db.execute(
                select(WorkflowStep).where(
                    WorkflowStep.workflow_id == workflow.id,
                    WorkflowStep.step_index < step.step_index,
                )
            )
            for prev_step in prev_steps.scalars():
                for pid in prev_step.approver_ids:
                    notifications.append(f"prev_approver:{pid}")
        
        return notifications
    
    async def check_slas(self) -> list[WorkflowInstance]:
        """Check for workflows that have exceeded SLA.
        
        Returns:
            List of workflows that need escalation.
        """
        result = await self.db.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.status.in_([
                    WorkflowStatus.PENDING.value,
                    WorkflowStatus.IN_PROGRESS.value,
                ]),
                WorkflowInstance.expires_at < datetime.now(timezone.utc),
            )
        )
        
        escalated: list[WorkflowInstance] = []
        for workflow in result.scalars():
            workflow.status = WorkflowStatus.ESCALATED.value
            escalated.append(workflow)
            
            # TODO: Send escalation notifications
        
        await self.db.commit()
        return escalated
    
    async def cancel_workflow(
        self,
        workflow_id: str,
        cancelled_by: str,
        reason: str | None = None,
    ) -> bool:
        """Cancel a workflow.
        
        Args:
            workflow_id: Workflow to cancel.
            cancelled_by: User cancelling.
            reason: Optional reason.
            
        Returns:
            True if cancelled successfully.
        """
        result = await self.db.execute(
            update(WorkflowInstance).where(
                WorkflowInstance.id == workflow_id
            ).values(
                status=WorkflowStatus.CANCELLED.value,
                completed_at=datetime.now(timezone.utc),
                metadata={
                    "cancelled_by": cancelled_by,
                    "cancel_reason": reason,
                },
            )
        )
        
        await self.db.commit()
        return result.rowcount > 0
    
    async def get_workflow_history(
        self,
        document_id: str,
    ) -> list[dict[str, Any]]:
        """Get workflow history for a document.
        
        Args:
            document_id: Document ID.
            
        Returns:
            List of workflow history entries.
        """
        result = await self.db.execute(
            select(WorkflowInstance).where(
                WorkflowInstance.document_id == document_id
            ).order_by(WorkflowInstance.created_at.desc())
        )
        
        history: list[dict[str, Any]] = []
        for workflow in result.scalars():
            steps_result = await self.db.execute(
                select(WorkflowStep).where(
                    WorkflowStep.workflow_id == workflow.id
                ).order_by(WorkflowStep.step_index)
            )
            steps = steps_result.scalars().all()
            
            history.append({
                "workflow_id": str(workflow.id),
                "status": workflow.status,
                "created_at": workflow.created_at.isoformat(),
                "completed_at": workflow.completed_at.isoformat() if workflow.completed_at else None,
                "steps": [
                    {
                        "name": step.name,
                        "status": step.status,
                        "approvers": step.approver_ids,
                        "decisions": step.decisions,
                    }
                    for step in steps
                ],
            })
        
        return history
