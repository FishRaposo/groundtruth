"""Prepare an explicit nominal role request without changing its activity."""

import pytest
from app.services.answer_reader import reader_question


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Regarding the Aurora panel, What is the responsible review role?",
            "Regarding the Aurora panel, which role is responsible for the review?",
        ),
        (
            "What is the responsible review role for the Aurora panel?",
            "For the Aurora panel, which role is responsible for the review?",
        ),
    ],
)
def test_explicit_responsible_role_uses_an_equivalent_role_question(question, expected):
    assert reader_question(question) == expected


def test_qualified_role_activity_and_topic_are_preserved():
    assert reader_question(
        "Regarding the Aurora panel after shutdown, "
        "What is the responsible final safety review role?"
    ) == (
        "Regarding the Aurora panel after shutdown, "
        "which role is responsible for the final safety review?"
    )


@pytest.mark.parametrize(
    "question",
    [
        "Who should identify the Aurora panel owner?",
        "What is the role that is not responsible for reviewing Aurora?",
        "What is the responsible review role's training duration?",
        "What is the responsible review role for Aurora and who can replace it?",
        "At the Aurora clinic, What is the responsible intake role?",
        "On Monday, What is the responsible final review role?",
        "What is the responsible review role of the Aurora coordinator?",
        "What is the responsible review role for Aurora, and can it delegate?",
    ],
)
def test_other_role_relationships_are_not_silently_rewritten(question):
    assert reader_question(question) == question
