"""Pure typed registry over canonical request and immutable source records.

No database/model resolver or authorization occurs here. Callers must supply
canonical body, chunk mappings and immutable identity; validate_source checks
their literal consistency. Proposals and structural completeness are discovery
results only. QA/NLI support, access and current-version gates remain mandatory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evidence_policy import (
    MAX_PATTERN_PROPOSALS_PER_REQUIREMENT,
    MAX_PATTERN_PROPOSALS_PER_SOURCE,
    PATTERN_REGISTRY_CONTRACT,
    dependency_reading_profile,
    reading_version,
)
from app.services.evidence_proposals import (
    EvidenceProposal,
    make_proposal,
    validate_source,
)
from app.services.procedure_discovery import (
    ProcedureRejected,
    discover_plan,
    discover_procedure_candidates,
)
from app.services.procedure_paragraphs import PATTERN as PARAGRAPH_PATTERN
from app.services.requirement_binding import role_discovery_ranges

ROLE_PATTERN = "literal-lead-deputy-v1"
NUMBERED_PATTERN = "complete-numbered-procedure-v1"
NARRATIVE_PATTERN = "complete-narrative-procedure-v1"
ENVELOPE_PATTERN = "source-declared-envelope-v2"
PATTERN_IDS = frozenset(
    {ROLE_PATTERN, NUMBERED_PATTERN, NARRATIVE_PATTERN, PARAGRAPH_PATTERN}
)


@dataclass(frozen=True)
class PatternBatch:
    proposals: tuple[EvidenceProposal, ...]
    observations: tuple[dict[str, Any], ...]
    complete: bool


def pattern_ids(reading_profile="clause_bound_v1"):
    if reading_profile == "clause_bound_v1":
        return PATTERN_IDS
    reading_version(reading_profile)
    captured_patterns = set()
    if reading_profile == "contextual_source_v4":
        from app.services.captured_availability_evidence import PATTERN as field_pattern
        from app.services.captured_role_evidence import PATTERN as role_pattern

        captured_patterns = {role_pattern, field_pattern}
    return (
        PATTERN_IDS
        | ({ENVELOPE_PATTERN} if dependency_reading_profile(reading_profile) else set())
        | (
            {"staged-role-declaration-v1", "staged-dependent-field-v1"}
            if reading_profile in {"contextual_source_v2", "contextual_source_v3"}
            else set()
        )
        | captured_patterns
    )


def _envelope_seed(source, requirement):
    from app.services.contextual_procedures import (
        RoutineRejected,
        _envelope_declaration,
        _envelope_named_subject,
    )

    try:
        declaration = _envelope_declaration(source.body)
        left, right = _envelope_named_subject(declaration["subject"])
        first_name, last_name = _envelope_named_subject(requirement.topic)
        declared_name = " ".join(declaration["subject"][left:right].split()).casefold()
        requested_name = " ".join(
            requirement.topic[first_name:last_name].split()
        ).casefold()
        if declared_name != requested_name:
            return None
    except RoutineRejected:
        return None
    first, last = declaration.span()
    located = next(
        (item for item in source.chunks if item.start <= first < last <= item.end), None
    )
    if located is None:
        raise ProcedureRejected("procedure_pattern_seed_unrepresentable")
    return located, first - located.start, last - located.start


def collect_source_proposals(  # noqa: C901 - bounded discovery with explicit contracts
    requirement, sources, *, reading_profile="clause_bound_v1"
) -> PatternBatch:
    pattern_ids(reading_profile)
    registry = (
        PATTERN_REGISTRY_CONTRACT
        if reading_profile == "clause_bound_v1"
        else reading_version(reading_profile).pattern_registry
    )
    proposals = []
    observations = []
    seen = set()
    complete = True
    for source in sources:
        identity = tuple(
            source.identity.get(key)
            for key in ("document_id", "document_version", "content_hash")
        )
        if identity in seen:
            continue
        seen.add(identity)
        local = []
        try:
            validate_source(source)
            envelope = (
                _envelope_seed(source, requirement)
                if requirement.kind == "procedure"
                and dependency_reading_profile(reading_profile)
                else None
            )
            if envelope is not None:
                located, first, last = envelope
                local.append(
                    make_proposal(
                        requirement.id,
                        source,
                        located.chunk,
                        first,
                        last,
                        origin="source_pattern",
                        pattern_id=ENVELOPE_PATTERN,
                        grammar_version=registry,
                    )
                )
            elif requirement.kind == "procedure":
                for extent in discover_procedure_candidates(requirement, source):
                    plan = discover_plan(requirement, source, extent)
                    inventory = plan.required_inventory(source)
                    seed = inventory.get("seed_clause")
                    paragraphs = inventory.get("declared_paragraphs")
                    first, last = (
                        (seed["source_range"]["start"], seed["source_range"]["end"])
                        if seed
                        else (plan.start, plan.end)
                    )
                    if paragraphs:
                        first, last = (
                            paragraphs["paragraph_ranges"][0][key]
                            for key in ("start", "end")
                        )
                    located = next(
                        (
                            item
                            for item in source.chunks
                            if item.start <= first < last <= item.end
                        ),
                        None,
                    )
                    if located is None:
                        raise ProcedureRejected(
                            "procedure_pattern_seed_unrepresentable"
                        )
                    local.append(
                        make_proposal(
                            requirement.id,
                            source,
                            located.chunk,
                            first - located.start,
                            last - located.start,
                            origin="source_pattern",
                            pattern_id=PARAGRAPH_PATTERN
                            if paragraphs
                            else NUMBERED_PATTERN
                            if seed
                            else NARRATIVE_PATTERN,
                            grammar_version=registry,
                        )
                    )
            else:
                for item in source.chunks:
                    for first, last in role_discovery_ranges(
                        requirement, item.chunk.content
                    ):
                        proposal = make_proposal(
                            requirement.id,
                            source,
                            item.chunk,
                            first,
                            last,
                            origin="source_pattern",
                            pattern_id=ROLE_PATTERN,
                            grammar_version=registry,
                        )
                        if not any(
                            (
                                old.document_start,
                                old.document_end,
                                old.text,
                                old.pattern_id,
                            )
                            == (
                                proposal.document_start,
                                proposal.document_end,
                                proposal.text,
                                proposal.pattern_id,
                            )
                            for old in local
                        ):
                            local.append(proposal)
        except (ValueError, ProcedureRejected) as exc:
            observations.append(
                {
                    **source.identity,
                    "requirement_id": requirement.id,
                    "origin": "source_pattern",
                    "decision": str(exc),
                    "complete": False,
                }
            )
            complete = False
        if len(local) > MAX_PATTERN_PROPOSALS_PER_SOURCE:
            observations.append(
                {
                    **source.identity,
                    "requirement_id": requirement.id,
                    "origin": "source_pattern",
                    "decision": "pattern_source_budget_exceeded",
                    "observed_count": len(local),
                    "complete": False,
                    "truncated": True,
                }
            )
            complete = False
        proposals.extend(local)
    if len(proposals) > MAX_PATTERN_PROPOSALS_PER_REQUIREMENT:
        observations.append(
            {
                "requirement_id": requirement.id,
                "origin": "source_pattern",
                "decision": "pattern_requirement_budget_exceeded",
                "observed_count": len(proposals),
                "complete": False,
                "truncated": True,
            }
        )
        complete = False
    return PatternBatch(
        tuple(proposals) if complete else (), tuple(observations), complete
    )
