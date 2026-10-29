"""UNITONLY inference protocol; real925 receipts never used for acceptance."""

import uuid
from copy import deepcopy
from dataclasses import replace

import pytest
from app.config import Settings
from app.evidence_policy import resolve_evidence_policy
from app.models.chunk import ChunkWithScore
from app.services import requirement_answers
from app.services.answer_reader import ReaderSelection, passage_span
from app.services.answer_requirements import Requirement
from app.services.answer_support import SupportAssessment
from app.services.procedure_evidence import (
    LocatedChunk,
    ProcedureSource,
    single_chunk_source,
)

from tests.test_composite_procedures import chunk


def _captured_duration_fixture():
    from tests.test_source_bound_location974 import actual

    raw, _, plan, _ = actual()
    requirement = next(r for r in plan.requirements if r.kind == "duration")
    identity = {k: v for k, v in raw["identity"].items() if k != "snapshot_id"}
    member = ChunkWithScore(
        id=uuid.UUID(raw["chunk_id"]),
        document_id=uuid.UUID(identity["document_id"]),
        content=raw["body"],
        chunk_index=0,
        relevance_score=1.0,
        metadata=identity,
    )
    source = ProcedureSource(
        raw["body"],
        (LocatedChunk(member, 0, len(raw["body"])),),
        identity,
        raw["metadata"],
        None,
    )
    return raw["body"], member, source, requirement, plan


async def test_new_context_is_fixed_before_score_and_omits_unrelated_source_clause(
    monkeypatch,
):
    body, member, source, req, plan = _captured_duration_fixture()
    first = "The Citrine fragment desk observation lasts 14 simulated seconds."
    old_body = "The Copper review lasts 12 minutes. The cabinet is blue."
    old_member = chunk(old_body)
    question = "How long is the Copper review?"
    old_req = Requirement(
        "UNITONLY963",
        question,
        0,
        len(question),
        question,
        "duration",
        "Copper review",
        ("copper",),
    )
    calls = []

    async def qa(*args, **kwargs):
        context = args[1][0]
        text = next(v for v in ("14 simulated seconds", "12 minutes") if v in context)
        start = context.index(text)
        return [
            ReaderSelection(
                passage_span(context, start, start + len(text)),
                {
                    "raw_span": {
                        "start": start,
                        "end": start + len(text),
                        "text": text,
                    },
                    "null_margin": -3.0,
                },
            )
        ]

    async def assess(pairs, **kwargs):
        calls.extend(pairs)
        return [
            SupportAssessment("entailment", (-3.0, 3.0, 0.0), 3.0, True, 32)
            if p.premise == first
            else SupportAssessment("contradiction", (3.0, 0.0, -3.0), -3.0, False, 40)
            for p in pairs
        ]

    sources = {member.id: source, old_member.id: single_chunk_source(old_member)}

    async def resolve(current):
        return sources[current.id]

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", assess)
    config = Settings(
        GENERATION_MODE="extractive",
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1",
        ROLE_SCOPE_POLICY="ordinary_session_activity_v1",
        PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1",
        SOURCE_CONTEXT_POLICY="scoped_note_context_v2",
        EVIDENCE_READING_PROFILE="contextual_source_v4",
        QUANTITY_VERIFICATION_PROFILE="literal_source_count_v1",
        REQUEST_PARSER_MODE="local_dependency",
        SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1",
    )
    candidates = []
    found = await requirement_answers._find_witnesses(
        req, [member], config, candidates, resolve_source=resolve, request_plan=plan
    )
    assert found
    assert calls[-1].premise == first
    supported = next(c for c in candidates if c.get("decision") == "supported")
    assert "whole_source_support" not in supported
    assert supported["fact_context_support"]["source_range"] == {
        "start": body.index(first),
        "end": body.index(first) + len(first),
    }
    calls.clear()
    old_candidates = []
    old = config.model_copy(update={"SOURCE_GOVERNANCE_PROFILE": "all_sources_v1"})
    assert not await requirement_answers._find_witnesses(
        old_req, [old_member], old, old_candidates, resolve_source=resolve
    )
    assert calls[-1].premise == old_body
    assert any("whole_source_support" in c for c in old_candidates)


async def test_actual003_atomic_duration_enters_ni_and_independent_context_replay(
    monkeypatch,
):
    from app.services import contextual_mixed_output as output
    from app.services.linguistic_property_cover import factual_claim

    from tests.planning_library_unit830.test_support import metadata

    body, member, source, requirement, plan = _captured_duration_fixture()
    text = "14 simulated seconds"
    start = body.index(text)
    calls = []

    async def qa(*args, **kwargs):
        return [
            ReaderSelection(
                passage_span(body, start, start + len(text)),
                {
                    "raw_span": {
                        "start": start,
                        "end": start + len(text),
                        "text": text,
                    },
                    "null_margin": -3.0,
                },
            )
        ]

    async def assess(pairs, **kwargs):
        calls.extend(pairs)
        return [
            SupportAssessment("entailment", (-3.0, 3.0, 0.0), 3.0, True, 32)
            for _ in pairs
        ]

    async def resolve(_):
        return source

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", assess)
    config = Settings(
        GENERATION_MODE="extractive",
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1",
        ROLE_SCOPE_POLICY="ordinary_session_activity_v1",
        PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1",
        SOURCE_CONTEXT_POLICY="scoped_note_context_v2",
        EVIDENCE_READING_PROFILE="contextual_source_v4",
        QUANTITY_VERIFICATION_PROFILE="literal_source_count_v1",
        REQUEST_PARSER_MODE="local_dependency",
        SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1",
    )
    policy = resolve_evidence_policy(config)
    candidates = []
    found = await requirement_answers._find_witnesses(
        requirement,
        [member],
        config,
        candidates,
        resolve_source=resolve,
        request_plan=plan,
    )
    assert found and len(calls) == 2
    assert all(
        p.hypothesis
        == "The observation duration for Citrine fragment desk is 14 simulated seconds."
        for p in calls
    )
    assert all(
        p.premise == "The Citrine fragment desk observation lasts 14 simulated seconds."
        for p in calls
    )
    candidate = next(c for c in candidates if c.get("decision") == "supported")
    snapshot = {
        **source.identity,
        "body": body,
        "metadata": source.metadata,
        "chunks": [{"id": str(member.id), "index": 0, "content": body}],
    }
    chunks, _ = output.factual._source_inventory({str(member.document_id): snapshot})
    chunks[str(member.id)]["source"].metadata = source.metadata
    chunks[str(member.id)]["source"].identity["workspace_id"] = source.identity[
        "workspace_id"
    ]
    settings = {"evidence_profile": policy.record(), "support": metadata()}
    descriptor, supported, _, _ = output._fact_assessment(
        requirement, candidate, candidate["proposal"], chunks, settings, plan
    )
    assert supported and len(descriptor["nli_pairs"]) == 2
    nli_pairs = descriptor["nli_pairs"]
    assert isinstance(nli_pairs, list)
    context_pair = nli_pairs[-1]
    assert isinstance(context_pair, dict)
    assert context_pair["contract"] == "source-bound-witness-scope-v1"
    for field in ("source_range", "source_metadata", "hypothesis"):
        mutated = deepcopy(candidate)
        if field == "source_range":
            mutated["fact_context_support"][field]["end"] -= 1
        elif field == "source_metadata":
            mutated["fact_context_support"][field] = {"condition": "unverified"}
        else:
            mutated["fact_context_support"][field] += " fabricated"
        with pytest.raises(ValueError):
            output._fact_assessment(
                requirement, mutated, candidate["proposal"], chunks, settings, plan
            )
    use = next(u for u in plan.uses if u.requirement_id == requirement.id)
    conditioned = replace(
        plan,
        uses=tuple(
            replace(u, conditions=(u.original,)) if u is use else u for u in plan.uses
        ),
    )
    assert factual_claim(
        requirement, body, start, start + len(text), policy=policy, plan=conditioned
    ).rejection
    assert factual_claim(
        replace(requirement, attribute="duration"),
        body,
        start,
        start + len(text),
        policy=policy,
        plan=plan,
    ).rejection
    old = resolve_evidence_policy(
        config.model_copy(update={"SOURCE_GOVERNANCE_PROFILE": "all_sources_v1"})
    )
    assert factual_claim(
        requirement, body, start, start + len(text), policy=old, plan=plan
    ).rejection
