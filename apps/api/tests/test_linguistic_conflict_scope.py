"""UNITONLY NLI service; immutable current group resolution is exercised."""

from types import SimpleNamespace

import pytest
from app.models.query import QueryRequest
from app.services import procedure_evidence, requirement_answers
from app.services.answer_requirements import Requirement
from app.services.answer_support import SupportAssessment
from app.services.procedure_evidence import single_chunk_source

from tests.test_composite_procedures import chunk
from tests.test_linguistic_runtime_dispatch import config


@pytest.mark.parametrize(
    "label,expected",
    [("contradiction", False), ("neutral", True), ("entailment", True)],
)
async def test_curated_scope_inspects_full_sources_without_opponent_qa_answers(
    monkeypatch, label, expected
):
    question = "Give the complete ordinary Zinc review routine."
    req = Requirement(
        "r1",
        question,
        0,
        len(question),
        question,
        "procedure",
        "ordinary Zinc review",
        ("zinc",),
    )
    members = [
        chunk(
            "This directive governs the isolated audit variant of Zinc review. "
            f"{action} It does not govern the ordinary Zinc review."
        )
        for action in ["Delete the duplicate.", "Retain the duplicate."]
    ]
    sources = {m.id: single_chunk_source(m) for m in members}
    calls = []

    async def resolve(db, principal, request, member, inspected):
        return sources[member.id]

    async def nli(pairs, **kwargs):
        calls.extend(pairs)
        logits = {
            "contradiction": (5.0, 0.0, 0.0),
            "neutral": (0.0, 0.0, 5.0),
            "entailment": (0.0, 5.0, 0.0),
        }[label]
        return [
            SupportAssessment(
                label,
                logits,
                5.0 if label == "entailment" else -5.0,
                label == "entailment",
                64,
            )
            for _ in pairs
        ]

    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    monkeypatch.setattr(requirement_answers.support_service, "assess", nli)
    result = await requirement_answers._inspect_procedure_group(
        None,
        QueryRequest(question=question),
        None,
        req,
        config(),
        members,
        False,
        [
            SimpleNamespace(
                chunk=members[0], value="actual selected copy", completeness={}
            )
        ],
        {},
        [],
    )
    assert result["inspection_method"] == "curated-whole-source-scope-v1"
    assert result["relevant"] is expected
    assert len(result["source_extent_checks"]) == 2
    assert {pair.premise for pair in calls} == {s.body for s in sources.values()}
    assert all(
        row["scope_excluded"] is (not expected)
        for row in result["source_extent_checks"]
    )
