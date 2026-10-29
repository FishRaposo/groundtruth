"""Actual990 syntax/QA; pure slot binding, no plan/NI/currentness acceptance."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from app.services.answer_requirements import Requirement
from app.services.captured_plan_binding import CapturedRequestPlan
from app.services.captured_plan_requirements import CapturedRequirementUse
from app.services.linguistic_requirements import LiteralRange
from app.services.literal_quantity import (
    QuantityUnresolved,
    _bound_qualified_amount,
    _count_nominal,
    consume_quantity_candidate,
    produce_quantity_candidate,
)


def actual():
    data = json.loads(
        (Path(__file__).parent / "fixtures/qualified_count_actual1008.json").read_text(
            encoding="utf-8"
        )
    )
    raw = data["plan"]
    req = Requirement(
        **{
            **raw["requirements"][0],
            "anchors": tuple(raw["requirements"][0]["anchors"]),
            "depends_on": (),
        }
    )
    use = dict(raw["uses"][0])
    use["original"] = LiteralRange(**use["original"])
    for key in (
        "scopes",
        "conditions",
        "modality",
        "units",
        "governors",
        "references",
        "order_evidence",
        "quantifiers",
        "negation",
    ):
        use[key] = tuple(LiteralRange(**r) for r in use[key])
    for key in (
        "order_after",
        "head_token_indices",
        "consumed_token_indices",
        "execution_dependencies",
        "condition_ast",
    ):
        use[key] = tuple(use[key])
    plan = CapturedRequestPlan(
        question=raw["question"],
        evidence_profile_json=raw["evidence_profile_json"],
        requirements=(req,),
        uses=(CapturedRequirementUse(**use),),
        structure_json=json.dumps(
            {
                "question": raw["question"],
                "original_capture": data["request_capture"],
                "syntax_unresolved": data["syntax_unresolved"],
            }
        ),
        source_productions_json=json.dumps(
            {
                "original_inputs": {
                    "snapshots": data["snapshots"],
                    "source_captures": data["source_captures"],
                }
            }
        ),
    )
    snapshot = data["snapshots"][0]
    identity = {k: v for k, v in snapshot["identity"].items() if k != "snapshot_id"}
    return data, req, plan, snapshot, identity


def produce(index=0, *, requirement=None, plan_override=None):
    data, req, plan, snapshot, identity = actual()
    raw = data["candidates"][index]["raw_span"]
    options = {
        "source_identity": identity,
        "chunk_content": snapshot["body"],
        "chunk_start": 0,
        "raw_start": raw["start"],
        "raw_end": raw["end"],
        "evidence_profile": json.loads(plan.evidence_profile_json),
        "request_plan": plan if plan_override is None else plan_override,
    }
    return produce_quantity_candidate(
        req if requirement is None else requirement, snapshot["body"], **options
    ), options


@pytest.mark.parametrize("index", [0, 1])
def test_actual_requested_qualified_number_and_amount_reconstruct(index):
    (claim, binding), options = produce(index)
    data, req, _, snapshot, _ = actual()
    assert claim.value == "4 sibling leaves"
    assert claim.premise == "A Hazel Square leaf merge batch contains 4 sibling leaves."
    assert (
        claim.hypothesis == "The the sibling-leaf quantity for Hazel Square leaf merge "
        "is 4 sibling leaves."
    )
    assert binding["canonical_value"] == {"number": "4", "unit": "sibling leaves"}
    assert binding["model_support"] == "NOT_ASSERTED"
    assert binding["counted_np_alignment"]["requested_np"]["text"] == "sibling-leaf"
    assert binding["counted_np_alignment"]["source_np"]["text"] == "sibling leaves"
    assert binding["raw_value"]["text"] == ("4", "4 sibling leaves")[index]
    assert consume_quantity_candidate(binding, req, snapshot["body"], **options) == (
        claim,
        binding,
    )
    changed = deepcopy(binding)
    changed["canonical_value"]["unit"] = "leaves"
    with pytest.raises(QuantityUnresolved):
        consume_quantity_candidate(changed, req, snapshot["body"], **options)


def test_actual_broad_subject_number_span_remains_invalid():
    with pytest.raises(QuantityUnresolved):
        produce(2)


def test_both_actual_raw_forms_bind_same_immutable_field_identity():
    (_, number), _ = produce(0)
    (_, amount), _ = produce(1)
    assert number["value_identity"] == amount["value_identity"]
    assert number["canonical_field"] == amount["canonical_field"]
    assert number["source_identity"]["document_version"] == 2
    assert number["source_identity"]["content_hash"] == (
        "54b42a5474860ffdb6fa9bc7209b652589693eb630a906072d9af4a936c4ba11"
    )


def test_old_default_nominal_parser_stays_closed():
    data, _, _, _, _ = actual()
    capture = json.loads(data["source_captures"][0]["windows"][0]["capture_json"])
    with pytest.raises(QuantityUnresolved, match="nominal_qualification"):
        _count_nominal(capture["annotation"]["tokens"], 137, numeric=True)


@pytest.mark.parametrize(
    "variant",
    ["attribute", "question", "reference", "condition", "negation", "capture", "scope"],
)
def test_unknown_or_tampered_original_request_does_not_grant_qualification(variant):
    _, req, plan, _, _ = actual()
    if variant == "attribute":
        req = replace(req, attribute="the leaf quantity")
    elif variant == "question":
        plan = replace(plan, question=plan.question.replace("sibling", "foreign"))
    elif variant in {"reference", "condition", "negation"}:
        key = {
            "reference": "references",
            "condition": "conditions",
            "negation": "negation",
        }[variant]
        plan = replace(
            plan, uses=(replace(plan.uses[0], **{key: (plan.uses[0].original,)}),)
        )
    elif variant == "capture":
        structure = json.loads(plan.structure_json)
        structure["original_capture"]["annotation"]["tokens"][2]["dep"] = "compound"
        plan = replace(plan, structure_json=json.dumps(structure))
    else:
        req = replace(req, topic="foreign merge")
    with pytest.raises((QuantityUnresolved, ValueError)):
        produce(requirement=req, plan_override=plan)


@pytest.mark.parametrize(
    "variant",
    [
        "opposite_modifier",
        "wrong_unit",
        "omitted_modifier",
        "extra_modifier",
        "negation",
        "reference",
    ],
)
def test_closed_source_nominal_requires_all_and_only_requested_words(variant):
    """UNITONLY negative lexical/edge mutations of the actual graph; no retagging."""
    data, req, plan, snapshot, _ = actual()
    tokens = json.loads(data["source_captures"][0]["windows"][0]["capture_json"])[
        "annotation"
    ]["tokens"]
    body = snapshot["body"]
    if variant == "opposite_modifier":
        tokens[136]["text"] = "foreign"
        body = body[:723] + "foreign" + body[730:]
    elif variant == "wrong_unit":
        tokens[137]["text"], tokens[137]["lemma"] = "boards", "board"
        body = body[:731] + "boards" + body[737:]
    elif variant == "omitted_modifier":
        tokens[137]["children"].remove(136)
    elif variant == "extra_modifier":
        tokens[137]["children"].append(132)
    else:
        tokens[136]["dep"] = "neg" if variant == "negation" else "prep"
    with pytest.raises(QuantityUnresolved):
        _bound_qualified_amount(
            req,
            body,
            tokens,
            137,
            (plan.uses[0], plan.question, data["request_capture"]),
        )
