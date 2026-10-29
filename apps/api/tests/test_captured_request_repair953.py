"""Actual observed946 request syntax only; no models/SQL/source truth."""

import json
from pathlib import Path

from app.services.captured_plan_binding import prepare_candidate_plan, prepare_structure

from tests.captured_inputs_unit932.fixtures import profile
from tests.captured_productions_unit931.fixtures import arguments


def observed(case):
    rows = json.loads(
        (Path(__file__).parent / "fixtures/captured-requests953.json").read_text()
    )
    return next(r for r in rows if r["case_file"] == case)


def candidate(case):
    row = observed(case)
    args = arguments()
    args.update(
        question=row["question"], capture=row["capture"], evidence_profile=profile()
    )
    return prepare_candidate_plan(**args)


def test_actual_scalar_fields_and_shared_syntax_are_admitted_without_retagging():
    # Defect: existing closed quantity/duration/location frames are refused.
    row = observed("reranked-003")
    structure = prepare_structure(
        row["question"], row["capture"], reading_profile="contextual_source_v4"
    )
    assert structure["unresolved"] == []
    assert [n["kind"] for n in structure["nodes"]] == [
        "quantity",
        "duration",
        "location",
    ]
    assert structure["original_capture"] == row["capture"]
    assert row["capture"]["annotation"]["tokens"][1]["pos"] == "VERB"
    assert (
        "".join(r["token"]["text"] + r["whitespace"] for r in structure["consumption"])
        == row["question"]
    )
    assert (
        next(r for r in structure["consumption"] if r["token"]["text"] == "and")["role"]
        == "declared_frame_syntax"
    )


def test_actual_known_roles_do_not_lose_the_separate_copy_semantic_blocker():
    row = observed("reranked-002")
    structure = prepare_structure(
        row["question"], row["capture"], reading_profile="contextual_source_v4"
    )
    assert not any(
        r["reason"] == "unsupported_captured_request_production"
        for r in structure["unresolved"]
    )
    assert structure["pending_source_applicability"][0]["owner_id"] == "p3"
    assert (
        structure["pending_source_applicability"][0]["state"]
        == "PENDING_SOURCE_APPLICABILITY"
    )
    assert structure["syntax_unresolved"] == []


def test_actual_qualified_uses_keep_typed_conditions_and_condition_ast():
    # Defect: full features JSON was retained but typed use condition fields empty.
    plan = candidate("reranked-002")
    assert len(plan.uses) == 3
    for use in plan.uses:
        assert [r.text for r in use.conditions] == ["with no separate assignment"]
        assert len(use.condition_ast) == 1
        assert [r.text for r in use.modality] == ["no"]
        assert use.scopes[0].text == "an ordinary Citrine fragment desk session"
    assert any(
        r["reason"] == "pending_source_applicability"
        for r in json.loads(plan.unresolved_json)
    )


def test_alternative_coordination_is_not_admitted_as_closed_atomic_fields():
    from tests.staged_plan_unit837.fixtures_source import capture

    # UNITONLY structural contrast, derived from observed syntax, never retagging
    # the immutable actual observation or pretending a parser ran on new text.
    row = observed("reranked-003")
    tokens = row["capture"]["annotation"]["tokens"]
    group = [(t["text"], t["pos"], t["lemma"], t["dep"], t["head"]) for t in tokens]
    group[6] = ("or", "CCONJ", "or", "cc", tokens[6]["head"])
    question, modified = capture([group])
    structure = prepare_structure(
        question, modified, reading_profile="contextual_source_v4"
    )
    assert structure["syntax_unresolved"]
    assert not any(
        r["production"] == "captured_closed_atomic_frame"
        for r in structure["production_resolutions"]
    )
