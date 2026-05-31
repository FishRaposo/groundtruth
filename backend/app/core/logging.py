import logging
from typing import Any

from app.config import get_settings


def setup_logging(log_format: str = "text", log_level: str = "INFO") -> None:
    """Configure structured logging for the application.

    Sets up structlog with the appropriate renderer and integrates with
    standard library loggers for uvicorn and sqlalchemy.

    Args:
        log_format: Output format, either "json" for machine-readable or
            "text" for human-readable console output.
        log_level: The minimum log level to capture (e.g. "INFO", "DEBUG").
    """
    try:
        import structlog
    except ImportError:
        _setup_standard_logging(log_level)
        return

    _configure_standard_loggers(log_level)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        _add_service_name,
    ]

    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _add_service_name(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Add the service name to every structured log entry.

    Args:
        logger: The structlog logger instance.
        method_name: The name of the log method being called.
        event_dict: The current event dictionary.

    Returns:
        The event dictionary with service_name added.
    """
    event_dict["service_name"] = "groundtruth"
    return event_dict


def _configure_standard_loggers(log_level: str) -> None:
    """Set log levels on standard library loggers used by dependencies.

    Args:
        log_level: The minimum log level string.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "sqlalchemy"):
        std_logger = logging.getLogger(logger_name)
        std_logger.setLevel(level)


def _setup_standard_logging(log_level: str) -> None:
    """Fallback logging setup when structlog is not available.

    Args:
        log_level: The minimum log level string.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    _configure_standard_loggers(log_level)
