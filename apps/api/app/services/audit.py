"""Structured, redacted audit events with memory and SQLAlchemy sinks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.internal.context import DEFAULT_WORKSPACE_ID, get_request_context
from app.models.collection import AuditLog
from app.utils.time import utc_now

_SECRET_KEYS = {
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}

AUDITED_RESOURCE_TYPES = frozenset(
    {
        "document",
        "query",
        "workflow",
        "approval",
        "api_key",
        "admin",
        "configuration",
    }
)


def redact_audit_metadata(value: Any, key: str | None = None) -> Any:
    """Recursively redact credential-shaped fields before persistence."""
    if key and key.lower().replace("-", "_") in _SECRET_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: redact_audit_metadata(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_audit_metadata(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class AuditEvent:
    actor_id: str
    action: str
    resource_type: str
    resource_id: str | None
    workspace_id: str
    request_id: str | None
    metadata: dict[str, Any]
    created_at: datetime
    api_key_id: str | None = None


class AuditTrail:
    """Records events in memory and optionally flushes an AuditLog row."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    async def record(
        self,
        *,
        actor_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        workspace_id: str | None = None,
        request_id: str | None = None,
        api_key_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        db: Any | None = None,
    ) -> AuditEvent:
        context = get_request_context()
        event = AuditEvent(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            workspace_id=workspace_id or context.workspace_id or DEFAULT_WORKSPACE_ID,
            request_id=request_id or context.request_id,
            api_key_id=api_key_id or context.api_key_id,
            metadata=redact_audit_metadata(metadata or {}),
            created_at=utc_now(),
        )
        self._events.append(event)
        if db is not None:
            db.add(
                AuditLog(
                    user_id=event.actor_id,
                    api_key_id=event.api_key_id,
                    action=event.action,
                    resource_type=event.resource_type,
                    resource_id=event.resource_id,
                    details={
                        "workspace_id": event.workspace_id,
                        "request_id": event.request_id,
                        "metadata": event.metadata,
                    },
                )
            )
            await db.flush()
        return event

    def events(self, workspace_id: str | None = None) -> list[AuditEvent]:
        if workspace_id is None:
            return list(self._events)
        return [event for event in self._events if event.workspace_id == workspace_id]

    def reset(self) -> None:
        self._events.clear()


audit_trail = AuditTrail()
