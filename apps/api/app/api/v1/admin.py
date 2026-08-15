"""Additive read-only workspace administration surfaces."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.services.audit import AuditTrail, audit_trail
from app.services.cost_tracking import CostTracker, cost_tracker

router = APIRouter(prefix="/admin", tags=["admin"])


def get_cost_tracker() -> CostTracker:
    return cost_tracker


def get_audit_trail() -> AuditTrail:
    return audit_trail


def _require_admin(current_user: dict[str, Any]) -> None:
    if not current_user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin privileges required")


@router.get("/usage")
async def usage_summary(
    current_user: dict[str, Any] = Depends(get_current_user),
    tracker: CostTracker = Depends(get_cost_tracker),
) -> dict[str, Any]:
    """Return cost and latency aggregates for the caller's workspace only."""
    _require_admin(current_user)
    return tracker.summary(workspace_id=current_user.get("workspace_id", "default"))


@router.get("/audit")
async def audit_events(
    current_user: dict[str, Any] = Depends(get_current_user),
    trail: AuditTrail = Depends(get_audit_trail),
) -> list[dict[str, Any]]:
    """Return redacted audit events for the caller's workspace only."""
    _require_admin(current_user)
    return [
        {
            "actor_id": event.actor_id,
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "workspace_id": event.workspace_id,
            "request_id": event.request_id,
            "metadata": event.metadata,
            "created_at": event.created_at.isoformat(),
        }
        for event in trail.events(current_user.get("workspace_id", "default"))
    ]
