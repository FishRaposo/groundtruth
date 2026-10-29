"""UNITONLY sources; public v2 property inventory over retained request syntax."""

from dataclasses import replace

import pytest
from app.services import requirement_answers
from app.services.answer_reader import ReaderSelection, passage_span
from app.services.answer_support import SupportAssessment
from app.services.procedure_evidence import single_chunk_source
from app.services.requirement_binding import support_claim

from tests.test_composite_procedures import chunk
from tests.test_dependency_frames import planned
from tests.test_linguistic_runtime_dispatch import config


def requirement(tail=""):
    plan = planned("e628-explicit-data-reference")
    resolved, _ = requirement_answers.resolve_linguistic_requirement(
        plan.requirements[1], plan, {"r1": "The records steward"}
    )
    if tail:
        resolved = replace(
            resolved, question=resolved.question.rstrip("?") + " " + tail + "?"
        )
    return resolved


def bind(body, raw="09:00", *, tail=""):
    start = body.index(raw)
    return support_claim(
        requirement(tail),
        body,
        start,
        start + len(raw),
        reading_profile="contextual_source_v2",
    )


@pytest.mark.parametrize("raw", ["09:00", "13:00"])
def test_same_actor_sentences_are_one_complete_literal_inventory(raw):
    first = "The records steward is available from 09:00 to 12:00."
    second = "The records steward is available from 13:00 to 17:00."
    body = first + "\n\n" + second
    claim = bind(body, raw)
    assert claim.rejection is None
    assert claim.value == body
    assert body[claim.start : claim.end] == body
    assert claim.support_start == claim.premise_start == 0
    assert claim.support_end == claim.premise_end == len(body)
    assert [check.premise for check in claim.checks] == [first, second]
    assert "09:00 to 12:00" in claim.hypothesis
    assert "13:00 to 17:00" in claim.hypothesis
    assert all("is available" in check.hypothesis for check in claim.checks)


@pytest.mark.parametrize(
    "tail",
    [
        "within Copper review",
        "as part of Copper review",
        "while assigned to Copper review",
        "only when Copper review is running",
        "under the alternate Copper schedule",
        "although the visiting deputy covers the afternoon",
    ],
)
def test_unconsumed_source_scope_or_predicate_cannot_establish_zinc_property(tail):
    body = f"The records steward is available from 09:00 to 12:00 {tail}."
    assert bind(body).rejection is not None


@pytest.mark.parametrize(
    "secondary",
    [
        "the visiting deputy will be available from 13:00 to 17:00",
        "the visiting deputy is also available from 13:00 to 17:00",
        "the visiting deputy may be available from 13:00 to 17:00",
        "the visiting deputy is available from 13:00 to 17:00",
    ],
)
@pytest.mark.parametrize("raw", ["09:00", "13:00"])
def test_raw_value_cannot_cross_another_actors_coordinated_predicate(secondary, raw):
    body = f"The records steward is available from 09:00 to 12:00 and {secondary}."
    assert bind(body, raw).rejection is not None


@pytest.mark.parametrize(
    "body",
    [
        "The records steward is available from 09:00 to 12:00. "
        "A separate rule applies.",
        "A separate rule applies. "
        "The records steward is available from 09:00 to 12:00.",
        "The records steward is available from 09:00 to 12:00; the deputy works later.",
        "The records steward is available from 09:00 to 12:00. "
        "The deputy is available from 13:00 to 17:00.",
    ],
)
def test_unconsumed_context_requires_refusal_instead_of_partial_inventory(body):
    assert bind(body).rejection is not None


@pytest.mark.parametrize(
    "tail",
    [
        "if approval is recorded",
        "unless the supervisor defers the check",
        "when Copper review is running",
        "before the review starts",
    ],
)
def test_literal_requested_condition_is_retained_once(tail):
    body = f"The records steward is available from 09:00 to 12:00 {tail}."
    claim = bind(body, tail=tail)
    assert claim.rejection is None
    assert claim.value == f"from 09:00 to 12:00 {tail}"
    assert claim.hypothesis.count(tail) == 1
    assert "is available" in claim.hypothesis


@pytest.mark.parametrize("tail", ["if approval is recorded", "for Zinc review"])
def test_actual_requested_scope_must_be_consumed_not_silently_appended(tail):
    body = "The records steward is available from 09:00 to 12:00."
    assert bind(body, tail=tail).rejection is not None


@pytest.mark.parametrize("scope", ["for", "during", "in"])
def test_known_complete_namespace_production_keeps_matching_scope(scope):
    body = f"The records steward is available from 09:00 to 12:00 {scope} Zinc review."
    claim = bind(body)
    assert claim.rejection is None
    assert f"{scope} Zinc review" in claim.value
    assert bind(body.replace("Zinc", "Copper")).rejection is not None


def test_fractional_duration_is_literal_without_conversion():
    body = "The records steward is available for 2.5 hours during Zinc review."
    claim = bind(body, "2.5 hours")
    assert claim.rejection is None
    assert claim.value == "for 2.5 hours during Zinc review"
    assert "2.5 hours" in claim.hypothesis


def test_raw_actor_span_is_not_a_property_value():
    body = "The records steward is available from 09:00 to 12:00."
    assert bind(body, "records steward").rejection is not None


def test_inventory_overflow_is_an_explicit_refusal():
    body = " ".join(
        "The records steward is available from 09:00 to 12:00." for _ in range(9)
    )
    assert bind(body).rejection is not None


@pytest.mark.parametrize("reject_check", [False, True])
async def test_each_inventory_assertion_needs_its_own_real_support_input(
    monkeypatch, reject_check
):
    body = (
        "The records steward is available from 09:00 to 12:00. "
        "The records steward is available from 13:00 to 17:00."
    )
    member = chunk(body)
    start = body.index("09:00")
    calls = []

    async def reader(*args, **kwargs):
        return [
            ReaderSelection(
                passage_span(body, start, start + 5),
                {
                    "raw_span": {"start": start, "end": start + 5, "text": "09:00"},
                    "null_margin": -3.0,
                },
            )
        ]

    async def resolve(_):
        return single_chunk_source(member)

    async def support(pairs, **kwargs):
        calls.extend(pairs)
        return [
            SupportAssessment("neutral", (0.0, 0.0, 5.0), -5.0, False, 64)
            if reject_check and i == 2
            else SupportAssessment("entailment", (0.0, 5.0, 0.0), 5.0, True, 64)
            for i, _ in enumerate(pairs)
        ]

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", reader)
    monkeypatch.setattr(requirement_answers.support_service, "assess", support)
    candidates = []
    found = await requirement_answers._find_witnesses(
        requirement(), [member], config(), candidates, resolve_source=resolve
    )
    assert bool(found) is not reject_check
    assert len(calls) == 4
    assert calls[1].premise.endswith("12:00.")
    assert calls[2].premise.endswith("17:00.")
    assert calls[-1].premise == body
    if found:
        assert found[0].value == body
