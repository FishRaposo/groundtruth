"""Explicit profile-v4 ingress using shared exact staged rendering mechanics."""

from app.services import contextual_mixed_output as mixed
from app.services import staged_output as shared

PROFILE = "contextual_source_v4"
CERTIFICATE_FIELD = shared.CAPTURED_CERTIFICATE_FIELD


def build_output(selection, **context):
    return shared.build_output(selection, reading_profile=PROFILE, **context)


def reconstruct_certificate(selection, **context):
    return shared.reconstruct_certificate(selection, reading_profile=PROFILE, **context)


def verify_output(selection, **context):
    try:
        expected = reconstruct_certificate(selection, **context)
        mixed._same(
            selection[CERTIFICATE_FIELD],
            expected,
            "Captured output certificate differs",
        )
        return True
    except (ValueError, KeyError, TypeError, RecursionError):
        return False
