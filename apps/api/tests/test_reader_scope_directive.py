"""Answer-scope grammar must not create entities or erase real proper names."""

import pytest
from app.services.reader_questions import named_anchors, question_parts, scope_matches


@pytest.mark.parametrize(
    "directive", ["Limit the answer", "LIMIT THE ANSWER", "Please limit the answer"]
)
@pytest.mark.parametrize(
    "joiner",
    ["to the document titled", "TO the document titled", "TO THE DOCUMENT TITLED"],
)
def test_answer_scope_directive_is_not_an_entity(directive, joiner):
    question = f"Who supervises Aurora trials? {directive} {joiner} Aurora guide."
    assert named_anchors(question) == ("aurora",)
    assert all(
        scope_matches(part, "Aurora trials are supervised by the recorder.")
        for part in question_parts(question)
    )


@pytest.mark.parametrize(
    "question",
    [
        "Who supervises the Limit fixture?",
        "Limit fixture inspection: who supervises it?",
        "What is the Limit answer register?",
    ],
)
def test_limit_in_a_proper_name_remains_an_entity(question):
    assert "limit" in named_anchors(question)
    assert not all(
        scope_matches(part, "Borealis is supervised by the recorder.")
        for part in question_parts(question)
    )


def test_scope_command_preserves_the_named_source_constraint():
    question = (
        "Who supervises Aurora trials? LIMIT THE ANSWER TO THE DOCUMENT TITLED "
        "Borealis guide."
    )
    assert named_anchors(question) == ("aurora", "borealis")
    assert not all(
        scope_matches(part, "Aurora trials are supervised by the recorder.")
        for part in question_parts(question)
    )
