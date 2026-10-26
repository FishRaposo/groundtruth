"""Curated membership does not make an unrelated fact oppose this request."""

import pytest
from app.config import Settings
from app.models.query import QueryRequest
from app.services import requirement_answers as module
from app.services.answer_support import SupportAssessment

from tests.test_requirement_cover_boundaries import chunk, valid, witness


@pytest.mark.parametrize("other_scope", ["Willow review", "Quartz cache recovery"])
async def test_unrelated_group_cannot_become_a_conflict_from_model_contradiction(
    monkeypatch, other_scope
):
    question = "Who leads Quartz review?"
    req = module.plan_requirements(question)[0]
    selected = chunk("Alice leads Quartz review.", 1)
    opponents = [
        chunk(f"Bob leads {other_scope}.", 2, "other-procedure"),
        chunk(f"Carol leads {other_scope}.", 3, "other-procedure"),
    ]

    async def found(
        current, scope, config, candidates, *, policy=None, resolve_source=None
    ):
        assert policy is not None
        assert callable(resolve_source)
        return [witness(req, selected, "Alice", "Alice leads Quartz review.")]

    async def inspect(*args, **kwargs):
        return opponents, False

    called = []

    async def contradiction(pairs, config=None):
        called.extend(pairs)
        return [
            SupportAssessment("contradiction", (5, -5, -5), -10, False) for _ in pairs
        ]

    monkeypatch.setattr(module, "_find_witnesses", found)
    monkeypatch.setattr(module, "inspect_curated_group", inspect)
    monkeypatch.setattr(module.support_service, "assess", contradiction)
    result = await module.select_requirement_answer(
        None,
        QueryRequest(question=question),
        None,
        [selected, *opponents],
        Settings(),
        validate_current=valid,
    )
    assert result.reason is None
    assert {c.id for c in result.chunks} == {selected.id}
    assert not any(group["relevant"] for group in result.conflicts)
    assert called == []


async def test_known_group_opponent_without_qa_keeps_its_curated_scope(monkeypatch):
    question = "Who leads Quartz review?"
    req = module.plan_requirements(question)[0]
    selected = chunk("Alice leads Quartz review.", 1, "review-procedure")
    # The curated opposing member omits the namespace. It receives no QA witness.
    opponent = chunk("Bob leads the review.", 2, "review-procedure")

    async def found(
        current, scope, config, candidates, *, policy=None, resolve_source=None
    ):
        assert policy is not None
        assert callable(resolve_source)
        return [witness(req, selected, "Alice", "Alice leads Quartz review.")]

    async def inspect(*args, **kwargs):
        return [selected, opponent], False

    async def contradiction(pairs, config=None):
        return [
            SupportAssessment("contradiction", (5, -5, -5), -10, False) for _ in pairs
        ]

    monkeypatch.setattr(module, "_find_witnesses", found)
    monkeypatch.setattr(module, "inspect_curated_group", inspect)
    monkeypatch.setattr(module.support_service, "assess", contradiction)
    result = await module.select_requirement_answer(
        None,
        QueryRequest(question=question),
        None,
        [selected, opponent],
        Settings(),
        validate_current=valid,
    )
    assert "curated conflict" in result.reason
    assert result.conflicts[0]["relevant"] is True


async def agreement_case(monkeypatch, *, unverified_member=False, incomplete=False):
    question = "Who leads Quartz review?"
    req = module.plan_requirements(question)[0]
    members = [
        chunk(
            "Alice leads Quartz review. Procedure A retains the record.",
            1,
            "procedures",
        ),
        chunk(
            "Alice leads Quartz review. Procedure B discards the record.",
            2,
            "procedures",
        ),
    ]
    if unverified_member:
        members.append(chunk("Bob leads Quartz review.", 3, "procedures"))

    async def found(*args, **kwargs):
        return [
            witness(req, source, "Alice", "Alice leads Quartz review.")
            for source in members[:2]
        ]

    async def inspect(*args, **kwargs):
        return members, False

    async def entail(pairs, config=None):
        return (
            []
            if incomplete
            else [SupportAssessment("entailment", (-5, 5, -5), 10, True) for _ in pairs]
        )

    monkeypatch.setattr(module, "_find_witnesses", found)
    monkeypatch.setattr(module, "inspect_curated_group", inspect)
    monkeypatch.setattr(module.support_service, "assess", entail)
    return await module.select_requirement_answer(
        None,
        QueryRequest(question=question),
        None,
        members,
        Settings(),
        validate_current=valid,
    )


async def test_opposing_procedures_do_not_veto_a_fact_with_complete_validated_agreement(
    monkeypatch,
):
    result = await agreement_case(monkeypatch)
    assert result.reason is None
    assert not result.conflicts[0]["relevant"]


async def test_missing_qa_witness_on_a_curated_opponent_cannot_be_called_agreement(
    monkeypatch,
):
    result = await agreement_case(monkeypatch, unverified_member=True)
    assert result.reason is not None
    assert result.conflicts[0]["relevant"]


async def test_incomplete_conflict_classifier_output_is_an_execution_error(monkeypatch):
    with pytest.raises(RuntimeError, match="incomplete conflict"):
        await agreement_case(monkeypatch, incomplete=True)
