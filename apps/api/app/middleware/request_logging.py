import hashlib
import time
import uuid
from typing import Any, Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings
from app.internal.context import bind_request_context

settings = get_settings()

try:
    import structlog

    logger = structlog.get_logger("groundtruth.request")
except ImportError:
    import logging

    logger = logging.getLogger("groundtruth.request")

HEALTH_PATHS = {"/api/health", "/health", "/"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that logs structured request information for every request.

    Adds a correlation ID to each request, logs method/path/status/duration,
    and captures body sizes for POST/PUT and query responses.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[..., Awaitable[Response]]
    ) -> Response:
        """Process and log the request.

        Args:
            request: The incoming HTTP request.
            call_next: The next middleware or endpoint handler.

        Returns:
            The response from the next handler, with correlation ID header.
        """
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        workspace_id = request.headers.get("X-Workspace-ID", "default")
        raw_api_key = request.headers.get("X-API-Key")
        api_key_id = (
            hashlib.sha256(raw_api_key.encode()).hexdigest()[:12]
            if raw_api_key
            else None
        )
        start_time = time.perf_counter()

        request_body_size: int | None = None
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("Content-Length")
            request_body_size = int(content_length) if content_length else None

        request.state.correlation_id = correlation_id
        request.state.workspace_id = workspace_id
        with bind_request_context(
            request_id=correlation_id,
            workspace_id=workspace_id,
            api_key_id=api_key_id,
        ):
            response = await call_next(request)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Workspace-ID"] = workspace_id

        api_key_prefix: str | None = None
        api_key = getattr(request.state, "api_key", None)
        if api_key is not None:
            api_key_prefix = getattr(api_key, "key_prefix", None)

        if request.url.path not in HEALTH_PATHS:
            log_data: dict[str, Any] = {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "correlation_id": correlation_id,
                "workspace_id": workspace_id,
                "client_ip": request.client.host if request.client else None,
            }

            if api_key_prefix is not None:
                log_data["api_key_prefix"] = api_key_prefix

            if request_body_size is not None:
                log_data["request_body_size"] = request_body_size

            if request.url.path.startswith("/api/queries") and request.method == "GET":
                response_body_size = response.headers.get("Content-Length")
                if response_body_size:
                    log_data["response_body_size"] = int(response_body_size)

            if response.status_code >= 400:
                log_data["event"] = "request_error"
                self._log_error(log_data)
            else:
                log_data["event"] = "request"
                self._log_info(log_data)

        return response

    def _log_info(self, data: dict[str, Any]) -> None:
        """Log an informational request record.

        Args:
            data: The structured log data dictionary.
        """
        try:
            logger.info(**data)
        except TypeError:
            logger.info(data.get("event", "request"), extra=data)

    def _log_error(self, data: dict[str, Any]) -> None:
        """Log an error-level request record.

        Args:
            data: The structured log data dictionary.
        """
        try:
            logger.error(**data)
        except TypeError:
            logger.error(data.get("event", "request_error"), extra=data)
