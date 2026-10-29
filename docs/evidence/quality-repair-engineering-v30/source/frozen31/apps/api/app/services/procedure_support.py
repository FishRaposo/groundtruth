"""Fixed, source-preserving imperative proofs for complete procedure extents.

Templates are chosen by grammar, never by classifier score. Unknown source
sentences are rejected, not omitted. No morphology or generative rewriting.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from app.services.answer_requirements import Requirement
from app.services.answer_support import SupportPair
from app.services.procedure_evidence import (
    ProcedureExtent,
    ProcedureRejected,
    ProcedureSource,
)
from app.services.requirement_binding import (
    _step_markers,
    _worksheet_declaration,
    _worksheet_namespace,
)
from app.services.requirement_contract import (
    REQUIRED_INVENTORY_CONTRACT,
    numbered_seed_core,
)

MAX_STEPS = 32
MAX_UNITS = 64
MAX_EDGES = 64
COPY_PROFILE = "source_declared_procedure_copy_v1"


def verification_method(unit: ProofUnit) -> str:
    if (
        unit.kind in {"namespace", "applicability", "bound_condition"}
        and unit.name != "paragraph_request_constraints"
    ):
        return "nli_entailment"
    return (
        "exact_source_copy"
        if unit.kind in {"instruction", "prohibition"}
        else "exact_source_structure"
    )


def copy_request_binding(
    requirement: Requirement, question: str, *, plan=None, source=None
) -> dict[str, Any]:
    """Consume the complete atomic request, preserving the public planner's scope.

    Source parsing remains the existing binder's responsibility. This closed
    request grammar admits coverage categories, never arbitrary added conditions.
    Independent factual clauses remain separately planned NLI requirements.
    """
    topic = re.escape(requirement.topic)
    atom = (
        r"(?:(?:its|the|every|all|each)\s+)?(?:(?:exact|final|last|opening|closing|ordered|material)\s+)*"
        r"(?:prerequisites?|conditions?|parameters?|settings?|measurements?|prohibitions?|forbidden\s+actions?|closure|reconciliation\s+steps?|actions?|instructions?)"
    )
    features = rf"{atom}(?:(?:,\s*(?:and\s+)?|\s+and\s+){atom})*"
    coverage = rf"(?:,\s*(?:in order,\s*)?including\s+{features})?"
    patterns = (
        (
            r"(?:Give|Provide|State|Quote)\s+(?:the\s+)?(?:entire|complete|full)"
            r"(?:\s+ordered)?(?:\s+(?:ordinary|standard|normal))?\s+"
            r"(?:procedure|method|instructions|steps)\s+(?:for|of)\s+"
            rf"(?:the\s+)?{topic}{coverage}[.!?]?"
        ),
        (
            r"How do I carry out the complete (?:ordinary|standard|normal) "
            rf"routine at the {topic}\? Quote the full ordered instructions, "
            r"from prerequisites through final closure[.]?"
        ),
        (
            rf"Provide all instructions for an? {topic}, "
            rf"retaining their order and {features}[.]?"
        ),
        rf"I need the full {topic} procedure, including {features}[.]?",
    )
    original = requirement.original_text.strip()
    if plan is not None and plan.structure == "numbered":
        if source is None or not numbered_topic_matches(requirement, source, plan):
            raise ProcedureRejected("procedure_request_scope_not_fully_consumed")
    if plan is not None and plan.declared_paragraphs is not None:
        modes = set(re.findall(r"\b(?:ordinary|standard|normal)\b", original, re.I))
        if modes and {m.casefold() for m in modes} != {
            plan.declared_paragraphs["mode"].casefold()
        }:
            raise ProcedureRejected("procedure_request_mode_mismatch")
    if question[
        requirement.input_start : requirement.input_end
    ] != requirement.original_text or not any(
        re.fullmatch(p, original, re.I) for p in patterns
    ):
        raise ProcedureRejected("procedure_request_not_fully_consumed")
    return {
        "question": question,
        "requirement_id": requirement.id,
        "original_text": requirement.original_text,
        "input_range": {"start": requirement.input_start, "end": requirement.input_end},
        "topic": requirement.topic,
    }


def numbered_topic_matches(requirement, source, plan) -> bool:
    """Consume a topic using the existing canonical source namespace/declaration.

    A namespace substring is discovery context, not a complete request match.
    No unit hypothesis or producer-supplied topic descriptor establishes scope.
    """
    namespace_unit = next(u for u in plan.units if u.kind == "namespace")
    applicability = next(u for u in plan.units if u.kind == "applicability")
    first_step = plan.steps[0][1]
    namespace = _worksheet_namespace(requirement, source.body, applicability.start)
    worksheet = namespace is not None and _trim(
        source.body, namespace.start(), namespace.end()
    ) == (namespace_unit.start, namespace_unit.end)
    if worksheet:
        declaration = _worksheet_declaration(source.body[:first_step])
    else:
        namespace = _HEADING.match(source.body)
        declarations = list(_APPLICABILITY.finditer(source.body, 0, first_step))
        declaration = declarations[0] if len(declarations) == 1 else None
    if (
        namespace is None
        or declaration is None
        or _trim(source.body, declaration.start(), declaration.end())
        != (applicability.start, applicability.end)
    ):
        return False

    def normal(text):
        if worksheet:
            text = text.replace("-", " ")
        return re.sub(r"^(?:the|an?)\s+", "", " ".join(text.casefold().split()))

    scope = normal(namespace.group("scope"))
    conditions = normal(declaration.group("conditions"))
    topic = normal(requirement.topic)
    mode = re.match(r"(ordinary|standard|normal)\b", conditions)
    requested_modes = set(
        re.findall(
            r"\b(?:ordinary|standard|normal)\b", requirement.original_text.casefold()
        )
    )
    if mode and requested_modes - {mode.group(1)}:
        return False
    if not worksheet:
        return topic in {scope, conditions}
    # The source's entire class qualification is literal. Do not drop an
    # unknown prefix, noun class, suffix, condition, object or measurement.
    declared = re.fullmatch(r"(ordinary|standard|normal) worksheets?(.*)", conditions)
    if declared is None:
        return False
    qualifier, tail = declared.groups()
    prefix = f"{qualifier} {scope} "
    allowed = {prefix + noun + tail for noun in ("worksheet", "worksheets")}
    mark = re.fullmatch(r" with no (.+)", tail)
    if mark is not None:
        # Existing factorable worksheet spellings, with the source's exact mark.
        value = mark.group(1)
        allowed.update(
            {
                prefix + f"with no {value}",
                prefix + f"worksheet bearing no {value}",
                prefix + f"no {value} procedure",
                prefix + f"no {value} method",
            }
        )
    return topic in allowed


async def assess_plan(plan, source, requirement, config, service, *, copy=False):
    """Keep all obligations; only source-exact obligations avoid model inference."""
    if copy and not {"namespace", "applicability"}.issubset(
        {u.kind for u in plan.units}
    ):
        raise ProcedureRejected("procedure_copy_source_declaration_required")
    chosen = [
        u for u in plan.units if not copy or verification_method(u) == "nli_entailment"
    ]
    pairs = [
        SupportPair(
            source.body[u.premise_range["start"] : u.premise_range["end"]],
            u.hypothesis,
            requirement.id,
            f"{source.identity['document_id']}:{u.name}",
        )
        for u in chosen
    ]
    decisions = await service.assess(pairs, config=config)
    if len(decisions) != len(chosen):
        raise RuntimeError("Incomplete procedure support decisions")
    from dataclasses import asdict

    assessed = dict(zip((u.name for u in chosen), decisions, strict=True))
    records = []
    for unit in plan.units:
        record = {
            "name": unit.name,
            "kind": unit.kind,
            "source_range": {"start": unit.start, "end": unit.end},
            "premise_range": unit.premise_range,
            "hypothesis": unit.hypothesis,
        }
        if copy:
            record["verification_method"] = verification_method(unit)
        if unit.name in assessed:
            record.update(asdict(assessed[unit.name]))
        else:
            record["supported"] = True
        records.append(record)
    return decisions, records


async def assess_condition_scope(source, requirement, scope, config, service) -> bool:
    """Verify exclusive applicability using the entire opponent, never QA.

    A literal condition is only a proposal. Unknown/mixed governing material is
    part of this mandatory pair; no source prefix or selected fragment replaces
    the full premise, and the existing tokenizer budget remains authoritative.
    """
    from dataclasses import asdict

    from app.evidence_policy import resolve_evidence_policy
    from app.services.answer_reader import reader_service
    from app.services.requirement_contract import condition_model_settings

    scope["model_settings"] = condition_model_settings(
        reader_service.metadata(config),
        service.metadata(config),
        {
            "max_length": config.READER_MAX_LENGTH,
            "stride": config.READER_STRIDE,
            "n_best": config.READER_N_BEST,
            "max_span_tokens": config.READER_MAX_SPAN_TOKENS,
        },
        resolve_evidence_policy(config).record(),
        config.GENERATION_MODE,
    )
    if scope.get("contract") in (
        "procedure-condition-scope-v2",
        "procedure-condition-scope-v3",
    ):
        method = "contextual_source_reading_and_nli"
        if scope["contract"] == "procedure-condition-scope-v3":
            from app.services.source_context_references import (
                compile_reference_obligation,
                exact_structure_equal,
                obligation_plan,
            )

            reading = scope["context_reading"]
            if not exact_structure_equal(
                scope.get("obligation_plan"), obligation_plan(reading)
            ) or not exact_structure_equal(
                scope.get("reference_obligations"),
                [compile_reference_obligation(reading)],
            ):
                raise ValueError("Invalid mandatory reference structure")
            method = "contextual_source_reading_nli_and_exact_reference"
        pairs = [
            SupportPair(
                source.body[
                    check["premise_range"]["start"] : check["premise_range"]["end"]
                ],
                check["hypothesis"],
                requirement.id,
                f"{source.identity['document_id']}:context-scope:{check['name']}",
            )
            for check in scope["semantic_checks"]
        ]
        decisions = await service.assess(pairs, config=config)
        if len(decisions) != len(pairs):
            raise RuntimeError("Incomplete contextual source scope decisions")
        from app.services.requirement_contract import valid_condition_assessment

        verified = True
        for check, pair, decision in zip(
            scope["semantic_checks"], pairs, decisions, strict=True
        ):
            check.update(
                pair=asdict(pair),
                assessment=asdict(decision),
                verification_method="nli_entailment",
            )
            verified = (
                valid_condition_assessment(check["assessment"], scope["model_settings"])
                and verified
            )
        scope["verification_method"] = method
        scope["reason"] = (
            "verified_contextual_excluded_source_condition"
            if verified
            else "procedure_condition_scope_unconfirmed"
        )
        return verified
    pair = SupportPair(
        source.body,
        scope["hypothesis"],
        requirement.id,
        f"{source.identity['document_id']}:condition-scope",
    )
    scope["pair"] = asdict(pair)
    decisions = await service.assess(
        [pair],
        config=config,
    )
    if len(decisions) != 1:
        raise RuntimeError("Incomplete procedure condition scope decisions")
    decision = decisions[0]
    scope["assessment"] = asdict(decision)
    scope["verification_method"] = "nli_entailment"
    verified = (
        decision.supported
        and decision.label == "entailment"
        and type(decision.pair_tokens) is int
        and 0 < decision.pair_tokens <= 512
    )
    scope["reason"] = (
        "verified_excluded_source_condition"
        if verified
        else "procedure_condition_scope_unconfirmed"
    )
    return verified


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
