"""Document-first role inspection cannot hide unavailable or newly added sources."""

import uuid

from app.models.chunk import Chunk
from app.models.document import Document, DocumentVersion
from app.models.query import QueryRequest
from app.services.role_scope_inspection import (
    check_role_read_set,
    inspect_role_manifest,
)
from sqlalchemy import delete, select

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


def principal(keys):
    return {"id": keys["owner"], "workspace_id": "ops-a", "is_admin": False}


async def test_complete_manifest_has_exact_source_and_detects_new_scope_member(
    real_client,
):
    client, factory, keys = real_client
    document = await upload(client, "The record steward leads Meridian review.")
    request = QueryRequest(question="Who leads Meridian review session?")
    async with factory() as db:
        manifest = await inspect_role_manifest(db, principal(keys), request)
        assert manifest.complete is True
        assert len(manifest.sources) == 1
        assert manifest.sources[0].body == "The record steward leads Meridian review."
        assert manifest.sources[0].identity["document_id"] == document["id"]
        assert (
            await check_role_read_set(db, principal(keys), request, manifest.record())
        )["consistent"] is True
    await upload(
        client, "For Meridian review sessions, the lead is the duty supervisor."
    )
    async with factory() as db:
        checked = await check_role_read_set(
            db, principal(keys), request, manifest.record()
        )
    assert checked == {"consistent": False, "reason": "role_scope_inspection_changed"}


async def test_explicit_filters_narrow_manifest_without_granting_other_ownership(
    real_client,
):
    client, factory, keys = real_client
    first = await upload(client, "The record steward leads Meridian review.")
    other = await upload(
        client, "For Meridian review sessions, the lead is the duty supervisor."
    )
    async with factory() as db:
        row = await db.get(Document, uuid.UUID(other["id"]))
        row.owner_id = keys["reader"]
        await db.commit()
        request = QueryRequest(
            question="Who leads Meridian review session?",
            document_ids=[first["id"], other["id"]],
        )
        manifest = await inspect_role_manifest(db, principal(keys), request)
        assert manifest.complete is True
        assert [s.identity["document_id"] for s in manifest.sources] == [first["id"]]
        scoped = QueryRequest(question=request.question, document_ids=[])
        empty = await inspect_role_manifest(db, principal(keys), scoped)
        assert empty.complete and empty.sources == ()


async def test_ready_document_with_missing_current_chunks_blocks_complete_inspection(
    real_client,
):
    client, factory, keys = real_client
    document = await upload(
        client, "For Meridian review sessions, the lead is the duty supervisor."
    )
    async with factory() as db:
        await db.execute(
            delete(Chunk).where(Chunk.document_id == uuid.UUID(document["id"]))
        )
        await db.commit()
        manifest = await inspect_role_manifest(
            db,
            principal(keys),
            QueryRequest(question="Who leads Meridian review session?"),
        )
        assert manifest.complete is False
        assert manifest.reason == "role_scope_chunk_manifest_incomplete"
        assert manifest.read_set["documents"][0]["document_id"] == document["id"]


async def test_corrupt_snapshot_and_revoked_access_invalidate_prior_manifest(
    real_client,
):
    client, factory, keys = real_client
    document = await upload(client, "The record steward leads Meridian review.")
    request = QueryRequest(question="Who leads Meridian review session?")
    async with factory() as db:
        manifest = await inspect_role_manifest(db, principal(keys), request)
        snapshot = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == uuid.UUID(document["id"])
            )
        )
        snapshot.normalized_content = "Altered authoritative body."
        await db.commit()
        assert (
            await check_role_read_set(db, principal(keys), request, manifest.record())
        )["consistent"] is False
        snapshot.normalized_content = "The record steward leads Meridian review."
        row = await db.get(Document, uuid.UUID(document["id"]))
        row.owner_id = keys["reader"]
        await db.commit()
        assert (
            await check_role_read_set(db, principal(keys), request, manifest.record())
        )["consistent"] is False
