"""Request-local declared-source copy execution, separate from pure replay."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from dataclasses import asdict

from app.evidence_policy import source_copy_version
from app.models.query import AnswerSpan
from app.request_parser_catalog import MAX_QUESTION_CHARS
from app.services.answer_reader import reader_service
from app.services.answer_support import (
    SupportInputBudgetExceeded,
    SupportPair,
    support_service,
)
from app.services.evidence_proposals import (
    QAObservation,
    make_proposal,
    qa_raw_candidates,
)
from app.services.linguistic_source_scope import MAX_WINDOWS
from app.services.procedure_evidence import ProcedureRejected, resolve_version
from app.services.source_pattern_proposals import collect_source_proposals


class SourceWindowRejected(ValueError):
    """Valid source text exceeds the declared exact window representation."""


async def _windows(body, config, cache):
    from app.services.request_parser import capture_async

    limit = min(MAX_QUESTION_CHARS, config.REQUEST_PARSER_MAX_CHARS)
    key = hashlib.sha256(body.encode()).hexdigest(), limit
    if key not in cache:
        result = []
        cursor = 0
        while cursor < len(body):
            end = min(cursor + limit, len(body))
            if end < len(body):
                ends = [
                    m.end() for m in re.finditer(r"[.!?](?=\s|$)|\n", body[cursor:end])
                ]
                if not ends:
                    raise SourceWindowRejected(
                        "Source sentence exceeds the parser window budget"
                    )
                end = cursor + max(ends)
            text = body[cursor:end]
            if not text.strip():
                raise SourceWindowRejected("Source window contains only whitespace")
            result.append(
                {
                    "start": cursor,
                    "end": end,
                    "capture": await capture_async(text, config),
                }
            )
            if len(result) > MAX_WINDOWS:
                raise SourceWindowRejected("Source capture window budget exceeded")
            cursor = end
        cache[key] = json.dumps(result, allow_nan=False)
    return json.loads(cache[key])


async def find_procedure_witnesses(  # noqa: C901 - model/immutable-source lifecycle
    db,
    request,
    principal,
    current,
    config,
    candidates,
    inspected,
    contexts,
    validate_current,
    *,
    request_plan,
    source_window_cache,
    seeds=None,
    pattern_observations=None,
    reading_profile="contextual_source_v2",
):
    from app.services.contextual_mixed_output import procedure_obligations
    from app.services.contextual_source_proof import SourceGuardRefusal, build_envelope
    from app.services.requirement_answers import (
        Witness,
        _reader_subject_scope,
        source_identity,
    )

    if request_plan is None:
        raise RuntimeError(
            "Linguistic procedures require the captured actual request plan"
        )
    from app.evidence_policy import dependency_reading_profile, staged_reading_profile

    if not dependency_reading_profile(reading_profile):
        raise ValueError("Explicit dependency reading profile required")
    staged = staged_reading_profile(reading_profile)
    if staged:
        if reading_profile == "contextual_source_v4":
            from app.services.captured_answer_planning import (
                CapturedAnswerContext as StagedAnswerContext,
            )
        else:
            from app.services.staged_answer_planning import StagedAnswerContext

        if type(request_plan) is not StagedAnswerContext:
            raise RuntimeError("Actual staged execution context is required")
    scope = _reader_subject_scope(
        current, seeds if seeds is not None else list(inspected.values()), candidates
    )
    scope = [
        c
        for c in scope
        if not current.source_workspace
        or (c.metadata or {}).get("workspace_id") == current.source_workspace
    ]
    predictions = await reader_service.select_atomic(
        current.question, [c.content for c in scope], config=config
    )
    by_document = {}
    for member, prediction in zip(scope, predictions, strict=True):
        observed = QAObservation.capture(
            current.id,
            member,
            prediction,
            question=current.question,
            reader_identity=reader_service.metadata(config),
        )
        candidates.append(
            {
                **source_identity(member),
                "requirement_id": current.id,
                "decision": "qa_observation",
                "qa_observation": observed.record(),
            }
        )
        try:
            source = await resolve_version(db, principal, request, member, inspected)
        except ProcedureRejected as exc:
            candidates.append(
                {
                    **source_identity(member),
                    "requirement_id": current.id,
                    "decision": str(exc),
                }
            )
            continue
        entry = by_document.setdefault(
            source.identity["document_id"], {"source": source, "proposals": []}
        )
        for item in source.chunks:
            inspected[item.chunk.id] = item.chunk
        for raw in qa_raw_candidates(prediction.diagnostics):
            margin = raw.get("null_margin")
            if (
                isinstance(margin, bool)
                or not isinstance(margin, (int, float))
                or not math.isfinite(margin)
                or margin > config.READER_NULL_THRESHOLD
            ):
                continue
            proposal = make_proposal(
                current.id,
                source,
                member,
                raw["start"],
                raw["end"],
                origin="qa_reader",
                observation=observed,
            ).record()
            entry["proposals"].append((proposal, margin))
    found = []
    for entry in by_document.values():
        source = entry["source"]
        batch = collect_source_proposals(
            current, [source], reading_profile=reading_profile
        )
        candidates.extend(batch.observations)
        if pattern_observations is not None:
            pattern_observations.extend(deepcopy(batch.observations))
        if not batch.complete:
            continue
        proposals = [(p.record(), None) for p in batch.proposals] + entry["proposals"]
        unique = {}
        for proposal, margin in proposals:
            unique.setdefault(proposal["proposal_id"], (proposal, margin))
        proposals = list(unique.values())
        if not proposals:
            continue
        proposal, margin = proposals[0]
        member = next(
            c.chunk for c in source.chunks if str(c.chunk.id) == proposal["chunk_id"]
        )
        diagnostic = {
            **source_identity(member),
            "requirement_id": current.id,
            "origin": proposal["origin"],
            "proposal": proposal,
            "raw_span": proposal["chunk_range"],
            "null_margin": margin,
            "duplicate_proposals": [p for p, _ in proposals[1:]],
        }
        candidates.append(diagnostic)
        for other, other_margin in proposals[1:]:
            duplicate_member = next(
                c.chunk for c in source.chunks if str(c.chunk.id) == other["chunk_id"]
            )
            candidates.append(
                {
                    **source_identity(duplicate_member),
                    "requirement_id": current.id,
                    "origin": other["origin"],
                    "proposal": other,
                    "raw_span": other["chunk_range"],
                    "null_margin": other_margin,
                    "decision": "duplicate_complete_procedure",
                }
            )
        identity = {k: v for k, v in source.identity.items() if v is not None}
        try:
            windows = await _windows(source.body, config, source_window_cache)
            if staged:
                from app.services.staged_source_proof import (
                    build_envelope as staged_envelope,
                )

                actual = request_plan.snapshots()
                identity = {
                    key: actual[source.identity["document_id"]][key]
                    for key in (
                        "document_id",
                        "document_version",
                        "content_hash",
                        "workspace_id",
                        "snapshot_id",
                    )
                }
                envelope = staged_envelope(
                    source.body,
                    identity,
                    current.topic,
                    windows,
                    question=request.question,
                    requirement_id=current.id,
                    planning_inputs=request_plan.inputs(),
                    retained_inputs=request_plan.inputs(),
                    authoritative_snapshots=actual,
                    reading_profile=reading_profile,
                )
            else:
                envelope = build_envelope(
                    source.body,
                    identity,
                    current.topic,
                    request_plan,
                    windows,
                    source_copy_policy=source_copy_version(
                        reading_profile=reading_profile
                    ).policy,
                )
            obligations = envelope["nli_obligations"]
            required_copy = envelope.get("required_copy") if staged else None
            execution = None
            if required_copy:
                from app.services import required_copy_runtime
                from app.services.answer_support import SupportAssessment

                assessed, execution = await required_copy_runtime.assess_envelope(
                    config, envelope, current.id
                )
                from app.services.contextual_source_proof import _same, _support

                _same(
                    execution["support_metadata"],
                    _support(
                        {"evidence_support": request_plan.inputs()["support_metadata"]}
                    ),
                )
                decisions = [SupportAssessment(**row["assessment"]) for row in assessed]
            else:
                decisions = await support_service.assess(
                    [
                        SupportPair(
                            row["premise"],
                            row["hypothesis"],
                            current.id,
                            source.identity["document_id"],
                        )
                        for row in obligations
                    ],
                    config=config,
                )
            if len(decisions) != len(obligations) or not decisions:
                raise RuntimeError("Procedure support returned incomplete decisions")
            record = {
                "requirement_id": current.id,
                "source_identity": identity,
                "requested_subject": current.topic,
                "source_windows": windows,
                "envelope_inventory": envelope,
                "nli_assessments": [
                    {**row, "assessment": json.loads(json.dumps(asdict(decision)))}
                    for row, decision in zip(obligations, decisions, strict=True)
                ],
            }
            if required_copy:
                from app.services.required_copy_source import proof_from_envelope

                if execution is None:
                    raise RuntimeError(
                        "Required-copy service execution receipt missing"
                    )
                record["required_copy_execution"] = execution
                required_copy_runtime.replay_execution(
                    record,
                    json.loads(json.dumps(record)),
                    envelope,
                    execution["support_metadata"],
                    require_runtime=True,
                )
                proof = proof_from_envelope(current, source, proposal, envelope)
            else:
                proof = procedure_obligations(
                    current,
                    source,
                    proposal,
                    method="consumer_envelope",
                    consumer_inventory=envelope,
                    **({"reading_profile": reading_profile} if staged else {}),
                )
            diagnostic.update(source_guard_record=record, procedure_completeness=proof)
            supported = all(d.supported for d in decisions)
            diagnostic["decision"] = "supported" if supported else "support_rejected"
            if not supported:
                continue
            if not all([await validate_current(item.chunk) for item in source.chunks]):
                diagnostic["decision"] = "procedure_source_changed"
                continue
            await resolve_version(db, principal, request, member, inspected)
            copied_sources = [source]
            if required_copy:
                from app.services.staged_answer_planning import recheck_inputs

                copied_sources = await required_copy_runtime.current_sources(
                    db,
                    principal,
                    request,
                    required_copy,
                    request_plan.snapshots(),
                    inspected,
                    validate_current,
                )
                sql_check = await recheck_inputs(
                    db, principal, request.question, request_plan.inputs()
                )
                if (
                    type(sql_check) is not dict
                    or sql_check.get("consistent") is not True
                ):
                    diagnostic["decision"] = "required_copy_planning_read_set_changed"
                    continue
            for copied in copied_sources:
                context = {
                    **copied.identity,
                    "origin": "immutable-procedure-context",
                    "body_bytes": len(copied.body.encode()),
                    "sources": [
                        {
                            **source_identity(item.chunk),
                            "document_range": {"start": item.start, "end": item.end},
                            "score_status": (item.chunk.metadata or {}).get(
                                "score_status"
                            ),
                            "ranking_score": item.chunk.relevance_score
                            if (item.chunk.metadata or {}).get("score_status")
                            == "ranked"
                            else None,
                        }
                        for item in copied.chunks
                    ],
                }
                if context not in contexts:
                    contexts.append(context)
            chunks = {
                str(item.chunk.id): item.chunk
                for copied in copied_sources
                for item in copied.chunks
            }
            fragments = tuple(
                (
                    chunks[part["chunk_id"]],
                    AnswerSpan(
                        start=part["chunk_start"],
                        end=part["chunk_end"],
                        text=chunks[part["chunk_id"]].content[
                            part["chunk_start"] : part["chunk_end"]
                        ],
                    ),
                )
                for part in proof["fragments"]
            )
            seed_span = next(
                span
                for chunk, span in fragments
                if str(chunk.id) == proposal["chunk_id"]
            )
            found.append(
                Witness(
                    current.id,
                    member,
                    seed_span,
                    required_copy["rendered_text"]
                    if required_copy
                    else (
                        source.body[proof["extent"]["start"] : proof["extent"]["end"]]
                        if envelope.get("source_copy_policy")
                        == "ordinary_activity_quote_v2"
                        else source.body
                    ),
                    obligations[0]["hypothesis"],
                    min(d.entailment_margin for d in decisions),
                    margin,
                    (),
                    fragments,
                    proof,
                    tuple(p for p, _ in proposals),
                )
            )
        except (
            SourceGuardRefusal,
            SourceWindowRejected,
            ProcedureRejected,
            SupportInputBudgetExceeded,
        ) as exc:
            diagnostic["decision"] = str(exc)
            reference_evidence = getattr(exc, "reference_evidence", None)
            if reference_evidence is not None:
                diagnostic["reference_evidence"] = reference_evidence
    return found
