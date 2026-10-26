"""Additive read-only workspace administration surfaces."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.db.session import get_db
from app.models.collection import AuditLog
from app.models.query import Query
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
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return cost and latency aggregates for the caller's workspace only."""
    _require_admin(current_user)
    if get_settings().connected:
        rows = (
            await db.scalars(
                select(Query).where(
                    Query.workspace_id == current_user.get("workspace_id", "default")
                )
            )
        ).all()
        tokens = sum(
            int((row.token_usage or {}).get("total_tokens", 0)) for row in rows
        )
        latency = [
            int((row.retrieval_trace or {}).get("latency_ms", 0)) for row in rows
        ]
        from app.internal.vendor_core.llmmetrics import _percentile

        latencies = sorted(float(value) for value in latency)
        return {
            "workspace_id": current_user.get("workspace_id", "default"),
            "total_requests": len(rows),
            "request_count": len(rows),
            "total_tokens": tokens,
            "total_cost": None,
            "estimated_cost": None,
            "input_tokens": sum(
                int((row.token_usage or {}).get("prompt_tokens", 0)) for row in rows
            ),
            "output_tokens": sum(
                int((row.token_usage or {}).get("completion_tokens", 0)) for row in rows
            ),
            "p50_latency_ms": _percentile(latencies, 50),
            "p95_latency_ms": _percentile(latencies, 95),
            "p99_latency_ms": _percentile(latencies, 99),
            "error_rate": sum(row.outcome in {"error", "interrupted"} for row in rows)
            / max(len(rows), 1),
            "cost_by_model": {},
            "cost_by_prompt_version": {},
            "estimated": True,
            "pricing_provenance": (
                "unknown; local extractive generation has no provider charge"
            ),
            "average_latency_ms": sum(latency) / max(len(latency), 1),
            "models": [],
            "by_model": {},
            "outcomes": {
                outcome: sum(row.outcome == outcome for row in rows)
                for outcome in ("completed", "refused", "error", "interrupted")
            },
        }
    return tracker.summary(workspace_id=current_user.get("workspace_id", "default"))


@router.get("/audit")
async def audit_events(
    current_user: dict[str, Any] = Depends(get_current_user),
    trail: AuditTrail = Depends(get_audit_trail),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return redacted audit events for the caller's workspace only."""
    _require_admin(current_user)
    if get_settings().connected:
        workspace = current_user.get("workspace_id", "default")
        scope = AuditLog.details["workspace_id"].as_string() == workspace
        if workspace == "default":
            scope = or_(scope, AuditLog.details["workspace_id"].as_string().is_(None))
        rows = (
            await db.scalars(
                select(AuditLog)
                .where(scope)
                .order_by(AuditLog.created_at.desc())
                .limit(1000)
            )
        ).all()
        return [
            {
                "actor_id": row.user_id,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "workspace_id": (row.details or {}).get("workspace_id", "default"),
                "request_id": (row.details or {}).get("request_id"),
                "metadata": (row.details or {}).get("metadata", {}),
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
            if (row.details or {}).get("workspace_id", "default")
            == current_user.get("workspace_id", "default")
        ]
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
