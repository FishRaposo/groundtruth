"""Actual in-memory SQLite queries via an immediate async adapter, UNITONLY.

The adapter executes real SQL statements; it does not exercise async driver
cancellation, HTTP authorization, models, or publication races.
"""

import uuid
from contextlib import nullcontext
from copy import deepcopy

import pytest
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus, DocumentVersion, SourceType
from app.services.procedure_output import load_snapshots
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session

from tests.test_linguistic_role_consumer import role_data


def mutate_rows(document, version, chunk, mutation):
    if mutation == "metadata":
        document.metadata_ = {"condition": "emergency"}
    elif mutation == "owner":
        document.owner_id = "another-owner"
    elif mutation == "version":
        document.version_number += 1
    elif mutation == "snapshot":
        version.id = uuid.uuid4()
    elif mutation == "chunk":
        chunk.content = "Changed current chunk"


def load_from_sql(
    monkeypatch,
    *,
    profile="contextual_source_v2",
    mutation=None,
    include_inspected=False,
):
    data = role_data()
    snapshot = next(iter(data["source_snapshots"].values()))
    engine = create_engine("sqlite:///:memory:")
    for table in (Document.__table__, DocumentVersion.__table__, Chunk.__table__):
        assert isinstance(table, Table)
        table.create(engine)
    with Session(engine) as db:
        document = Document(
            id=uuid.UUID(snapshot["document_id"]),
            title="Role UNITONLY",
            source_type=SourceType.TEXT,
            status=DocumentStatus.READY,
            workspace_id=snapshot["workspace_id"],
            owner_id=snapshot["owner_id"],
            version_number=snapshot["document_version"],
            content_hash=snapshot["content_hash"],
            metadata_=deepcopy(snapshot["metadata"]),
        )
        version = DocumentVersion(
            id=uuid.UUID(snapshot["snapshot_id"]),
            document_id=document.id,
            workspace_id=document.workspace_id,
            version_number=document.version_number,
            content_hash=document.content_hash,
            normalized_content=snapshot["body"],
            chunks=deepcopy(snapshot["chunks"]),
        )
        part = snapshot["chunks"][0]
        chunk = Chunk(
            id=uuid.UUID(part["id"]),
            document_id=document.id,
            content=part["content"],
            chunk_index=part["index"],
            metadata_={},
        )
        db.add_all([document, version, chunk])
        db.commit()
        mutate_rows(document, version, chunk, mutation)
        db.commit()
        calls = []

        class ImmediateSQL:
            no_autoflush = nullcontext()

            async def scalar(self, statement):
                calls.append(str(statement))
                return db.scalar(statement)

            async def scalars(self, statement):
                calls.append(str(statement))
                return db.scalars(statement)

        async def immediate(awaitable):
            return await awaitable

        monkeypatch.setattr("app.db.cancellation.complete_read", immediate)
        selection = data["selection"]
        selection["evidence_profile"]["evidence_reading_profile"] = profile
        # Role documents alone must request their own independent snapshots.
        if not include_inspected:
            selection["inspected_sources"] = []
        operation = load_snapshots(ImmediateSQL(), selection)
        try:
            operation.send(None)
        except StopIteration as done:
            return done.value, calls
        finally:
            operation.close()
            db.close()
            engine.dispose()
        raise AssertionError("Immediate SQL adapter unexpectedly suspended")


def test_v2_role_manifest_loads_every_body_metadata_and_chunk_receipt(monkeypatch):
    snapshots, calls = load_from_sql(monkeypatch)
    assert len(snapshots) == 1
    actual = next(iter(snapshots.values()))
    assert actual["owner_id"] == "owner-a" and actual["status"] == "ready"
    assert actual["role_live_chunks"][0]["metadata"] == {}
    assert len(calls) == 3


@pytest.mark.parametrize(
    "mutation", ["metadata", "owner", "version", "snapshot", "chunk"]
)
def test_loader_cannot_obtain_receipt_authority_from_retained_flags(
    monkeypatch, mutation
):
    with pytest.raises(ValueError):
        load_from_sql(monkeypatch, mutation=mutation)


def test_legacy_profile_does_not_expand_role_only_snapshot_universe(monkeypatch):
    snapshots, calls = load_from_sql(monkeypatch, profile="contextual_source_v1")
    assert snapshots == {} and calls == []


def test_legacy_loaded_snapshot_keeps_its_original_shape(monkeypatch):
    snapshots, calls = load_from_sql(
        monkeypatch, profile="contextual_source_v1", include_inspected=True
    )
    assert len(calls) == 1
    assert set(next(iter(snapshots.values()))) == {
        "document_id",
        "document_version",
        "content_hash",
        "workspace_id",
        "body",
        "chunks",
        "captured_scope",
        "metadata",
    }
