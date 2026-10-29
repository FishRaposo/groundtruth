"""Independently reported request/modality/precision defects remain regressions."""

import pytest
from app.services.answer_requirements import plan_requirements
from app.services.requirement_answers import witness_value_identity
from app.services.requirement_binding import support_claim


def plan(question):
    return plan_requirements(question, reading_profile="contextual_source_v1")


@pytest.mark.parametrize(
    "tail",
    [
        "may I rotate its wheel",
        "why is the activity ethical",
        "can I open its vault",
        "must we record its tax status",
        "whether its permit is valid",
    ],
)
def test_unknown_or_permission_conjunct_does_not_vanish(tail):
    question = f"For Copper engraving, identify the lead and {tail}?"
    requirements = plan(question)
    assert len(requirements) == 2
    assert tail in requirements[1].question


@pytest.mark.parametrize(
    "fragment",
    [
        "what is the lead's accreditation number",
        "explain the lead's professional history",
        "what is the deputy's birth date",
    ],
)
def test_nested_role_attribute_does_not_become_a_role_lookup(fragment):
    req = plan(f"For Copper engraving, {fragment}?")[0]
    assert req.kind == "generic"
    assert fragment in req.question


@pytest.mark.parametrize("modal", ["Must", "Should"])
def test_obligation_is_not_weakened_to_permission(modal):
    source = "The Copper wheel is on the bench. You may rotate the Copper wheel."
    question = f"{modal} the Copper wheel be rotated?"
    req = plan(question)[0]
    start = source.index("rotate")
    claim = support_claim(
        req, source, start, len(source) - 1, reading_profile="contextual_source_v1"
    )
    assert claim.rejection or modal.casefold() in claim.hypothesis.casefold()
    assert claim.rejection or " may " not in claim.hypothesis


@pytest.mark.parametrize(
    "first,last",
    [
        ("12345678901234567890123456781", "12345678901234567890123456782"),
        ("1.12345678901234567890123456781", "1.12345678901234567890123456782"),
    ],
)
def test_numeric_equivalence_never_rounds_unequal_values(first, last):
    req = plan("How many widgets are in the Copper pack?")[0]
    assert witness_value_identity(
        req, first + " widgets", reading_profile="contextual_source_v1"
    ) != witness_value_identity(
        req, last + " widgets", reading_profile="contextual_source_v1"
    )


def test_decimal_duration_is_one_exact_source_span():
    source = "The Copper wheel uses 26 letters. The alignment check lasts 1.5 minutes."
    req = plan("How long is the Copper alignment check?")[0]
    start = source.index("1.5 minutes")
    claim = support_claim(
        req, source, start, start + 11, reading_profile="contextual_source_v1"
    )
    assert claim.rejection is None
    assert claim.value == "1.5 minutes"
    assert source[claim.premise_start : claim.premise_end] == claim.premise


@pytest.mark.parametrize(
    "fragment",
    [
        "identify the lead for Copper engraving and chant its oath",
        "give the complete Copper engraving routine and chant its oath",
    ],
)
def test_unparsed_coordination_is_an_unresolved_obligation(fragment):
    req = plan(fragment)[0]
    assert req.kind == "generic"
    assert "chant its oath" in req.question
