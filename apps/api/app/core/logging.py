"""Application logging configuration, backed by the internal vendor core (loguru).

Keeps the historical ``setup_logging(log_format, log_level)`` signature used by
``app.main`` while routing configuration through the internal vendor core. Domain
modules that use ``structlog.get_logger()`` continue to work unchanged.
"""

from app.internal.vendor_core.logging import setup_logging as _vendor_setup_logging


def setup_logging(log_format: str = "text", log_level: str = "INFO") -> None:
    """Configure structured logging through the internal vendor core.

    Args:
        log_format: Retained for signature compatibility (the vendor core honors
            ``LOG_FORMAT=json`` via its own JSON sink configuration).
        log_level: The minimum log level to capture (e.g. "INFO", "DEBUG").
    """
    _vendor_setup_logging(level=log_level, service_name="groundtruth")
