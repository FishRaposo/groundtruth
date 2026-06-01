"""ASGI middleware that collects Prometheus metrics for every request."""

from __future__ import annotations

import time
from typing import Callable, Awaitable


from app.core.metrics import track_request


class MetricsMiddleware:
    """ASGI middleware that records request count and latency metrics.

    Skips ``/metrics`` and ``/api/health`` paths so that monitoring probes
    do not pollute the application metrics.
    """

    SKIPPED_PATHS: frozenset[str] = frozenset({
        "/metrics",
        "/api/health",
        "/api/health/ready",
        "/api/health/live",
    })

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        """Wrap the given ASGI application.

        Args:
            app: The next ASGI application in the middleware chain.
        """
        self.app = app

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        """Intercept an HTTP request, measure its duration, and record metrics.

        Args:
            scope: The ASGI connection scope.
            receive: The ASGI receive callable.
            send: The ASGI send callable.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.SKIPPED_PATHS:
            await self.app(scope, receive, send)
            return

        start = time.monotonic()

        status_code: int = 500

        async def send_with_status(message: dict) -> None:
            """Capture the response status code before forwarding."""
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            method = scope.get("method", "UNKNOWN")
            duration = time.monotonic() - start
            track_request(method=method, endpoint=path, status_code=status_code, duration=duration)
