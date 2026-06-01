"""Timezone-aware datetime helpers."""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC datetime with timezone stripped (naive UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
