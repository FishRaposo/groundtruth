"""Application logging configuration, backed by shared_core (loguru).

Keeps the historical ``setup_logging(log_format, log_level)`` signature used by
``app.main`` while routing configuration through ``shared_core.logging``. Domain
modules that use ``structlog.get_logger()`` continue to work unchanged.
"""

from shared_core.logging import setup_logging as _shared_setup_logging


def setup_logging(log_format: str = "text", log_level: str = "INFO") -> None:
    """Configure structured logging for the application via shared_core.

    Args:
        log_format: Retained for signature compatibility (shared_core honors
            ``LOG_FORMAT=json`` via its own JSON sink configuration).
        log_level: The minimum log level to capture (e.g. "INFO", "DEBUG").
    """
    _shared_setup_logging(level=log_level, service_name="groundtruth")
