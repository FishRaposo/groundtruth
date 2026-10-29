"""Select the recorded output contract without retrocertifying legacy answers.

Markers in either the presented selection or its independently retained capture
require contextual replay. Removing one marker must not downgrade verification.
Authorization and immutable snapshot loading remain caller responsibilities.
"""

from __future__ import annotations

from app.evidence_policy import reading_version
from app.services import procedure_output


def _captured_marker(selection):
    if type(selection) is not dict:
        return False
    version = reading_version("contextual_source_v4")
    profile = selection.get("evidence_profile")
    profile = profile if type(profile) is dict else {}
    inputs = selection.get("staged_request_inputs")
    inputs = inputs if type(inputs) is dict else {}
    plan = selection.get("request_plan")
    plan = plan if type(plan) is dict else {}
    return (
        profile.get("contract") == version.evidence_profile
        or profile.get("evidence_reading_profile") == version.profile
        or inputs.get("contract") == version.request_inputs
        or plan.get("contract") == version.request_plan
        or "captured_output_certificate" in selection
    )


def _requires_captured(selection, query_context):
    if _captured_marker(selection):
        return True
    if query_context is not None:
        try:
            return _captured_marker(procedure_output.retained_selection(query_context))
        except (KeyError, TypeError, AttributeError, ValueError):
            pass
    return False


def _staged_marker(selection):
    if not isinstance(selection, dict):
        return False
    from app.services.staged_output import CERTIFICATE_FIELD, INPUTS_FIELD

    version = reading_version("contextual_source_v3")
    profile = selection.get("evidence_profile")
    profile = profile if isinstance(profile, dict) else {}
    return (
        selection.get("contract") == version.requirement
        or profile.get("contract") == version.evidence_profile
        or profile.get("evidence_reading_profile") == version.profile
        or CERTIFICATE_FIELD in selection
        or INPUTS_FIELD in selection
    )


def _requires_staged(selection, query_context):
    if _staged_marker(selection):
        return True
    if query_context is not None:
        try:
            return _staged_marker(procedure_output.retained_selection(query_context))
        except (KeyError, TypeError, AttributeError, ValueError):
            pass
    return False


def _contextual_marker(selection) -> bool:
    if not isinstance(selection, dict):
        return False
    profile = selection.get("evidence_profile")
    profile = profile if isinstance(profile, dict) else {}
    versions = tuple(
        reading_version(name)
        for name in ("contextual_source_v1", "contextual_source_v2")
    )
    return (
        selection.get("contract") in {version.requirement for version in versions}
        or profile.get("evidence_reading_profile")
        in {version.profile for version in versions}
        or profile.get("contract") in {version.evidence_profile for version in versions}
        or "contextual_output_certificate" in selection
        or _linguistic_marker(selection)
    )


def _linguistic_marker(selection):
    from app.services.contextual_mixed_output import CERTIFICATE_FIELD

    if not isinstance(selection, dict):
        return False
    profile = selection.get("evidence_profile")
    profile = profile if isinstance(profile, dict) else {}
    version = reading_version("contextual_source_v2")
    return (
        selection.get("contract") == version.requirement
        or profile.get("contract") == version.evidence_profile
        or profile.get("evidence_reading_profile") == version.profile
        or CERTIFICATE_FIELD in selection
    )


def _requires_linguistic(selection, query_context):
    if _linguistic_marker(selection):
        return True
    if query_context is not None:
        try:
            return _linguistic_marker(
                procedure_output.retained_selection(query_context)
            )
        except (KeyError, TypeError, AttributeError, ValueError):
            pass
    return False


def is_contextual(selection, query_context=None) -> bool:
    if _requires_captured(selection, query_context):
        return True
    if _requires_staged(selection, query_context):
        return True
    if _contextual_marker(selection):
        return True
    if query_context is not None:
        try:
            return _contextual_marker(
                procedure_output.retained_selection(query_context)
            )
        except (KeyError, TypeError, AttributeError, ValueError):
            pass
    return False


def has_output_contract(selection, query_context=None) -> bool:
    return is_contextual(selection, query_context) or procedure_output.has_v3(
        selection, query_context=query_context
    )


def certify_output(selection, **context):
    if _requires_captured(selection, context.get("query_context")):
        from app.services.captured_output import (
            CERTIFICATE_FIELD,
            reconstruct_certificate,
        )

        selection[CERTIFICATE_FIELD] = reconstruct_certificate(selection, **context)
        return None
    if _requires_staged(selection, context.get("query_context")):
        from app.services.staged_output import (
            CERTIFICATE_FIELD,
            reconstruct_certificate,
        )

        selection[CERTIFICATE_FIELD] = reconstruct_certificate(selection, **context)
        return None
    if _requires_linguistic(selection, context.get("query_context")):
        from app.services.contextual_mixed_output import (
            CERTIFICATE_FIELD,
            reconstruct_certificate,
        )

        if (
            not {"question", "answer", "citations", "source_snapshots", "query_context"}
            <= context.keys()
        ):
            raise ValueError("Actual linguistic publication context is required")
        selection[CERTIFICATE_FIELD] = reconstruct_certificate(selection, **context)
        return None
    if is_contextual(selection, context.get("query_context")):
        from app.services.contextual_output import certify_output as contextual_certify

        return contextual_certify(selection, **context)
    return procedure_output.certify_output(selection, **context)


def verify_output(selection, **context) -> bool:
    if _requires_captured(selection, context.get("query_context")):
        from app.services.captured_output import verify_output as captured_verify

        return captured_verify(selection, **context)
    if _requires_staged(selection, context.get("query_context")):
        from app.services.staged_output import verify_output as staged_verify

        return staged_verify(selection, **context)
    if _requires_linguistic(selection, context.get("query_context")):
        from app.services.contextual_mixed_output import verify_output as mixed_verify

        return mixed_verify(selection, **context)
    if is_contextual(selection, context.get("query_context")):
        from app.services.contextual_output import verify_output as contextual_verify

        return contextual_verify(selection, **context)
    return procedure_output.verify_output(selection, **context)
