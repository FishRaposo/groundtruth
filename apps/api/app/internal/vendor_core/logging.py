# Vendored from FishRaposo/operator-shared-core v1.3.0.
# Source commit: dbf276a7708da65b55e1f10b35af634b300d1f07.
import contextvars
import sys
import time
import uuid
from typing import Any

from fastapi import Request, Response
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable to hold correlation ID across async tasks
correlation_id_var: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "correlation_id", default=None
)


def correlation_id_patcher(record: Any) -> None:
    """Loguru patcher that appends correlation ID to the record's extra attributes."""
    corr_id = correlation_id_var.get()
    record["extra"]["correlation_id"] = corr_id if corr_id else "-"


def setup_logging(level: str = "INFO", service_name: str = "service") -> None:
    """Configures structured logs using loguru."""
    logger.remove()

    # Custom format containing service name, correlation ID, and level details
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{extra[service]}</cyan> | "
        "<magenta>{extra[correlation_id]}</magenta> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        colorize=True,
        format=log_format,
        level=level,
        backtrace=True,
        diagnose=True,
    )

    logger.configure(
        extra={"service": service_name},
        patcher=correlation_id_patcher,
    )
    logger.info(f"Logging configured for service: {service_name} (Level: {level})")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware for logging and correlation ID tracing."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Extract or generate Correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        # Set the contextvar token
        token = correlation_id_var.set(correlation_id)

        # Store on request state
        request.state.correlation_id = correlation_id

        start_time = time.perf_counter()

        logger.info(
            f"Request started: {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"Request failed: {request.method} {request.url.path} - "
                f"Exception: {str(exc)} - Duration: {duration:.2f}ms"
            )
            correlation_id_var.reset(token)
            raise exc

        duration = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"Request completed: {request.method} {request.url.path} - "
            f"Status: {response.status_code} - Duration: {duration:.2f}ms"
        )

        # Add X-Correlation-ID response header
        response.headers["X-Correlation-ID"] = correlation_id

        correlation_id_var.reset(token)
        return response
