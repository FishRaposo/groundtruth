"""Prometheus metrics endpoint for monitoring and alerting."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.core.metrics import get_metrics

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
