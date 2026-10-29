"""Request-local complete evidence selection; model scores never grant authority."""

from __future__ import annotations

import json
import math
import re
import uuid
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from functools import partial
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.evidence_policy import EvidencePolicy, resolve_evidence_policy
from app.models.chunk import ChunkWithScore
from app.models.query import AnswerSpan, QueryRequest
from app.services.access_control.scope import Principal
from app.services.answer_reader import reader_service
from app.services.answer_requirements import (
    Requirement,
    owner_relative_alternatives,
    plan_requirements,
    resolve_requirement,
)
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
from app.services.linguistic_dependencies import (
    resolve_linguistic_requirement as resolve_linguistic_requirement,
)
from app.services.requirement_binding import (
    condition_relation,
    relation_present,
    role_argument_identity,
    support_claim,
)
from app.services.requirement_conflict_scope import source_relation_scope
from app.services.requirement_contract import (
    CURRENT_CONTRACT,
    PROCEDURE_CONTRACT,
    PROCEDURE_COPY_CONTRACT,
)
from app.services.retrieval.scoped import inspect_curated_group, retrieve_scoped
from app.services.source_pattern_proposals import collect_source_proposals

CONTRACT = CURRENT_CONTRACT


def witness_value_identity(
    requirement: Requirement,
    value: str,
    *,
    reading_profile: str = "clause_bound_v1",
    quantity_binding=None,
) -> str:
    """Existing literal conflict identity, including the legacy role exception."""
    if quantity_binding is not None:
        from app.services.count_runtime import count_identity

        return count_identity(quantity_binding)
    if reading_profile != "clause_bound_v1":
        from app.evidence_policy import reading_version
        from app.services.contextual_values import contextual_value_identity

        reading_version(reading_profile)
        return contextual_value_identity(requirement, value)
    return (
        role_argument_identity(value)
        if requirement.kind in {"owner", "deputy"}
        else value
    )


@dataclass(frozen=True)
class Witness:
    requirement: str
    chunk: ChunkWithScore
    span: AnswerSpan
    value: str
    hypothesis: str
    margin: float
    null_margin: float | None
    proof_edges: tuple[Any, ...] = ()
    fragments: tuple[tuple[ChunkWithScore, AnswerSpan], ...] = ()
    completeness: dict[str, Any] | None = None
    proposals: tuple[dict[str, Any], ...] = ()
    quantity_binding: dict[str, Any] | None = None
    typed_role_descriptor: dict | None = None


@dataclass(frozen=True)
class RequirementAnswer:
    chunks: tuple[ChunkWithScore, ...]
    spans: dict[uuid.UUID, AnswerSpan]
    requirements: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    inspected_sources: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    followups: list[dict[str, Any]]
    reason: str | None
    passages: dict[uuid.UUID, tuple[AnswerSpan, ...]] = field(default_factory=dict)
    procedure_contexts: list[dict[str, Any]] = field(default_factory=list)
    procedure_groups: tuple[dict[str, Any], ...] = ()
    procedure_read_set: dict[str, Any] = field(default_factory=dict)
    evidence_profile: dict[str, Any] = field(default_factory=dict)
    proposals: tuple[dict[str, Any], ...] = ()
    qa_observations: tuple[dict[str, Any], ...] = ()
    pattern_observations: tuple[dict[str, Any], ...] = ()
    selected_proposal_ids: tuple[str, ...] = ()
    role_scope_read_set: dict[str, Any] = field(default_factory=dict)
    role_scope_interpretations: tuple[dict[str, Any], ...] = ()
    role_scope_findings: tuple[dict[str, Any], ...] = ()
    request_plan: dict[str, Any] = field(default_factory=dict)
    request_capture: dict[str, Any] = field(default_factory=dict)
    source_guard_records: tuple[dict[str, Any], ...] = ()
    staged_request_inputs: dict[str, Any] = field(default_factory=dict)
    staged_execution_capture_json: str = ""


def source_identity(chunk: ChunkWithScore) -> dict[str, Any]:
    metadata = chunk.metadata or {}
    return {
        "chunk_id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "document_version": metadata.get("document_version"),
        "content_hash": metadata.get("content_hash"),
    }


def _raw_predictions(prediction: Any) -> list[dict[str, Any]]:
    return qa_raw_candidates(prediction.diagnostics)


def _cover(witnesses: list[Witness], requirement_ids: list[str]) -> list[Witness]:
    """Exact bounded bit-mask cover; no citation truncation after selection."""
    required = {identifier: 1 << i for i, identifier in enumerate(requirement_ids)}
    by_document: dict[uuid.UUID, list[Witness]] = {}
    for witness in witnesses:
        by_document.setdefault(witness.chunk.document_id, []).append(witness)
    states: dict[int, tuple[uuid.UUID, ...]] = {0: ()}
    for identifier, entries in by_document.items():
        mask = 0
        for witness in entries:
            mask |= required[witness.requirement]
        for old_mask, group in list(states.items()):
            new_group = (*group, identifier)
            if len(new_group) > 8:
                continue
            combined = old_mask | mask
            previous = states.get(combined)
            if previous is None or len(new_group) < len(previous):
                states[combined] = new_group
    identifiers = states.get((1 << len(requirement_ids)) - 1, ())
    if not identifiers:
        return []
    return [w for identifier in identifiers for w in by_document[identifier]]


def _literal_source_range(
    text: Any, content: str, start: Any = None, end: Any = None
) -> dict[str, int] | None:
    if not isinstance(text, str) or not text:
        return None
    if start is not None or end is not None:
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(content)
            or content[start:end] != text
        ):
            return None
        return {"start": start, "end": end}
    first = content.find(text)
    if first < 0 or content.find(text, first + 1) >= 0:
        return None
    return {"start": first, "end": first + len(text)}


def _check_range(check: Any, content: str) -> dict[str, int] | None:
    return _literal_source_range(
        check.premise,
        content,
        getattr(check, "start", None),
        getattr(check, "end", None),
    )


def _primary_range(claim: Any, content: str) -> dict[str, int] | None:
    return _literal_source_range(
        claim.premise,
        content,
        getattr(claim, "premise_start", None),
        getattr(claim, "premise_end", None),
    )


def _valid_check(check: Any, content: str) -> bool:
    return (
        isinstance(check.name, str)
        and bool(check.name)
        and isinstance(check.hypothesis, str)
        and bool(check.hypothesis)
        and _check_range(check, content) is not None
    )


def _claim_source_error(claim: Any, content: str) -> str | None:
    if (
        type(claim.start) is not int
        or type(claim.end) is not int
        or not 0 <= claim.start < claim.end <= len(content)
        or content[claim.start : claim.end] != claim.value
    ):
        return "invalid_bound_answer"
    checks = getattr(claim, "checks", ())
    if not isinstance(checks, tuple) or len(checks) > 8:
        return "condition_proof_budget_exceeded"
    elif any(not _valid_check(check, content) for check in checks):
        return "support_check_not_source_bound"
    if _primary_range(claim, content) is None:
        return "support_premise_not_source_bound"
    return None


def _edge_record(edge: Any) -> dict[str, Any]:
    return {
        "name": edge.name,
        "source_range": {"start": edge.source_start, "end": edge.source_end},
        "target_range": {"start": edge.target_start, "end": edge.target_end},
        "requirement_id": edge.requirement_id,
        "depends_on": list(edge.depends_on),
    }


def _raw_context_verified(claim: Any, content: str, raw: dict[str, Any]) -> bool:
    """Normalization cannot hide part of the model's accepted source context."""
    start, end = raw.get("start"), raw.get("end")
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(content)
    ):
        return False
    ranges = [_primary_range(claim, content)]
    ranges.extend(
        _check_range(check, content) for check in getattr(claim, "checks", ())
    )
    return any(
        scope is not None and scope["start"] <= start < end <= scope["end"]
        for scope in ranges
    )


def _edge_kind_valid(edge: Any, current: Requirement) -> bool:
    if edge.name == "operation_antecedent_to_deputy":
        return (
            current.kind == "deputy"
            and current.relation == "deputy"
            and not current.depends_on
        )
    if edge.name in {
        "worksheet_namespace_to_applicability",
        "worksheet_applicability_to_instructions",
    }:
        return current.kind == "procedure"
    if edge.name == "worksheet_namespace_to_prohibition":
        return current.kind in {"procedure", "prohibition"}
    return (
        edge.name == "scoped_deputy_to_permission"
        and current.kind == "availability"
        and current.relation == "cover_window"
        and len(current.depends_on) == 1
    )


def _edge_range_valid(edge: Any, content: str, ranges: list[dict[str, int]]) -> bool:
    points = (edge.source_start, edge.source_end, edge.target_start, edge.target_end)
    if not all(type(point) is int for point in points):
        return False
    if not 0 <= points[0] < points[1] <= points[2] < points[3] <= len(content):
        return False
    return all(
        any(r["start"] <= start < end <= r["end"] for r in ranges)
        for start, end in ((points[0], points[1]), (points[2], points[3]))
    )


def _claim_edges_error(claim: Any, current: Requirement, content: str) -> str | None:
    edges = getattr(claim, "proof_edges", ())
    if not isinstance(edges, tuple) or len(edges) > 8:
        return "proof_edge_budget_or_shape_invalid"
    primary = _primary_range(claim, content)
    ranges = [primary] if primary is not None else []
    ranges.extend(
        r
        for check in getattr(claim, "checks", ())
        if (r := _check_range(check, content)) is not None
    )
    for edge in edges:
        try:
            if (
                edge.requirement_id != current.id
                or edge.depends_on != current.depends_on
                or not _edge_kind_valid(edge, current)
                or not _edge_range_valid(edge, content, ranges)
                or not _edge_checks_valid(edge, claim, content)
            ):
                return "proof_edge_not_bound_to_requirement"
        except (AttributeError, TypeError, ValueError):
            return "proof_edge_not_bound_to_requirement"
    return None


def _edge_checks_valid(edge: Any, claim: Any, content: str) -> bool:
    """A broad primary premise cannot impersonate separate mandatory checks."""
    checks = getattr(claim, "checks", ())

    def checked(name: str, start: int, end: int) -> bool:
        matching = [check for check in checks if check.name == name]
        return len(matching) == 1 and _check_range(matching[0], content) == {
            "start": start,
            "end": end,
        }

    if edge.name == "operation_antecedent_to_deputy":
        return checked(
            "operation_owner_antecedent", edge.source_start, edge.source_end
        ) and checked("operation_deputy_assignment", edge.target_start, edge.target_end)

    if edge.name == "worksheet_namespace_to_applicability":
        return checked(
            "procedure_namespace", edge.source_start, edge.source_end
        ) and checked("procedure_applicability", edge.target_start, edge.target_end)
    if edge.name == "worksheet_applicability_to_instructions":
        primary = _primary_range(claim, content)
        return (
            checked("procedure_applicability", edge.source_start, edge.source_end)
            and primary is not None
            and primary["start"]
            <= edge.target_start
            < edge.target_end
            == primary["end"]
        )
    if edge.name == "worksheet_namespace_to_prohibition":
        matching = [
            check
            for check in checks
            if re.fullmatch(r"procedure_prohibition_[1-8]", check.name)
            and (scope := _check_range(check, content)) is not None
            and scope["start"] == edge.target_start
            and scope["end"] >= edge.target_end
        ]
        return (
            checked("procedure_namespace", edge.source_start, edge.source_end)
            and len(matching) == 1
        )
    # The scoped deputy edge additionally depends on a verified originating
    # requirement; select_requirement_answer resolves and pins that witness.
    return edge.name == "scoped_deputy_to_permission"


def _eligible_candidates(
    current,
    scope_chunks,
    predictions,
    config,
    candidates,
    role_target=None,
    *,
    policy=None,
    request_plan=None,
):
    policy = policy or resolve_evidence_policy(config)
    pending = []
    for chunk, prediction in zip(scope_chunks, predictions, strict=True):
        if prediction.span is None and not _raw_predictions(prediction):
            candidates.append(
                {
                    **source_identity(chunk),
                    "requirement_id": current.id,
                    "decision": "qa_no_answer",
                }
            )
            continue
        if (
            current.source_workspace
            and (chunk.metadata or {}).get("workspace_id") != current.source_workspace
        ):
            candidates.append(
                {
                    **source_identity(chunk),
                    "requirement_id": current.id,
                    "decision": "requested_workspace_mismatch",
                }
            )
            continue
        for raw in _raw_predictions(prediction):
            margin = raw.get("null_margin")
            if (
                isinstance(margin, bool)
                or not isinstance(margin, (int, float))
                or not math.isfinite(margin)
                or margin > config.READER_NULL_THRESHOLD
            ):
                continue
            bound = _bind_candidate(
                current,
                chunk,
                raw,
                margin,
                candidates,
                role_target=role_target,
                reading_profile=policy.evidence_reading_profile,
                policy=policy,
                request_plan=request_plan,
            )
            if bound is not None:
                pending.append(bound)
    return pending


def _bind_candidate(
    current,
    chunk,
    raw,
    margin,
    candidates,
    proposal=None,
    role_target=None,
    *,
    reading_profile="clause_bound_v1",
    policy=None,
    request_plan=None,
):
    from app.services.linguistic_property_cover import factual_claim, requirement_bound

    if requirement_bound(policy):
        claim = factual_claim(
            current,
            chunk.content,
            raw["start"],
            raw["end"],
            policy=policy,
            plan=request_plan,
        )
    elif reading_profile == "clause_bound_v1":
        # Preserve existing injectable library adapters' four-argument call.
        claim = support_claim(current, chunk.content, raw["start"], raw["end"])
    else:
        claim = support_claim(
            current,
            chunk.content,
            raw["start"],
            raw["end"],
            reading_profile=reading_profile,
        )
    from app.services.role_scope_policy import activity_role_candidate_scope

    activity_scope = activity_role_candidate_scope(
        current,
        chunk.content,
        raw["start"],
        raw["end"],
        chunk.metadata or {},
        policy=policy,
        request_plan=request_plan,
    )
    relation = (
        activity_scope[0]
        if activity_scope is not None
        else condition_relation(current, chunk.content, chunk.metadata or {})
    )
    rejection = claim.rejection or (
        "source_condition_not_established" if relation != "applies" else None
    )
    from app.services.role_scope_policy import (
        literal_role_candidate_matches,
        session_role_scope,
    )

    target = role_target or session_role_scope(current)
    literal_match = (
        activity_scope[1]
        if activity_scope is not None
        else (
            target is None
            or literal_role_candidate_matches(
                current, chunk.content, raw["start"], raw["end"], target
            )
        )
    )
    if target is not None and not literal_match:
        rejection = rejection or "role_session_or_activity_scope_unverified"
    rejection = rejection or _claim_source_error(claim, chunk.content)
    if rejection is None and not _raw_context_verified(claim, chunk.content, raw):
        rejection = "raw_context_not_verified"
    rejection = rejection or _claim_edges_error(claim, current, chunk.content)
    diagnostic = {
        **source_identity(chunk),
        "requirement_id": current.id,
        "raw_span": {"start": raw["start"], "end": raw["end"]},
        "null_margin": margin,
        "hypothesis": claim.hypothesis,
        "validated_answer_span": {
            "start": claim.start,
            "end": claim.end,
            "text": claim.value,
        },
        "condition": relation,
        "decision": rejection or "support_pending",
        "primary_support_range": _primary_range(claim, chunk.content),
        "proof_edges": []
        if rejection
        else [_edge_record(edge) for edge in getattr(claim, "proof_edges", ())],
    }
    if proposal is not None:
        diagnostic.update(proposal=proposal, origin=proposal["origin"])
    candidates.append(diagnostic)
    if rejection or claim.hypothesis is None:
        return None
    return chunk, claim, margin, diagnostic


def _reader_subject_scope(
    current: Requirement,
    chunks: list[ChunkWithScore],
    candidates: list[dict[str, Any]],
) -> list[ChunkWithScore]:
    # The later binder already requires every named anchor in a nondependent
    # source context. No missing-anchor context can become a valid witness.
    # Keep dependent role-only pages and unnamed questions deliberately broad.
    if current.depends_on or not current.anchors:
        return chunks
    eligible = []
    for chunk in chunks:
        words = set(re.findall(r"\w[\w-]*", chunk.content.casefold()))
        if not set(current.anchors).isdisjoint(words):
            eligible.append(chunk)
        else:
            candidates.append(
                {
                    **source_identity(chunk),
                    "requirement_id": current.id,
                    "decision": "reader_not_queried_subject_scope",
                    "model_queried": False,
                }
            )
    return eligible


async def _find_witnesses(  # noqa: C901 - common strict proof gate for both origins
    current: Requirement,
    scope_chunks: list[ChunkWithScore],
    config: Settings,
    candidates: list[dict[str, Any]],
    *,
    policy: EvidencePolicy | None = None,
    resolve_source=None,
    role_target: str | None = None,
    pattern_observations=None,
    request_plan=None,
) -> list[Witness]:
    policy = policy or resolve_evidence_policy(config)
    scope_chunks = _reader_subject_scope(current, scope_chunks, candidates)
    reader_identity = reader_service.metadata(config)
    predictions = await reader_service.select_atomic(
        current.question, [c.content for c in scope_chunks], config=config
    )
    pending = _eligible_candidates(
        current,
        scope_chunks,
        predictions,
        config,
        candidates,
        role_target,
        policy=policy,
        request_plan=request_plan,
    )
    observations = []
    for member, prediction in zip(scope_chunks, predictions, strict=True):
        observation = QAObservation.capture(
            current.id,
            member,
            prediction,
            question=current.question,
            reader_identity=reader_identity,
        )
        observations.append(observation)
        candidates.append(
            {
                **source_identity(member),
                "requirement_id": current.id,
                "decision": "qa_observation",
                "qa_observation": observation.record(),
            }
        )
    from app.services.procedure_evidence import ProcedureRejected, single_chunk_source

    sources = []
    if policy.source_patterns:
        for member in scope_chunks:
            try:
                source = (
                    await resolve_source(member)
                    if resolve_source
                    else single_chunk_source(member)
                )
                sources.append(source)
            except (ValueError, ProcedureRejected) as exc:
                candidates.append(
                    {
                        **source_identity(member),
                        "requirement_id": current.id,
                        "origin": "source_pattern",
                        "decision": str(exc),
                        "complete": False,
                    }
                )
                return []
        batch = collect_source_proposals(
            current,
            sources,
            **(
                {"reading_profile": policy.evidence_reading_profile}
                if policy.dependency_reading
                else {}
            ),
        )
        candidates.extend(batch.observations)
        if pattern_observations is not None:
            pattern_observations.extend(deepcopy(batch.observations))
        if not batch.complete:
            return []
        by_chunk = {
            item.chunk.id: item.chunk for source in sources for item in source.chunks
        }
        for proposal in batch.proposals:
            member = by_chunk[uuid.UUID(proposal.chunk_id)]
            raw = {"start": proposal.chunk_start, "end": proposal.chunk_end}
            bound = _bind_candidate(
                current,
                member,
                raw,
                None,
                candidates,
                proposal.record(),
                role_target,
                reading_profile=policy.evidence_reading_profile,
                policy=policy,
                request_plan=request_plan,
            )
            if bound is not None:
                bound[3]["proposal"] = proposal.record()
                pending.append(bound)
    for member, _claim, margin, diagnostic in pending:
        if margin is None:
            continue
        observation = next(
            item for item in observations if item.chunk_id == str(member.id)
        )
        try:
            source = next(
                (
                    source
                    for source in sources
                    if any(item.chunk.id == member.id for item in source.chunks)
                ),
                None,
            )
            if source is None:
                source = (
                    await resolve_source(member)
                    if resolve_source
                    else single_chunk_source(member)
                )
            raw = diagnostic["raw_span"]
            diagnostic["proposal"] = make_proposal(
                current.id,
                source,
                member,
                raw["start"],
                raw["end"],
                origin="qa_reader",
                observation=observation,
            ).record()
            if policy.contextual_source:
                diagnostic["origin"] = "qa_reader"
        except (ValueError, ProcedureRejected) as exc:
            # QA-only legacy direct callers lack an immutable source resolver.
            # Connected callers provide it; source patterns always fail closed above.
            if policy.source_patterns or resolve_source is not None:
                diagnostic["decision"] = str(exc)
                return []
    # Literal duplicates share proof, retaining both discovery origins.
    unique = {}
    for member, claim, margin, diagnostic in pending:
        key = (member.id, claim.start, claim.end, claim.hypothesis)
        proposal = diagnostic.get("proposal")
        if key in unique:
            kept = unique[key][3]
            kept.setdefault("duplicate_proposals", []).append(proposal)
            diagnostic["decision"] = "duplicate_literal_proposal"
        else:
            unique[key] = (member, claim, margin, diagnostic)
    pending = list(unique.values())
    if policy.source_bound_counts and current.kind == "quantity":
        from app.services.count_runtime import capture_count
        from app.services.literal_quantity import QuantityUnresolved

        bound_counts = []
        for member, claim, margin, diagnostic in pending:
            source = next(
                source
                for source in sources
                if any(part.chunk.id == member.id for part in source.chunks)
            )
            try:
                bound_claim, proof = await capture_count(
                    current,
                    source,
                    member,
                    diagnostic["raw_span"],
                    config,
                    evidence_profile=policy.record(),
                    request_plan=request_plan,
                )
            except QuantityUnresolved as exc:
                diagnostic["decision"] = str(exc)
                continue
            if asdict(bound_claim) != asdict(claim):
                diagnostic["decision"] = "source_bound_count_claim_differs"
                continue
            diagnostic["quantity_binding"] = proof
            bound_counts.append((member, claim, margin, diagnostic))
        pending = bound_counts
    if policy.dependency_reading:
        from app.services.linguistic_property_cover import property_cover_error

        covered = []
        for member, claim, margin, diagnostic in pending:
            source = next(
                source
                for source in sources
                if any(part.chunk.id == member.id for part in source.chunks)
            )
            error = property_cover_error(
                current, source, member, diagnostic["raw_span"], claim
            )
            if error:
                diagnostic["decision"] = error
            else:
                covered.append((member, claim, margin, diagnostic))
        pending = covered
    pairs = []
    sizes = []
    linguistic = policy.dependency_reading
    context_pending = []
    for chunk, claim, _, diagnostic in pending:
        context_record = None
        if linguistic:
            from app.services.linguistic_property_cover import (
                FactContextUnresolved,
                factual_support_context,
            )

            source = next(
                source
                for source in sources
                if any(item.chunk.id == chunk.id for item in source.chunks)
            )
            try:
                context_key, context_record = factual_support_context(
                    current,
                    source,
                    chunk,
                    diagnostic["raw_span"],
                    claim,
                    policy=policy,
                    plan=request_plan,
                )
            except FactContextUnresolved as exc:
                diagnostic["decision"] = str(exc)
                continue
            diagnostic[context_key] = context_record
        context_pending.append((chunk, claim, _, diagnostic))
        checks = getattr(claim, "checks", ())
        pairs.append(
            SupportPair(claim.premise, claim.hypothesis, current.id, str(chunk.id))
        )
        pairs.extend(
            SupportPair(check.premise, check.hypothesis, current.id, str(chunk.id))
            for check in checks
        )
        if context_record is not None:
            pairs.append(
                SupportPair(
                    context_record["premise"],
                    claim.hypothesis,
                    current.id,
                    str(chunk.id),
                )
            )
        sizes.append(1 + len(checks) + int(linguistic))
    pending = context_pending
    assessments = await support_service.assess(pairs, config=config) if pairs else []
    if len(assessments) != len(pairs):
        raise RuntimeError("Support classifier returned incomplete decisions")
    found = []
    cursor = 0
    for (chunk, claim, null_margin, diagnostic), size in zip(
        pending, sizes, strict=True
    ):
        decisions = assessments[cursor : cursor + size]
        cursor += size
        assessment = decisions[0]
        local_decisions = decisions[:-1] if linguistic else decisions
        if linguistic:
            from app.services.linguistic_property_cover import requirement_bound

            context_key = (
                "fact_context_support"
                if requirement_bound(policy)
                else "whole_source_support"
            )
            diagnostic[context_key]["assessment"] = asdict(decisions[-1])
        diagnostic["support"] = asdict(assessment)
        diagnostic["support_checks"] = [
            {
                "name": check.name,
                "hypothesis": check.hypothesis,
                "source_range": _check_range(check, chunk.content),
                **asdict(decision),
            }
            for check, decision in zip(
                getattr(claim, "checks", ()), local_decisions[1:], strict=True
            )
        ]
        supported = all(decision.supported for decision in decisions)
        diagnostic["decision"] = "supported" if supported else "support_rejected"
        if supported:
            support_start = getattr(claim, "support_start", None)
            support_end = getattr(claim, "support_end", None)
            if (
                support_start is None
                or support_end is None
                or not 0 <= support_start < support_end <= len(chunk.content)
            ):
                diagnostic["decision"] = "supporting_clause_offsets_missing"
                continue
            span = AnswerSpan(
                start=support_start,
                end=support_end,
                text=chunk.content[support_start:support_end],
            )
            found.append(
                Witness(
                    current.id,
                    chunk,
                    span,
                    claim.value,
                    claim.hypothesis,
                    assessment.entailment_margin,
                    null_margin,
                    getattr(claim, "proof_edges", ()),
                    proposals=tuple(
                        p
                        for p in (
                            diagnostic.get("proposal"),
                            *diagnostic.get("duplicate_proposals", ()),
                        )
                        if p
                    ),
                    quantity_binding=diagnostic.get("quantity_binding"),
                )
            )
    return found


def _selected_passages(
    selected: list[Witness],
) -> dict[uuid.UUID, tuple[AnswerSpan, ...]]:
    by_chunk: dict[uuid.UUID, list[Witness]] = {}
    for witness in selected:
        for chunk, span in witness.fragments or ((witness.chunk, witness.span),):
            by_chunk.setdefault(chunk.id, []).append(
                Witness(
                    witness.requirement,
                    chunk,
                    span,
                    witness.value,
                    witness.hypothesis,
                    witness.margin,
                    witness.null_margin,
                )
            )
    result = {}
    for identifier, entries in by_chunk.items():
        merged: list[AnswerSpan] = []
        for witness in sorted(
            entries, key=lambda item: (item.span.start, item.span.end)
        ):
            span = witness.span
            adjacent = bool(
                merged
                and re.fullmatch(
                    r"[\s,;]*(?:(?:and|but|whereas|while)\s*)?",
                    witness.chunk.content[merged[-1].end : span.start],
                    re.I,
                )
            )
            if merged and (span.start <= merged[-1].end or adjacent):
                previous = merged.pop()
                end = max(previous.end, span.end)
                span = AnswerSpan(
                    start=previous.start,
                    end=end,
                    text=witness.chunk.content[previous.start : end],
                )
            merged.append(span)
        result[identifier] = tuple(merged)
    return result


def _curated_subject_scope(
    current: Requirement,
    applicable: list[ChunkWithScore],
    witnesses: list[Witness],
) -> tuple[list[ChunkWithScore], list[Witness], list[str]]:
    from app.services.curated_conflict_proof import subject_scope

    return subject_scope(current, applicable, witnesses)


def _complete_fact_agreement(
    members: list[ChunkWithScore], witnesses: list[Witness]
) -> bool:
    """Agreement needs a validated identical fact on every applicable member.

    A missing QA witness can never erase a known opposing member. This proves
    only the requested fact; other instructions in the group may still differ.
    """
    from app.services.curated_conflict_proof import complete_fact_agreement

    return complete_fact_agreement(members, witnesses)


async def _inspect_conflicts(  # noqa: C901 - retain scoped complete opponent inspection
    db: AsyncSession,
    request: QueryRequest,
    principal: Principal,
    inspected: dict[uuid.UUID, ChunkWithScore],
    requirements: tuple[Requirement, ...],
    resolved: dict[str, Requirement],
    by_requirement: dict[str, list[Witness]],
    config: Settings,
    validate_current: Callable[[ChunkWithScore], Awaitable[bool]],
    procedure_contexts: list[dict[str, Any]] | None = None,
    role_scope_findings: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    conflicts = []
    factual_source_window_cache = {}
    groups: dict[str, list[ChunkWithScore]] = {}
    for chunk in inspected.values():
        group = (chunk.metadata or {}).get("conflict_group")
        if isinstance(group, str) and group:
            groups.setdefault(group, []).append(chunk)
    conflict_found = False
    for group, members in groups.items():
        additional, truncated = await inspect_curated_group(
            db,
            group,
            principal=principal,
            document_ids=request.document_ids,
            collection_ids=request.collection_ids,
        )
        known = {member.id: member for member in members}
        for member in additional:
            if await validate_current(member):
                known[member.id] = member
            elif resolve_evidence_policy(config).dependency_reading:
                truncated = True
        members = list(known.values())
        for member in members:
            inspected[member.id] = member
        for requirement in requirements:
            current = resolved.get(requirement.id)
            if current is None:
                continue
            if current.kind == "procedure":
                record = await _inspect_procedure_group(
                    db,
                    request,
                    principal,
                    current,
                    config,
                    members,
                    truncated,
                    by_requirement.get(current.id, []),
                    inspected,
                    procedure_contexts if procedure_contexts is not None else [],
                )
                record["group"] = group
                conflicts.append(record)
                conflict_found = conflict_found or record["relevant"]
                continue
            if resolve_evidence_policy(config).dependency_reading:
                from app.services.linguistic_conflicts import inspect_fact_group

                record = await inspect_fact_group(
                    db,
                    request,
                    principal,
                    current,
                    config,
                    members,
                    truncated,
                    by_requirement.get(current.id, []),
                    inspected,
                    procedure_contexts if procedure_contexts is not None else [],
                    source_window_cache=factual_source_window_cache,
                )
                record["group"] = group
                conflicts.append(record)
                conflict_found = conflict_found or record["relevant"]
                continue
            applicable = [
                member
                for member in members
                if condition_relation(current, member.content, member.metadata or {})
                == "applies"
                and relation_present(current, member.content)
            ]
            applicable, claims, scope_excluded = _curated_subject_scope(
                current, applicable, by_requirement.get(current.id, [])
            )
            finding = next(
                (
                    item
                    for item in role_scope_findings or []
                    if item["requirement_id"] == current.id and item["complete"]
                ),
                None,
            )
            if finding is not None:
                from app.services.role_scope_policy import session_role_scope

                allowed = set(
                    finding["session_documents"]
                    if session_role_scope(current)
                    else finding["activity_documents"]
                )
                known_contexts = {item["document_id"] for item in finding["contexts"]}
                scope_excluded.extend(
                    str(member.document_id)
                    for member in applicable
                    if str(member.document_id) in known_contexts - allowed
                )
                applicable = [
                    member
                    for member in applicable
                    if str(member.document_id) in allowed
                    or str(member.document_id) not in known_contexts
                ]
            pairs = [
                SupportPair(
                    member.content, witness.hypothesis, current.id, str(member.id)
                )
                for member in applicable
                for witness in claims
            ]
            assessments = (
                await support_service.assess(pairs, config=config) if pairs else []
            )
            if len(assessments) != len(pairs):
                raise RuntimeError(
                    "Support classifier returned incomplete conflict decisions"
                )
            agreement = (
                not truncated
                and bool(assessments)
                and all(assessment.supported for assessment in assessments)
                and _complete_fact_agreement(
                    applicable, by_requirement.get(current.id, [])
                )
            )
            relevant = (
                truncated or len({member.document_id for member in applicable}) >= 2
            ) and any(
                a.label != "neutral"
                and (
                    a.supported
                    or a.logits[0] - max(a.logits[1:]) >= config.SUPPORT_MIN_MARGIN
                )
                for a in assessments
            )
            supported_group = any(
                witness.chunk.id in {member.id for member in applicable}
                for witness in by_requirement.get(current.id, [])
            )
            incomplete_relevant = truncated and supported_group
            relevant = relevant or incomplete_relevant
            if agreement:
                relevant = False
            conflicts.append(
                {
                    "group": group,
                    "requirement_id": current.id,
                    "applicable_documents": sorted(
                        {str(m.document_id) for m in applicable}
                    ),
                    "relevant": relevant,
                    "requested_fact_agreement": agreement,
                    "agreement_method": "identical-validated-member-witnesses-v1"
                    if agreement
                    else None,
                    "inspection_complete": not truncated,
                    "subject_scope_excluded_documents": sorted(set(scope_excluded)),
                    "source_scope_decisions": [
                        {
                            **source_identity(member),
                            "relation_scope": source_relation_scope(
                                current, member.content
                            ),
                            "included": member in applicable,
                        }
                        for member in members
                    ],
                    "outcome": "comparison_unconfirmed"
                    if incomplete_relevant
                    else "curated_conflict"
                    if relevant
                    else "not_relevant",
                    "assessments": [asdict(a) for a in assessments],
                }
            )
            conflict_found = conflict_found or relevant

    return conflicts, conflict_found


async def _inspect_procedure_group(  # noqa: C901 - full bounded opponent inspection
    db,
    request,
    principal,
    current,
    config,
    members,
    truncated,
    witnesses,
    inspected,
    contexts,
):
    """Opponents are inspected structurally, never revived as QA answer proposals."""
    policy = resolve_evidence_policy(config)
    if (
        policy.evidence_reading_profile == "contextual_source_v2"
        or policy.source_governance_profile == "requirement_bound_v1"
    ):
        from app.services.linguistic_conflicts import inspect_group

        return await inspect_group(
            db,
            request,
            principal,
            current,
            config,
            members,
            truncated,
            witnesses,
            inspected,
            contexts,
        )
    from app.services.procedure_evidence import (
        ProcedureRejected,
        bind_extent,
        inspection_identity,
        resolve_version,
    )
    from app.services.procedure_support import build_plan
    from app.services.requirement_binding import _step_markers

    by_document = {}
    inspection_sources = [inspection_identity(member) for member in members]
    for member in sorted(members, key=lambda c: c.chunk_index):
        by_document.setdefault(member.document_id, member)
    checks = []
    values = []
    excluded = []
    unconfirmed = False
    for document_id, seed in by_document.items():
        record = {
            **source_identity(seed),
            "proposal_origin": "structural-opponent-inspection",
            "answer_witness": False,
        }
        try:
            source = await resolve_version(db, principal, request, seed, inspected)
            for item in source.chunks:
                inspected[item.chunk.id] = item.chunk
            contexts.append(
                {
                    **source.identity,
                    "origin": "curated-procedure-inspection",
                    "sources": [source_identity(item.chunk) for item in source.chunks],
                }
            )
            # The legacy conflict helper classifies chunk-local scope, not an
            # entire body containing a namespace plus applicability/instructions.
            # Full procedure binding and mandatory requested-scope proofs below
            # establish this context; a QA-null opponent is never discarded.
            if (
                condition_relation(current, source.body, source.metadata)
                == "irrelevant"
            ):
                excluded.append(str(document_id))
                continue
            existing = next(
                (
                    w
                    for w in witnesses
                    if w.chunk.document_id == document_id and w.completeness
                ),
                None,
            )
            if existing is not None:
                record.update(existing.completeness)
                values.append(existing.value)
            else:
                if resolve_evidence_policy(config).procedure_copy:
                    from app.services.procedure_support import assess_condition_scope
                    from app.services.requirement_conflict_scope import (
                        procedure_condition_exclusion,
                    )

                    scope = procedure_condition_exclusion(
                        current,
                        source.body,
                        source.metadata,
                        [w.completeness for w in witnesses[:1]],
                        context_policy=resolve_evidence_policy(
                            config
                        ).source_context_policy,
                    )
                    if scope is not None:
                        record["condition_scope"] = scope
                        if not await assess_condition_scope(
                            source, current, scope, config, support_service
                        ):
                            raise ProcedureRejected(
                                "procedure_condition_scope_unconfirmed"
                            )
                        # Exclusion does not confer answer eligibility. Keep the
                        # complete inspection and recheck authority after inference.
                        await resolve_version(db, principal, request, seed, inspected)
                        record.update(status="irrelevant", reason=scope["reason"])
                        checks.append(record)
                        excluded.append(str(document_id))
                        continue
                # This is only a structural comparison cursor, not a QA-accepted
                # candidate and never an eligible answer witness.
                copy_profile = resolve_evidence_policy(config).procedure_copy
                if copy_profile:
                    from app.services.procedure_evidence import (
                        discover_procedure_candidates,
                    )
                    from app.services.procedure_support import copy_request_binding

                    extents = discover_procedure_candidates(current, source)
                    if len(extents) != 1:
                        raise ProcedureRejected("procedure_opponent_extent_unverified")
                    extent = extents[0]
                    plan = build_plan(current, source, extent)
                    copy_request_binding(
                        current, request.question, plan=plan, source=source
                    )
                else:
                    markers = _step_markers(source.body)
                    if not markers or markers[0].group(1) != "1":
                        raise ProcedureRejected("procedure_opponent_extent_unverified")
                    first = markers[0].end()
                    while first < len(source.body) and source.body[first].isspace():
                        first += 1
                    ending = re.search(r"[.!?](?=\s|$)", source.body[first:])
                    if ending is None:
                        raise ProcedureRejected("procedure_opponent_extent_unverified")
                    last = first + ending.end()
                    located = next(
                        (c for c in source.chunks if c.start <= first < last <= c.end),
                        None,
                    )
                    if located is None:
                        raise ProcedureRejected(
                            "procedure_opponent_context_budget_exceeded"
                        )
                    raw = {
                        "start": first - located.start,
                        "end": last - located.start,
                        "text": source.body[first:last],
                    }
                    extent = bind_extent(current, source, located.chunk, raw)
                    plan = build_plan(current, source, extent)
                required_inventory = plan.required_inventory(source)
                from app.services.procedure_support import assess_plan

                decisions, proof_units = await assess_plan(
                    plan, source, current, config, support_service, copy=copy_profile
                )
                record.update(
                    step_count=len(plan.steps),
                    mandatory_proof_count=len(plan.units),
                    extent={"start": plan.start, "end": plan.end},
                    required_inventory=required_inventory,
                    proof_units=proof_units,
                )
                if not all(
                    d.supported
                    and type(d.pair_tokens) is int
                    and 0 < d.pair_tokens <= 512
                    for d in decisions
                ):
                    raise ProcedureRejected("procedure_opponent_support_unconfirmed")
                await resolve_version(db, principal, request, seed, inspected)
                values.append(source.body[plan.start : plan.end])
            record["status"] = "supported"
        except SupportInputBudgetExceeded as exc:
            record.update(
                status="unsupported",
                reason="procedure_support_budget_exceeded",
                pair_token_lengths=list(exc.lengths),
            )
            unconfirmed = True
        except ProcedureRejected as exc:
            record.update(status="unsupported", reason=str(exc))
            if exc.opposed_source_units:
                record["opposed_source_units"] = list(exc.opposed_source_units)
            unconfirmed = True
        checks.append(record)
    supported_group = bool(witnesses)
    agreement = (
        bool(values)
        and not unconfirmed
        and not truncated
        and all(value == values[0] for value in values)
    )
    relevant = supported_group and (
        unconfirmed or truncated or (len(values) >= 2 and not agreement)
    )
    return {
        "requirement_id": current.id,
        "inspection_method": PROCEDURE_COPY_CONTRACT
        if resolve_evidence_policy(config).procedure_copy
        else PROCEDURE_CONTRACT,
        "inspection_sources": inspection_sources,
        "inspection_complete": not truncated and not unconfirmed,
        "requested_fact_agreement": agreement,
        "relevant": relevant,
        "source_extent_checks": checks,
        "subject_scope_excluded_documents": excluded,
        "applicable_documents": [
            r["document_id"] for r in checks if r["status"] != "irrelevant"
        ],
        "outcome": "comparison_unconfirmed"
        if unconfirmed or truncated
        else "curated_conflict"
        if relevant
        else "agreement"
        if values
        else "not_relevant",
    }


async def _find_scoped_witnesses(
    db: AsyncSession,
    request: QueryRequest,
    principal: Principal,
    current: Requirement,
    config: Settings,
    candidates: list[dict[str, Any]],
    inspected: dict[uuid.UUID, ChunkWithScore],
    followups: list[dict[str, Any]],
    validate_current: Callable[[ChunkWithScore], Awaitable[bool]],
    procedure_contexts: list[dict[str, Any]],
    policy: EvidencePolicy | None = None,
    request_plan=None,
    source_window_cache=None,
    pattern_observations=None,
) -> list[Witness]:
    from app.services.procedure_evidence import resolve_version

    async def resolve_source(member):
        return await resolve_version(db, principal, request, member, inspected)

    if current.kind == "procedure":
        found = await _find_procedure_witnesses(
            db,
            request,
            principal,
            current,
            config,
            candidates,
            inspected,
            procedure_contexts,
            validate_current,
            policy=policy,
            **(
                {
                    "request_plan": request_plan,
                    "source_window_cache": source_window_cache,
                }
                if policy and policy.dependency_reading
                else {}
            ),
            pattern_observations=pattern_observations,
        )
    else:
        found = await _find_witnesses(
            current,
            list(inspected.values()),
            config,
            candidates,
            policy=policy,
            resolve_source=resolve_source,
            pattern_observations=pattern_observations,
            request_plan=request_plan,
        )
    if (
        found
        or len(followups) >= 8
        or any(
            row.get("requirement_id") == current.id
            and row.get("origin") == "source_pattern"
            and row.get("complete") is False
            for row in candidates
        )
    ):
        return found
    followup = await retrieve_scoped(
        db,
        current.question,
        principal=principal,
        document_ids=request.document_ids,
        collection_ids=request.collection_ids,
        top_k=8,
        method=request.retrieval_method,
    )
    new_chunks = [
        chunk
        for chunk in followup.chunks
        if chunk.id not in inspected and await validate_current(chunk)
    ]
    followups.append(
        {
            "requirement_id": current.id,
            "query": current.question,
            "method": followup.method,
            "elapsed_ms": followup.elapsed_ms,
            "vector_count": followup.vector_count,
            "keyword_count": followup.keyword_count,
            "sources": [source_identity(chunk) for chunk in new_chunks],
        }
    )
    for chunk in new_chunks:
        inspected[chunk.id] = chunk
    if new_chunks and current.kind == "procedure":
        return await _find_procedure_witnesses(
            db,
            request,
            principal,
            current,
            config,
            candidates,
            inspected,
            procedure_contexts,
            validate_current,
            seeds=new_chunks,
            policy=policy,
            **(
                {
                    "request_plan": request_plan,
                    "source_window_cache": source_window_cache,
                }
                if policy and policy.dependency_reading
                else {}
            ),
            pattern_observations=pattern_observations,
        )
    return (
        await _find_witnesses(
            current,
            new_chunks,
            config,
            candidates,
            policy=policy,
            resolve_source=resolve_source,
            pattern_observations=pattern_observations,
            request_plan=request_plan,
        )
        if new_chunks
        else []
    )


async def _find_procedure_witnesses(  # noqa: C901 - all-or-nothing bounded evidence gate
    db,
    request,
    principal,
    current,
    config,
    candidates,
    inspected,
    contexts,
    validate_current,
    seeds=None,
    policy: EvidencePolicy | None = None,
    request_plan=None,
    source_window_cache=None,
    pattern_observations=None,
):
    from app.services.procedure_evidence import (
        ProcedureRejected,
        bind_extent,
        project_cover,
        resolve_version,
    )
    from app.services.procedure_support import build_plan

    policy = policy or resolve_evidence_policy(config)
    if policy.dependency_reading:
        from app.services.linguistic_procedure_runtime import find_procedure_witnesses

        return await find_procedure_witnesses(
            db,
            request,
            principal,
            current,
            config,
            candidates,
            inspected,
            contexts,
            validate_current,
            seeds=seeds,
            request_plan=request_plan,
            source_window_cache={}
            if source_window_cache is None
            else source_window_cache,
            pattern_observations=pattern_observations,
            **(
                {"reading_profile": policy.evidence_reading_profile}
                if policy.staged_request
                else {}
            ),
        )
    scope = _reader_subject_scope(
        current, seeds if seeds is not None else list(inspected.values()), candidates
    )
    eligible = []
    for member in scope:
        if (
            current.source_workspace
            and (member.metadata or {}).get("workspace_id") != current.source_workspace
        ):
            candidates.append(
                {
                    **source_identity(member),
                    "requirement_id": current.id,
                    "decision": "requested_workspace_mismatch",
                }
            )
        else:
            eligible.append(member)
    scope = eligible
    reader_identity = reader_service.metadata(config)
    predictions = await reader_service.select_atomic(
        current.question, [c.content for c in scope], config=config
    )
    work = []
    for chunk, prediction in zip(scope, predictions, strict=True):
        observation = QAObservation.capture(
            current.id,
            chunk,
            prediction,
            question=current.question,
            reader_identity=reader_identity,
        )
        candidates.append(
            {
                **source_identity(chunk),
                "requirement_id": current.id,
                "decision": "qa_observation",
                "qa_observation": observation.record(),
            }
        )
        if prediction.span is None:
            candidates.append(
                {
                    **source_identity(chunk),
                    "requirement_id": current.id,
                    "decision": "qa_no_answer",
                }
            )
            continue
        for raw in _raw_predictions(prediction):
            margin = raw.get("null_margin")
            if (
                isinstance(margin, bool)
                or not isinstance(margin, (int, float))
                or not math.isfinite(margin)
                or margin > config.READER_NULL_THRESHOLD
            ):
                continue
            work.append((chunk, raw, float(margin), None, observation))
    if policy.source_patterns:
        sources = []
        seen_documents = set()
        for member in scope:
            if member.document_id in seen_documents:
                continue
            seen_documents.add(member.document_id)
            try:
                source = await resolve_version(
                    db, principal, request, member, inspected
                )
                sources.append(source)
                for item in source.chunks:
                    inspected[item.chunk.id] = item.chunk
            except ProcedureRejected as exc:
                candidates.append(
                    {
                        **source_identity(member),
                        "requirement_id": current.id,
                        "origin": "source_pattern",
                        "decision": str(exc),
                        "complete": False,
                    }
                )
                return []
        batch = collect_source_proposals(current, sources)
        candidates.extend(batch.observations)
        if pattern_observations is not None:
            pattern_observations.extend(deepcopy(batch.observations))
        if not batch.complete:
            return []
        by_chunk = {
            str(item.chunk.id): item.chunk
            for source in sources
            for item in source.chunks
        }
        for proposal in batch.proposals:
            raw = {
                "start": proposal.chunk_start,
                "end": proposal.chunk_end,
                "text": proposal.text,
            }
            work.append(
                (by_chunk[proposal.chunk_id], raw, None, proposal.record(), None)
            )
    found = []
    established = {}
    for chunk, raw, margin, proposal, observation in work:
        diagnostic = {
            **source_identity(chunk),
            "requirement_id": current.id,
            "raw_span": {key: raw.get(key) for key in ("start", "end")},
            "null_margin": margin,
            "origin": "source_pattern" if proposal else "qa_reader",
        }
        candidates.append(diagnostic)
        try:
            source = await resolve_version(db, principal, request, chunk, inspected)
            if proposal is None:
                try:
                    proposal = make_proposal(
                        current.id,
                        source,
                        chunk,
                        raw["start"],
                        raw["end"],
                        origin="qa_reader",
                        observation=observation,
                    ).record()
                except ValueError as exc:
                    if policy.source_patterns:
                        raise ProcedureRejected(str(exc)) from exc
            if proposal is not None:
                diagnostic["proposal"] = proposal
            context = {
                **source.identity,
                "origin": "immutable-procedure-context",
                "body_bytes": len(source.body.encode("utf-8")),
                "sources": [
                    {
                        **source_identity(item.chunk),
                        "document_range": {"start": item.start, "end": item.end},
                        "score_status": (item.chunk.metadata or {}).get("score_status"),
                        "ranking_score": item.chunk.relevance_score
                        if (item.chunk.metadata or {}).get("score_status") == "ranked"
                        else None,
                    }
                    for item in source.chunks
                ],
            }
            if context not in contexts:
                contexts.append(context)
            for item in source.chunks:
                inspected[item.chunk.id] = item.chunk
            extent = bind_extent(current, source, chunk, raw)
            key = (chunk.document_id, extent.claim.start, extent.claim.end)
            if key in established:
                index = established[key]
                if proposal is not None and proposal not in found[index].proposals:
                    found[index] = replace(
                        found[index], proposals=(*found[index].proposals, proposal)
                    )
                diagnostic["decision"] = "duplicate_complete_procedure"
                continue
            if proposal is not None and proposal["origin"] == "source_pattern":
                from app.services.procedure_evidence import (
                    discover_procedure_candidates,
                )

                if not any(
                    candidate.claim == extent.claim
                    and candidate.closure == extent.closure
                    and candidate.boundary == extent.boundary
                    for candidate in discover_procedure_candidates(current, source)
                ):
                    raise ProcedureRejected("procedure_pattern_extent_mismatch")
            plan = build_plan(current, source, extent)
            required_inventory = plan.required_inventory(source)
            fragments = project_cover(source, plan.start, plan.end, plan.steps)
            from app.services.procedure_support import (
                COPY_PROFILE,
                assess_plan,
                copy_request_binding,
            )

            binding = (
                copy_request_binding(
                    current, request.question, plan=plan, source=source
                )
                if policy.procedure_copy
                else None
            )
            decisions, diagnostic["support_checks"] = await assess_plan(
                plan,
                source,
                current,
                config,
                support_service,
                copy=policy.procedure_copy,
            )
            if not all(decision.supported for decision in decisions):
                raise ProcedureRejected("procedure_mandatory_support_rejected")
            if any(
                type(decision.pair_tokens) is not int
                or not 0 < decision.pair_tokens <= 512
                for decision in decisions
            ):
                raise ProcedureRejected("procedure_support_length_unrecorded")
            # Long model work must not publish a now-stale source.
            if not await validate_current(chunk):
                raise ProcedureRejected("procedure_source_changed")
            await resolve_version(db, principal, request, chunk, inspected)
            completeness = {
                "contract": PROCEDURE_COPY_CONTRACT
                if policy.procedure_copy
                else PROCEDURE_CONTRACT,
                **(
                    {
                        "source_body": source.body,
                        "procedure_verification_profile": COPY_PROFILE,
                        "request_binding": binding,
                    }
                    if policy.procedure_copy
                    else {}
                ),
                "status": "supported",
                **source.identity,
                "body_length": len(source.body),
                "extent": {"start": plan.start, "end": plan.end},
                "closure": {"kind": extent.closure, "end": extent.claim.end},
                "structure": plan.structure,
                "step_count": len(plan.steps) if plan.structure == "numbered" else None,
                "mandatory_proof_count": len(plan.units),
                "coverage_complete": True,
                "step_ranges": [
                    {"ordinal": ordinal, "start": left, "end": right}
                    for ordinal, left, right in plan.steps
                ],
                "proof_units": diagnostic["support_checks"],
                "required_inventory": required_inventory,
                "structure_edges": list(plan.edges),
                "raw_seed": {
                    "proposal_id": proposal["proposal_id"] if proposal else None,
                    "origin": proposal["origin"] if proposal else None,
                    "chunk_id": str(chunk.id),
                    "text": source.body[extent.raw_start : extent.raw_end],
                    "chunk_range": diagnostic["raw_span"],
                    "document_range": {
                        "start": extent.raw_start,
                        "end": extent.raw_end,
                    },
                },
                "fragments": [
                    {
                        "chunk_id": str(c.id),
                        "chunk_start": span.start,
                        "chunk_end": span.end,
                        "document_start": left,
                        "document_end": right,
                    }
                    for c, span, left, right in fragments
                ],
            }
            if extent.boundary is not None:
                completeness["closure"]["boundary_range"] = {
                    "start": extent.boundary[0],
                    "end": extent.boundary[1],
                }
            diagnostic.update(decision="supported", procedure_completeness=completeness)
            seed_fragment = next(
                (span for c, span, _, _ in fragments if c.id == chunk.id), None
            )
            if seed_fragment is None:
                raise ProcedureRejected("procedure_seed_not_cited")
            found.append(
                Witness(
                    current.id,
                    chunk,
                    seed_fragment,
                    source.body[plan.start : plan.end],
                    f"The complete procedure is for {current.topic}.",
                    min(d.entailment_margin for d in decisions),
                    margin,
                    (),
                    tuple((c, span) for c, span, _, _ in fragments),
                    completeness,
                    (proposal,) if proposal is not None else (),
                )
            )
            established[key] = len(found) - 1
        except SupportInputBudgetExceeded as exc:
            diagnostic.update(
                decision="procedure_support_budget_exceeded",
                pair_token_lengths=list(exc.lengths),
            )
        except ProcedureRejected as exc:
            diagnostic["decision"] = str(exc)
            if exc.opposed_source_units:
                diagnostic["opposed_source_units"] = list(exc.opposed_source_units)
            if exc.source_range is not None:
                diagnostic["unparsed_source_range"] = {
                    "start": exc.source_range[0],
                    "end": exc.source_range[1],
                }
                diagnostic["unparsed_source_form"] = exc.source_form

    return found


async def _owner_relative_attempt(
    requirement: Requirement,
    alternatives: dict[str, Requirement],
    values: dict[str, str],
    by_requirement: dict[str, list[Witness]],
    lookup: Callable[[Requirement], Awaitable[list[Witness]]],
    candidates: list[dict[str, Any]],
    followups: list[dict[str, Any]],
) -> tuple[Requirement | None, list[Witness], dict[str, Any] | None]:
    alternative = alternatives.get(requirement.id)
    if alternative is None:
        return None, [], None
    root_id = alternative.depends_on[0]
    owner = values.get(root_id)
    roots = [w for w in by_requirement.get(root_id, []) if w.value == owner]
    if not owner or not roots:
        return None, [], None
    try:
        current = resolve_requirement(alternative, values)
    except ValueError:
        return None, [], None
    candidate_start, followup_start = len(candidates), len(followups)
    found = await lookup(current)
    for diagnostic in (*candidates[candidate_start:], *followups[followup_start:]):
        diagnostic["interpretation"] = "owner_relative_deputy"
    if not found:
        return None, [], None
    interpretation = {
        "kind": "owner_relative_deputy",
        "meaning": "The verified owner's deputy for this coordinated request.",
        "original_activity": alternative.topic,
        "owner_requirement_id": root_id,
        "resolved_owner": owner,
        "owner_evidence": [source_identity(w.chunk) for w in roots],
        "deputy_evidence": [source_identity(w.chunk) for w in found],
    }
    return current, found, interpretation


def _seed_captured_inspection(inspected, context, policy):
    """Reuse the complete validated source universe, retaining ranked retrieval."""
    if (
        policy.evidence_reading_profile != "contextual_source_v4"
        or policy.source_governance_profile != "requirement_bound_v1"
    ):
        return
    from app.evidence_policy import recorded_evidence_policy
    from app.services.curated_conflict_proof import _same, inspection_identity
    from app.services.staged_plan_replay import _actual_source, _snapshot
    from app.services.staged_typed_conflicts import source_chunks

    profile = policy.record()
    _same(
        recorded_evidence_policy(profile).record(),
        profile,
        "Canonical source policy required",
    )
    if context is None or not context.resolved_request:
        raise ValueError("Complete captured planning context required")
    _same(
        json.loads(context.plan.evidence_profile_json),
        profile,
        "Captured source policy differs",
    )
    original = json.loads(context.plan.source_productions_json)["original_inputs"]
    snapshots = context.snapshots()
    rows = original["snapshots"]
    identities = [row["identity"] for row in rows]
    _same(
        sorted(identities, key=lambda row: row["document_id"]),
        sorted(
            original["manifest"]["publications"], key=lambda row: row["document_id"]
        ),
        "Complete captured source identities differ",
    )
    expected = {row["document_id"] for row in identities}
    if len(expected) != len(rows) or set(snapshots) != expected:
        raise ValueError("Complete captured source authority differs")
    for row in rows:
        _actual_source(_snapshot(row), snapshots)
    members = source_chunks(snapshots, evidence_profile=profile)
    known = {member.id: member for member in members}
    if not set(inspected) <= set(known):
        raise ValueError("Retrieved source outside captured authority")
    for member in members:
        existing = inspected.get(member.id)
        if existing is not None:
            _same(
                inspection_identity(existing),
                inspection_identity(member),
                "Retrieved source differs from captured publication",
            )
            _same(
                existing.chunk_index,
                member.chunk_index,
                "Retrieved source ordinal differs",
            )
        else:
            inspected[member.id] = member


async def select_requirement_answer(
    db: AsyncSession,
    request: QueryRequest,
    principal: Principal,
    chunks: list[ChunkWithScore],
    config: Settings,
    *,
    validate_current: Callable[[ChunkWithScore], Awaitable[bool]],
    policy: EvidencePolicy | None = None,
) -> RequirementAnswer:
    policy = policy or resolve_evidence_policy(config)
    staged_context = None
    if policy.staged_request:
        from app.services.captured_production_policy import selected_version

        if selected_version(policy.evidence_reading_profile) is not None:
            from app.services.captured_answer_planning import prepare_context
        else:
            from app.services.staged_answer_planning import prepare_context

        staged_context = await prepare_context(db, principal, request, config)
    result = await _select_requirement_answer(
        db,
        request,
        principal,
        chunks,
        config,
        validate_current=validate_current,
        policy=policy,
        staged_context=staged_context,
    )
    if staged_context is not None:
        result = replace(
            result,
            staged_request_inputs=staged_context.inputs(),
            staged_execution_capture_json=staged_context.inputs_json,
        )
    return result


async def _select_requirement_answer(  # noqa: C901 - typed complete requirement cover
    db: AsyncSession,
    request: QueryRequest,
    principal: Principal,
    chunks: list[ChunkWithScore],
    config: Settings,
    *,
    validate_current: Callable[[ChunkWithScore], Awaitable[bool]],
    policy: EvidencePolicy | None = None,
    staged_context=None,
) -> RequirementAnswer:
    policy = policy or resolve_evidence_policy(config)
    # The caller already verified immutable current snapshots and SQL authority.
    # All state below belongs to this one request, including null/rejected evidence.
    request_plan = {}
    request_capture = {}
    planned = None
    if policy.dependency_reading:
        from app.services.request_parser import capture_async, validate_capture

        # Configured runtime/asset/capture failures are execution failures,
        # distinct from a valid graph that retains unresolved request grammar.
        request_capture = (
            staged_context.inputs()["capture"]
            if staged_context is not None
            else await capture_async(request.question, config)
        )
        validate_capture(request.question, request_capture)
    try:
        if policy.dependency_reading:
            from app.services.linguistic_requirements import plan_request

            planned = (
                staged_context
                if staged_context is not None
                else plan_request(request.question, request_capture)
            )
            request_plan = planned.record()
            if not planned.resolved_request:
                return RequirementAnswer(
                    (),
                    {},
                    [],
                    [],
                    [],
                    [],
                    [],
                    "The request contains unresolved requirements; "
                    "no partial answer was published.",
                    evidence_profile=policy.record(),
                    request_plan=request_plan,
                    request_capture=request_capture,
                )
            requirements = planned.requirements
        else:
            requirements = plan_requirements(
                request.question, reading_profile=policy.evidence_reading_profile
            )
    except ValueError as exc:
        return RequirementAnswer(
            (), {}, [], [], [], [], [], str(exc), evidence_profile=policy.record()
        )
    inspected = {chunk.id: chunk for chunk in chunks}
    _seed_captured_inspection(inspected, staged_context, policy)
    from app.services.role_scope_inspection import (
        check_role_read_set,
        inspect_role_contexts,
        inspect_role_manifest,
    )
    from app.services.role_scope_policy import plan_activity_role, session_role_scope

    role_plans = {
        requirement.id: plan_activity_role(requirement, policy, request_plan=planned)
        for requirement in requirements
        if isinstance(requirement, Requirement)
    }
    role_source_windows = None
    role_manifest = None
    role_read_set = {}
    role_interpretations = []
    role_findings = []
    if any(role_plans.values()):
        role_manifest = await inspect_role_manifest(
            db,
            principal,
            request,
            reading_profile=(
                policy.evidence_reading_profile
                if policy.contextual_source
                else "clause_bound_v1"
            ),
        )
        if policy.dependency_reading and role_manifest.complete:
            from app.services.role_scope_inspection import capture_role_contexts

            role_source_windows = await capture_role_contexts(role_manifest, config)
        role_read_set = role_manifest.record()
        for source in role_manifest.sources:
            for member in source.chunks:
                inspected.setdefault(member.id, member)
    candidates: list[dict[str, Any]] = []
    pattern_observations: list[dict[str, Any]] = []
    typed_actors = {}
    typed_fields = {}
    if policy.staged_request and staged_context is not None:
        from app.services import staged_typed_conflicts

        if policy.evidence_reading_profile == "contextual_source_v4":
            from app.services import captured_role_consumer as staged_role_consumer
        else:
            from app.services import staged_role_consumer

        if not (
            policy.evidence_reading_profile == "contextual_source_v4"
            and policy.source_governance_profile == "requirement_bound_v1"
        ) and any(
            staged_role_consumer.typed_requirement(req, staged_context)
            for req in requirements
        ):
            for chunk in staged_typed_conflicts.source_chunks(
                staged_context.snapshots()
            ):
                inspected[chunk.id] = chunk
    followups: list[dict[str, Any]] = []
    procedure_contexts: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    witnesses: list[Witness] = []
    values: dict[str, str] = {}
    resolved: dict[str, Requirement] = {}
    by_requirement: dict[str, list[Witness]] = {}
    alternatives = {
        req.id: req
        for req in owner_relative_alternatives(
            tuple(req for req in requirements if isinstance(req, Requirement))
        )
    }
    effective = {req.id: req for req in requirements}
    lookup = partial(
        _find_scoped_witnesses,
        db,
        request,
        principal,
        config=config,
        candidates=candidates,
        inspected=inspected,
        followups=followups,
        validate_current=validate_current,
        procedure_contexts=procedure_contexts,
        policy=policy,
        **(
            {"request_plan": planned, "source_window_cache": {}}
            if policy.dependency_reading
            else {}
        ),
        pattern_observations=pattern_observations,
    )
    for requirement in requirements:
        record = {
            "id": requirement.id,
            "original_text": requirement.original_text,
            "input_range": {
                "start": requirement.input_start,
                "end": requirement.input_end,
            },
            "kind": requirement.kind,
            "source_workspace": requirement.source_workspace,
            "depends_on": list(requirement.depends_on),
            "status": "unsupported",
            "witnesses": [],
        }
        records.append(record)
        try:
            if policy.dependency_reading:
                current, dependency_binding = resolve_linguistic_requirement(
                    requirement, planned, values
                )
                if dependency_binding:
                    record["dependency_binding"] = dependency_binding
            else:
                current = resolve_requirement(requirement, values)
        except ValueError as exc:
            record["reason"] = str(exc)
            continue
        resolved[requirement.id] = current
        record["prepared_question"] = current.question
        role_plan = role_plans.get(requirement.id)
        if policy.evidence_reading_profile == "contextual_source_v4":
            from app.services import captured_role_consumer as typed_roles
        else:
            from app.services import staged_role_consumer as typed_roles

        if (
            policy.staged_request
            and staged_context is not None
            and typed_roles.typed_requirement(current, staged_context)
        ):
            if staged_context is None:
                raise ValueError("Actual typed role planning context required")
            from app.services.staged_role_evidence import RoleSourceUnrepresentable

            try:
                evidence = await typed_roles.assess_requirement(
                    config, staged_context, current, typed_actors, typed_fields
                )
            except RoleSourceUnrepresentable as exc:
                record["reason"] = str(exc)
                candidates.append(
                    {
                        "requirement_id": current.id,
                        "decision": "typed_source_unrepresentable",
                        "reason": str(exc),
                        "typed_prior_executions": json.loads(
                            exc.__dict__.get("typed_prior_executions_json", "[]")
                        ),
                        "execution_failure": json.loads(
                            exc.__dict__.get("role_evidence_json", "null")
                        ),
                    }
                )
                continue
            if evidence is None:
                record["reason"] = "dependent_field_not_established_for_actual_actor"
                continue
            descriptor, proof, observation, member, literal = typed_roles.view(evidence)
            candidates.append(typed_roles.candidate(evidence))
            pattern_observations.append(observation)
            inspected.setdefault(member.id, member)
            if not await validate_current(member):
                record["reason"] = "typed_role_source_changed"
                continue
            found = (
                [
                    Witness(
                        current.id,
                        member,
                        AnswerSpan(**descriptor["span"]),
                        literal,
                        "",
                        proof["margin"],
                        None,
                        proposals=tuple(proof["origins"]),
                        typed_role_descriptor=descriptor,
                    )
                ]
                if evidence.supported
                else []
            )
        elif role_plan is not None:
            if role_manifest is None:
                raise RuntimeError("Missing request-local role manifest")
            finding = inspect_role_contexts(
                role_manifest,
                role_plan,
                **(
                    {"evidence_profile": policy.record()}
                    if policy.source_governance_profile == "requirement_bound_v1"
                    else {}
                ),
                **(
                    {"source_windows": role_source_windows}
                    if policy.dependency_reading and role_source_windows is not None
                    else {}
                ),
            )
            role_findings.append(finding)
            record["role_scope_inspection"] = finding
            if not finding["complete"]:
                record["reason"] = (
                    finding["reason"] or "role_scope_inspection_incomplete"
                )
                continue
            scope = "session" if finding["session_documents"] else "activity"
            if scope == "activity" and role_plan.session_only:
                record["reason"] = "session_assignment_not_documented"
                continue
            current = role_plan.prepared(scope)
            interpreted = role_plan.record(scope)
            role_interpretations.append(interpreted)
            record.update(
                role_scope_interpretation=interpreted,
                prepared_question=current.question,
            )
            resolved[current.id] = effective[current.id] = current
            allowed_documents = set(
                finding["session_documents"]
                if scope == "session"
                else finding["activity_documents"]
            )
            members = [
                member
                for member in inspected.values()
                if str(member.document_id) in allowed_documents
            ]
            from app.services.procedure_evidence import resolve_version

            async def resolve_role_source(member):
                return await resolve_version(db, principal, request, member, inspected)

            found = await _find_witnesses(
                current,
                members,
                config,
                candidates,
                policy=policy,
                resolve_source=resolve_role_source,
                role_target=current.topic,
                pattern_observations=pattern_observations,
                request_plan=staged_context.plan
                if staged_context is not None
                else None,
            )
        elif policy.activity_roles and session_role_scope(current) is not None:
            # Qualified/named/conditional requests cannot enter the permissive
            # old generic binder and acquire an undisclosed activity fallback.
            record["reason"] = "role_session_scope_not_interpretable"
            continue
        else:
            found = await lookup(current)
        if not found and role_plan is None:
            alternate, alternate_found, interpretation = await _owner_relative_attempt(
                requirement,
                alternatives,
                values,
                by_requirement,
                lookup,
                candidates,
                followups,
            )
            if alternate is not None:
                current, found = alternate, alternate_found
                resolved[current.id] = current
                effective[current.id] = current
                record.update(
                    prepared_question=current.question,
                    depends_on=list(current.depends_on),
                    interpretation=interpretation,
                )
        if found:
            found.sort(
                key=lambda witness: (
                    -witness.margin,
                    witness.null_margin
                    if witness.null_margin is not None
                    else math.inf,
                    str(witness.chunk.id),
                )
            )
            best = found[0]
            values[current.id] = best.value
            by_requirement[current.id] = found
            witnesses.extend(found)
            record["status"] = "supported"
            if best.completeness is not None:
                record["procedure_completeness"] = best.completeness
            record["witnesses"] = [
                {
                    **source_identity(w.chunk),
                    "value": w.value,
                    "span": w.span.model_dump(),
                    "entailment_margin": w.margin,
                    "proof_edges": [_edge_record(edge) for edge in w.proof_edges],
                    "proposals": list(w.proposals),
                    **(
                        {"quantity_binding": w.quantity_binding}
                        if w.quantity_binding
                        else {}
                    ),
                    **(
                        {
                            "document_range": {
                                "start": w.proposals[0]["document_range"]["start"]
                                - w.proposals[0]["chunk_range"]["start"]
                                + w.span.start,
                                "end": w.proposals[0]["document_range"]["start"]
                                - w.proposals[0]["chunk_range"]["start"]
                                + w.span.end,
                            }
                        }
                        if w.proposals
                        else {}
                    ),
                    **(
                        {"procedure_completeness": w.completeness}
                        if w.completeness
                        else {}
                    ),
                    **(w.typed_role_descriptor or {}),
                }
                for w in found
            ]
            if (policy.source_patterns or role_plan is not None) and len(
                {
                    witness_value_identity(
                        current,
                        w.value,
                        reading_profile=policy.evidence_reading_profile,
                        quantity_binding=w.quantity_binding,
                    )
                    for w in found
                }
            ) > 1:
                # Keep every supported alternative for conflict inspection; a
                # ranking tie cannot choose one incompatible literal fact.
                record.update(
                    status="unsupported", reason="conflicting_supported_proposals"
                )
                values.pop(current.id, None)
        else:
            record["reason"] = (
                "No authoritative candidate establishes this requested fact."
            )
            if current.kind == "procedure":
                rejections = [
                    c.get("decision")
                    for c in candidates
                    if c.get("requirement_id") == current.id
                    and c.get("decision")
                    not in {
                        "reader_not_queried_subject_scope",
                        "duplicate_complete_procedure",
                    }
                ]
                if rejections:
                    record["reason_detail"] = record["reason"]
                    record["reason"] = (
                        "procedure_support_budget_exceeded"
                        if "procedure_support_budget_exceeded" in rejections
                        else rejections[-1]
                    )

    conflicts, conflict_found = await _inspect_conflicts(
        db,
        request,
        principal,
        inspected,
        tuple(
            req
            for req in effective.values()
            if not (
                policy.staged_request
                and staged_context is not None
                and typed_roles.typed_requirement(req, staged_context)
            )
        ),
        resolved,
        by_requirement,
        config,
        validate_current,
        procedure_contexts,
        role_scope_findings=role_findings,
    )
    if policy.staged_request and staged_context is not None:
        if policy.evidence_reading_profile == "contextual_source_v4":
            from app.services import captured_typed_conflicts as staged_typed_conflicts
        else:
            from app.services import staged_typed_conflicts

        typed_requirements = tuple(
            req
            for req in requirements
            if typed_roles.typed_requirement(req, staged_context)
        )
        typed_conflicts = staged_typed_conflicts.records(
            staged_context.plan,
            typed_requirements,
            {**typed_actors, **typed_fields},
            staged_context.snapshots(),
        )
        conflicts.extend(typed_conflicts)
        conflict_found = conflict_found or any(
            row["relevant"] for row in typed_conflicts
        )

    missing = [record["id"] for record in records if record["status"] != "supported"]
    dependency_roots = {
        identifier for req in effective.values() for identifier in req.depends_on
    }
    consistent = [
        w
        for w in witnesses
        if w.requirement not in dependency_roots or w.value == values.get(w.requirement)
    ]
    selected = (
        _cover(consistent, [requirement.id for requirement in requirements])
        if requirements and not missing
        else []
    )
    if any(w.completeness is not None for w in selected):
        from app.services.procedure_evidence import ProcedureRejected, resolve_version

        for witness in selected:
            if witness.completeness is None:
                continue
            try:
                await resolve_version(db, principal, request, witness.chunk, inspected)
            except ProcedureRejected as exc:
                for record in records:
                    if record["id"] == witness.requirement:
                        record.update(status="unsupported", reason=str(exc))
                        record["procedure_completeness"] = {
                            **witness.completeness,
                            "status": "unsupported",
                            "coverage_complete": False,
                        }
                missing = [
                    record["id"]
                    for record in records
                    if record["status"] != "supported"
                ]
                selected = []
                break
    procedure_read_set = {}
    consistency_refusal = None
    if any(w.completeness is not None for w in selected) or (
        policy.contextual_source and selected
    ):
        from app.services.procedure_evidence import (
            capture_read_set,
            check_read_set,
            invalidate_inspection,
        )

        procedure_read_set = capture_read_set(
            list(inspected.values()),
            conflicts,
            request,
            **({"include_factual_groups": True} if policy.contextual_source else {}),
        )
        consistency = await check_read_set(db, principal, request, procedure_read_set)
        procedure_read_set["after_proofs"] = consistency
        if not consistency["consistent"]:
            invalidate_inspection(records, conflicts, consistency)
            if policy.contextual_source:
                for record in records:
                    record.update(status="unsupported", reason=consistency["reason"])
                consistency_refusal = (
                    "The inspected current evidence or its access changed during "
                    "execution; retry the request against the current sources."
                )
            missing = [
                record["id"] for record in records if record["status"] != "supported"
            ]
            conflict_found = True
            selected = []
    if role_read_set:
        # The captured manifest is published into the result whenever role
        # evidence exists; the drift check must run even when the answer is
        # carried entirely by findings/interpretations with no witnesses.
        with db.no_autoflush:
            consistency = await check_role_read_set(
                db, principal, request, role_read_set
            )
        role_read_set["after_proofs"] = consistency
        if not consistency["consistent"]:
            for record in records:
                if record.get("role_scope_interpretation"):
                    record.update(status="unsupported", reason=consistency["reason"])
            missing = [
                record["id"] for record in records if record["status"] != "supported"
            ]
            selected = []
    selected_chunks: dict[uuid.UUID, ChunkWithScore] = {}
    spans: dict[uuid.UUID, AnswerSpan] = {}
    for witness in selected:
        for chunk, span in witness.fragments or ((witness.chunk, witness.span),):
            identifier = chunk.id
            selected_chunks[identifier] = chunk
            previous = spans.get(identifier)
            start = min(previous.start, span.start) if previous else span.start
            end = max(previous.end, span.end) if previous else span.end
            spans[identifier] = AnswerSpan(
                start=start, end=end, text=chunk.content[start:end]
            )
    reason = consistency_refusal or (
        (
            "The requested operation has a relevant curated conflict; "
            "human review is required."
        )
        if conflict_found
        else (
            "The authorized current sources do not establish every requested "
            "fact. Missing: "
        )
        + ", ".join(missing)
        if missing
        else "Complete evidence does not fit the bounded citation budget."
        if not selected
        else None
    )
    return RequirementAnswer(
        tuple(selected_chunks.values()),
        spans,
        records,
        candidates,
        [source_identity(c) for c in inspected.values()],
        conflicts,
        followups,
        reason,
        _selected_passages(selected),
        procedure_contexts,
        tuple(
            {
                "requirement_id": w.requirement,
                "text": w.value,
                "chunk_ids": [str(c.id) for c, _ in w.fragments],
                "fragments": [
                    {"chunk_id": str(c.id), "start": span.start, "end": span.end}
                    for c, span in w.fragments
                ],
            }
            for w in selected
            if w.completeness
        ),
        procedure_read_set,
        policy.record(),
        tuple(
            {
                row["proposal"]["proposal_id"]: row["proposal"]
                for row in candidates
                if "proposal" in row
            }.values()
        ),
        tuple(
            {
                row["qa_observation"]["observation_id"]: row["qa_observation"]
                for row in candidates
                if "qa_observation" in row
            }.values()
        ),
        tuple(pattern_observations)
        if policy.dependency_reading
        else tuple(row for row in candidates if row.get("origin") == "source_pattern"),
        tuple(
            dict.fromkeys(
                proposal["proposal_id"]
                for witness in selected
                for proposal in witness.proposals
            )
        ),
        role_read_set,
        tuple(role_interpretations),
        tuple(role_findings),
        request_plan,
        request_capture,
        tuple(
            row["source_guard_record"]
            for row in candidates
            if "source_guard_record" in row
        ),
    )
