"""Inspect more authorized small sources instead of inventing irrelevant scopes."""

from app.models.query import QueryRequest
from app.services.role_scope_inspection import inspect_role_manifest

from tests.test_contextual_scope_sql import PRINCIPAL, publish

pytest_plugins = ["tests.test_connected_contract"]


async def test_contextual_count_budget_preserves_unknowns_and_legacy_limit(
    connected_db,
):
    db, _ = connected_db
    for i in range(80):
        await publish(db, 1000 + i, f"Unclassified source statement number {i}.")
    await db.commit()
    question = QueryRequest(question="Who is the lead for the Copper review?")
    contextual = await inspect_role_manifest(
        db, PRINCIPAL, question, reading_profile="contextual_source_v1"
    )
    assert contextual.complete
    assert len(contextual.sources) == 80
    assert contextual.read_set["limits"] == {
        "documents": 128,
        "body_bytes": 128 * 1024,
        "total_body_bytes": 512 * 1024,
        "chunks_per_document": 256,
    }
    legacy = await inspect_role_manifest(db, PRINCIPAL, question)
    assert not legacy.complete
    assert legacy.reason == "role_scope_document_budget_exceeded"
    assert legacy.read_set["limits"]["documents"] == 64


async def test_contextual_document_budget_still_fails_closed(connected_db):
    db, _ = connected_db
    for i in range(129):
        await publish(db, 1200 + i, f"Unclassified source statement number {i}.")
    await db.commit()
    result = await inspect_role_manifest(
        db,
        PRINCIPAL,
        QueryRequest(question="Who is the lead for Copper?"),
        reading_profile="contextual_source_v1",
    )
    assert not result.complete
    assert result.reason == "role_scope_document_budget_exceeded"
    assert len(result.read_set["documents"]) == 129
