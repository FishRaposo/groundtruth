"""Fixed, source-preserving imperative proofs for complete procedure extents.

Templates are chosen by grammar, never by classifier score. Unknown source
sentences are rejected, not omitted. No morphology or generative rewriting.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.answer_requirements import Requirement
from app.services.answer_support import SupportPair
from app.services.procedure_discovery import (
    _APPLICABILITY as _APPLICABILITY,
)
from app.services.procedure_discovery import (
    _HEADING as _HEADING,
)
from app.services.procedure_discovery import (
    _SENTENCE as _SENTENCE,
)
from app.services.procedure_discovery import (
    MAX_EDGES as MAX_EDGES,
)
from app.services.procedure_discovery import (
    MAX_STEPS as MAX_STEPS,
)
from app.services.procedure_discovery import (
    MAX_UNITS as MAX_UNITS,
)
from app.services.procedure_discovery import (
    VERBS as VERBS,
)
from app.services.procedure_discovery import (
    ProcedurePlan as ProcedurePlan,
)
from app.services.procedure_discovery import (
    ProofUnit as ProofUnit,
)
from app.services.procedure_discovery import (
    _build_plan as _build_plan,
)
from app.services.procedure_discovery import (
    _complete_first_clause_seed as _complete_first_clause_seed,
)
from app.services.procedure_discovery import (
    _declared_plan as _declared_plan,
)
from app.services.procedure_discovery import (
    _first_clause_descriptor as _first_clause_descriptor,
)
from app.services.procedure_discovery import (
    _instruction as _instruction,
)
from app.services.procedure_discovery import (
    _narrative_plan as _narrative_plan,
)
from app.services.procedure_discovery import (
    _reject_declared_opposition as _reject_declared_opposition,
)
from app.services.procedure_discovery import (
    _reject_internal_opposition as _reject_internal_opposition,
)
from app.services.procedure_discovery import (
    _trim as _trim,
)
from app.services.procedure_discovery import (
    build_plan as build_plan,
)
from app.services.procedure_discovery import (
    discover_plan as discover_plan,
)
from app.services.procedure_evidence import (
    ProcedureRejected,
)
from app.services.requirement_binding import (
    _worksheet_declaration,
    _worksheet_namespace,
)

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
