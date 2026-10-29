"""UNITONLY model doubles; actual source resolution and claim binding."""

import pytest
from app.services import requirement_answers
from app.services.answer_reader import ReaderSelection, passage_span
from app.services.answer_requirements import plan_requirements
from app.services.answer_support import SupportAssessment
from app.services.procedure_evidence import single_chunk_source

from tests.test_composite_procedures import chunk
from tests.test_linguistic_runtime_dispatch import config


@pytest.mark.parametrize("whole_supported", [False, True])
async def test_factual_witness_requires_the_full_source_not_only_favorable_clause(
    monkeypatch, whole_supported
):
    body = (
        "The Copper alignment check lasts 7 minutes. "
        "A separate note qualifies this rule."
    )
    member = chunk(body)
    question = "How long is the Copper alignment check?"
    requirement = plan_requirements(question, reading_profile="contextual_source_v1")[0]
    start = body.index("7 minutes")
    calls = []

    async def qa(*args, **kwargs):
        return [
            ReaderSelection(
                passage_span(body, start, start + 9),
                {
                    "raw_span": {"start": start, "end": start + 9, "text": "7 minutes"},
                    "null_margin": -3.0,
                },
            )
        ]

    async def nli(pairs, **kwargs):
        calls.extend(pairs)
        return [
            SupportAssessment("entailment", (0.0, 5.0, 0.0), 5.0, True, 32)
            if p.premise != body or whole_supported
            else SupportAssessment("neutral", (0.0, 0.0, 5.0), -5.0, False, 32)
            for p in pairs
        ]

    async def resolve(_):
        return single_chunk_source(member)

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", nli)
    candidates = []
    witnesses = await requirement_answers._find_witnesses(
        requirement, [member], config(), candidates, resolve_source=resolve
    )
    assert any(p.premise == body for p in calls)
    assert bool(witnesses) is whole_supported
    checked = [c for c in candidates if "whole_source_support" in c]
    assert checked and checked[0]["whole_source_support"]["premise"] == body
    assert (
        checked[0]["whole_source_support"]["assessment"]["supported"] is whole_supported
    )
    assert (
        checked[0]["whole_source_support"]["source_identity"]["content_hash"]
        == member.metadata["content_hash"]
    )
