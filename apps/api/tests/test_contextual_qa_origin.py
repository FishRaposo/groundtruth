"""Real discovery/assessment producer, UNITONLY model-service inputs.

Exposes the live612 metadata mismatch without fabricating candidate.origin.
No successful API or genuine model outcome is claimed by this regression.
"""

import pytest
from app.models.chunk import Chunk
from app.services import requirement_answers
from app.services.answer_reader import ReaderSelection, passage_span
from app.services.answer_requirements import plan_requirements
from app.services.answer_support import SupportAssessment
from app.services.procedure_evidence import resolve_version
from app.services.retrieval.scoped import scored_chunk
from sqlalchemy import select

from tests.test_contextual_runtime_contract import configuration
from tests.test_contextual_scope_sql import PRINCIPAL, publish

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize("contextual", [True, False])
async def test_actual_qa_producer_records_contextual_origin_without_changing_legacy(
    connected_db, monkeypatch, contextual
):
    db, _ = connected_db
    body = (
        "The Copper cipher wheel uses a 26-letter alphabet. "
        "The alignment check lasts 7 minutes."
    )
    if not contextual:
        body = "The Copper alignment check lasts 7 minutes."
    doc = await publish(db, 1701, body)
    await db.commit()
    chunk = await db.scalar(select(Chunk).where(Chunk.document_id == doc.id))
    assert chunk is not None
    member = scored_chunk(chunk, doc, 1.0)
    start = body.index("7 minutes")
    value = "7 minutes" if contextual else "7"
    end = start + len(value)
    raw = {"start": start, "end": end, "text": value}

    async def qa(*args, **kwargs):
        return [
            ReaderSelection(
                passage_span(body, start, end),
                {"raw_span": raw, "null_margin": -3.0},
            )
        ]

    async def nli(pairs, **kwargs):
        return [
            SupportAssessment("entailment", (0.0, 5.0, 0.0), 5.0, True, 28)
            for _ in pairs
        ]

    request = requirement_answers.QueryRequest(
        question=(
            "How long is the Copper alignment check?"
            if contextual
            else "How long does Copper alignment check last?"
        )
    )
    config = configuration()
    if not contextual:
        config.EVIDENCE_READING_PROFILE = "clause_bound_v1"
    req = plan_requirements(
        request.question, reading_profile=config.EVIDENCE_READING_PROFILE
    )[0]
    inspected = {}

    async def resolve(member):
        return await resolve_version(db, PRINCIPAL, request, member, inspected)

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", nli)
    candidates = []
    found = await requirement_answers._find_witnesses(
        req, [member], config, candidates, resolve_source=resolve
    )
    if not contextual:
        assert found
        assert all(
            "origin" not in c
            for c in candidates
            if c.get("proposal", {}).get("origin") == "qa_reader"
        )
        return
    assert found
    supported = [c for c in candidates if c.get("decision") == "supported"]
    assert supported and supported[0]["proposal"]["origin"] == "qa_reader"
    assert supported[0]["origin"] == "qa_reader"
