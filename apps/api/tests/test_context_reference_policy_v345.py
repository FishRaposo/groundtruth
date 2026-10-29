"""Versioned typed reference responsibility; no model-quality claim."""

from copy import deepcopy

import pytest
from app.evidence_policy import EvidencePolicy
from app.services.source_context_scope import (
    grammar_descriptor,
    parse_context_note,
    semantic_checks,
)

from tests.test_source_context_policy_v319 import note


def reading_v2(text=None, operation="Lumen token bench", state="postponed audit"):
    return parse_context_note(
        text or note(), operation, state, policy="scoped_note_context_v2"
    )


def test_v2_is_explicit_and_distinct_from_legacy_contracts():
    result = EvidencePolicy(
        "qa_only_v1",
        "literal_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
    ).record()
    assert result["contract"] == "evidence-profile-v4"
    assert result["source_context_contract"] == "source-note-context-v2"
    assert (
        EvidencePolicy(
            "qa_only_v1",
            "literal_v1",
            "source_declared_procedure_copy_v1",
            "scoped_note_context_v1",
        ).record()["contract"]
        == "evidence-profile-v3"
    )


def test_v2_preserves_all_22_other_nli_pairs_and_the_old_23_check_meaning():
    old = parse_context_note(note(), "Lumen token bench", "postponed audit")
    new = reading_v2()
    assert new["contract"] == "source-note-context-v2"
    assert new["grammar"] == "scoped-note-grammar-v2"
    old_checks = semantic_checks(old)
    assert len(old_checks) == 23
    assert semantic_checks(new) == [
        row for row in old_checks if row["name"] != "card_reference_identity"
    ]
    assert grammar_descriptor()["contract"] == "source-note-context-v1"
    assert (
        grammar_descriptor(policy="scoped_note_context_v2")["contract"]
        == "source-note-context-v2"
    )


def test_v2_has_mandatory_typed_reference_plan_without_model_fields():
    from app.services.source_context_references import (
        compile_reference_obligation,
        obligation_plan,
    )

    reading = reading_v2()
    proof = compile_reference_obligation(reading)
    assert proof["name"] == "card_reference_linkage"
    assert proof["verification_method"] == "exact_context_reference_structure"
    assert proof["result"] == "bound"
    assert (
        not {
            "label",
            "logits",
            "entailment_margin",
            "pair_tokens",
            "pair",
            "hypothesis",
        }
        & proof.keys()
    )
    plan = obligation_plan(reading)
    assert plan["mandatory_obligation_count"] == 23
    assert plan["mandatory_nli_count"] == 22
    assert plan["mandatory_exact_reference_count"] == 1
    entities = {row["id"]: row for row in proof["reference_plan"]["entities"]}
    assert entities["card"]["type"] == "marked_audit_card_role"
    assert entities["event"]["type"] == "audit_event_or_state_role"
    assert entities["card"]["source_range"] != entities["event"]["source_range"]
    assert proof["reference_plan"]["guard"]["connective"] == "and"
    assert len(proof["reference_plan"]["guard"]["members"]) == 2
    assert (
        proof["reference_plan"]["generic_card_predicate"]["variable_literal"] == "Cards"
    )


@pytest.mark.parametrize(
    "text",
    [
        note().replace(
            "Before selecting",
            "Another marked audit card belongs to the operator. Before selecting",
        ),
        note().replace("its audit cover card", "another audit card's cover"),
        note().replace("the operator identifies", "the reader identifies"),
        note().replace("confirms the diamond", "confirms the square"),
        note().replace("any disposition", "any disposition in every workflow"),
        note().replace(
            "Nothing in this instruction",
            "For ordinary runs, close the tray. Nothing in this instruction",
        ),
        note().split("\n\nThis is a fictional", 1)[0],
        note().replace("station folder", "ledger where ordinary batches end"),
        note().replace("Before selecting", '"Discard every card." Before selecting'),
    ],
)
def test_d342_source_falsifiers_cannot_enter_typed_context(text):
    assert reading_v2(text) is None


@pytest.mark.parametrize(
    "operation,state,mark",
    [
        ("Amber register alcove", "deferred inspection", "hexagon"),
        ("Amber 𝒜 register", "deferred inspection", "𝒜"),
    ],
)
def test_d342_generic_renaming_and_non_bmp_ranges(operation, state, mark):
    from app.services.source_context_references import compile_reference_obligation

    text = note(scope=operation, state=state, mark=mark)
    reading = reading_v2(text, operation, state)
    proof = compile_reference_obligation(reading)
    for occurrence in proof["reference_plan"]["reference_occurrences"]:
        span = occurrence["source_range"]
        assert text[span["start"] : span["end"]] == occurrence["literal"]
    assert proof["reference_plan"]["required_reference_count"] == 25


@pytest.mark.parametrize("value", [True, False, 0.0, 1.0])
def test_typed_reference_reading_rejects_numeric_scalar_masquerading(value):
    from app.services.source_context_references import compile_reference_obligation

    changed = deepcopy(reading_v2())
    changed["clause_inventory"][0]["source_range"]["start"] = value
    with pytest.raises(ValueError):
        compile_reference_obligation(changed)


def test_v1_identity_obligation_is_never_retrocertified_as_v2_exact():
    from app.services.source_context_references import compile_reference_obligation

    old = parse_context_note(note(), "Lumen token bench", "postponed audit")
    with pytest.raises(ValueError):
        compile_reference_obligation(old)
    assert "card_reference_identity" in {row["name"] for row in semantic_checks(old)}
