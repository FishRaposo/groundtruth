"""Closed typed discovery registry. A proposal is never a support decision."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evidence_policy import (
    MAX_PATTERN_PROPOSALS_PER_REQUIREMENT,
    MAX_PATTERN_PROPOSALS_PER_SOURCE,
    PATTERN_REGISTRY_CONTRACT,
)
from app.services.evidence_proposals import (
    EvidenceProposal,
    make_proposal,
    validate_source,
)
from app.services.procedure_evidence import (
    ProcedureRejected,
    discover_procedure_candidates,
)
from app.services.procedure_paragraphs import PATTERN as PARAGRAPH_PATTERN
from app.services.procedure_support import discover_plan
from app.services.requirement_binding import role_discovery_ranges

ROLE_PATTERN = "literal-lead-deputy-v1"
NUMBERED_PATTERN = "complete-numbered-procedure-v1"
NARRATIVE_PATTERN = "complete-narrative-procedure-v1"
PATTERN_IDS = frozenset(
    {ROLE_PATTERN, NUMBERED_PATTERN, NARRATIVE_PATTERN, PARAGRAPH_PATTERN}
)


@dataclass(frozen=True)
class PatternBatch:
    proposals: tuple[EvidenceProposal, ...]
    observations: tuple[dict[str, Any], ...]
    complete: bool


def collect_source_proposals(requirement, sources) -> PatternBatch:  # noqa: C901 - closed bounded registry
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
            if requirement.kind == "procedure":
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
                            grammar_version=PATTERN_REGISTRY_CONTRACT,
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
                            grammar_version=PATTERN_REGISTRY_CONTRACT,
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
