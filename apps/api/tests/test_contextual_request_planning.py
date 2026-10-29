"""Complete request obligations through the production planner seam."""

import pytest
from app.services.answer_requirements import plan_requirements


def contextual(question):
    return plan_requirements(question, reading_profile="contextual_source_v1")


@pytest.mark.parametrize(
    "question,kinds",
    [
        (
            "For an ordinary Copper engraving session, name the activity lead "
            "and deputy and give the entire alignment routine in order.",
            ["owner", "deputy", "procedure"],
        ),
        (
            "Who are the ordinary lead and deputy for Copper engraving, "
            "and what are all the steps of its sheet routine?",
            ["owner", "deputy", "procedure"],
        ),
        (
            "List the full Copper engraving routine in order "
            "and identify the lead and deputy for an ordinary session.",
            ["procedure", "owner", "deputy"],
        ),
        (
            "For Copper engraving, identify the lead, deputy, "
            "plus the complete card routine.",
            ["owner", "deputy", "procedure"],
        ),
        (
            "How many letters are on the Copper outer wheel, "
            "and where does the ordinary session meet?",
            ["quantity", "location"],
        ),
        (
            "Tell me the lane count for the Copper sheet "
            "and the bench used for its sessions.",
            ["quantity", "location"],
        ),
        ("What is the length of a Copper viewing turn?", ["duration"]),
        ("Who is in charge during the Copper quiet session?", ["owner"]),
    ],
)
def test_every_coordinated_obligation_is_preserved(question, kinds):
    requirements = contextual(question)
    assert [r.kind for r in requirements] == kinds
    for req in requirements:
        assert req.original_text == question[req.input_start : req.input_end]
        assert req.topic and "Copper" in req.topic
        assert req.question and req.id


def test_unknown_conjunct_cannot_disappear_into_a_supported_role():
    question = (
        "For Copper engraving, identify the lead and explain its secret accreditation."
    )
    requirements = contextual(question)
    assert [r.kind for r in requirements] == ["owner", "generic"]
    assert "secret accreditation" in requirements[1].original_text


def test_conditions_and_role_dependency_survive_coordination():
    question = (
        "For Copper engraving, identify the lead and give that role's hours "
        "when the room is closed."
    )
    requirements = contextual(question)
    assert [r.kind for r in requirements] == ["owner", "availability"]
    assert requirements[1].depends_on == ("r1",)
    assert "when the room is closed" in requirements[1].question


def test_legacy_default_is_unchanged_and_unknown_profiles_fail():
    question = "Who leads Copper engraving?"
    assert plan_requirements(question) == plan_requirements(
        question, reading_profile="clause_bound_v1"
    )
    with pytest.raises(ValueError, match="reading profile"):
        plan_requirements(question, reading_profile="invented")


def test_role_relation_and_its_condition_are_not_lost_by_preparation():
    req = contextual(
        "For Copper engraving, identify the lead when the room is closed."
    )[0]
    assert req.relation == "leads"
    assert "when the room is closed" in req.question
