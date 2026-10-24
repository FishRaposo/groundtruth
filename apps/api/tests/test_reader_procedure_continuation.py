"""Ordinary topic sentences and sequence markers survive canonical ingestion."""

import pytest
from app.services.reader_questions import mismatch_reason
from app.services.reader_support import procedure_features


@pytest.mark.parametrize(
    "instructions",
    [
        "First, isolate the console. Next, inspect the seal. Finally, sign the card.",
        "Begin by isolating the console. After that, inspect the seal. "
        "Finish by signing the card.",
    ],
)
def test_sequence_can_follow_its_immediate_topic_sentence(instructions):
    context = "At Nova, Morgan supervises seal inspection. " + instructions
    start = context.index("isolat")
    result = procedure_features(
        "What are the steps for Nova seal inspection?",
        context,
        start=start,
        end=start + len("isolate"),
        anchors=("nova",),
    )
    assert result["selected_sequence"] is True


def test_explicit_other_heading_does_not_inherit_preceding_topic():
    context = (
        "At Nova, Morgan supervises seal inspection. "
        "Office closing: First, lock the desk. Next, turn off the lights."
    )
    start = context.index("lock")
    result = procedure_features(
        "What are the steps for Nova seal inspection?",
        context,
        start=start,
        end=start + len("lock the desk"),
        anchors=("nova",),
    )
    assert result["selected_sequence"] is False


@pytest.mark.parametrize(
    "question",
    [
        "Regarding Nova inspection, what is the session window?",
        "What is the Nova session window?",
        "What is its time window?",
    ],
)
def test_explicit_session_window_accepts_an_exact_clock_interval(question):
    context = "Nova inspections are booked from 09:20 to 10:30."
    start = context.index("09:20")
    assert (
        mismatch_reason(
            question,
            context,
            start,
            start + len("09:20 to 10:30"),
        )
        is None
    )


def test_window_size_remains_a_non_temporal_attribute():
    context = "Nova inspections are booked from 09:20 to 10:30."
    start = context.index("09:20")
    assert (
        mismatch_reason(
            "What is the Nova window size?",
            context,
            start,
            start + len("09:20 to 10:30"),
        )
        is not None
    )


@pytest.mark.parametrize(
    "question",
    [
        "Regarding Nova, what is the box count for the session window?",
        "What is the total number of boxes in the time window?",
    ],
)
def test_window_qualifier_cannot_change_a_count_request(question):
    context = "Nova inspections are booked from 09:20 to 10:30."
    start = context.index("09:20")
    assert (
        mismatch_reason(
            question,
            context,
            start,
            start + len("09:20 to 10:30"),
        )
        is not None
    )
