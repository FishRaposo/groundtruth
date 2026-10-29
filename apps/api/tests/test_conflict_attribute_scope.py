"""Typed conflict relevance is not answer support or group inheritance."""

from dataclasses import replace

import pytest
from app.services import requirement_binding as binding
from app.services.answer_requirements import Requirement
from app.services.requirement_conflict_scope import source_relation_scope


def availability():
    question = "For standard Quartz review, during which hours may Alice substitute?"
    return Requirement(
        "r1",
        question,
        0,
        len(question),
        question,
        "availability",
        "Alice",
        ("quartz",),
        ("r0",),
        "cover_window",
        "availability",
    )


def start_time():
    question = "What time does the standard Quartz review session start?"
    return Requirement(
        "r1",
        question,
        0,
        len(question),
        question,
        "start_time",
        "standard Quartz review session",
        ("quartz",),
        (),
        "starts",
        "start_time",
    )


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "For standard Quartz review, Bob may substitute only on Monday "
            "from 10:00 to 18:00. These are Bob's cover hours.",
            "irrelevant",
        ),
        (
            "Alice archives the Quartz review notes. "
            "Bob is present from 10:00 to 18:00.",
            "irrelevant",
        ),
        (
            "For standard Quartz review, the Alice may substitute only on Friday "
            "from 09:00 to 17:00.",
            "applies",
        ),
        (
            "For standard Quartz review, Alice may not substitute on Friday "
            "from 09:00 to 17:00.",
            "applies",
        ),
        (
            "Alice may substitute only on Monday from 10:00 to 18:00.",
            "unknown",
        ),
        (
            "For standard Willow review, Alice may substitute only on Monday "
            "from 10:00 to 18:00.",
            "irrelevant",
        ),
        (
            "For standard Quartz review, Alice may substitute for Willow review "
            "only on Monday from 10:00 to 18:00.",
            "irrelevant",
        ),
        (
            "Alice is the deputy for standard Quartz review and may substitute "
            "only on Monday from 10:00 to 18:00.",
            "applies",
        ),
        ("For standard Quartz review, it may substitute on Monday.", "unknown"),
        ("Alice archives the Quartz review notes.", "unknown"),
    ],
)
def test_availability_keeps_actor_predicate_and_original_activity(body, expected):
    assert source_relation_scope(availability(), body) == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            "For standard Quartz review session, the arrival window begins at 08:30.",
            "irrelevant",
        ),
        (
            "For standard Quartz review session, the session starts at 09:30.",
            "applies",
        ),
        ("The standard Quartz review session begins at 09:30.", "applies"),
        (
            "For standard Willow review session, the standard Quartz review "
            "session starts at 09:30.",
            "irrelevant",
        ),
        (
            "Quartz review stores the archive. "
            "The Willow review session starts at 08:30.",
            "irrelevant",
        ),
        ("The standard Quartz cache recovery session starts at 08:30.", "irrelevant"),
        ("The session starts at 08:30.", "unknown"),
        ("The standard Quartz review session has a blue cover.", "unknown"),
    ],
)
def test_start_time_excludes_arrival_and_explicit_other_activity(body, expected):
    assert source_relation_scope(start_time(), body) == expected


def test_condition_applicability_remains_an_independent_guard():
    req = availability()
    body = "For exception Quartz review, Alice may substitute on Monday."
    assert binding.condition_relation(req, body, {}) == "irrelevant"


def test_unresolved_request_actor_never_becomes_a_verified_identity():
    req = replace(availability(), topic="it")
    assert (
        source_relation_scope(req, "For standard Quartz review, it may substitute.")
        == "unknown"
    )


@pytest.mark.parametrize("kind", ["owner", "deputy", "procedure"])
def test_existing_typed_kinds_delegate_without_reimplementation(monkeypatch, kind):
    req = replace(availability(), kind=kind)
    calls = []

    def original(current, body):
        calls.append((current, body))
        return "irrelevant"

    monkeypatch.setattr(binding, "source_relation_scope", original)
    assert source_relation_scope(req, "body") == "irrelevant"
    assert calls == [(req, "body")]


@pytest.mark.parametrize("kind", ["generic", "quantity", "duration", "weekday"])
def test_other_kinds_stay_unknown(kind):
    assert (
        source_relation_scope(replace(availability(), kind=kind), "Alice is present.")
        == "unknown"
    )


@pytest.mark.parametrize(
    ("req", "unparsed", "foreign"),
    [
        (
            availability(),
            "Alice's cover hours for standard Quartz review are Monday "
            "from 10:00 to 18:00.",
            "Bob is present from 10:00 to 18:00.",
        ),
        (
            start_time(),
            "The standard Quartz review session is scheduled at 10:00.",
            "The Willow review session starts at 08:30.",
        ),
        (
            availability(),
            "Monday from 10:00 to 18:00 is assigned to Alice "
            "for standard Quartz review.",
            "For standard Willow review, Bob may substitute on Friday.",
        ),
        (
            start_time(),
            "For standard Quartz review, the session's opening time is 10:00.",
            "The arrival window begins at 08:30.",
        ),
        (
            availability(),
            "Alice's relief entitlement for standard Quartz review is suspended.",
            "Bob is present from 10:00 to 18:00.",
        ),
        (
            start_time(),
            "The commencement of standard Quartz review is deferred.",
            "The Willow review session starts at 08:30.",
        ),
    ],
)
def test_unparsed_temporal_statement_survives_foreign_statement_aggregation(
    req, unparsed, foreign
):
    assert source_relation_scope(req, unparsed) == "unknown"
    for body in (unparsed + " " + foreign, foreign + " " + unparsed):
        assert source_relation_scope(req, body) == "unknown"


@pytest.mark.parametrize(
    ("req", "body"),
    [
        (
            availability(),
            "Bob is present from 10:00 to 18:00, Alice's cover hours "
            "are Monday from 09:00 to 17:00.",
        ),
        (
            availability(),
            "Bob is present from 10:00 to 18:00 while Alice's duty window "
            "covers Monday afternoon.",
        ),
        (
            start_time(),
            "The arrival window begins at 08:30, the standard Quartz review "
            "session is scheduled at 10:00.",
        ),
    ],
)
def test_partial_temporal_parse_cannot_establish_whole_statement_irrelevance(req, body):
    assert source_relation_scope(req, body) == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["availability", "start_time"])
@pytest.mark.parametrize("peer_label", ["neutral", "contradiction"])
async def test_unknown_opponent_without_qa_is_compared_after_foreign_append(
    monkeypatch, kind, peer_label
):
    from app.config import Settings
    from app.models.query import QueryRequest
    from app.services import requirement_answers as controller
    from app.services.answer_support import SupportAssessment

    from tests.test_requirement_cover_boundaries import chunk, valid, witness

    req = availability() if kind == "availability" else start_time()
    if kind == "availability":
        chosen = (
            "For standard Quartz review, Alice may substitute only on Friday "
            "from 09:00 to 17:00. These are Alice's cover hours."
        )
        opponent = (
            "Alice's cover hours for standard Quartz review are Monday from "
            "10:00 to 18:00. Bob is present from 10:00 to 18:00."
        )
        value = "Friday from 09:00 to 17:00"
        hypothesis = "Alice may substitute only on Friday from 09:00 to 17:00"
    else:
        chosen = "The standard Quartz review session starts at 09:30."
        opponent = (
            "The standard Quartz review session is scheduled at 10:00. "
            "The Willow review session starts at 08:30."
        )
        value = "09:30"
        hypothesis = "The standard Quartz review session starts at 09:30"
    selected, peer = chunk(chosen, 1, "curated"), chunk(opponent, 2, "curated")
    seen = []

    async def inspect(*args, **kwargs):
        return [selected, peer], False

    async def assess(pairs, config=None):
        seen.extend(pairs)
        return [
            SupportAssessment("entailment", (-5, 5, -5), 10, True)
            if pair.premise == chosen
            else SupportAssessment(peer_label, (5, -5, 5), -10, False)
            for pair in pairs
        ]

    async def no_qa(*args, **kwargs):
        raise AssertionError("Conflict membership must not require opponent QA")

    monkeypatch.setattr(controller, "inspect_curated_group", inspect)
    monkeypatch.setattr(controller.support_service, "assess", assess)
    monkeypatch.setattr(controller.reader_service, "select_atomic", no_qa)
    _, veto = await controller._inspect_conflicts(
        None,
        QueryRequest(question=req.question),
        None,
        {selected.id: selected, peer.id: peer},
        (req,),
        {req.id: req},
        {req.id: [witness(req, selected, value, hypothesis)]},
        Settings(),
        valid,
    )
    assert any(pair.premise == opponent for pair in seen)
    assert veto
