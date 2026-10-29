"""Wire exact negative relation proposals without changing their modality."""

import pytest
from app.services.answer_requirements import Requirement, plan_requirements
from app.services.requirement_binding import support_claim


def test_complete_negative_predicate_keeps_contiguous_classifier_proof():
    context = (
        "Meridian is a symbolic puzzle only: its transform of ABC is BCA, "
        "and it does not describe a biological sample. Other output is absent."
    )
    req = plan_requirements(
        "Does Meridian symbolic puzzle describe a biological sample?"
    )[0]
    start = context.index("does not describe")
    claim = support_claim(req, context, start, len(context))
    assert claim.rejection is None
    assert claim.value == "does not describe a biological sample"
    assert claim.hypothesis == (
        "Meridian symbolic puzzle does not describe a biological sample"
    )
    assert claim.premise == context[: context.index(" Other output")]
    assert context[claim.support_start : claim.support_end] == claim.premise


@pytest.mark.parametrize(
    "question",
    [
        "Does Meridian symbolic puzzle describe a biological organism?",
        "Can Meridian symbolic puzzle describe a biological sample?",
        "May Meridian symbolic puzzle describe a biological sample?",
        "Does Willow symbolic puzzle describe a biological sample?",
    ],
)
def test_other_object_entity_or_modality_cannot_use_the_negative(question):
    context = (
        "Meridian is a symbolic puzzle only: its transform of ABC is BCA, "
        "and it does not describe a biological sample."
    )
    req = plan_requirements(question)[0]
    start = context.index("does not describe")
    assert support_claim(req, context, start, len(context) - 1).rejection is not None


@pytest.mark.parametrize(
    "question,context,value",
    [
        (
            "Does Quartz write an empty record?",
            "Willow is a partner of Quartz. It does not write an empty record.",
            "does not write an empty record",
        ),
        (
            "May Quartz write an empty record?",
            "Quartz does not write an empty record.",
            "does not write an empty record",
        ),
        (
            "Can Quartz write an empty record?",
            "Quartz may not write an empty record.",
            "may not write an empty record",
        ),
    ],
)
def test_rejected_negative_relations_never_fall_through_to_another_claim(
    question, context, value
):
    req = Requirement(
        "r1",
        question,
        0,
        len(question),
        question,
        "boolean",
        "Quartz",
        ("quartz",),
        relation="boolean",
    )
    start = context.index(value)
    result = support_claim(req, context, start, start + len(value))
    assert result.rejection is not None
    assert result.hypothesis is None
