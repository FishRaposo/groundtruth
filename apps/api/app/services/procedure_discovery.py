"""Shared pure procedure discovery and inventories, never model decisions.

Relocated from procedure_evidence/procedure_support without changing grammar.
The legacy modules re-export these definitions. Runtime inference is owned there;
only the optional ProcedurePlan.pairs call imports its inference pair DTO lazily.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from app.services.answer_requirements import Requirement
from app.services.requirement_binding import (
    _SECTION_HEAD,
    SupportClaim,
    _step_markers,
    _worksheet_declaration,
    _worksheet_namespace,
    condition_relation,
    named_anchors,
    support_claim,
)
from app.services.requirement_contract import (
    REQUIRED_INVENTORY_CONTRACT,
    numbered_seed_core,
)

if TYPE_CHECKING:
    from app.models.chunk import ChunkWithScore
    from app.services.answer_support import SupportPair

MAX_STEPS = 32
MAX_UNITS = 64
MAX_EDGES = 64


class ProcedureRejected(ValueError):
    """An unsupported source/content plan, never a runtime asset failure."""

    def __init__(
        self,
        code: str,
        source_range: tuple[int, int] | None = None,
        source_form: str | None = None,
        *,
        opposed_source_units: tuple[dict[str, Any], ...] = (),
    ) -> None:
        super().__init__(code)
        self.source_range = source_range
        self.source_form = source_form
        self.opposed_source_units = opposed_source_units


@dataclass(frozen=True)
class LocatedChunk:
    chunk: ChunkWithScore
    start: int
    end: int


@dataclass(frozen=True)
class ProcedureSource:
    body: str
    chunks: tuple[LocatedChunk, ...]
    identity: dict[str, Any]
    metadata: dict[str, Any]
    captured_scope: dict[str, Any] | None


@dataclass(frozen=True)
class ProcedureExtent:
    claim: SupportClaim
    raw_start: int
    raw_end: int
    closure: str
    boundary: tuple[int, int] | None = None


def discover_procedure_candidates(
    requirement: Requirement,
    source: ProcedureSource,
) -> tuple[ProcedureExtent, ...]:
    """Unassessed extents from the exact grammar also used by QA binding."""
    from app.services.procedure_paragraphs import scope_matches
    from app.services.requirement_binding import procedure_discovery_ranges

    declared = _declared_paragraphs(source.body)
    if declared is not None:
        if not scope_matches(declared, requirement.topic):
            return ()
        return (_bind_document_extent(requirement, source, *declared.paragraphs[0]),)

    return tuple(
        _bind_document_extent(requirement, source, first, last)
        for first, last in procedure_discovery_ranges(requirement, source.body)
        if _legacy_discovery_instruction(source.body[first:last])
    )


def _declared_paragraphs(body):
    from app.services.procedure_paragraphs import ParagraphRejected, parse

    try:
        return parse(body)
    except ParagraphRejected as exc:
        raise ProcedureRejected(str(exc)) from exc


def _legacy_discovery_instruction(text):
    """Do not join an unterminated colon caption to a later prose paragraph.

    Legacy complete narrative sentences keep their open action vocabulary;
    this guard uses the literal paragraph boundary, not a new verb whitelist.
    """
    from app.services.requirement_binding import _step_markers

    if _step_markers(text):
        return True
    heading = _SECTION_HEAD.match(text)
    following = text[heading.end() :].lstrip() if heading else text.lstrip()
    ending = re.search(r"[.!?](?=\s|$)", following)
    first_sentence = following[: ending.end()] if ending else following
    return re.search(r"\n[^\S\n]*\n", first_sentence) is None


def _declared_extent(requirement, source, parsed, first, last):
    from app.services.procedure_paragraphs import scope_matches
    from app.services.requirement_binding import (
        _procedure_constraints,
        _procedure_numbers_present,
        _procedure_scope_prohibited,
    )

    if not scope_matches(parsed, requirement.topic):
        raise ProcedureRejected("procedure_activity_mismatch")
    value = source.body[parsed.start : parsed.end]
    if not parsed.start <= first < last <= parsed.end:
        raise ProcedureRejected("procedure_raw_not_in_extent")
    if condition_relation(requirement, source.body, source.metadata) != "applies":
        raise ProcedureRejected("procedure_source_condition_not_established")
    if _procedure_scope_prohibited(requirement, source.body):
        raise ProcedureRejected("procedure_scope_prohibited")
    if not _procedure_constraints(requirement.original_text, value):
        raise ProcedureRejected("procedure_original_constraint_missing")
    if not _procedure_numbers_present(requirement.original_text, value):
        raise ProcedureRejected("procedure_parameter_missing")
    claim = SupportClaim(
        f"The procedure for {requirement.topic} is: {value}",
        value,
        value,
        parsed.start,
        parsed.end,
        None,
    )
    return ProcedureExtent(
        claim, first, last, "declared_paragraph_end", parsed.end_marker
    )


def _bind_document_extent(requirement, source, first, last) -> ProcedureExtent:
    declared = _declared_paragraphs(source.body)
    if declared is not None:
        return _declared_extent(requirement, source, declared, first, last)
    claim = support_claim(requirement, source.body, first, last)
    if claim.rejection or claim.hypothesis is None:
        raise ProcedureRejected(claim.rejection or "procedure_binding_unverified")
    if condition_relation(requirement, source.body, source.metadata) != "applies":
        raise ProcedureRejected("procedure_source_condition_not_established")
    if not (0 <= claim.start <= first < last <= claim.end <= len(source.body)):
        raise ProcedureRejected("procedure_raw_not_in_extent")
    if source.body[claim.start : claim.end] != claim.value:
        raise ProcedureRejected("procedure_extent_not_literal")
    # A complete immutable EOF is evidence. A local chunk limit is never EOF.
    # Unknown trailing governing material is refused rather than dropped.
    tail = source.body[claim.end :]
    if tail.strip():
        offset = claim.end + len(tail) - len(tail.lstrip())
        heading = _SECTION_HEAD.match(source.body[offset:])
        target = (heading.group("scope") or heading.group("title")) if heading else ""
        named = set(named_anchors(target))
        if (
            heading is None
            or not named
            or not requirement.anchors
            or named.intersection(requirement.anchors)
            or (
                heading.group("scope") is None
                and not target.casefold().endswith("procedure")
            )
        ):
            raise ProcedureRejected("procedure_extent_unverified_tail")
        return ProcedureExtent(
            claim, first, last, "independent_section", (offset, offset + heading.end())
        )
    return ProcedureExtent(claim, first, last, "immutable_eof")


# A controlled imperative vocabulary, not an inflector. Explicit actors,
# advice, declaratives, quotations and unknown forms remain unsupported.
VERBS = frozenset(
    (
        "verify check copy compare count record place arrange attach leave carry ask "
        "confirm retain obtain close lock return end skip reopen scan show wait open "
        "sign read select press save stop send keep remove enter inspect review mark "
        "label print put turn restart start disconnect connect hold release notify "
        "submit write collect file take move set use"
    ).split()
)
_SENTENCE = re.compile(r"\S.*?(?:[.!?](?=\s|$)|$)", re.S)
_HEADING = re.compile(r"\A\s*(?P<scope>[^.!?:\n]+?)\s+procedure[.:](?=\s)", re.I)
_APPLICABILITY = re.compile(
    r"(?:^|(?<=[.!?])\s+)(?:this|the\s+following|the)\s+complete\s+(?:procedure|method)\s+applies\s+to\s+(?P<conditions>[^.!?]+)[.!?]",
    re.I,
)


@dataclass(frozen=True)
class ProofUnit:
    name: str
    kind: str
    start: int
    end: int
    hypothesis: str
    premise_start: int | None = None
    premise_end: int | None = None

    @property
    def premise_range(self) -> dict[str, int]:
        return {
            "start": self.start if self.premise_start is None else self.premise_start,
            "end": self.end if self.premise_end is None else self.premise_end,
        }


@dataclass(frozen=True)
class ProcedurePlan:
    start: int
    end: int
    steps: tuple[tuple[int, int, int], ...]
    units: tuple[ProofUnit, ...]
    edges: tuple[dict[str, Any], ...]
    structure: str = "numbered"
    declared_paragraphs: dict[str, Any] | None = None

    def required_inventory(self, source: ProcedureSource) -> dict[str, Any]:
        """Serialize the full source-planned obligations before model assessment."""
        return {
            "contract": REQUIRED_INVENTORY_CONTRACT,
            **source.identity,
            "extent": {"start": self.start, "end": self.end},
            "structure": self.structure,
            "step_ranges": [
                {"ordinal": ordinal, "start": first, "end": last}
                for ordinal, first, last in self.steps
            ],
            "units": [
                {
                    "name": unit.name,
                    "kind": unit.kind,
                    "source_range": {"start": unit.start, "end": unit.end},
                    "premise_range": unit.premise_range,
                    "hypothesis": unit.hypothesis,
                    "step": next(
                        (
                            ordinal
                            for ordinal, first, last in self.steps
                            if unit.kind in {"instruction", "prohibition"}
                            and first <= unit.start < unit.end <= last
                        ),
                        None,
                    ),
                }
                for unit in self.units
            ],
            "structure_edges": [dict(edge) for edge in self.edges],
            **(
                {"seed_clause": _first_clause_descriptor(source.body, self.units)}
                if self.structure == "numbered"
                else {}
            ),
            **(
                {"declared_paragraphs": self.declared_paragraphs}
                if self.declared_paragraphs is not None
                else {}
            ),
        }

    def pairs(
        self, source: ProcedureSource, requirement: Requirement
    ) -> list[SupportPair]:
        from app.services.answer_support import SupportPair

        return [
            SupportPair(
                source.body[u.premise_range["start"] : u.premise_range["end"]],
                u.hypothesis,
                requirement.id,
                f"{source.identity['document_id']}:{u.name}",
            )
            for u in self.units
        ]


def _trim(body: str, left: int, right: int) -> tuple[int, int]:
    while left < right and body[left].isspace():
        left += 1
    while right > left and body[right - 1].isspace():
        right -= 1
    return left, right


def _instruction(body: str, left: int, right: int, name: str) -> ProofUnit:
    left, right = _trim(body, left, right)
    text = body[left:right]
    clause = text.rstrip(".!?")
    if not clause or any(c in clause for c in '"“”'):
        raise ProcedureRejected(
            "procedure_unsupported_instruction_grammar", (left, right), text
        )
    negative = re.match(r"(?:do\s+not|never)\s+([A-Za-z]+)\b", clause, re.I)
    verb = negative.group(1) if negative else clause.split()[0]
    if verb.casefold() not in VERBS:
        raise ProcedureRejected(
            "procedure_unsupported_instruction_grammar", (left, right), text
        )
    preserved = clause[0].lower() + clause[1:]
    hypothesis = (
        f"The instructions require that you {preserved}."
        if negative
        else f"The instructions require you to {preserved}."
    )
    return ProofUnit(
        name, "prohibition" if negative else "instruction", left, right, hypothesis
    )


def _reject_internal_opposition(body: str, units: list[ProofUnit]) -> None:
    """Only exact whole predicates oppose; never erase arguments or conditions."""
    seen: dict[str, dict[str, ProofUnit]] = {}
    for unit in units:
        if unit.kind not in {"instruction", "prohibition"}:
            continue
        predicate = body[unit.start : unit.end].strip().rstrip(".!?").strip()
        if unit.kind == "prohibition":
            predicate = re.sub(r"^(?:do\s+not|never)\s+", "", predicate, flags=re.I)
        key = " ".join(predicate.casefold().split())
        other = "instruction" if unit.kind == "prohibition" else "prohibition"
        matches = seen.setdefault(key, {})
        if other in matches:
            raise ProcedureRejected(
                "procedure_internal_opposition",
                opposed_source_units=tuple(
                    {
                        "name": item.name,
                        "kind": item.kind,
                        "source_range": {"start": item.start, "end": item.end},
                        "source_form": body[item.start : item.end],
                        "hypothesis": item.hypothesis,
                    }
                    for item in (matches[other], unit)
                ),
            )
        matches[unit.kind] = unit


def _first_clause_descriptor(
    body: str, units: Sequence[ProofUnit]
) -> dict[str, Any] | None:
    first = next((unit for unit in units if unit.name == "step_1_action_1"), None)
    if first is None:
        return None
    return {
        "unit_name": first.name,
        "source_range": {"start": first.start, "end": first.end},
        "text": body[first.start : first.end],
    }


def _complete_first_clause_seed(
    body: str, units: list[ProofUnit], extent: ProcedureExtent
) -> bool:
    return (
        numbered_seed_core(
            _first_clause_descriptor(body, units),
            body[extent.raw_start : extent.raw_end],
            {"start": extent.raw_start, "end": extent.raw_end},
            len(body),
        )
        is not None
    )


def build_plan(  # noqa: C901 - bounded complete grammar and mandatory proof inventory
    requirement: Requirement, source: ProcedureSource, extent: ProcedureExtent
) -> ProcedurePlan:
    return _build_plan(requirement, source, extent, validate_seed=True)


def discover_plan(
    requirement: Requirement, source: ProcedureSource, extent: ProcedureExtent
) -> ProcedurePlan:
    """Inventory all structural obligations before choosing a source seed."""
    return _build_plan(requirement, source, extent, validate_seed=False)


def _build_plan(  # noqa: C901 - shared grammar, seed checks remain mandatory for binding
    requirement: Requirement,
    source: ProcedureSource,
    extent: ProcedureExtent,
    *,
    validate_seed: bool,
) -> ProcedurePlan:
    body, claim = source.body, extent.claim
    if extent.closure == "declared_paragraph_end":
        return _declared_plan(requirement, source, extent, validate_seed=validate_seed)
    markers = _step_markers(body[claim.start : claim.end])
    if not markers:
        return _narrative_plan(requirement, source, extent)
    if not markers or any(m.group(1) is None for m in markers):
        raise ProcedureRejected("procedure_numeric_order_required")
    numbers = [int(m.group(1)) for m in markers]
    if numbers != list(range(1, len(numbers) + 1)):
        raise ProcedureRejected("procedure_order_unverified")
    if len(markers) > MAX_STEPS:
        raise ProcedureRejected("procedure_support_budget_exceeded")
    first_step = claim.start + markers[0].start(1)
    declaration = _worksheet_declaration(body[:first_step])
    namespace = (
        _worksheet_namespace(requirement, body, declaration.start())
        if declaration
        else None
    )
    worksheet = namespace is not None
    if not worksheet:
        namespace = _HEADING.match(body)
        declarations = list(_APPLICABILITY.finditer(body, 0, first_step))
        declaration = declarations[-1] if len(declarations) == 1 else None
    if (
        namespace is None
        or declaration is None
        or namespace.end() > declaration.start()
    ):
        raise ProcedureRejected("procedure_governance_unverified")
    conditions = declaration.group("conditions").strip()
    if re.search(r"\b(?:unless|except|not|never)\b", conditions, re.I):
        raise ProcedureRejected("procedure_unsupported_applicability_grammar")
    ns_start, ns_end = _trim(body, namespace.start(), namespace.end())
    app_start, app_end = _trim(body, declaration.start(), declaration.end())
    scope = namespace.group("scope").strip()
    units = [
        ProofUnit(
            "namespace",
            "namespace",
            ns_start,
            ns_end,
            f"This worksheet convention is for {scope}."
            if worksheet
            else f"This procedure is for {scope}.",
        ),
        ProofUnit(
            "applicability",
            "applicability",
            app_start,
            app_end,
            f"The complete procedure applies to {conditions}.",
        ),
        ProofUnit(
            "requested_scope",
            "request_scope",
            ns_start,
            app_end,
            f"The complete procedure is for {requirement.topic}.",
        ),
    ]
    edges: list[dict[str, Any]] = [
        {
            "name": "namespace_to_applicability",
            "source": "namespace",
            "target": "applicability",
        }
    ]
    starts = [claim.start + m.start(1) for m in markers]
    steps = []
    start = min(claim.start, app_start)
    # Inventory every prelude sentence. Only the actual governing heading and
    # applicability declaration are structural; other sentences need proofs.
    for i, sentence in enumerate(_SENTENCE.finditer(body, 0, first_step)):
        left, right = _trim(body, sentence.start(), sentence.end())
        if (left, right) in {(ns_start, ns_end), (app_start, app_end)}:
            continue
        if not body[left:right].strip():
            continue
        unit = _instruction(body, left, right, f"prelude_{i + 1}")
        units.append(unit)
        edges.append(
            {"name": "namespace_to_action", "source": "namespace", "target": unit.name}
        )
        start = min(start, left)
    for i, marker in enumerate(markers):
        left = starts[i]
        right = starts[i + 1] if i + 1 < len(starts) else claim.end
        steps.append((i + 1, left, right))
        instruction_start = claim.start + marker.end()
        for ordinal, sentence in enumerate(
            _SENTENCE.finditer(body, instruction_start, right)
        ):
            unit = _instruction(
                body,
                sentence.start(),
                sentence.end(),
                f"step_{i + 1}_action_{ordinal + 1}",
            )
            units.append(replace(unit, premise_start=left, premise_end=right))
            edges.append(
                {
                    "name": "applicability_to_action",
                    "source": "applicability",
                    "target": unit.name,
                    "step": i + 1,
                }
            )
    # Preserve every supplementary binder check, including configured arguments
    # and destinations. They cannot be replaced by a broad namespace check.
    for i, check in enumerate(claim.checks):
        left, right = check.start, check.end
        if (
            type(left) is not int
            or type(right) is not int
            or not 0 <= left < right <= len(body)
            or body[left:right] != check.premise
        ):
            raise ProcedureRejected("procedure_condition_not_source_bound")
        units.append(
            ProofUnit(
                f"bound_condition_{i + 1}",
                "bound_condition",
                left,
                right,
                check.hypothesis,
            )
        )
    if len(units) > MAX_UNITS or len(edges) > MAX_EDGES:
        raise ProcedureRejected("procedure_support_budget_exceeded")
    _reject_internal_opposition(body, units)
    core_start, core_end = _trim(body, extent.raw_start, extent.raw_end)
    if validate_seed and not any(
        u.kind in {"instruction", "prohibition"}
        and u.start <= core_start < core_end <= u.end
        for u in units
    ):
        raise ProcedureRejected("procedure_raw_not_in_mandatory_action_premise")
    if (
        validate_seed
        and not steps[0][1] <= extent.raw_start < extent.raw_end <= steps[0][2]
    ):
        raise ProcedureRejected("procedure_first_step_seed_required")
    if validate_seed and not _complete_first_clause_seed(body, units, extent):
        raise ProcedureRejected("procedure_full_first_clause_seed_required")
    return ProcedurePlan(start, claim.end, tuple(steps), tuple(units), tuple(edges))


def _declared_plan(requirement, source, extent, *, validate_seed):
    from app.services.procedure_paragraphs import (
        STRUCTURE,
        parse,
        seed_matches,
        unit_specs,
    )

    parsed = parse(source.body)
    if parsed is None:
        raise ProcedureRejected("procedure_paragraph_declaration_unverified")
    if validate_seed and not seed_matches(
        parsed,
        source.body[extent.raw_start : extent.raw_end],
        (extent.raw_start, extent.raw_end),
    ):
        raise ProcedureRejected("procedure_paragraph_first_seed_required")
    specs, edges = unit_specs(parsed, requirement.topic, requirement.original_text)
    units = tuple(
        ProofUnit(
            s["name"],
            s["kind"],
            s["source_range"]["start"],
            s["source_range"]["end"],
            s["hypothesis"],
            s["premise_range"]["start"],
            s["premise_range"]["end"],
        )
        for s in specs
    )
    if len(units) > MAX_UNITS or len(edges) > MAX_EDGES:
        raise ProcedureRejected("procedure_support_budget_exceeded")
    _reject_declared_opposition(source.body, parsed.paragraphs)
    return ProcedurePlan(
        parsed.start,
        parsed.end,
        (),
        units,
        tuple(edges),
        STRUCTURE,
        parsed.record(requirement.topic, requirement.original_text),
    )


def _reject_declared_opposition(body, paragraphs):
    # Sentence boundaries cannot erase a conditional prefix: each entire source
    # sentence participates, and only exact whole positive/negative predicates oppose.
    units = []
    for left, right in paragraphs:
        for sentence in _SENTENCE.finditer(body, left, right):
            first, last = _trim(body, sentence.start(), sentence.end())
            negative = re.match(r"(?:do\s+not|never)\b", body[first:last], re.I)
            units.append(
                ProofUnit(
                    str(len(units)),
                    "prohibition" if negative else "instruction",
                    first,
                    last,
                    "",
                )
            )
    _reject_internal_opposition(body, units)


def _narrative_plan(
    requirement: Requirement, source: ProcedureSource, extent: ProcedureExtent
) -> ProcedurePlan:
    """Preserve the binder's complete scoped narrative relation, without counting steps.

    The literal entire extent is mandatory, as are every existing supplementary
    condition/goal check. Oversized pairs are refused by the unchanged tokenizer
    budget; this path never rewrites narrative prose into guessed imperatives.
    """
    body, claim = source.body, extent.claim
    if body[: claim.start].strip() or claim.premise != body[claim.start : claim.end]:
        raise ProcedureRejected("procedure_narrative_full_premise_unverified")
    if (
        not isinstance(claim.hypothesis, str)
        or claim.hypothesis.strip() == claim.premise.strip()
    ):
        raise ProcedureRejected("procedure_narrative_relation_unverified")
    units = [
        ProofUnit(
            "whole_method", "whole_method", claim.start, claim.end, claim.hypothesis
        )
    ]
    for index, check in enumerate(claim.checks):
        left, right = check.start, check.end
        if (
            type(left) is not int
            or type(right) is not int
            or not 0 <= left < right <= len(body)
            or body[left:right] != check.premise
        ):
            raise ProcedureRejected("procedure_condition_not_source_bound")
        units.append(
            ProofUnit(
                f"bound_condition_{index + 1}",
                "bound_condition",
                left,
                right,
                check.hypothesis,
            )
        )
    if len(units) > MAX_UNITS:
        raise ProcedureRejected("procedure_support_budget_exceeded")
    if not claim.start <= extent.raw_start < extent.raw_end <= claim.end:
        raise ProcedureRejected("procedure_raw_not_in_mandatory_action_premise")
    return ProcedurePlan(claim.start, claim.end, (), tuple(units), (), "narrative")
