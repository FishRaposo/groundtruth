"""Canonical HTTP ingestion publishes derived scope without changing snapshots."""

import json
import uuid
from types import SimpleNamespace

from app.config import get_settings
from app.models.document import Document, DocumentVersion
from app.services.declared_source_scope import validate_source_cover
from app.services.document.declared_scope_index import INDEX_KEY, publication_metadata
from sqlalchemy import select

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


def enable_contextual(monkeypatch):
    for name, value in {
        "ANSWER_SELECTION_MODE": "reader",
        "ANSWER_SUPPORT_MODE": "local_nli",
        "GENERATION_MODE": "extractive",
        "ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1",
        "ROLE_SCOPE_POLICY": "ordinary_session_activity_v1",
        "PROCEDURE_VERIFICATION_PROFILE": "source_declared_procedure_copy_v1",
        "SOURCE_CONTEXT_POLICY": "scoped_note_context_v2",
        "EVIDENCE_READING_PROFILE": "contextual_source_v1",
    }.items():
        monkeypatch.setattr(get_settings(), name, value)


async def test_upload_reindex_update_restore_publish_current_index_atomically(
    real_client, monkeypatch
):
    client, factory, _ = real_client
    enable_contextual(monkeypatch)
    first = "The records steward leads Meridian review."
    item = await upload(client, first)
    identifier = uuid.UUID(item["id"])
    async with factory() as db:
        doc = await db.get(Document, identifier)
        cover = doc.metadata_[INDEX_KEY]
        assert validate_source_cover(cover, first, cover["identity"])
        assert cover["identity"]["document_version"] == 1
        snapshot = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == identifier,
                DocumentVersion.version_number == 1,
            )
        )
        original_chunks = json.dumps(snapshot.chunks, sort_keys=True)
    response = await client.post(f"/api/documents/{identifier}/reindex")
    assert response.status_code == 200, response.text
    async with factory() as db:
        doc = await db.get(Document, identifier)
        assert doc.version_number == 1 and doc.metadata_[INDEX_KEY] == cover
        snapshot = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == identifier,
                DocumentVersion.version_number == 1,
            )
        )
        assert json.dumps(snapshot.chunks, sort_keys=True) == original_chunks
    updated = "The evening steward leads Meridian review."
    response = await client.post(
        f"/api/v1/documents/{identifier}/versions",
        files={"file": ("version.txt", updated, "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed", response.text
    async with factory() as db:
        doc = await db.get(Document, identifier)
        assert doc.version_number == 2
        assert doc.metadata_[INDEX_KEY]["identity"]["document_version"] == 2
        assert validate_source_cover(
            doc.metadata_[INDEX_KEY], updated, doc.metadata_[INDEX_KEY]["identity"]
        )
    response = await client.post(f"/api/v1/documents/{identifier}/versions/1/restore")
    assert response.status_code == 200, response.text
    async with factory() as db:
        doc = await db.get(Document, identifier)
        assert doc.version_number == 3
        assert doc.metadata_[INDEX_KEY]["identity"]["document_version"] == 3
        assert validate_source_cover(
            doc.metadata_[INDEX_KEY], first, doc.metadata_[INDEX_KEY]["identity"]
        )
        snapshot = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == identifier,
                DocumentVersion.version_number == 1,
            )
        )
        assert json.dumps(snapshot.chunks, sort_keys=True) == original_chunks


async def test_legacy_publication_does_not_claim_a_contextual_index(real_client):
    client, factory, _ = real_client
    item = await upload(client, "The records steward leads Meridian review.")
    async with factory() as db:
        doc = await db.get(Document, uuid.UUID(item["id"]))
        assert INDEX_KEY not in doc.metadata_


def test_legacy_adapter_preserves_opaque_metadata_and_requires_no_new_controls():
    metadata = {"custom": "kept", INDEX_KEY: {"historical": "opaque"}}
    actual = publication_metadata(
        metadata,
        "body",
        document_id="legacy",
        version=1,
        workspace=None,
        config=SimpleNamespace(),
    )
    assert actual == metadata
    assert actual is not metadata
