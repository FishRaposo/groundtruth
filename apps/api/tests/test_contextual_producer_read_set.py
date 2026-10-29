"""Producer branch regression, real SQLite; UNITONLY injected model witness.

This tests publication-inventory wiring, not genuine inference or API success.
The separate real-process test owns model/API acceptance.
"""

from app.models.chunk import Chunk
from app.models.query import AnswerSpan, QueryRequest
from app.services import requirement_answers
from app.services.retrieval.scoped import scored_chunk
from sqlalchemy import select

from tests.test_contextual_runtime_contract import configuration
from tests.test_contextual_scope_sql import PRINCIPAL, publish

pytest_plugins = ["tests.test_connected_contract"]


async def test_actual_contextual_fact_producer_captures_publication_inventory(
    connected_db, monkeypatch
):
    db, _ = connected_db
    body = "The Copper check lasts 7 minutes."
    doc = await publish(db, 1601, body)
    await db.commit()
    chunk = await db.scalar(select(Chunk).where(Chunk.document_id == doc.id))
    assert chunk is not None
    member = scored_chunk(chunk, doc, 1.0)

    async def fixed_witness(*args, **kwargs):
        return [
            requirement_answers.Witness(
                "r1",
                member,
                AnswerSpan(start=0, end=len(body), text=body),
                "7 minutes",
                "The Copper check lasts 7 minutes",
                5.0,
                -3.0,
            )
        ]

    async def current(candidate):
        return True

    monkeypatch.setattr(requirement_answers, "_find_scoped_witnesses", fixed_witness)
    result = await requirement_answers.select_requirement_answer(
        db,
        QueryRequest(question="How long is the Copper check?"),
        PRINCIPAL,
        [member],
        configuration(),
        validate_current=current,
    )
    assert result.reason is None
    assert result.chunks and result.requirements[0]["status"] == "supported"
    assert result.procedure_read_set["sources"][0]["chunk_id"] == str(chunk.id)
    assert result.procedure_read_set["after_proofs"]["consistent"] is True


async def test_revoked_fact_is_not_mislabeled_as_a_curated_conflict(
    connected_db, monkeypatch
):
    db, _ = connected_db
    body = "The Copper check lasts 7 minutes."
    doc = await publish(db, 1602, body)
    await db.commit()
    chunk = await db.scalar(select(Chunk).where(Chunk.document_id == doc.id))
    assert chunk is not None
    member = scored_chunk(chunk, doc, 1.0)

    async def revoke_after_model_boundary(*args, **kwargs):
        doc.owner_id = "different-owner"
        await db.commit()
        return [
            requirement_answers.Witness(
                "r1",
                member,
                AnswerSpan(start=0, end=len(body), text=body),
                "7 minutes",
                "The Copper check lasts 7 minutes",
                5.0,
                -3.0,
            )
        ]

    async def current(candidate):
        return True

    monkeypatch.setattr(
        requirement_answers, "_find_scoped_witnesses", revoke_after_model_boundary
    )
    result = await requirement_answers.select_requirement_answer(
        db,
        QueryRequest(question="How long is the Copper check?"),
        PRINCIPAL,
        [member],
        configuration(),
        validate_current=current,
    )
    assert not result.chunks
    assert result.requirements[0]["status"] == "unsupported"
    assert result.reason and "changed" in result.reason.lower()
    assert "curated conflict" not in result.reason.lower()
