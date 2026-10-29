"""Explicit captured-production selection through the central version registry."""

from app.evidence_policy import ReadingVersion, reading_version

SOURCE_CONTRACT = "captured-source-productions-v1"
CONTEXT_CONTRACT = "captured-governing-context-v1"
REQUEST_CONTRACT = "captured-request-productions-v1"


def selected_version(reading_profile: str | None) -> ReadingVersion | None:
    if reading_profile is None:
        return None
    if type(reading_profile) is not str:
        raise ValueError("An explicit registered reading profile is required")
    version = reading_version(reading_profile)
    if version.source_productions is None and version.fact_context is None:
        return None
    if (
        version.source_productions != SOURCE_CONTRACT
        or version.fact_context != CONTEXT_CONTRACT
    ):
        raise ValueError("Unsupported captured production/context contract")
    return version
