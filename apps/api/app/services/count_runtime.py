"""Immutable count fields before NLI; model-free reconstruction before publication.

The parser proposes syntax, never facts. Exact field binding rejects wrong units
even when the separately mandatory classifier assigns a positive score.
"""

from copy import deepcopy

from app.services.literal_quantity import (
    QuantityUnresolved,
    consume_quantity_candidate,
    produce_quantity_candidate,
)

CONTRACT = "source-bound-count-capture-v1"


def _options(source, member, raw):
    matches = [part for part in source.chunks if part.chunk.id == member.id]
    if len(matches) != 1:
        raise ValueError("Count chunk has no unique immutable source mapping")
    return {
        "source_identity": source.identity,
        "chunk_content": member.content,
        "chunk_start": matches[0].start,
        "raw_start": raw["start"],
        "raw_end": raw["end"],
    }


async def capture_count(
    requirement,
    source,
    member,
    raw,
    config,
    *,
    evidence_profile=None,
    request_plan=None,
):
    from app.evidence_policy import resolve_evidence_policy
    from app.services.literal_quantity import _typed_capture, _typed_mode
    from app.services.request_parser import capture_async

    profile = (
        resolve_evidence_policy(config).record()
        if evidence_profile is None
        else evidence_profile
    )
    if requirement.relation != "count" and _typed_mode(profile):
        _, request_capture, source_capture, _ = _typed_capture(
            requirement, source.body, source.identity, profile, request_plan, None, None
        )
        claim, binding = produce_quantity_candidate(
            requirement,
            source.body,
            **_options(source, member, raw),
            request_capture=request_capture,
            source_capture=source_capture,
            evidence_profile=profile,
            request_plan=request_plan,
        )
        return claim, {
            "contract": CONTRACT,
            "request_capture": deepcopy(request_capture),
            "source_capture": deepcopy(source_capture),
            "binding": binding,
        }

    # Reject unsupported relation/field/units before spending parser or NLI work.
    # Only an explicitly unresolved noun alignment may ask the parser for syntax.
    try:
        produce_quantity_candidate(
            requirement, source.body, **_options(source, member, raw)
        )
    except QuantityUnresolved as exc:
        if str(exc) != "differing_noun_form_requires_actual_capture":
            raise
    request_capture = await capture_async(requirement.question, config)
    source_capture = await capture_async(source.body, config)
    claim, binding = produce_quantity_candidate(
        requirement,
        source.body,
        **_options(source, member, raw),
        request_capture=request_capture,
        source_capture=source_capture,
    )
    return claim, {
        "contract": CONTRACT,
        "request_capture": deepcopy(request_capture),
        "source_capture": deepcopy(source_capture),
        "binding": binding,
    }


def reconstruct_count(
    record,
    requirement,
    source,
    member,
    raw,
    *,
    evidence_profile=None,
    request_plan=None,
):
    if (
        type(record) is not dict
        or set(record) != {"contract", "request_capture", "source_capture", "binding"}
        or record["contract"] != CONTRACT
    ):
        raise ValueError("Source-bound count capture schema invalid")
    claim, binding = consume_quantity_candidate(
        record["binding"],
        requirement,
        source.body,
        **_options(source, member, raw),
        request_capture=record["request_capture"],
        source_capture=record["source_capture"],
        evidence_profile=evidence_profile,
        request_plan=request_plan,
    )
    return claim, {**deepcopy(record), "binding": binding}


def count_identity(record):
    """Only call after capture/reconstruction against the actual source/request."""
    return record["binding"]["value_identity"]
