"""Context can establish a subject; it cannot substitute another attribute."""

import pytest
from app.services.answer_requirements import plan_requirements
from app.services.requirement_binding import support_claim

SOURCE = (
    "The Copper cipher wheel uses a 26-letter outer alphabet. "
    "The alignment check lasts 7 minutes. "
    "Do not rotate the outer alphabet during a check. "
    "For a reversed alphabet demonstration, use the silver pointer "
    "instead of the brass pointer."
)


def bound(question, answer, source=SOURCE):
    req = plan_requirements(question, reading_profile="contextual_source_v1")[0]
    start = source.index(answer)
    return support_claim(
        req, source, start, start + len(answer), reading_profile="contextual_source_v1"
    )


def test_duration_inherits_the_declared_source_subject_without_invented_premise():
    claim = bound("How long is the Copper alignment check?", "7 minutes")
    assert claim.rejection is None
    assert claim.hypothesis == "the Copper alignment check lasts 7 minutes"
    assert claim.premise in SOURCE
    assert "Copper cipher wheel" in claim.premise
    assert (
        SOURCE[claim.support_start : claim.support_end]
        == "The alignment check lasts 7 minutes."
    )


def test_quantity_keeps_the_asked_noun_and_entity():
    claim = bound("How many letters are on the Copper outer wheel?", "26")
    assert claim.rejection is None
    assert "letters" in claim.hypothesis and "Copper outer wheel" in claim.hypothesis


def test_passive_boolean_preserves_the_prohibition_not_a_yes_answer():
    claim = bound(
        "May the Copper outer alphabet be rotated during the check?",
        "Do not rotate the outer alphabet during a check",
    )
    assert claim.rejection is None
    assert "not" in claim.hypothesis and "Copper" in claim.hypothesis
    assert "rotat" in claim.hypothesis


def test_selected_alternative_is_bound_to_the_requested_condition():
    claim = bound(
        "Which pointer is used for the reversed alphabet demonstration?",
        "silver pointer",
    )
    assert claim.rejection is None
    assert (
        claim.hypothesis
        == "silver pointer is used for the reversed alphabet demonstration"
    )
    wrong = bound(
        "Which pointer is used for the reversed alphabet demonstration?",
        "brass pointer",
    )
    assert wrong.rejection is not None


@pytest.mark.parametrize(
    "question,answer",
    [
        ("How long is the Copper alignment check?", "26"),
        ("What is the Copper alignment check's temperature?", "7 minutes"),
        ("How long is the Copper alignment check?", "silver pointer"),
        ("How long is the Zinc alignment check?", "7 minutes"),
    ],
)
def test_wrong_attribute_unit_and_entity_cannot_become_support(question, answer):
    assert bound(question, answer).rejection is not None


def test_unsupported_request_grammar_stays_unresolved():
    assert (
        bound("Why is the Copper activity ethical?", "silver pointer").rejection
        is not None
    )


def test_legacy_binding_default_stays_identical():
    req = plan_requirements("How long does Copper alignment last?")[0]
    start = SOURCE.index("7 minutes")
    assert support_claim(req, SOURCE, start, start + 9) == support_claim(
        req, SOURCE, start, start + 9, reading_profile="clause_bound_v1"
    )
