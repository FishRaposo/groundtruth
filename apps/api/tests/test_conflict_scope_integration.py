"""Six bounded relevance controls; no QA/NLI/database/corpus/service calls."""

from app.config import Settings
from app.models.query import QueryRequest
from app.services import requirement_answers as controller
from app.services.answer_requirements import Requirement
from app.services.answer_support import SupportAssessment

from tests.test_requirement_cover_boundaries import chunk, valid, witness


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


SELECTED = (
    "For standard Quartz review, Alice may substitute only on Friday "
    "from 09:00 to 17:00. These are Alice's cover hours."
)


async def inspect(
    monkeypatch,
    req,
    selected_text,
    other_text,
    value,
    hypothesis,
    foreign_decision="neutral",
):
    selected = chunk(selected_text, 1, "curated")
    other = chunk(other_text, 2, "curated")

    async def group(*args, **kwargs):
        return [selected, other], False

    pairs_seen = []

    async def assess(pairs, config=None):
        pairs_seen.extend(pairs)
        return [
            SupportAssessment("entailment", (-5, 5, -5), 10, True)
            if pair.premise == selected_text
            else SupportAssessment("contradiction", (5, -5, -5), -10, False)
            if foreign_decision == "contradiction"
            else SupportAssessment("neutral", (-5, -5, 5), -10, False)
            for pair in pairs
        ]

    monkeypatch.setattr(controller, "inspect_curated_group", group)
    monkeypatch.setattr(controller.support_service, "assess", assess)
    result = await controller._inspect_conflicts(
        None,
        QueryRequest(question=req.question),
        None,
        {selected.id: selected, other.id: other},
        (req,),
        {req.id: req},
        {req.id: [witness(req, selected, value, hypothesis)]},
        Settings(),
        valid,
    )
    return result, pairs_seen


async def test_01_foreign_actor_cannot_veto_validated_dependent_cover_window(
    monkeypatch,
):
    req = availability()
    other = (
        "For standard Quartz review, Bob may substitute only on Monday "
        "from 10:00 to 18:00. These are Bob's cover hours."
    )
    (records, conflict), pairs = await inspect(
        monkeypatch,
        req,
        SELECTED,
        other,
        "Friday from 09:00 to 17:00",
        "Alice may substitute only on Friday from 09:00 to 17:00",
    )
    assert req.depends_on == ("r0",)
    assert not conflict, records


def test_02_incidental_actor_and_namespace_cannot_scope_a_different_hours_predicate():
    req = availability()
    other = chunk(
        "Alice archives the Quartz review notes. Bob is present from 10:00 to 18:00.",
        3,
        "unrelated",
    )
    scoped, _, _ = controller._curated_subject_scope(req, [other], [])
    # This only tests pre-NLI eligibility, not a claim that neutral NLI vetoes.
    assert scoped == []


async def test_03_arrival_attribute_cannot_veto_the_validated_session_start(
    monkeypatch,
):
    question = "What time does the standard Quartz review session start?"
    req = Requirement(
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
    selected = "For standard Quartz review session, the session starts at 09:30."
    other = "For standard Quartz review session, the arrival window begins at 08:30."
    (records, conflict), _ = await inspect(
        monkeypatch,
        req,
        selected,
        other,
        "09:30",
        "The standard Quartz review session starts at 09:30",
    )
    assert not conflict, records


async def test_04_same_actor_same_attribute_opposition_still_requires_review(
    monkeypatch,
):
    other = (
        "For standard Quartz review, Alice may substitute only on Monday "
        "from 10:00 to 18:00. These are Alice's cover hours."
    )
    (_, conflict), _ = await inspect(
        monkeypatch,
        availability(),
        SELECTED,
        other,
        "Friday from 09:00 to 17:00",
        "Alice may substitute only on Friday from 09:00 to 17:00",
        foreign_decision="contradiction",
    )
    assert conflict


async def test_05_explicit_other_condition_is_excluded_before_comparison(monkeypatch):
    other = (
        "For exception Quartz review, Bob may substitute only on Monday "
        "from 10:00 to 18:00. These are Bob's cover hours."
    )
    (_, conflict), pairs = await inspect(
        monkeypatch,
        availability(),
        SELECTED,
        other,
        "Friday from 09:00 to 17:00",
        "Alice may substitute only on Friday from 09:00 to 17:00",
    )
    assert not conflict
    assert all(pair.premise == SELECTED for pair in pairs)


async def test_06_known_group_missing_namespace_same_actor_is_retained(monkeypatch):
    other = (
        "Alice may substitute only on Monday from 10:00 to 18:00. "
        "These are Alice's cover hours."
    )
    (_, conflict), pairs = await inspect(
        monkeypatch,
        availability(),
        SELECTED,
        other,
        "Friday from 09:00 to 17:00",
        "Alice may substitute only on Friday from 09:00 to 17:00",
        foreign_decision="contradiction",
    )
    assert conflict
    assert any(pair.premise == other for pair in pairs)
