"""Actual exposed count inputs through inference seams, not model acceptance."""

import json
import uuid

from app.config import Settings
from app.models.chunk import ChunkWithScore
from app.services import requirement_answers
from app.services.answer_reader import ReaderSelection, passage_span
from app.services.answer_support import SupportAssessment
from app.services.procedure_discovery import LocatedChunk, ProcedureSource

from tests.test_typed_count_fields968 import actual


async def test_actual_atomic_quantity_keeps_count_proof_through_output_replay(
    monkeypatch,
):
    requirement, snapshot, identity, plan, _ = actual()
    assert len(snapshot.chunks) == 1
    part = snapshot.chunks[0]
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
    source = ProcedureSource(
        snapshot.body,
        (LocatedChunk(member, part.literal.start, part.literal.end),),
        identity,
        json.loads(snapshot.metadata_json),
        None,
    )
    value = "6"
    start = member.content.index("6 datagram fragments")
    calls = []

    async def qa(*args, **kwargs):
        return [
            ReaderSelection(
                passage_span(member.content, start, start + len(value)),
                {
                    "raw_span": {
                        "start": start,
                        "end": start + len(value),
                        "text": value,
                    },
                    "null_margin": -3.0,
                },
            )
        ]

    async def ni(pairs, **kwargs):
        calls.extend(pairs)
        return [
            SupportAssessment("entailment", (-3.0, 3.0, 0.0), 3.0, True, 32)
            for _ in pairs
        ]

    async def resolve(_):
        return source

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
    )
    candidates = []
    found = await requirement_answers._find_witnesses(
        requirement,
        [member],
        config,
        candidates,
        resolve_source=resolve,
        request_plan=plan,
    )
    assert found and calls, [(c.get("decision"), c.get("reason")) for c in candidates]
    assert found[0].value == "6 datagram fragments"
    candidate = next(c for c in candidates if c.get("decision") == "supported")
    assert (
        candidate["quantity_binding"]["binding"]["method"]
        == "typed_atomic_count_field_v1"
    )

    from app.services import contextual_mixed_output as output

    from tests.planning_library_unit830.test_support import metadata

    wire = {
        **identity,
        "body": source.body,
        "metadata": source.metadata,
        "chunks": [{"id": str(member.id), "index": 0, "content": member.content}],
    }
    chunks, _ = output.factual._source_inventory({identity["document_id"]: wire})
    chunks[str(member.id)]["source"].metadata = source.metadata
    # Match the real mixed-output _sources enrichment after snapshot decoding.
    chunks[str(member.id)]["source"].identity["workspace_id"] = identity["workspace_id"]
    settings = {
        "evidence_profile": json.loads(plan.evidence_profile_json),
        "support": metadata(),
    }
    descriptor, supported, _, _ = output._fact_assessment(
        requirement,
        candidate,
        candidate["proposal"],
        chunks,
        settings,
        plan,
    )
    assert supported
    assert descriptor["quantity_binding"] == candidate["quantity_binding"]
