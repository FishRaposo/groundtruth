"""Strict staged-request output ingress over independently retained execution.

Only shared pure rendering/evidence mechanics are delegated. The request is
reconstructed through its own new contract, never a resolved legacy projection.
"""

from copy import deepcopy

from app.evidence_policy import reading_version, recorded_evidence_policy
from app.services import contextual_mixed_output as mixed
from app.services import staged_role_consumer, staged_source_proof
from app.services.procedure_output import retained_selection
from app.services.staged_plan_replay import reconstruct_request

PROFILE = "contextual_source_v3"
CERTIFICATE_FIELD = "staged_output_certificate"
INPUTS_FIELD = "staged_request_inputs"
CAPTURED_CERTIFICATE_FIELD = "captured_output_certificate"


def _version(reading_profile):
    if reading_profile not in {PROFILE, "contextual_source_v4"}:
        raise ValueError("Explicit registered staged output profile required")
    return reading_version(reading_profile)


def _capture(selection, *, reading_profile=PROFILE):
    version = _version(reading_profile)
    result = deepcopy(selection)
    result.pop(
        CAPTURED_CERTIFICATE_FIELD if version.request_inputs else CERTIFICATE_FIELD,
        None,
    )
    if "staged_publication_check" in result:
        mixed._same(
            result.pop("staged_publication_check"),
            {"consistent": True, "reason": None},
            "Staged publication recheck is not strictly successful",
        )
    return result


def _inputs(selection, question, snapshots, query_context, *, reading_profile=PROFILE):
    version = _version(reading_profile)
    policy = recorded_evidence_policy(selection["evidence_profile"])
    if (
        selection.get("contract") != version.requirement
        or policy.evidence_reading_profile != version.profile
        or policy.staged_request is not True
    ):
        raise ValueError("Actual staged selection/profile required")
    captured = retained_selection(query_context)
    if type(captured) is not dict:
        raise ValueError("Independently retained staged execution required")
    actual_inputs = selection[INPUTS_FIELD]
    retained_inputs = captured[INPUTS_FIELD]
    reconstruct = reconstruct_request
    if version.request_inputs:
        from app.services.captured_plan_binding import (
            reconstruct_request as reconstruct,
        )

    plan = reconstruct(
        actual_inputs,
        question=question,
        authoritative_snapshots=snapshots,
        retained_inputs=retained_inputs,
        require_runtime=True,
    )
    mixed._same(
        selection["request_plan"], plan.record(), "Whole staged request differs"
    )
    return plan, actual_inputs, retained_inputs


def build_output(
    selection, *, question, source_snapshots, query_context, reading_profile=PROFILE
):
    """No external callbacks or claimed plan can replace the strict consumer."""
    try:
        plan, inputs, retained = _inputs(
            selection,
            question,
            source_snapshots,
            query_context,
            reading_profile=reading_profile,
        )
        actual_selection = _capture(selection, reading_profile=reading_profile)
        captured = retained_selection(query_context)
        if type(captured) is not dict:
            raise ValueError("Independently retained staged selection required")
        actual_context = {
            "provenance": {
                "answer_selection": _capture(captured, reading_profile=reading_profile)
            }
        }
        role_consumer = staged_role_consumer
        if _version(reading_profile).request_inputs:
            from app.services import captured_role_consumer as role_consumer

        typed_roles = role_consumer.reconstruct_selection(
            actual_selection,
            question=question,
            planning_inputs=inputs,
            retained_inputs=retained,
            authoritative_snapshots=source_snapshots,
            retained_selection=captured,
        )

        def request_reconstructor(actual_question, _context):
            if actual_question != question:
                raise ValueError("Staged original question differs")
            return plan

        def source_guard(
            actual_selection,
            requirement,
            snapshot,
            actual_plan,
        ):
            mixed._same(
                actual_plan.record(), plan.record(), "Staged plan changed during output"
            )
            if requirement.kind != "procedure":
                return mixed.reconstruct_factual_source_guard(
                    actual_selection,
                    requirement,
                    snapshot,
                    actual_plan,
                    reading_profile=reading_profile,
                )
            return staged_source_proof.reconstruct_source_guard(
                actual_selection,
                requirement,
                snapshot,
                question=question,
                planning_inputs=inputs,
                retained_inputs=retained,
                authoritative_snapshots=source_snapshots,
                retained_records=captured["source_guard_records"],
                reading_profile=reading_profile,
            )

        return mixed.build_output(
            actual_selection,
            question=question,
            source_snapshots=source_snapshots,
            query_context=actual_context,
            reading_profile=reading_profile,
            request_reconstructor=request_reconstructor,
            source_guard_reconstructor=source_guard,
            typed_role_evidence=typed_roles,
        )
    except (KeyError, TypeError, AttributeError, IndexError, RecursionError) as exc:
        raise ValueError("Staged output inputs do not reconstruct") from exc


def reconstruct_certificate(selection, *, answer, citations, **context):
    result = build_output(selection, **context)
    mixed._same(answer, result["answer"], "Actual staged answer differs from renderer")
    expected = result["citations"]
    if type(citations) is not list or len(citations) != len(expected):
        raise ValueError("Actual staged citation inventory differs")
    for actual, canonical in zip(citations, expected, strict=True):
        if type(actual) is not dict or not set(canonical) <= actual.keys():
            raise ValueError("Actual staged citation is incomplete")
        for key, value in canonical.items():
            mixed._same(actual[key], value, "Actual staged citation evidence differs")
    return result["certificate"]


def verify_output(selection, **context):
    try:
        expected = reconstruct_certificate(selection, **context)
        mixed._same(
            selection[CERTIFICATE_FIELD], expected, "Staged output certificate differs"
        )
        return True
    except (ValueError, KeyError, TypeError, RecursionError):
        return False
