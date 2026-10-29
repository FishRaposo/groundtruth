"""Bounded native/identity/governance controls, no generated fuzz or model use."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from app.services import captured_plan_binding as binding
from app.services import captured_planning_support as support
from app.services import planning_declarations as source
from app.services.captured_plan_inputs import capture_inputs_v2
from app.services.staged_answer_planning import source_snapshots

from tests.captured_productions_unit931.test_request import BASE
from tests.planning_library_unit830.test_support import metadata, retained
from tests.staged_plan_unit837.fixtures_source import capture

from .test_plan import case
from .test_runtime import inspection
from .test_structure import captured


def supported(name="labels"):
    args = {**case(name), "support_metadata": metadata()}
    prepared = support.prepare_planning_assertions(**args)
    observations, executions = retained(prepared)
    args.update(observations=observations, actual_executions=executions)
    return args, binding.reconstruct_captured_plan(**args)


@pytest.mark.parametrize(
    "change", ["model", "tokens", "numeric", "pair", "execution_id", "channel"]
)
def test_receipt_mutations_cannot_claim_planning_support(change):
    args, _ = supported()
    executions = args["actual_executions"]
    first = executions[0]
    if change == "model":
        meta = json.loads(first.support_metadata_json)
        meta["revision"] = "forged"
        first = replace(first, support_metadata_json=source.canonical(meta))
    elif change == "tokens":
        first = replace(first, pair_tokens=True)
    elif change == "numeric":
        assessment = json.loads(first.assessment_json)
        assessment["logits"] = [0.0, -3.0, 3.0]
        first = replace(first, assessment_json=source.canonical(assessment))
    elif change == "pair":
        first = replace(first, pair=replace(first.pair, hypothesis="unrelated fact"))
    elif change == "execution_id":
        first = replace(first, execution_id=executions[1].execution_id)
    else:
        first = replace(first, capture_kind="producer_supported")
    args["actual_executions"] = (first, *executions[1:])
    with pytest.raises(ValueError):
        binding.reconstruct_captured_plan(**args)


@pytest.mark.parametrize(
    "change", ["kind", "id", "historical", "unit", "binding", "readiness"]
)
def test_presented_plan_is_reconstructed_not_trusted(change):
    args, plan = supported("actors-dependent")
    record = plan.record()
    if change in {"kind", "id"}:
        record["requirements"][0][change] = "forged"
    elif change == "historical":
        partial = json.loads(record["structure_json"])
        partial["historical_partial"]["unknowns"] = []
        record["structure_json"] = source.canonical(partial)
    elif change == "unit":
        operations = json.loads(record["operation_ledger_json"])
        operations.pop()
        record["operation_ledger_json"] = source.canonical(operations)
    elif change == "binding":
        edges = json.loads(record["edges_json"])
        edges[-1]["value_slot_id"] = "forged"
        record["edges_json"] = source.canonical(edges)
    else:
        record["publication_ready"] = True
    assert not binding.validate_captured_plan(record, **args)


def test_current_authoritative_title_and_non_cited_source_cannot_be_dropped():
    args, _ = supported()
    inputs = capture_inputs_v2(**args)
    actual = source_snapshots(inspection(args))
    current = deepcopy(actual)
    last = next(reversed(current))
    current[last]["title"] += " changed"
    with pytest.raises(ValueError):
        binding.reconstruct_request(
            inputs,
            question=args["question"],
            authoritative_snapshots=current,
            retained_inputs=inputs,
        )
    current = deepcopy(actual)
    current.pop(last)
    with pytest.raises(ValueError):
        binding.reconstruct_request(
            inputs,
            question=args["question"],
            authoritative_snapshots=current,
            retained_inputs=inputs,
        )


@pytest.mark.parametrize(
    "metadata_value", [{"condition": "pending"}, {"conflict_group": "opponents"}]
)
def test_curated_governance_never_becomes_copy_domain_waiver(metadata_value):
    args = case()
    snapshots = list(args["snapshots"])
    snapshots[-1] = replace(
        snapshots[-1], metadata_json=source.canonical(metadata_value)
    )
    args["snapshots"] = tuple(snapshots)
    candidate = binding.prepare_candidate_plan(**args)
    assert any(
        r["reason"] == "source_governance_or_production_unresolved"
        for r in json.loads(candidate.unresolved_json)
    )
    assert len(json.loads(candidate.operation_ledger_json)) == 20


def test_declared_sources_with_missing_capture_membership_fail_closed():
    args = case()
    args["source_captures"] = args["source_captures"][:-1]
    with pytest.raises(ValueError):
        binding.prepare_candidate_plan(**args)


@pytest.mark.parametrize("kind", ["modifier", "reference", "condition", "negation"])
def test_unknown_request_material_stays_unresolved_with_original_bytes(kind):
    rows = list(BASE)
    extra = {
        "modifier": ("eligible", "ADJ", "eligible", "amod", 3),
        "reference": ("its", "PRON", "its", "poss", 3),
        "negation": ("not", "PART", "not", "neg", 3),
    }
    if kind == "condition":
        rows = rows[:-1] + [
            ("before", "ADP", "before", "prep", 2),
            ("approval", "NOUN", "approval", "pobj", 6),
            (".", "PUNCT", ".", "punct", 2),
        ]
    else:
        rows = [
            (word, pos, lemma, dep, head + (head >= 1))
            for word, pos, lemma, dep, head in rows
        ]
        rows.insert(1, extra[kind])
    question, annotation = capture([rows])
    result = binding.prepare_structure(
        question, annotation, reading_profile="contextual_source_v4"
    )
    assert result["unresolved"]
    assert result["original_capture"] == annotation
    assert (
        "".join(t["token"]["text"] + t["whitespace"] for t in result["consumption"])
        == question
    )


def test_unknown_dependent_antecedent_is_not_guessed():
    row = captured("actors-dependent")
    from app.services.request_parser import _proposals, make_capture

    annotation = deepcopy(row["capture"]["annotation"])
    # UNITONLY structural mutant: same raw bytes, reference attached elsewhere.
    annotation["tokens"][7]["head"] = 5
    annotation["tokens"][8]["children"].remove(7)
    annotation["tokens"][5]["children"].append(7)
    annotation["tokens"][5]["children"].sort()
    annotation["linguistic_proposals"] = _proposals(
        annotation["tokens"], annotation["sentences"]
    )
    observed = make_capture(annotation)
    result = binding.prepare_structure(
        row["text"], observed, reading_profile="contextual_source_v4"
    )
    assert result["unresolved"]
    assert not result["edges"]


def test_unscoped_fact_remains_possible_governance_not_accounted_by_domain():
    from tests.captured_inputs_unit932.fixtures import profile
    from tests.captured_productions_unit931.fixtures import unit_inputs

    rows = [
        ("Availability", "NOUN", "availability", "nsubj", 1),
        ("is", "AUX", "be", "ROOT", 1),
        ("mornings", "NOUN", "morning", "attr", 1),
        (".", "PUNCT", ".", "punct", 1),
    ]
    args = unit_inputs([rows])
    candidate = binding.prepare_candidate_plan(**args, evidence_profile=profile())
    operations = json.loads(candidate.operation_ledger_json)
    factual = [r for r in operations if r["raw"]["text"].strip()]
    assert factual[0]["disposition"] == "UNRESOLVED_POSSIBLE_GOVERNANCE"
