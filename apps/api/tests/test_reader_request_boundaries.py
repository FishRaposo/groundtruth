"Preserve request intent without treating prefaces as separate questions."

import pytest
from app.services.reader_questions import mismatch_reason, question_parts, scope_matches


@pytest.mark.parametrize(
    "question, source",
    [
        (
            "As the document owner, what size is recorded for the spare panel?",
            "The planned size of the spare panel is 12 cells.",
        ),
        (
            "From beginning to end, what are the steps for the Aurora panel?",
            "The Aurora panel procedure is listed below.",
        ),
        (
            (
                'Using only "Aurora maintenance notes", are walk-in '
                "reviews offered for the Aurora panel?"
            ),
            "The Aurora panel does not offer walk-in reviews.",
        ),
    ],
)
def test_nonquestion_preface_is_not_a_missing_answer_part(question, source):
    parts = question_parts(question)
    assert len(parts) == 1
    assert scope_matches(parts[0], source)
    assert "?" not in parts[0].question[:-1]


def test_imperative_sentence_does_not_become_an_entity_anchor():
    parts = question_parts(
        (
            "I am preparing the Aurora panel. Copy the entire "
            "procedure in its stated order."
        )
    )
    assert len(parts) == 1
    assert parts[0].anchors == ("aurora",)
    assert scope_matches(
        parts[0], "Aurora panel maintenance. Complete procedure: 1. Pause. 2. Inspect."
    )


def test_a_second_request_sentence_remains_a_distinct_required_part():
    parts = question_parts(
        (
            "Which role owns the Aurora panel review? Also give the "
            "scheduled day and time."
        )
    )
    assert len(parts) >= 2
    assert all(part.anchors == ("aurora",) for part in parts)
    assert any("scheduled day" in part.question for part in parts)
    assert all("Also" not in part.anchors for part in parts)


@pytest.mark.parametrize(
    "question",
    [
        "What exact amount must a participant pay for the Aurora review?",
        "How much must a participant pay for the Aurora review?",
    ],
)
def test_payment_cannot_be_answered_with_duration_or_count(question):
    source = "The Aurora review takes 18 minutes."
    start = source.index("18 minutes")
    assert (
        mismatch_reason(question, source, start, start + len("18 minutes")) is not None
    )


def test_payment_with_explicit_currency_evidence_remains_eligible():
    source = "The Aurora review costs 18 euros."
    start = source.index("18 euros")
    assert (
        mismatch_reason(
            "What amount must a participant pay for the Aurora review?",
            source,
            start,
            start + len("18 euros"),
        )
        is None
    )


def test_source_scope_preface_is_retained_and_cannot_supply_identity():
    parts = question_parts(
        (
            'Using only "Aurora maintenance notes", what is the '
            "owner of the Aurora panel?"
        )
    )
    assert len(parts) == 1
    assert 'Using only "Aurora maintenance notes"' in parts[0].question
    assert not scope_matches(parts[0], "The Borealis panel owner is the steward.")


@pytest.mark.parametrize(
    "question, words",
    [
        (
            (
                "For the Aurora panel, identify the review owner plus "
                "the session day and start time."
            ),
            ("owner", "session day", "start time"),
        ),
        (
            (
                "Give the review duration for the Aurora panel, then "
                "the reservation role and deadline."
            ),
            ("duration", "reservation role", "deadline"),
        ),
        (
            (
                "Please combine the responsible review role and the "
                "session start for the Aurora panel."
            ),
            ("review role", "session start"),
        ),
    ],
)
def test_each_explicit_nominal_request_is_required_separately(question, words):
    parts = question_parts(question)
    assert len(parts) == len(words)
    assert all(part.anchors == ("aurora",) for part in parts)
    for word in words:
        assert any(word in part.question for part in parts)
    assert all("Aurora panel" in part.question for part in parts)


def test_shared_topic_does_not_turn_reservation_question_into_duration_question():
    parts = question_parts(
        (
            "Give the review duration for the Aurora panel, then "
            "the reservation role and deadline."
        )
    )
    assert len(parts) == 3
    assert all("duration" not in part.question for part in parts[1:])


def test_noun_coordination_inside_a_procedure_is_not_split():
    question = "Give the steps for checking the Aurora day and night seals in order."
    assert len(question_parts(question)) == 1


def test_capitalized_nominal_command_carries_shared_topic_backwards():
    parts = question_parts(
        "Identify the review owner and deadline for the Aurora panel."
    )
    assert len(parts) == 2
    assert all(part.anchors == ("aurora",) for part in parts)
    assert all("Aurora panel" in part.question for part in parts)


def test_question_sentence_is_not_absorbed_by_following_nominal_command():
    parts = question_parts(
        "Who owns the Aurora panel? Also give the scheduled day and time."
    )
    assert len(parts) == 3
    assert all("?" not in part.question[:-1] for part in parts)
    assert "owns" in parts[0].question
    assert all("owns" not in part.question for part in parts[1:])


def test_copy_inside_a_proper_name_remains_an_authority_anchor():
    part = question_parts("Who owns the Copy queue?")[0]
    assert "copy" in part.anchors
    assert not scope_matches(part, "The Borealis queue belongs to the steward.")


def test_pay_attention_does_not_request_money():
    source = "The Aurora panel needs close attention."
    start = source.index("close attention")
    assert (
        mismatch_reason(
            "How much attention must I pay to the Aurora panel?",
            source,
            start,
            start + 15,
        )
        is None
    )


def test_euro_symbol_is_recognized_without_a_currency_word():
    source = "The Aurora fee is \u20ac18."
    start = source.index("\u20ac18")
    assert (
        mismatch_reason("What amount must I pay for Aurora?", source, start, start + 3)
        is None
    )
