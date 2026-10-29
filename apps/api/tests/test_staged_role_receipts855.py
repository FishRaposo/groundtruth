"""Actual SQLite/API role receipts; UNITONLY embedding and identity transport."""

import copy
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.models.document import Document, DocumentVersion
from app.models.query import QueryRequest
from app.services.linguistic_role_consumer import _manifest, _record
from app.services.role_scope_inspection import (
    check_role_read_set,
    inspect_role_manifest,
)
from app.services.staged_publication_context import CONTEXT_KEY, validated_projection
from app.services.staged_snapshot_store import load_staged_snapshots
from sqlalchemy import select

from tests.test_staged_snapshot_store849 import channels, staged
from tests.test_staged_snapshot_store849 import tmp_path as tmp_path

pytest_plugins = ["tests.test_connected_contract"]


def configure(monkeypatch):
    settings = staged(monkeypatch)
    fake = SimpleNamespace(
        signature={"mode": "UNITONLY", "revision": "UNITONLY", "dimension": 2},
        chunk_content=lambda body: [body],
        embed_texts=AsyncMock(side_effect=lambda bodies: [[1.0, 0.0] for _ in bodies]),
    )
    monkeypatch.setattr("app.services.ingestion_jobs.embedding_service", fake)
    monkeypatch.setattr("app.services.embedding.embedding_service", fake)
    return settings


def principal(keys):
    return {"id": keys["owner"], "workspace_id": "ops-a", "is_admin": False}


async def publish(client):
    response = await client.post(
        "/api/documents/upload",
        data={"title": "UNITONLY accepted source"},
        files={
            "files": (
                "unitonly855.txt",
                "The record steward leads Cedar review.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ingestions"][0]["status"] == "completed", data
    return uuid.UUID(data["documents"][0]["id"])


def replay(selection, manifest):
    """UNITONLY container for actual receipt, no resolved plan/model evidence."""
    return {
        **selection,
        "evidence_profile": {"evidence_reading_profile": "contextual_source_v3"},
        "request_plan": {"question": "Who leads Cedar review?"},
        "role_scope_read_set": {
            **manifest.record(),
            "after_proofs": {"consistent": True, "reason": None},
        },
    }


async def test_actual_upload_semantic_role_receipt_matches_independent_loader(
    real_client, monkeypatch
):
    configure(monkeypatch)
    client, factory, keys = real_client
    identifier = await publish(client)
    request = QueryRequest(question="Who leads Cedar review?")
    async with factory() as db:
        snapshot = await db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == identifier)
        )
        selection, query = channels(snapshot)
        archive = await load_staged_snapshots(db, selection, query_context=query)
        manifest = await inspect_role_manifest(
            db, principal(keys), request, reading_profile="contextual_source_v3"
        )
        assert manifest.complete, manifest.reason
        assert manifest.record()["documents"] == [_record(archive[str(identifier)])]
        source = manifest.sources[0]
        assert source.metadata == archive[str(identifier)]["metadata"]
        assert [part.metadata for part in source.chunks] == [
            part["metadata"] for part in archive[str(identifier)]["chunks"]
        ]
        assert _manifest(replay(selection, manifest), archive).complete
        assert (
            await check_role_read_set(db, principal(keys), request, manifest.record())
        )["consistent"]


@pytest.mark.parametrize("mutation", ["missing", "corrupt"])
async def test_v3_missing_or_corrupt_projection_never_falls_back(
    real_client, monkeypatch, mutation
):
    configure(monkeypatch)
    client, factory, keys = real_client
    identifier = await publish(client)
    async with factory() as db:
        snapshot = await db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == identifier)
        )
        rows = copy.deepcopy(snapshot.chunks)
        if mutation == "missing":
            del rows[0]["metadata"][CONTEXT_KEY]
        else:
            rows[0]["metadata"][CONTEXT_KEY]["context_hash"] = "0" * 64
        snapshot.chunks = rows
        await db.commit()
        manifest = await inspect_role_manifest(
            db,
            principal(keys),
            QueryRequest(question="Who leads Cedar review?"),
            reading_profile="contextual_source_v3",
        )
        assert not manifest.complete
        assert manifest.reason == "role_scope_staged_publication_context_invalid"


@pytest.mark.parametrize(
    "change", ["metadata", "title", "live_metadata", "reindex", "update"]
)
async def test_archive_role_receipt_stays_immutable_but_whole_sql_recheck_changes(
    real_client, monkeypatch, change
):
    from app.models.chunk import Chunk
    from app.services.request_planning_manifest import inspect_planning_manifest
    from app.services.staged_answer_planning import recheck_inputs

    configure(monkeypatch)
    client, factory, keys = real_client
    identifier = await publish(client)
    request = QueryRequest(question="Who leads Cedar review?")
    async with factory() as db:
        snapshot = await db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == identifier)
        )
        selection, query = channels(snapshot)
        archive = await load_staged_snapshots(db, selection, query_context=query)
        old_role = await inspect_role_manifest(
            db, principal(keys), request, reading_profile="contextual_source_v3"
        )
        old_sql = await inspect_planning_manifest(db, principal(keys), request)
        assert old_role.complete and old_sql.complete
        inputs = {"sql_read_set_json": json.dumps(old_sql.record())}
        assert (await recheck_inputs(db, principal(keys), request.question, inputs))[
            "consistent"
        ]
        assert old_role.record()["index_universe"]
        old_bytes = copy.deepcopy(snapshot.chunks)
    if change in {"reindex", "update"}:
        if change == "reindex":
            fake = SimpleNamespace(
                signature={
                    "mode": "UNITONLY",
                    "revision": "UNITONLY-reindex",
                    "dimension": 2,
                },
                chunk_content=lambda body: [body],
                embed_texts=AsyncMock(
                    side_effect=lambda bodies: [[0.0, 1.0] for _ in bodies]
                ),
            )
            monkeypatch.setattr("app.services.ingestion_jobs.embedding_service", fake)
            response = await client.post(f"/api/documents/{identifier}/reindex")
        else:
            response = await client.post(
                f"/api/v1/documents/{identifier}/versions?base_version=1",
                data={"title": "Changed publication title"},
                files={
                    "file": (
                        "unitonly855.txt",
                        "The new custodian leads Cedar review.",
                        "text/plain",
                    )
                },
            )
        assert (
            response.status_code == 200 and response.json()["status"] == "completed"
        ), response.text
    else:
        async with factory() as db:
            doc = await db.get(Document, identifier)
            if change == "metadata":
                doc.metadata_ = {**doc.metadata_, "condition": "new mutable condition"}
            elif change == "title":
                doc.title = "Changed current display title"
            else:
                chunk = await db.scalar(
                    select(Chunk).where(Chunk.document_id == identifier)
                )
                chunk.metadata_ = {
                    **chunk.metadata_,
                    "condition": "new mutable chunk condition",
                }
            await db.commit()
    async with factory() as db:
        loaded = await load_staged_snapshots(db, selection, query_context=query)
        assert loaded == archive
        assert (await db.get(DocumentVersion, snapshot.id)).chunks == old_bytes
        assert _manifest(replay(selection, old_role), loaded).complete
        role_check = await check_role_read_set(
            db, principal(keys), request, old_role.record()
        )
        assert role_check["consistent"] is (change != "update")
        current_sql = await recheck_inputs(
            db, principal(keys), request.question, inputs
        )
        assert current_sql == {
            "consistent": False,
            "reason": "planning_publications_changed",
        }
        current = await inspect_role_manifest(
            db, principal(keys), request, reading_profile="contextual_source_v3"
        )
        assert current.complete
        latest = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == identifier,
                DocumentVersion.version_number == (2 if change == "update" else 1),
            )
        )
        assert current.record()["documents"] == [_record(validated_projection(latest))]


@pytest.mark.parametrize(
    "change", ["revoke", "workspace", "not_ready", "new_source", "index"]
)
async def test_v3_current_authorized_membership_and_index_recheck_remain_actual(
    real_client, monkeypatch, change
):
    from app.models.document import DocumentStatus
    from app.models.query import Query
    from app.services.connected_query import source_access
    from app.services.request_planning_manifest import inspect_planning_manifest
    from app.services.staged_answer_planning import recheck_inputs

    configure(monkeypatch)
    client, factory, keys = real_client
    identifier = await publish(client)
    request = QueryRequest(question="Who leads Cedar review?")
    async with factory() as db:
        snapshot = await db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == identifier)
        )
        selection, query = channels(snapshot)
        old_role = await inspect_role_manifest(
            db, principal(keys), request, reading_profile="contextual_source_v3"
        )
        sql = await inspect_planning_manifest(db, principal(keys), request)
        inputs = {"sql_read_set_json": json.dumps(sql.record())}
        # UNITONLY identity transport; actual source_access SQL, no API stub.
        selection.update(
            contract="requirement-evidence-v5",
            inspected_sources=[],
            requirements=[],
            candidates=[],
            procedure_contexts=[],
        )
        query = {"provenance": {"answer_selection": copy.deepcopy(selection)}}
        row = Query(
            sources=[],
            provenance={"answer_selection": selection},
            retrieval_trace=query,
        )
        assert await source_access(db, row, principal(keys))
    if change == "new_source":
        await publish(client)
    else:
        async with factory() as db:
            doc = await db.get(Document, identifier)
            if change == "revoke":
                doc.owner_id = keys["reader"]
            elif change == "workspace":
                doc.workspace_id = "other-workspace"
            elif change == "not_ready":
                doc.status = DocumentStatus.ERROR
            else:
                doc.metadata_ = {
                    **doc.metadata_,
                    "declared_source_scope": {"UNITONLY": "changed index"},
                }
            await db.commit()
    async with factory() as db:
        assert not (
            await check_role_read_set(db, principal(keys), request, old_role.record())
        )["consistent"]
        assert not (
            await recheck_inputs(db, principal(keys), request.question, inputs)
        )["consistent"]
        archive = await load_staged_snapshots(db, selection, query_context=query)
        assert _manifest(replay(selection, old_role), archive).complete
        row = Query(
            sources=[],
            provenance={"answer_selection": selection},
            retrieval_trace=query,
        )
        if change in {"revoke", "workspace"}:
            assert not await source_access(db, row, principal(keys))
        elif change == "not_ready":
            # History ACL is document_scope, separate from current READY membership.
            assert await source_access(db, row, principal(keys))
