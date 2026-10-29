"""An explicit before-clause can bind adjacent imperative instructions only."""

import pytest
from app.services.reader_questions import mismatch_reason


@pytest.mark.parametrize(
    ("question", "context", "answer"),
    [
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue. "
            "Restore the staging snapshot and verify checks.",
            "deployment queue",
        ),
        (
            "What must be closed before replacing the intake filter?",
            "Close the inlet valve. Replace the intake filter and verify the seal.",
            "inlet valve",
        ),
    ],
)
def test_explicit_before_binds_adjacent_actions(question, context, answer):
    start = context.index(answer)
    assert mismatch_reason(question, context, start, start + len(answer)) is None


@pytest.mark.parametrize(
    "context",
    [
        "Pause the deployment queue. Record the log. Restore the staging snapshot.",
        "Pause the deployment queue. Violet: restore the staging snapshot.",
        "Pause the deployment queue. Do not restore the staging snapshot.",
        "The depot pauses the deployment queue. Restore the staging snapshot.",
        "Pause the deployment queue. The staging snapshot requires manual review.",
        "Pausing the deployment queue is prohibited. Restore the staging snapshot.",
        "Pause neither the deployment queue nor its worker. "
        "Restore the staging snapshot.",
        "Pause the deployment queue? Restore the staging snapshot.",
    ],
)
def test_before_does_not_waive_unrelated_or_negated_topic(context):
    answer = "deployment queue"
    start = context.index(answer)
    assert (
        mismatch_reason(
            "What must be paused before restoring the staging snapshot?",
            context,
            start,
            start + len(answer),
        )
        == "requested_topic_is_introduced_after_selected_clause"
    )
