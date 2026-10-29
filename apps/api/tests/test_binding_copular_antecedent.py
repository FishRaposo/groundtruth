"""A source pronoun must name the exact immediately preceding subject."""

import pytest
from app.services.answer_requirements import plan_requirements
from app.services.requirement_binding import support_claim


def bind(context, value="not a synonym for null"):
    req = plan_requirements("In Meridian, is an empty string a synonym for null?")[0]
    start = context.index(value)
    return support_claim(req, context, start, start + len(value))


def test_exact_adjacent_copular_antecedent_and_negative_property():
    context = (
        "In Meridian, an empty string is a non-null key; it is not a synonym for null."
    )
    claim = bind(context)
    assert claim.rejection is None
    assert claim.hypothesis == "In Meridian, an empty string is not a synonym for null"
    assert claim.premise == context.rstrip(".")
    assert context[claim.support_start : claim.support_end] == context


@pytest.mark.parametrize(
    "context",
    [
        "In Meridian, a numeric zero is a non-null key; it is not a synonym for null.",
        "In Meridian, an empty string follows a numeric zero; "
        "it is not a synonym for null.",
        "In Meridian, a label for an empty string is a key; "
        "it is not a synonym for null.",
        "In Meridian, an empty string is a key. A zero is a key; "
        "it is not a synonym for null.",
        "In Meridian, an empty string is a key; an export is a file; "
        "it is not a synonym for null.",
    ],
)
def test_unrelated_or_intervening_subject_cannot_be_the_pronoun(context):
    assert bind(context).rejection is not None


def test_different_negative_property_is_not_a_matching_classification():
    context = "In Meridian, an empty string is a key; it is not a label for null."
    assert bind(context, "not a label for null").rejection is not None
