"""Opt-in v2 raw input transport; structural productions confer no acceptance.

This new-only interface rejects default/legacy selection. Historical callers
continue using staged_plan_replay unchanged. Authoritative source records must
come from the caller's independent SQL load; this module grants neither current
SQL membership nor authorization, factual support, or publication readiness.
"""

import json
from dataclasses import asdict, dataclass

from app.evidence_policy import (
    EvidencePolicy,
    reading_version,
    recorded_evidence_policy,
    validate_evidence_engines,
)
from app.services import captured_request_productions as request_productions
from app.services import captured_source_productions as source_productions
from app.services import planning_declarations as source
from app.services import staged_plan_replay as legacy
from app.services.request_parser import validate_capture

CONTRACT = "staged-request-inputs-v2"
canonical = source.canonical
_EXTRA_FIELDS = frozenset(
    {"evidence_profile", "request_productions", "source_productions"}
)
_FIELDS = legacy._FIELDS | _EXTRA_FIELDS


@dataclass(frozen=True)
class DecodedCapturedInputs:
    """Detached raw arguments and replayed syntax, never a semantic plan."""

    arguments: dict
    evidence_profile: dict
    request_productions: dict
    source_productions: dict


def _profile(value):
    value = value.record() if type(value) is EvidencePolicy else value
    source._native(value)
    if type(value) is not dict:
        raise ValueError("Explicit canonical new evidence profile required")
    policy = recorded_evidence_policy(value)
    version = reading_version(policy.evidence_reading_profile)
    if version.request_inputs != CONTRACT:
        raise ValueError("This interface only accepts the new input contract")
    # Validate declared controls, without claiming that these engines ran.
    validate_evidence_engines(
        policy.proposal_profile,
        policy.role_scope_policy,
        "reader",
        "local_nli",
        procedure=policy.procedure_verification_profile,
        generation="extractive",
        context=policy.source_context_policy,
        reading=policy.evidence_reading_profile,
        request_parser=version.request_parser,
        quantity=policy.quantity_verification_profile,
    )
    if canonical(policy.record()) != canonical(value):
        raise ValueError("Evidence profile is not the canonical registered record")
    return json.loads(canonical(value)), version.profile


def _productions(arguments, reading_profile):
    request = request_productions.reconstruct_request_productions(
        arguments["question"], arguments["capture"], reading_profile=reading_profile
    )
    sources = source_productions.reconstruct_source_productions(
        **{
            key: arguments[key]
            for key in (
                "question",
                "capture",
                "manifest",
                "snapshots",
                "source_captures",
                "sql_read_set_json",
            )
        },
        reading_profile=reading_profile,
    )
    return request, sources


def _validate_raw(arguments):
    validate_capture(arguments["question"], arguments["capture"])
    manifest = arguments["manifest"]
    snapshots = arguments["snapshots"]
    source._inputs(manifest, snapshots, arguments["source_captures"])
    if set(manifest.publications) != {row.identity for row in snapshots}:
        raise ValueError("Complete source/capture manifest inventory required")
    source._json_object(arguments["sql_read_set_json"])


def capture_inputs_v2(
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    *,
    support_metadata,
    sql_read_set_json,
    observations,
    actual_executions,
    evidence_profile=None,
):
    """Detach old native inputs and add complete fixed production records.

    Profile selection must be explicit; no default or old record is upgraded.
    Capturing output observations does not make them production identity inputs.
    Receipt containers must be finite native lists/tuples, never iterators.
    """
    try:
        if type(observations) not in (list, tuple) or type(actual_executions) not in (
            list,
            tuple,
        ):
            raise ValueError("Finite native list/tuple receipt containers required")
        profile, reading_profile = _profile(evidence_profile)
        arguments = {
            "question": question,
            "capture": capture,
            "manifest": manifest,
            "snapshots": snapshots,
            "source_captures": source_captures,
            "support_metadata": support_metadata,
            "sql_read_set_json": sql_read_set_json,
            "observations": observations,
            "actual_executions": actual_executions,
        }
        _validate_raw(arguments)
        # Check before the historical serializer can normalize tuple/non-native
        # metadata inside a receipt into a different JSON value.
        source._native(support_metadata)
        for row in (*observations, *actual_executions):
            source._native(asdict(row))
        record = legacy.capture_inputs(**arguments)
        source._native(record)
        request, sources = _productions(arguments, reading_profile)
        record.update(
            contract=CONTRACT,
            evidence_profile=profile,
            request_productions=request,
            source_productions=sources,
        )
        source._native(record)
        return json.loads(canonical(record))
    except (KeyError, TypeError, AttributeError, IndexError, RecursionError) as exc:
        raise ValueError("New staged input capture does not reconstruct") from exc


def decode_inputs_v2(record, *, question, authoritative_snapshots, retained_inputs):
    """Replay full productions using independent source and retained channels.

    Output observations/executions survive typed transport but are not validated
    as evidence here. A later semantic consumer must bind and assess them. This
    interface accepts no producer callback, readiness flag, or self-hash proof.
    """
    try:
        source._native(record)
        source._native(retained_inputs)
        if (
            type(record) is not dict
            or set(record) != _FIELDS
            or record.get("contract") != CONTRACT
            or type(question) is not str
            or record.get("question") != question
            or type(retained_inputs) is not dict
            or canonical(record) != canonical(retained_inputs)
        ):
            raise ValueError("Actual retained new request inputs differ or are missing")
        # Detach before constructing dataclasses, which contain native dicts.
        record = json.loads(canonical(record))
        profile, reading_profile = _profile(record["evidence_profile"])
        # Solely a typed structural view. Never invoke legacy.reconstruct_request
        # or the historical semantic planner to manufacture a resolved v2 plan.
        structural = {
            key: value for key, value in record.items() if key not in _EXTRA_FIELDS
        }
        structural["contract"] = legacy.CONTRACT
        arguments = legacy._arguments(structural, authoritative_snapshots)
        _validate_raw(arguments)
        if canonical(legacy.capture_inputs(**arguments)) != canonical(structural):
            raise ValueError("Native input fields differ after typed structural replay")
        request, sources = _productions(arguments, reading_profile)
        if canonical(request) != canonical(record["request_productions"]) or canonical(
            sources
        ) != canonical(record["source_productions"]):
            raise ValueError("Full captured production records do not reconstruct")
        return DecodedCapturedInputs(arguments, profile, request, sources)
    except (KeyError, TypeError, AttributeError, IndexError, RecursionError) as exc:
        raise ValueError("New staged request inputs do not reconstruct") from exc
