"""Structured audit-event contracts."""

from __future__ import annotations

import pytest
from app.services.audit import AUDITED_RESOURCE_TYPES, AuditTrail


class RecordingSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.flushed = False

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed = True


async def test_audit_event_redacts_secrets_and_retains_context() -> None:
    trail = AuditTrail()
    event = await trail.record(
        actor_id="actor",
        action="create",
        resource_type="api_key",
        resource_id="key-1",
        workspace_id="ws-1",
        request_id="req-1",
        metadata={
            "token": "secret",
            "nested": {"authorization": "Bearer secret", "safe": "kept"},
        },
    )
    assert event.workspace_id == "ws-1"
    assert event.request_id == "req-1"
    assert event.metadata["token"] == "[REDACTED]"
    assert event.metadata["nested"] == {
        "authorization": "[REDACTED]",
        "safe": "kept",
    }
    assert trail.events(workspace_id="ws-1") == [event]


async def test_audit_event_can_be_persisted_without_committing_caller_transaction() -> (
    None
):
    session = RecordingSession()
    trail = AuditTrail()
    event = await trail.record(
        actor_id="actor",
        action="delete",
        resource_type="document",
        resource_id="doc-1",
        workspace_id="ws-1",
        db=session,
    )
    assert session.flushed is True
    assert len(session.added) == 1
    persisted = session.added[0]
    assert persisted.action == event.action
    assert persisted.details["workspace_id"] == "ws-1"


@pytest.mark.parametrize(
    "resource_type",
    ["document", "query", "workflow", "approval", "api_key", "admin", "configuration"],
)
async def test_declared_mutation_resource_types_are_auditable(
    resource_type: str,
) -> None:
    assert resource_type in AUDITED_RESOURCE_TYPES
    event = await AuditTrail().record(
        actor_id="actor", action="mutate", resource_type=resource_type
    )
    assert event.resource_type == resource_type
