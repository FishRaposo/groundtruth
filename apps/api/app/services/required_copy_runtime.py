"""Actual support boundary and independently retained required-copy replay."""

import asyncio
import json
import uuid
from dataclasses import asdict
from typing import Literal

from app.config import Settings
from app.models.chunk import ChunkWithScore
from app.services import answer_support, planning_declarations, planning_support
from app.services import contextual_source_proof as body
from app.services.staged_planning_runtime import (
    DEFAULT_ADAPTER_LIMITS,
    RuntimeLimits,
    _retained_execution_receipts,
)

CONTRACT = "required-copy-execution-v1"


def checks(envelope, requirement_id):
    source = envelope["source_identity"]
    raw = envelope["source_body"]
    return tuple(
        planning_support.PlanningAssertion(
            body._digest(obligation),
            obligation["name"],
            "required_copy_relation",
            body._digest(obligation),
            planning_declarations.SourceIdentity(**source),
            planning_declarations.RawRange(0, len(raw), raw),
            body._json(obligation),
            planning_support.PlanningPair(
                obligation["premise"],
                obligation["hypothesis"],
                requirement_id,
                obligation.get("source_identity", source)["document_id"],
            ),
        )
        for obligation in envelope["nli_obligations"]
    )


async def assess_envelope(
    config: Settings,
    envelope,
    requirement_id,
    *,
    limits: RuntimeLimits = DEFAULT_ADAPTER_LIMITS,
    execution_capture_kind: Literal["runtime_capture", "UNITONLY"] = "runtime_capture",
):
    """No producer observation/await intervenes before detached service receipts."""
    if type(limits) is not RuntimeLimits:
        raise ValueError("Typed required-copy runtime limits required")
    assertions = checks(envelope, requirement_id)
    if not assertions or len(assertions) > limits.max_pairs:
        raise ValueError("Required-copy mandatory pair budget exceeded; no truncation")
    selected = config.model_copy(deep=True)
    before_raw = json.loads(
        body._json(answer_support.support_service.metadata(selected))
    )
    before = body._support({"evidence_support": before_raw})
    pairs = tuple(answer_support.SupportPair(**asdict(a.pair)) for a in assertions)
    async with asyncio.timeout(limits.inference_timeout_seconds):
        decisions = await answer_support.support_service.assess(list(pairs), selected)
    after_raw = json.loads(
        body._json(answer_support.support_service.metadata(selected))
    )
    after = body._support({"evidence_support": after_raw})
    executions = _retained_execution_receipts(
        assertions, pairs, decisions, body._json(after), execution_capture_kind
    )
    body._same(before, after)
    rows = [
        {**obligation, "assessment": json.loads(execution.assessment_json)}
        for obligation, execution in zip(
            envelope["nli_obligations"], executions, strict=True
        )
    ]
    receipt = {
        "contract": CONTRACT,
        "support_metadata": after,
        "service_metadata_before": before_raw,
        "service_metadata_after": after_raw,
        "executions": [asdict(row) for row in executions],
    }
    # Numeric authority is the existing source assessment validator; there is
    # no new formula or invented model support for an exact literal copy.
    for row in rows:
        body._assessment(row["assessment"], after)
    return rows, json.loads(body._json(receipt))


def replay_execution(record, retained_record, envelope, support, *, require_runtime):
    """Require a separate actual trace channel plus complete exact pair replay."""
    receipt = record["required_copy_execution"]
    if type(receipt) is not dict or set(receipt) != {
        "contract",
        "support_metadata",
        "service_metadata_before",
        "service_metadata_after",
        "executions",
    }:
        raise body.SourceGuardError("Required-copy execution schema differs")
    body._same(receipt, retained_record["required_copy_execution"])
    body._same(receipt["contract"], CONTRACT)
    body._same(receipt["support_metadata"], support)
    for raw in (receipt["service_metadata_before"], receipt["service_metadata_after"]):
        body._same(body._support({"evidence_support": raw}), support)
    expected = checks(envelope, record["requirement_id"])
    rows = receipt["executions"]
    body._same(len(rows), len(expected))
    assessments = body._assessments(record, envelope, support)
    seen = set()
    for actual, check, observed in zip(rows, expected, assessments, strict=True):
        execution = planning_support.NliExecution(
            **{**actual, "pair": planning_support.PlanningPair(**actual["pair"])}
        )
        if not execution.execution_id or execution.execution_id in seen:
            raise body.SourceGuardError(
                "Unique actual required-copy execution required"
            )
        seen.add(execution.execution_id)
        if execution.capture_kind not in {"runtime_capture", "UNITONLY"} or (
            require_runtime and execution.capture_kind != "runtime_capture"
        ):
            raise body.SourceGuardError(
                "Required-copy production requires runtime execution"
            )
        body._same(execution.assertion_id, check.id)
        body._same(asdict(execution.pair), asdict(check.pair))
        body._same(execution.support_metadata_json, body._json(support))
        body._same(execution.assessment_json, body._json(observed["assessment"]))
        body._same(execution.pair_tokens, observed["assessment"]["pair_tokens"])
    return assessments


async def current_sources(
    db, principal, request, required, snapshots, inspected, validate_current
):
    """Use the actual SQL/current-source resolver for every copied document."""
    from app.services.procedure_evidence import resolve_version

    sources = []
    for document in required["documents"]:
        sid = document["identity"]["document_id"]
        snapshot = snapshots[sid]
        raw = snapshot["chunks"][0]
        identifier = uuid.UUID(raw["id"])
        metadata = {
            **raw["metadata"],
            **snapshot["metadata"],
            **document["identity"],
            "score_status": "not_ranked",
            "ranking_score": None,
        }
        seed = inspected.get(identifier) or ChunkWithScore(
            id=identifier,
            document_id=uuid.UUID(sid),
            content=raw["content"],
            chunk_index=raw["index"],
            relevance_score=0.0,
            metadata=metadata,
        )
        source = await resolve_version(db, principal, request, seed, inspected)
        body._same(source.body, snapshot["body"])
        for key, value in source.identity.items():
            body._same(value, document["identity"][key])
        expected_ids = [c["id"] for c in snapshot["chunks"]]
        body._same([str(c.chunk.id) for c in source.chunks], expected_ids)
        if not all([await validate_current(c.chunk) for c in source.chunks]):
            raise body.SourceGuardRefusal("Required-copy current source changed")
        for chunk in source.chunks:
            inspected[chunk.chunk.id] = chunk.chunk
        sources.append(source)
    return sources
