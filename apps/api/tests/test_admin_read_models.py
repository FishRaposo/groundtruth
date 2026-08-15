"""Read-only workspace admin usage and audit contracts."""

from app.api.v1.admin import audit_events, usage_summary
from app.services.audit import AuditTrail
from app.services.cost_tracking import CostTracker


async def test_admin_read_models_are_workspace_scoped() -> None:
    tracker = CostTracker()
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=12,
        workspace_id="ws-a",
    )
    trail = AuditTrail()
    await trail.record(
        actor_id="user-a",
        action="restore_version",
        resource_type="document",
        workspace_id="ws-a",
        metadata={"token": "secret"},
    )
    await trail.record(
        actor_id="user-b",
        action="delete",
        resource_type="document",
        workspace_id="ws-b",
    )
    current_user = {"id": "admin", "is_admin": True, "workspace_id": "ws-a"}

    usage = await usage_summary(current_user=current_user, tracker=tracker)
    audit = await audit_events(current_user=current_user, trail=trail)

    assert usage["total_requests"] == 1
    assert len(audit) == 1
    assert audit[0]["workspace_id"] == "ws-a"
    assert audit[0]["metadata"]["token"] == "[REDACTED]"
