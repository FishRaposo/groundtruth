"""Catch lost nominal governors, capture mutation and silent policy activation."""

from copy import deepcopy

import pytest
from app.services import captured_request_productions as production
from app.services.staged_request import compile_request

from .fixtures import actual


def test_actual_nominal_governor_gets_a_closed_supplement_without_retagging():
    inputs = actual()
    before = deepcopy(inputs["capture"])
    historical = compile_request(inputs["question"], inputs["capture"]).record()
    result = production.reconstruct_request_productions(
        inputs["question"], inputs["capture"], reading_profile="contextual_source_v4"
    )
    assert result["productions"], (
        "The captured nominal request governor remains unrepresented"
    )
    row = result["productions"][0]
    assert row["kind"] == "role_catalogue" and row["operation"] == "labels_only"
    assert row["governor"]["original_token"]["pos"] == "NOUN"
    assert row["governor"]["original_token"]["dep"] == "compound"
    assert row["semantic_argument"]["text"] == "role labels"
    assert (
        "".join(
            item["token"]["text"] + item["whitespace"] for item in row["consumption"]
        )
        == inputs["question"]
    )
    assert result["historical_partial"] == historical
    assert inputs["capture"] == before
    assert not result["complete_plan"]


def test_actual_old_compiler_still_exposes_the_recorded917_request_gap():
    inputs = actual()
    partial = compile_request(inputs["question"], inputs["capture"])
    assert partial.nodes[0].kind == "generic"
    assert any(
        row.reason == "unrecognized_request_predicate" for row in partial.unknowns
    )


@pytest.mark.parametrize(
    "profile",
    [None, "contextual_source_v1", "contextual_source_v2", "contextual_source_v3"],
)
def test_default_and_historical_profiles_do_not_activate_supplemental_productions(
    profile,
):
    inputs = actual()
    result = production.reconstruct_request_productions(
        inputs["question"], inputs["capture"], reading_profile=profile
    )
    assert result["productions"] == [] and not result["policy_enabled"]
    assert (
        result["historical_partial"]
        == compile_request(inputs["question"], inputs["capture"]).record()
    )


def test_unknown_profile_and_capture_mismatch_fail_closed():
    inputs = actual()
    for profile in (True, "contextual_source_v4-forged"):
        with pytest.raises(ValueError):
            production.reconstruct_request_productions(
                inputs["question"], inputs["capture"], reading_profile=profile
            )
    with pytest.raises(ValueError):
        production.reconstruct_request_productions(
            inputs["question"] + " extra",
            inputs["capture"],
            reading_profile="contextual_source_v4",
        )


def test_consumption_and_non_native_transport_tampers_do_not_replay():
    inputs = actual()
    record = production.reconstruct_request_productions(
        inputs["question"], inputs["capture"], reading_profile="contextual_source_v4"
    )
    assert production.validate_request_productions(
        record,
        inputs["question"],
        inputs["capture"],
        reading_profile="contextual_source_v4",
    )
    changed = deepcopy(record)
    changed["productions"][0]["consumption"][0]["role"] = "literal_field"
    assert not production.validate_request_productions(
        changed,
        inputs["question"],
        inputs["capture"],
        reading_profile="contextual_source_v4",
    )
    changed = deepcopy(record)
    changed["productions"] = tuple(changed["productions"])
    assert not production.validate_request_productions(
        changed,
        inputs["question"],
        inputs["capture"],
        reading_profile="contextual_source_v4",
    )


BASE = [
    ("Show", "NOUN", "show", "compound", 2),
    ("role", "NOUN", "role", "compound", 2),
    ("labels", "NOUN", "label", "ROOT", 2),
    ("for", "ADP", "for", "prep", 2),
    ("Helios", "NOUN", "helios", "compound", 5),
    ("check", "NOUN", "check", "pobj", 3),
    (".", "PUNCT", ".", "punct", 2),
]


def test_another_registered_governor_and_literal_noun_scope_are_generic():
    from tests.staged_plan_unit837.fixtures_source import capture

    question, observed = capture([BASE])
    result = production.reconstruct_request_productions(
        question, observed, reading_profile="contextual_source_v4"
    )
    assert result["productions"][0]["scopes"][0]["text"] == "Helios check"


@pytest.mark.parametrize(
    "kind",
    [
        "reference",
        "condition",
        "ambiguous_governor",
        "modifier",
        "second_scope",
        "negation",
    ],
)
def test_unconsumed_reference_condition_and_ambiguity_stay_pending(kind):
    from tests.staged_plan_unit837.fixtures_source import capture

    rows = list(BASE)
    if kind in {"reference", "ambiguous_governor", "modifier", "negation"}:
        inserted = {
            "reference": ("its", "PRON", "its", "poss", 3),
            "ambiguous_governor": ("name", "NOUN", "name", "compound", 3),
            "modifier": ("eligible", "ADJ", "eligible", "amod", 3),
            "negation": ("not", "PART", "not", "neg", 3),
        }[kind]
        rows = [
            (word, pos, lemma, dep, head + (head >= 1))
            for word, pos, lemma, dep, head in rows
        ]
        rows.insert(1, inserted)
    elif kind == "condition":
        rows = rows[:-1] + [
            ("before", "ADP", "before", "prep", 2),
            ("approval", "NOUN", "approval", "pobj", 6),
            (".", "PUNCT", ".", "punct", 2),
        ]
    else:
        rows = rows[:-1] + [
            ("for", "ADP", "for", "prep", 2),
            ("Lyra", "PROPN", "Lyra", "compound", 8),
            ("check", "NOUN", "check", "pobj", 6),
            (".", "PUNCT", ".", "punct", 2),
        ]
    question, observed = capture([rows])
    before = deepcopy(observed)
    result = production.reconstruct_request_productions(
        question, observed, reading_profile="contextual_source_v4"
    )
    assert result["productions"] == [] and result["remaining_semantics"]
    assert result["original_capture"] == before and observed == before
