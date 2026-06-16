"""Prometheus metrics endpoint for monitoring and alerting."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response

from app.core.metrics import get_metrics
from app.services.cost_tracking import cost_tracker

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    """Return Prometheus metrics in exposition format.

    Returns:
        Response with Prometheus text format metrics.
    """
    return Response(
        content=get_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/api/metrics/cost")
async def cost_summary(workspace: str | None = None) -> dict[str, Any]:
    """Return per-workspace LLM cost/latency/error aggregates.

    Args:
        workspace: Optional workspace key. When provided, returns just that
            workspace's summary; otherwise returns per-workspace summaries plus
            a rolled-up total.
    """
    if workspace is not None:
        return cost_tracker.summary(workspace)
    return cost_tracker.summary_all()
