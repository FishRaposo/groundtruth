"""Workflow scoping, routing, notification, and status-stream contracts."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from app.api.v1.workflows import workflow_instance_visibility
from app.db.session import Base
from app.models.document import Document, DocumentStatus, SourceType
from app.models.document.workflow import ApprovalAction, WorkflowInstance, WorkflowStep
from app.services.document.processing.approval import (
    ApprovalWorkflowEngine,
    WorkflowStatus,
)
from app.services.notifications import InMemoryNotificationSink, NotificationOutbox
from app.services.workflow_events import WorkflowEventBroker
from app.tasks.workflows import enqueue_workflow_notification
from app.utils.time import utc_now
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def workflow_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def test_workflow_instance_visibility_is_workspace_and_owner_scoped() -> None:
    clause = workflow_instance_visibility({"id": "owner-1", "workspace_id": "ws-1"})
    compiled = str(
        clause.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert WorkflowInstance.workspace_id.key in compiled
    assert "ws-1" in compiled
    assert "owner-1" in compiled


async def test_notification_outbox_is_local_and_deduplicates() -> None:
    sink = InMemoryNotificationSink()
    outbox = NotificationOutbox(sinks=[sink])
    first = await outbox.enqueue(
        workspace_id="ws-1",
        event_type="workflow.approval_required",
        recipient="reviewer-1",
        payload={"workflow_id": "wf-1", "password": "secret"},
        deduplication_key="wf-1:step-1:reviewer-1",
    )
    second = await outbox.enqueue(
        workspace_id="ws-1",
        event_type="workflow.approval_required",
        recipient="reviewer-1",
        payload={"workflow_id": "wf-1"},
        deduplication_key="wf-1:step-1:reviewer-1",
    )
    assert first.id == second.id
    assert first.payload["password"] == "[REDACTED]"
    assert len(sink.delivered) == 1


async def test_workflow_task_enqueues_local_notification() -> None:
    sink = InMemoryNotificationSink()
    outbox = NotificationOutbox([sink])
    result = await enqueue_workflow_notification(
        outbox=outbox,
        workflow_id="wf-1",
        step_id="step-1",
        action="approve",
        approver_id="reviewer-1",
        workspace_id="ws-1",
    )
    assert result["delivery_mode"] == "local_outbox"
    assert len(sink.delivered) == 1


async def test_workflow_event_broker_replays_ordered_compatible_events() -> None:
    broker = WorkflowEventBroker()
    await broker.publish("wf-1", "status", {"status": "pending"})
    await broker.publish("wf-1", "status", {"status": "approved"})
    events = broker.snapshot("wf-1", after_event_id=0)
    assert [event.event_id for event in events] == [1, 2]
    assert [event.event_type for event in events] == ["status", "status"]
    assert events[-1].data == {"status": "approved"}


async def test_workflow_routes_and_escalates_with_local_events(
    workflow_session,
) -> None:
    document = Document(
        id=uuid.uuid4(),
        title="Review",
        source_type=SourceType.TEXT,
        status=DocumentStatus.READY,
        workspace_id="ws-1",
    )
    workflow_session.add(document)
    await workflow_session.commit()
    sink = InMemoryNotificationSink()
    broker = WorkflowEventBroker()
    engine = ApprovalWorkflowEngine(
        workflow_session,
        outbox=NotificationOutbox([sink]),
        event_broker=broker,
    )
    definition = await engine.create_workflow_definition(
        name="Review",
        description=None,
        steps=[
            {"name": "legal", "approvers": ["reviewer"], "sla_hours": 1},
            {"name": "publish", "approvers": ["publisher"], "sla_hours": 1},
        ],
        owner_id="owner",
        workspace_id="ws-1",
    )
    workflow = await engine.start_workflow(
        str(definition.id), str(document.id), "owner", workspace_id="ws-1"
    )
    steps = (
        (
            await workflow_session.execute(
                select(WorkflowStep)
                .where(WorkflowStep.workflow_id == workflow.id)
                .order_by(WorkflowStep.step_index)
            )
        )
        .scalars()
        .all()
    )
    result = await engine.process_approval(
        str(workflow.id),
        str(steps[0].id),
        "reviewer",
        ApprovalAction.APPROVE,
        workspace_id="ws-1",
    )
    assert result.success is True
    assert result.new_status == WorkflowStatus.IN_PROGRESS.value
    assert result.next_step == str(steps[1].id)

    workflow.expires_at = utc_now() - timedelta(minutes=1)
    workflow.status = WorkflowStatus.IN_PROGRESS.value
    await workflow_session.commit()
    escalated = await engine.check_slas()
    assert [item.id for item in escalated] == [workflow.id]
    assert broker.snapshot(str(workflow.id))[-1].data["status"] == "escalated"
    assert any(item.event_type == "workflow.escalated" for item in sink.delivered)


async def test_workflow_mutation_rejects_other_workspace(workflow_session) -> None:
    engine = ApprovalWorkflowEngine(workflow_session)
    result = await engine.process_approval(
        str(uuid.uuid4()),
        str(uuid.uuid4()),
        "reviewer",
        ApprovalAction.APPROVE,
        workspace_id="other",
    )
    assert result.success is False
    assert result.errors == ["Workflow not found"]


async def test_rejection_route_activates_named_step(workflow_session) -> None:
    document = Document(
        id=uuid.uuid4(),
        title="Correction",
        source_type=SourceType.TEXT,
        status=DocumentStatus.READY,
        workspace_id="ws-1",
    )
    workflow_session.add(document)
    await workflow_session.commit()
    engine = ApprovalWorkflowEngine(workflow_session)
    definition = await engine.create_workflow_definition(
        name="Correction",
        description=None,
        steps=[
            {
                "name": "review",
                "approvers": ["reviewer"],
                "rejection_route": "correction",
            },
            {"name": "correction", "approvers": ["owner"]},
        ],
        owner_id="owner",
        workspace_id="ws-1",
    )
    workflow = await engine.start_workflow(
        str(definition.id), str(document.id), "owner", workspace_id="ws-1"
    )
    steps = (
        (
            await workflow_session.execute(
                select(WorkflowStep)
                .where(WorkflowStep.workflow_id == workflow.id)
                .order_by(WorkflowStep.step_index)
            )
        )
        .scalars()
        .all()
    )
    result = await engine.process_approval(
        str(workflow.id),
        str(steps[0].id),
        "reviewer",
        ApprovalAction.REJECT,
        workspace_id="ws-1",
    )
    assert result.success is True
    assert result.new_status == WorkflowStatus.IN_PROGRESS.value
    assert steps[1].status == "pending"
