"""Reuse canonical SQL publication checks for contextual facts and curated groups."""

from app.models.chunk import Chunk
from app.models.query import QueryRequest
from app.services.procedure_evidence import capture_read_set, check_read_set
from app.services.retrieval.scoped import scored_chunk
from sqlalchemy import select

from tests.test_contextual_scope_sql import PRINCIPAL, publish

pytest_plugins = ["tests.test_connected_contract"]


async def test_factual_group_snapshot_detects_new_opponent_before_publication(
    connected_db,
):
    db, _ = connected_db
    doc = await publish(db, 601, "The Copper check lasts 7 minutes.")
    doc.metadata_ = {"conflict_group": "UNITONLY-current-facts"}
    await db.commit()
    chunk = await db.scalar(select(Chunk).where(Chunk.document_id == doc.id))
    assert chunk is not None
    member = scored_chunk(chunk, doc, 1.0)
    request = QueryRequest(question="How long is the Copper check?")
    conflicts = [
        {
            "group": "UNITONLY-current-facts",
            "inspection_method": "factual",
        }
    ]
    captured = capture_read_set(
        [member], conflicts, request, include_factual_groups=True
    )
    assert (await check_read_set(db, PRINCIPAL, request, captured))["consistent"]
    added = await publish(db, 602, "The Copper check lasts 99 minutes.")
    added.metadata_ = {"conflict_group": "UNITONLY-current-facts"}
    await db.commit()
    result = await check_read_set(db, PRINCIPAL, request, captured)
    assert not result["consistent"]
    assert result["changed_groups"] == ["UNITONLY-current-facts"]


async def test_publication_recheck_detects_revoked_factual_source(connected_db):
    db, _ = connected_db
    doc = await publish(db, 603, "The Copper check lasts 7 minutes.")
    await db.commit()
    chunk = await db.scalar(select(Chunk).where(Chunk.document_id == doc.id))
    assert chunk is not None
    member = scored_chunk(chunk, doc, 1.0)
    request = QueryRequest(question="How long is the Copper check?")
    captured = capture_read_set([member], [], request, include_factual_groups=True)
    doc.owner_id = "different-owner"
    await db.commit()
    result = await check_read_set(db, PRINCIPAL, request, captured)
    assert not result["consistent"]
    assert result["changed_source_ids"] == [str(chunk.id)]
