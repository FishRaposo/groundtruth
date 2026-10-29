"""Preserve explicit procedural intent and shared list modifiers."""

import pytest
from app.services.answer_reader import reader_question
from app.services.reader_questions import mismatch_reason, question_parts


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Walk me through the Nova valve inspection after shutdown in order.",
            "What are the steps for the Nova valve inspection after shutdown?",
        ),
        (
            "Take me through airing the Nova cover in sequence.",
            "What are the steps for airing the Nova cover?",
        ),
        (
            "In what order do we grade the Nova plates?",
            "What are the steps to grade the Nova plates?",
        ),
    ],
)
def test_explicit_ordered_procedure_has_equivalent_qa_form(question, expected):
    assert reader_question(question) == expected


def test_nonprocedural_whether_intent_is_never_turned_into_steps():
    question = "Walk me through whether Nova access is authorized in order."
    assert reader_question(question) == question


def test_postposed_location_qualifies_every_list_item():
    parts = question_parts("Give me the handler, its pattern, and the limit at Nova.")
    assert all(part.anchors == ("nova",) for part in parts)
    assert all("Nova" in part.question for part in parts)


def test_list_separator_is_not_inserted_as_a_requested_attribute():
    parts = question_parts("For Nova kits, give me the finish, plus the issue time.")
    assert len(parts) == 2
    assert all("plus" not in part.question.casefold() for part in parts)


def test_possessive_temporal_attribute_accepts_a_clock():
    question = "Regarding the Nova enclosure, What is its viewing time?"
    source = "Nova viewing starts at 14:20."
    start = source.index("14:20")
    assert mismatch_reason(question, source, start, start + 5) is None


def test_elapsed_time_cannot_borrow_a_start_clock():
    question = "Regarding Nova, What is its elapsed time?"
    source = "Nova viewing starts at 14:20."
    start = source.index("14:20")
    assert mismatch_reason(question, source, start, start + 5) is not None


def test_explicit_elapsed_clock_format_remains_valid():
    question = "Regarding Nova, What is its elapsed time?"
    source = "Nova elapsed time is 14:20."
    start = source.index("14:20")
    assert mismatch_reason(question, source, start, start + 5) is None
