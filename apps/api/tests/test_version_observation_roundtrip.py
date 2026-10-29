"""The authorized version HTTP payload must carry actual archived evidence."""

import copy
import uuid

import pytest
from app.models.document import Document, DocumentVersion
from app.portfolio.coverage import canonical_source_snapshot
from app.services import staged_publication_context as archive
from sqlalchemy import select

from tests.test_connected_contract import upload
from tests.test_staged_snapshot_store849 import staged
from tests.test_staged_snapshot_store849 import tmp_path as tmp_path

pytest_plugins = ["tests.test_connected_contract"]


async def test_http_version_observation_roundtrips_immutable_projection(
    real_client, monkeypatch
):
    staged(monkeypatch)
    client, factory, _ = real_client
    source = await upload(client, "The documented activity lead is the steward.")
    async with factory() as db:
        version = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == uuid.UUID(source["id"]),
                DocumentVersion.version_number == 1,
            )
        )
        expected = archive.validated_projection(version)
        document = await db.get(Document, uuid.UUID(source["id"]))
        document.title = "Changed mutable display title"
        document.metadata_ = {**document.metadata_, "condition": "mutable-only"}
        await db.commit()
    response = await client.get(f"/api/v1/documents/{source['id']}/versions/1")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("title") == expected["title"]
    assert payload.get("metadata") == expected["metadata"]
    canonical = canonical_source_snapshot(
        source["id"],
        {
            "version_number": 1,
            "content": expected["body"],
            "content_hash": expected["content_hash"],
        },
        payload,
        expected["workspace_id"],
    )
    for key in ("snapshot_id", "title", "metadata", "body", "chunks", "workspace_id"):
        assert canonical[key] == expected[key]
    assert payload["immutable_context_status"] == "recorded"


async def test_legacy_version_does_not_invent_immutable_title_or_metadata(real_client):
    client, _, _ = real_client
    source = await upload(client, "An old portable snapshot.")
    response = await client.get(f"/api/v1/documents/{source['id']}/versions/1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["normalized_content"] == "An old portable snapshot."
    assert payload.get("immutable_context_status") == "unrecorded"
    assert "title" not in payload and "metadata" not in payload


@pytest.mark.parametrize("corruption", ["context-hash", "source-title", "chunk-id"])
async def test_corrupt_recorded_version_context_is_safe_integrity_error(
    real_client, monkeypatch, corruption
):
    staged(monkeypatch)
    client, factory, _ = real_client
    source = await upload(client, "PRIVATE_SNAPSHOT_BODY_SHOULD_BE_WITHHELD")
    async with factory() as db:
        version = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == uuid.UUID(source["id"])
            )
        )
        chunks = copy.deepcopy(version.chunks)
        first = chunks[0]
        if corruption == "context-hash":
            first["metadata"] = {
                **first["metadata"],
                archive.CONTEXT_KEY: {
                    **first["metadata"][archive.CONTEXT_KEY],
                    "context_hash": "0" * 64,
                },
            }
        elif corruption == "source-title":
            first["metadata"]["source_context"] = {
                **first["metadata"]["source_context"],
                "title": "Changed title",
            }
        else:
            first["id"] = "not-a-uuid"
        version.chunks = chunks
        await db.commit()
    response = await client.get(f"/api/v1/documents/{source['id']}/versions/1")
    assert response.status_code == 409
    assert "PRIVATE_SNAPSHOT_BODY_SHOULD_BE_WITHHELD" not in response.text
    assert "context_hash" not in response.text
