"""Interpret request grammar without mistaking context or names for intent."""

import pytest
from app.services.answer_reader import reader_question
from app.services.reader_questions import mismatch_reason, question_parts
from app.services.reader_support import procedure_features, requests_procedure


def test_declarative_setup_is_context_not_a_required_answer():
    question = (
        "I am resetting the Aurora sand table. What depth and duration apply, "
        "when does the reset start, and where does the rake go?"
    )
    parts = question_parts(question)
    assert len(parts) == 3
    assert "I am resetting the Aurora sand table." in parts[0].question
    assert "What depth and duration apply" in parts[0].question
    assert all(part.anchors == ("aurora",) for part in parts)
    assert not any(part.question.endswith("sand table?") for part in parts)


def test_a_requested_action_is_not_absorbed_as_declarative_context():
    parts = question_parts("Give me the Aurora owner. When does the review start?")
    assert len(parts) == 2
    assert "owner" in parts[0].question
    assert "When" in parts[1].question


def test_sequence_in_an_entity_does_not_disable_attribute_requests():
    parts = question_parts(
        "Give the review duration for the Aurora frame sequence, "
        "then the reservation role and deadline."
    )
    assert len(parts) == 3
    assert all(part.anchors == ("aurora",) for part in parts)


def test_entity_sequence_does_not_turn_a_schedule_into_a_procedure():
    text = "The Aurora frame sequence session starts at 14:10."
    start = text.index("14:10")
    assert (
        mismatch_reason(
            "When does the Aurora frame sequence session start?", text, start, start + 5
        )
        is None
    )


def test_complete_ordered_procedure_is_an_explicit_procedural_request():
    text = "Aurora inspection: First, isolate. Next, inspect."
    assert (
        procedure_features(
            "What is the complete ordered practice procedure for Aurora?", text
        )["requested"]
        is True
    )


def test_number_of_steps_is_an_attribute_not_a_request_to_perform_them():
    parts = question_parts("Give me the number of steps for Aurora and the owner.")
    assert len(parts) == 2


def test_a_real_procedure_keeps_its_conjunctions():
    question = "Give the steps for checking the Aurora day and night seals in order."
    assert len(question_parts(question)) == 1


def test_nominal_start_time_accepts_its_clock_evidence():
    text = "The Aurora session starts at 14:10."
    start = text.index("14:10")
    assert (
        mismatch_reason("Regarding Aurora, What is start time?", text, start, start + 5)
        is None
    )


def test_time_required_is_elapsed_and_cannot_use_a_start_clock():
    text = "The Aurora session starts at 14:10."
    start = text.index("14:10")
    assert (
        mismatch_reason(
            "What is the time required to review Aurora?", text, start, start + 5
        )
        is not None
    )


def test_single_nominal_imperative_has_a_qa_form():
    part = question_parts("For Aurora, give the explicit walk-in restriction.")[0]
    assert part.question == "For Aurora, What is the explicit walk-in restriction?"


def test_politeness_does_not_split_a_rewritten_question_head():
    parts = question_parts(
        "Please combine the review role and session start for Aurora."
    )
    assert len(parts) == 2
    assert all("Please What" not in part.question for part in parts)


def test_role_predicate_does_not_become_the_following_question_subject():
    parts = question_parts(
        "Which role owns the Aurora review? Also give the scheduled day and time."
    )
    assert len(parts) == 3
    assert all("owns" not in part.question for part in parts[1:])


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "I am preparing the Aurora panel after shutdown. "
            "Copy the entire procedure in its stated order.",
            "What are the steps for the Aurora panel after shutdown?",
        ),
        (
            "Give every step, in order, for checking the Aurora panel after shutdown.",
            "What are the steps for checking the Aurora panel after shutdown?",
        ),
    ],
)
def test_explicit_full_procedure_imperative_keeps_its_qualified_subject(
    question, expected
):
    assert reader_question(question) == expected


@pytest.mark.parametrize(
    "question",
    [
        "What is the time required to give the Aurora talk?",
        "Who should identify the Aurora panel owner?",
    ],
)
def test_embedded_directive_verbs_do_not_rewrite_an_interrogative(question):
    parts = question_parts(question)
    assert len(parts) == 1
    assert parts[0].question == question


def test_a_prefaced_directive_retains_its_entire_qualified_subject():
    parts = question_parts(
        "For the Aurora panel in the dry room, please give the owner and deadline."
    )
    assert len(parts) == 2
    assert all("Aurora panel in the dry room" in part.question for part in parts)


def test_modal_sequence_follow_request_keeps_procedure_intent():
    assert requests_procedure(
        "What sequence should I follow to handle the Aurora shade cloth?"
    )


def test_sequence_number_is_an_attribute_not_a_procedure():
    assert not requests_procedure("What is the sequence number for the Aurora panel?")


def test_leading_regarding_is_context_but_midname_regarding_remains_an_anchor():
    assert question_parts("Regarding Aurora, what is its owner?")[0].anchors == (
        "aurora",
    )
    assert question_parts("Who owns the Regarding queue?")[0].anchors == ("regarding",)
