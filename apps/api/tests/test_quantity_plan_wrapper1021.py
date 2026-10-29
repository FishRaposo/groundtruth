"""Actual capture/real context wrapper; UNITONLY retained NI, no live services."""

import json
from dataclasses import replace
from functools import lru_cache
from types import SimpleNamespace

import pytest
from app.services import planning_declarations as source
from app.services.captured_answer_planning import CapturedAnswerContext
from app.services.captured_plan_binding import reconstruct_request
from app.services.captured_plan_inputs import capture_inputs_v2
from app.services.captured_planning_support import prepare_planning_assertions
from app.services.literal_quantity import QuantityUnresolved, produce_quantity_candidate

from tests.captured_inputs_unit932.fixtures import authoritative
from tests.planning_library_unit830.test_support import retained
from tests.test_source_stated_quantity1010 import actual


@lru_cache
def context():
    _, _, _, _, _, args = actual()
    prepared = prepare_planning_assertions(**args)
    observations, executions = retained(prepared)
    inputs = capture_inputs_v2(
        **args, observations=observations, actual_executions=executions
    )
    snapshots = authoritative(inputs)
    plan = reconstruct_request(
        inputs,
        question=args["question"],
        authoritative_snapshots=snapshots,
        retained_inputs=inputs,
        require_runtime=False,
    )
    return CapturedAnswerContext(
        plan, source.canonical(inputs), source.canonical(snapshots)
    )


def produce(plan):
    data, req, snapshot, identity, direct, _ = actual()
    row = data["candidates"][0]
    part = next(c for c in snapshot.chunks if c.chunk_id == row["chunk_id"])
    return produce_quantity_candidate(
        req,
        snapshot.body,
        source_identity=identity,
        chunk_content=part.literal.text,
        chunk_start=part.literal.start,
        raw_start=row["raw_span"]["start"],
        raw_end=row["raw_span"]["end"],
        evidence_profile=json.loads(direct.evidence_profile_json),
        request_plan=plan,
    )


def test_real_context_record_authority_and_direct_plan_paths_agree():
    wrapped = context()
    before = wrapped.record()
    assert produce(wrapped) == produce(wrapped.plan)
    assert wrapped.record() == before == wrapped.plan.record()
    assert produce(wrapped)[1]["method"] == "source_stated_qualified_quantity_v1"


@pytest.mark.parametrize(
    "variant", ["missing", "foreign", "foreign_plan", "invented_record"]
)
def test_invalid_context_wrapper_cannot_supply_source_authority(variant):
    wrapped = context()
    if variant == "missing":
        bad = replace(wrapped, plan=None)
    elif variant == "foreign":
        bad = SimpleNamespace(
            plan=wrapped.plan,
            record=wrapped.record,
            question=wrapped.question,
            requirements=wrapped.requirements,
            uses=wrapped.uses,
        )
    elif variant == "foreign_plan":
        from tests.test_requested_qualified_count1008 import actual as other
        from tests.test_requested_qualified_count1008 import produce as other_produce

        # A genuine differently scoped plan cannot be substituted into this wrapper.
        _ = other()
        (_, _), options = other_produce()
        bad = replace(wrapped, plan=options["request_plan"])
    else:

        class InvalidContext(CapturedAnswerContext):
            def record(self):
                return {**super().record(), "source_productions_json": "{}"}

        bad = InvalidContext(wrapped.plan, wrapped.inputs_json, wrapped.snapshots_json)
    with pytest.raises(QuantityUnresolved):
        produce(bad)


async def test_discover_uses_real_context_wrapper_not_only_underlying_plan(monkeypatch):
    import uuid

    from app.config import Settings
    from app.models.chunk import ChunkWithScore
    from app.services import requirement_answers
    from app.services.answer_reader import ReaderSelection, passage_span
    from app.services.answer_support import SupportAssessment
    from app.services.procedure_discovery import LocatedChunk, ProcedureSource

    raw, req, snapshot, identity, _, _ = actual()
    wrapped = context()
    part = next(
        c for c in snapshot.chunks if c.chunk_id == raw["candidates"][0]["chunk_id"]
    )
    member = ChunkWithScore(
        id=uuid.UUID(part.chunk_id),
        document_id=uuid.UUID(identity["document_id"]),
        content=part.literal.text,
        chunk_index=part.ordinal,
        relevance_score=0.8,
        metadata={
            **json.loads(part.metadata_json),
            "document_version": identity["document_version"],
            "content_hash": identity["content_hash"],
        },
    )
    immutable = ProcedureSource(
        snapshot.body,
        (LocatedChunk(member, part.literal.start, part.literal.end),),
        identity,
        json.loads(snapshot.metadata_json),
        None,
    )
    span = raw["candidates"][0]["raw_span"]
    calls = []

    async def qa(*args, **kwargs):
        return [
            ReaderSelection(
                passage_span(member.content, span["start"], span["end"]),
                {"raw_span": {**span, "text": "12"}, "null_margin": -3.0},
            )
        ]

    async def ni(pairs, **kwargs):
        calls.extend(pairs)
        return [
            SupportAssessment("entailment", (-3.0, 3.0, 0.0), 3.0, True, 32)
            for _ in pairs
        ]

    async def resolve(_):
        return immutable

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", ni)
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
        PROCEDURE_SCOPE_PROFILE="activity_quote_v1",
    )
    candidates = []
    found = await requirement_answers._find_witnesses(
        req, [member], config, candidates, resolve_source=resolve, request_plan=wrapped
    )
    assert found and calls, [(c.get("decision"), c.get("reason")) for c in candidates]
    assert (
        found[0].value
        == "A Copper Index lower-bound trace uses 12 sorted integer entries."
    )
    assert found[0].proposals[0]["chunk_range"] == span
    assert found[0].quantity_binding["binding"] == produce(wrapped.plan)[1]
