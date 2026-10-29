"""Actual SQLite/API publication; explicit UNITONLY embedding/parser boundaries."""

import copy
import json
import os
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus, DocumentVersion, SourceType
from app.models.query import QueryRequest
from app.services import planning_runtime, request_parser
from app.services import staged_publication_context as context
from app.services.document.versioning import DocumentVersionManager
from app.services.staged_snapshot_store import load_staged_snapshots
from sqlalchemy import select

from tests.test_linguistic_reading_profile import CONTROLS
from tests.test_planning_declarations import CAT, capture

pytest_plugins = ["tests.test_connected_contract"]


@pytest.fixture
def tmp_path(tmp_path_factory):
    """Ordinary task-owned files locally; standard pytest directory elsewhere."""
    root = os.environ.get("STAGED_SNAPSHOT_TEST_ROOT")
    if root:
        path = Path(root) / ("api-files-" + uuid.uuid4().hex)
        path.mkdir(parents=True)
        return path
    return tmp_path_factory.mktemp("staged-snapshot849")


def staged(monkeypatch):
    settings = get_settings()
    for key, value in {
        **CONTROLS,
        "EVIDENCE_READING_PROFILE": "contextual_source_v3",
        "REQUEST_PARSER_MODE": "local_dependency",
    }.items():
        monkeypatch.setattr(settings, key, value)
    return settings


def channels(*snapshots):
    """UNITONLY identity transport subset, never a resolved plan/model proof."""
    identities = [
        {
            "document_id": str(s.document_id),
            "document_version": s.version_number,
            "content_hash": s.content_hash,
            "workspace_id": s.workspace_id,
            "snapshot_id": str(s.id),
        }
        for s in snapshots
    ]
    selection = {
        "staged_request_inputs": {
            "contract": "staged-request-inputs-v1",
            "manifest": {"publications": identities},
            "snapshots": [
                {
                    "identity": row,
                    "title": "UNTRUSTED PRESENTATION",
                    "metadata_json": '{"producer":true}',
                }
                for row in identities
            ],
        }
    }
    return selection, {"provenance": {"answer_selection": copy.deepcopy(selection)}}


async def publish_library(db, body, title="UNITONLY publication", metadata=None):
    doc = Document(
        title=title,
        source_type=SourceType.TEXT,
        status=DocumentStatus.READY,
        owner_id="owner-a",
        workspace_id="ops-a",
        metadata_=metadata or {},
    )
    db.add(doc)
    await db.commit()
    chunk = Chunk(
        document_id=doc.id,
        content=body,
        chunk_index=0,
        metadata_={"UNITONLY": True, "document_version": 1},
    )
    db.add(chunk)
    await db.flush()
    version = await DocumentVersionManager(db).create_version(
        str(doc.id), body, [chunk], workspace_id="ops-a", document=doc
    )
    return doc, version


async def test_fresh_v3_library_context_and_loader_use_stored_truth(
    connected_db, monkeypatch
):
    staged(monkeypatch)
    db, _ = connected_db
    body = "The role labels are literal.\r\n  Preserve Élan 🧭 offsets."
    doc, snapshot = await publish_library(
        db,
        body,
        metadata={
            "condition": "UNITONLY conditional",
            "source_path": "UNITONLY-private-path",
            "nested": {"api_key": "UNITONLY-not-a-credential", "kept": [1, True]},
        },
    )
    assert context.CONTEXT_KEY in snapshot.chunks[0]["metadata"]
    projection = context.validated_projection(snapshot)
    assert projection["body"] == body
    assert projection["metadata"]["normalized_content"] == body
    assert projection["metadata"]["nested"] == {"kept": [1, True]}
    assert "source_path" not in projection["metadata"]
    selection, query = channels(snapshot)
    loaded = await load_staged_snapshots(db, selection, query_context=query)
    assert loaded[str(doc.id)] == projection
    assert loaded[str(doc.id)]["title"] != "UNTRUSTED PRESENTATION"
    assert loaded[str(doc.id)]["snapshot_id"] == str(snapshot.id)


async def test_loader_includes_noncited_members_and_both_channels(
    connected_db, monkeypatch
):
    staged(monkeypatch)
    db, _ = connected_db
    a, av = await publish_library(db, "First governing body.")
    b, bv = await publish_library(db, "Second noncited body.")
    selection, _ = channels(av)
    _, retained = channels(av, bv)
    result = await load_staged_snapshots(db, selection, query_context=retained)
    assert list(result) == [str(a.id), str(b.id)]
    assert result[str(b.id)]["body"] == "Second noncited body."


async def test_v3_planning_uses_projection_and_actual_sql_receipt(
    connected_db, monkeypatch
):
    config = staged(monkeypatch)
    db, _ = connected_db
    body, observed = capture([CAT])
    doc, snapshot = await publish_library(
        db, body, metadata={"condition": "published condition"}
    )
    doc.title = "Current mutable display"
    doc.metadata_ = {**doc.metadata_, "condition": "mutable condition"}
    await db.commit()

    async def parsed(raw, config):
        assert raw == body
        return observed

    monkeypatch.setattr(request_parser, "capture_async", parsed)
    result = await planning_runtime.inspect_planning_declarations(
        db,
        {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False},
        QueryRequest(question="List activity role labels."),
        config,
    )
    actual = result.snapshots[0]
    assert actual.title == "UNITONLY publication"
    assert json.loads(actual.metadata_json)["condition"] == "published condition"
    assert (
        json.loads(actual.chunks[0].metadata_json)
        == context.validated_projection(snapshot)["chunks"][0]["metadata"]
    )
    assert "ranking_score" not in json.loads(actual.chunks[0].metadata_json)
    assert (
        json.loads(result.sql_read_set_json)["selection_mode"]
        == "all_authorized_publications_v1"
    )


async def test_missing_corrupt_and_conflicting_context_refuse(
    connected_db, monkeypatch
):
    staged(monkeypatch)
    db, _ = connected_db
    _, snapshot = await publish_library(db, "Body for strict context.")
    original = copy.deepcopy(snapshot.chunks)
    snapshot.chunks = [{**row, "metadata": {}} for row in original]
    with pytest.raises(ValueError):
        context.validated_projection(snapshot)
    snapshot.chunks = copy.deepcopy(original)
    snapshot.chunks[0]["metadata"][context.CONTEXT_KEY]["context_hash"] = "0" * 64
    with pytest.raises(ValueError):
        context.validated_projection(snapshot)
    snapshot.chunks = original
    selection, query = channels(snapshot)
    query["provenance"]["answer_selection"]["staged_request_inputs"]["snapshots"][0][
        "identity"
    ]["document_version"] = 2
    with pytest.raises(ValueError):
        await load_staged_snapshots(db, selection, query_context=query)


async def test_legacy_profile_is_unchanged_and_never_retrocertified(connected_db):
    db, _ = connected_db
    _, snapshot = await publish_library(db, "Legacy body remains legacy.")
    assert context.CONTEXT_KEY not in snapshot.chunks[0]["metadata"]
    selection, query = channels(snapshot)
    with pytest.raises(ValueError):
        await load_staged_snapshots(db, selection, query_context=query)


async def test_current_chunk_mapping_mismatch_refuses_v3(connected_db, monkeypatch):
    config = staged(monkeypatch)
    db, _ = connected_db
    doc, _ = await publish_library(db, "Current complete body.")
    chunk = await db.scalar(select(Chunk).where(Chunk.document_id == doc.id))
    chunk.id = uuid.uuid4()
    await db.commit()
    with pytest.raises(ValueError):
        await planning_runtime.inspect_planning_declarations(
            db,
            {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False},
            QueryRequest(question="List role labels."),
            config,
        )


async def test_real_inline_upload_update_history_and_reindex(real_client, monkeypatch):
    staged(monkeypatch)
    client, factory, _ = real_client
    fake = SimpleNamespace(
        signature={
            "mode": "UNITONLY",
            "model": "UNITONLY",
            "revision": "UNITONLY",
            "dimension": 2,
        },
        chunk_content=lambda body: [body],
        embed_texts=AsyncMock(side_effect=lambda bodies: [[1.0, 0.0] for _ in bodies]),
    )
    monkeypatch.setattr("app.services.ingestion_jobs.embedding_service", fake)
    monkeypatch.setattr("app.services.embedding.embedding_service", fake)
    body = "  First Élan body.\nKeep original line offsets."
    response = await client.post(
        "/api/documents/upload",
        data={"title": "First accepted title"},
        files={"files": ("unitonly.txt", body, "text/plain")},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ingestions"][0]["status"] == "completed", payload
    ident = uuid.UUID(payload["documents"][0]["id"])
    async with factory() as db:
        first = await db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == ident)
        )
        original = copy.deepcopy(first.chunks)
        selection, query = channels(first)
        assert (
            context.validated_projection(first)["metadata"]["normalized_content"]
            == body
        )
    update = await client.post(
        f"/api/v1/documents/{ident}/versions?base_version=1",
        data={"title": "Second accepted title"},
        files={
            "file": ("unitonly.txt", "Second entirely different body.", "text/plain")
        },
    )
    assert update.status_code == 200 and update.json()["status"] == "completed", (
        update.text
    )
    async with factory() as db:
        result = await load_staged_snapshots(db, selection, query_context=query)
        assert result[str(ident)]["body"] == body
        assert result[str(ident)]["title"] == "First accepted title"
        latest = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == ident,
                DocumentVersion.version_number == 2,
            )
        )
        assert (
            context.validated_projection(latest)["metadata"]["normalized_content"]
            == "Second entirely different body."
        )
        latest_chunks = copy.deepcopy(latest.chunks)
    reindexed = await client.post(f"/api/documents/{ident}/reindex")
    assert reindexed.status_code == 200 and reindexed.json()["status"] == "completed", (
        reindexed.text
    )
    async with factory() as db:
        latest = await db.get(DocumentVersion, latest.id)
        first = await db.get(DocumentVersion, first.id)
        assert latest.chunks == latest_chunks and first.chunks == original
        assert (await db.get(Document, ident)).version_number == 2

    restored = await client.post(
        f"/api/v1/documents/{ident}/versions/1/restore?base_version=2"
    )
    assert restored.status_code == 200, restored.text
    async with factory() as db:
        version = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == ident,
                DocumentVersion.version_number == 3,
            )
        )
        projection = context.validated_projection(version)
        assert projection["body"] == body
        assert projection["title"] == "First accepted title"
        assert projection["metadata"]["normalized_content"] == body
        assert (await db.get(DocumentVersion, first.id)).chunks == original


@pytest.mark.parametrize(
    "mutation",
    [
        "body",
        "version",
        "workspace",
        "chunk_metadata",
        "chunk_id",
        "title",
        "context_metadata",
        "extra_context_field",
    ],
)
async def test_stored_projection_tampering_is_rejected(
    connected_db, monkeypatch, mutation
):
    staged(monkeypatch)
    db, _ = connected_db
    _, snapshot = await publish_library(db, "UNITONLY tamper body.")
    rows = copy.deepcopy(snapshot.chunks)
    if mutation == "body":
        snapshot.normalized_content += " altered"
    elif mutation == "version":
        snapshot.version_number += 1
    elif mutation == "workspace":
        snapshot.workspace_id = "other-workspace"
    elif mutation == "chunk_metadata":
        rows[0]["metadata"]["condition"] = "new condition"
    elif mutation == "chunk_id":
        rows[0]["id"] = str(uuid.uuid4())
    elif mutation == "title":
        rows[0]["metadata"]["source_context"]["title"] = "new title"
    elif mutation == "context_metadata":
        rows[0]["metadata"][context.CONTEXT_KEY]["metadata"]["condition"] = (
            "new condition"
        )
    else:
        rows[0]["metadata"][context.CONTEXT_KEY]["unrecognized"] = True
    snapshot.chunks = rows
    with pytest.raises(ValueError):
        context.validated_projection(snapshot)


@pytest.mark.parametrize(
    "mutation",
    [
        "boolean_version",
        "duplicate",
        "missing_snapshot_id",
        "wrong_snapshot_id",
        "wrong_workspace",
        "missing_inputs",
    ],
)
async def test_loader_rejects_invalid_identity_transports(
    connected_db, monkeypatch, mutation
):
    staged(monkeypatch)
    db, _ = connected_db
    _, snapshot = await publish_library(db, "UNITONLY transport body.")
    selection, _ = channels(snapshot)
    value = selection["staged_request_inputs"]
    if mutation == "boolean_version":
        value["manifest"]["publications"][0]["document_version"] = True
    elif mutation == "duplicate":
        value["manifest"]["publications"] *= 2
    elif mutation == "missing_snapshot_id":
        del value["manifest"]["publications"][0]["snapshot_id"]
    elif mutation in {"wrong_snapshot_id", "wrong_workspace"}:
        key = "snapshot_id" if mutation == "wrong_snapshot_id" else "workspace_id"
        for row in [
            value["manifest"]["publications"][0],
            value["snapshots"][0]["identity"],
        ]:
            row[key] = str(uuid.uuid4()) if key == "snapshot_id" else "wrong-workspace"
    else:
        selection.clear()
    with pytest.raises(ValueError):
        await load_staged_snapshots(db, selection)


async def test_two_chunk_context_references_and_role_receipt(connected_db, monkeypatch):
    from app.services.linguistic_role_consumer import _record
    from app.services.role_scope_inspection import inspect_role_manifest

    staged(monkeypatch)
    db, _ = connected_db
    body = "First exact part. Second exact part."
    doc = Document(
        title="UNITONLY two chunks",
        source_type=SourceType.TEXT,
        status=DocumentStatus.READY,
        owner_id="owner-a",
        workspace_id="ops-a",
        metadata_={"condition": "retained literal"},
    )
    db.add(doc)
    await db.commit()
    chunks = [
        Chunk(
            document_id=doc.id,
            content=text,
            chunk_index=index,
            metadata_={"document_version": 1},
        )
        for index, text in enumerate(["First exact part.", "Second exact part."])
    ]
    db.add_all(chunks)
    await db.flush()
    snapshot = await DocumentVersionManager(db).create_version(
        str(doc.id), body, chunks, document=doc, workspace_id="ops-a"
    )
    projection = context.validated_projection(snapshot)
    assert len(snapshot.chunks[1]["metadata"][context.CONTEXT_KEY]) == 2
    manifest = await inspect_role_manifest(
        db,
        {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False},
        QueryRequest(question="List roles."),
    )
    assert manifest.complete
    assert _record(projection) == manifest.record()["documents"][0]
    rows = copy.deepcopy(snapshot.chunks)
    rows[1]["metadata"][context.CONTEXT_KEY]["context_hash"] = "0" * 64
    snapshot.chunks = rows
    with pytest.raises(ValueError):
        context.validated_projection(snapshot)


async def test_v3_current_sql_membership_still_rechecked_after_capture(
    connected_db, monkeypatch
):
    config = staged(monkeypatch)
    db, _ = connected_db
    body, observed = capture([CAT])
    doc, _ = await publish_library(db, body)

    async def parsed(raw, config):
        assert raw == body
        doc.owner_id = "revoked-owner"
        await db.commit()
        return observed

    monkeypatch.setattr(request_parser, "capture_async", parsed)
    with pytest.raises(ValueError, match="Planning inspection changed"):
        await planning_runtime.inspect_planning_declarations(
            db,
            {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False},
            QueryRequest(question="List role labels."),
            config,
        )


async def test_v3_library_restore_rebinds_historical_context(connected_db, monkeypatch):
    staged(monkeypatch)
    db, _ = connected_db
    fake = SimpleNamespace(
        signature={"mode": "UNITONLY", "dimension": 2},
        embed_texts=AsyncMock(side_effect=lambda bodies: [[1.0, 0.0] for _ in bodies]),
    )
    monkeypatch.setattr("app.services.embedding.embedding_service", fake)
    doc, first = await publish_library(
        db, "First immutable body.", metadata={"condition": "old condition"}
    )
    original = copy.deepcopy(first.chunks)
    doc.title = "Mutable title"
    doc.metadata_ = {"condition": "mutable condition"}
    await db.commit()
    restored = await DocumentVersionManager(db).restore_version(
        str(doc.id), 1, workspace_id="ops-a"
    )
    assert restored.version_number == 2
    snapshot = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id, DocumentVersion.version_number == 2
        )
    )
    projection = context.validated_projection(snapshot)
    assert projection["metadata"]["condition"] == "old condition"
    assert projection["title"] == "UNITONLY publication"
    live = await db.scalar(select(Chunk).where(Chunk.document_id == doc.id))
    assert context.CONTEXT_KEY not in live.metadata_
    assert first.chunks == original
