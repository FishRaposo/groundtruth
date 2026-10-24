"""Require the selected passage to respect explicit attribute and topic scope."""

import pytest
from app.services.reader_questions import mismatch_reason
from app.services.reader_support import procedure_features


def test_nominal_session_start_is_a_temporal_attribute():
    source = "The Aurora review session starts on Tuesday at 09:20."
    raw = "Tuesday at 09:20"
    start = source.index(raw)
    assert (
        mismatch_reason(
            "What is the session start for Aurora?", source, start, start + len(raw)
        )
        is None
    )


def test_explicit_elapsed_duration_cannot_establish_session_start():
    source = "The Aurora review takes 18 minutes."
    raw = "18 minutes"
    start = source.index(raw)
    assert (
        mismatch_reason(
            "What is the session start for Aurora?", source, start, start + len(raw)
        )
        is not None
    )


def test_relative_session_start_retains_its_actual_start_relation():
    source = "The Aurora session starts 18 minutes after the bell."
    raw = "18 minutes after the bell"
    start = source.index(raw)
    assert (
        mismatch_reason(
            "What is the session start for Aurora?", source, start, start + len(raw)
        )
        is None
    )


@pytest.mark.parametrize(
    "source",
    [
        "The Aurora session takes place at 09:20.",
        "It takes 18 minutes to set up Aurora, which starts at 09:20.",
    ],
)
def test_takes_in_a_different_relation_does_not_reject_the_actual_start_clock(source):
    start = source.index("09:20")
    assert (
        mismatch_reason(
            "What is the session start for Aurora?", source, start, start + 5
        )
        is None
    )


@pytest.mark.parametrize(
    "question",
    [
        "What are the ordered steps for Aurora?",
        "What is the stated prohibition for Aurora?",
        "What is the session start for Aurora?",
    ],
)
def test_explicit_standard_scope_exclusion_is_not_an_unqualified_answer(question):
    source = (
        "For the Aurora exception, attach the marker to the inner edge. "
        "This exception is outside the standard review procedure."
    )
    raw = "inner edge"
    start = source.index(raw)
    assert mismatch_reason(question, source, start, start + len(raw)) is not None


def test_nondefault_scope_exclusion_does_not_invent_a_standard_scope():
    source = (
        "The Aurora exception uses the inner edge. "
        "This exception is outside the export procedure."
    )
    raw = "inner edge"
    start = source.index(raw)
    assert (
        mismatch_reason(
            "Which edge applies to Aurora?", source, start, start + len(raw)
        )
        is None
    )


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        (
            "The Aurora inspection covers six seals. Do not open the latch. ",
            True,
        ),
        (
            "The Aurora inspection covers six seals. "
            "The Borealis inspection covers two seals. ",
            False,
        ),
        ("The Aurora inspection covers six seals.\n\n", False),
    ],
)
def test_generic_procedure_heading_inherits_only_its_current_named_topic(
    prefix, expected
):
    source = prefix + "Complete procedure: 1. Isolate the console. 2. Inspect the seal."
    raw = "Isolate the console"
    start = source.index(raw)
    features = procedure_features(
        "What are the steps for Aurora inspection?",
        source,
        start=start,
        end=start + len(raw),
        anchors=("aurora",),
    )
    assert features["selected_sequence"] is expected


def test_explicit_different_procedure_heading_never_inherits_an_earlier_topic():
    source = (
        "The Aurora inspection covers six seals. "
        "Borealis procedure: 1. Isolate the console. 2. Inspect the seal."
    )
    raw = "Isolate the console"
    start = source.index(raw)
    assert not procedure_features(
        "What are the steps for Aurora inspection?",
        source,
        start=start,
        end=start + len(raw),
        anchors=("aurora",),
    )["selected_sequence"]


def test_session_start_location_is_not_the_session_start_time():
    source = "The Aurora session starts at 09:20."
    start = source.index("09:20")
    assert (
        mismatch_reason(
            "What is the session start location for Aurora?", source, start, start + 5
        )
        is not None
    )


@pytest.mark.parametrize(
    ("antecedent", "plural"), [("exception", "exceptions"), ("policy", "policies")]
)
def test_plural_own_scope_question_keeps_its_source(antecedent, plural):
    source = (
        f"The Aurora {antecedent} uses the inner edge. "
        f"This {antecedent} is outside the standard review procedure."
    )
    raw = "inner edge"
    start = source.index(raw)
    assert (
        mismatch_reason(
            f"Which {plural} apply to Aurora?", source, start, start + len(raw)
        )
        is None
    )


@pytest.mark.parametrize(
    "subject",
    [
        "The Borealis inspection replaces the Aurora inspection.",
        "The Aurora inspection replaces the Borealis inspection.",
    ],
)
def test_another_named_entity_disables_only_the_generic_heading_prior(subject):
    source = (
        subject + " Complete procedure: 1. Isolate the console. 2. Inspect the seal."
    )
    raw = "Isolate the console"
    start = source.index(raw)
    features = procedure_features(
        "What are the steps for Aurora inspection?",
        source,
        start=start,
        end=start + len(raw),
        anchors=("aurora",),
    )
    assert features["explicit_sequence"]
    assert not features["selected_sequence"]
