"""Actual ASGI/SQLite upload; generic UNITONLY documents, no model calls."""

import copy
import json
import uuid
from pathlib import Path

import pytest
from app.config import get_settings
from app.models.document import Document, DocumentVersion
from app.models.ingestion import IngestionJob
from app.services.staged_publication_context import validated_projection
from app.services.staged_snapshot_store import load_staged_snapshots
from sqlalchemy import func, select

from tests.test_staged_snapshot_store849 import channels, staged
from tests.test_staged_snapshot_store849 import tmp_path as tmp_path

pytest_plugins = ["tests.test_connected_contract"]

PUBLIC = {
    "condition": "UNITONLY ordinary review",
    "conflict_group": "UNITONLY-review-policy",
    "description": "UNITONLY source configuration",
    "tags": ["UNITONLY", "review"],
    "labels": {"purpose": "UNITONLY"},
    "fixture_kind": "UNITONLY-protocol",
    "portfolio_logical_id": "UNITONLY867-document",
    "synthetic": True,
}


async def test_initial_upload_metadata_is_archived_before_any_later_overlay(
    real_client, monkeypatch
):
    staged(monkeypatch)
    client, factory, keys = real_client
    body = "UNITONLY initial policy paragraph."
    response = await client.post(
        "/api/documents/upload",
        data={"title": "UNITONLY declared policy", "metadata": json.dumps(PUBLIC)},
        files={"files": ("unitonly867.txt", body, "text/plain")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["ingestions"][0]["status"] == "completed", response.text
    ident = uuid.UUID(response.json()["documents"][0]["id"])
    async with factory() as db:
        first = await db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == ident)
        )
        projection = validated_projection(first)
        assert {key: projection["metadata"].get(key) for key in PUBLIC} == PUBLIC
        assert projection["title"] == "UNITONLY declared policy"
        assert (
            projection["owner_id"] == keys["owner"]
            and projection["workspace_id"] == "ops-a"
        )
        old = copy.deepcopy(first.chunks)
        selection, query = channels(first)
    update = await client.post(
        f"/api/v1/documents/{ident}/versions?base_version=1",
        files={
            "file": (
                "unitonly867.txt",
                "UNITONLY changed policy paragraph.",
                "text/plain",
            )
        },
    )
    assert update.status_code == 200 and update.json()["status"] == "completed", (
        update.text
    )
    async with factory() as db:
        loaded = await load_staged_snapshots(db, selection, query_context=query)
        assert loaded[str(ident)] == projection
        assert (await db.get(DocumentVersion, first.id)).chunks == old
        assert (
            len(
                list(
                    (
                        await db.scalars(
                            select(DocumentVersion).where(
                                DocumentVersion.document_id == ident
                            )
                        )
                    ).all()
                )
            )
            == 2
        )


async def test_privileged_metadata_rejected_before_any_application_files_or_rows(
    real_client, monkeypatch
):
    staged(monkeypatch)
    client, factory, _ = real_client
    response = await client.post(
        "/api/documents/upload",
        data={"metadata": '{"owner_id":"UNITONLY-admin"}'},
        files={"files": ("unitonly867.txt", "UNITONLY rejected upload.", "text/plain")},
    )
    assert response.status_code == 422, response.text
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(Document)) == 0
        assert await db.scalar(select(func.count()).select_from(IngestionJob)) == 0
        assert await db.scalar(select(func.count()).select_from(DocumentVersion)) == 0
    assert not list(Path(get_settings().STORAGE_ROOT).rglob("*"))


@pytest.mark.parametrize(
    "raw",
    [
        '{"workspace_id":"UNITONLY-other"}',
        '{"visibility":"public"}',
        '{"source_context":{"title":"UNITONLY-forged"}}',
        '{"api_key":"UNITONLY_REJECTED_NEVER_ECHO"}',
        '{"condition":true}',
        "true",
        '{"synthetic":1}',
        '{"labels":{"apiKey":"UNITONLY_REJECTED_NEVER_ECHO"}}',
        '{"condition":"first","condition":"second"}',
        '{"labels":{"dept":"first","dept":"second"}}',
        '{"unknown_public_field":"UNITONLY"}',
        '{"description":' + ("[" * 8) + '"UNITONLY"' + ("]" * 8) + "}",
        (" " * (32 * 1024)) + "{}",
        '{"condition":NaN}',
    ],
    ids=[
        "workspace",
        "visibility",
        "source_context",
        "credential",
        "condition_bool",
        "top_bool",
        "synthetic_int",
        "label_credential",
        "duplicate_top",
        "duplicate_nested",
        "unknown",
        "depth",
        "bytes",
        "nonfinite",
    ],
)
async def test_invalid_metadata_has_zero_application_side_effects(
    real_client, monkeypatch, raw
):
    staged(monkeypatch)
    client, factory, _ = real_client
    response = await client.post(
        "/api/documents/upload",
        data={"metadata": raw},
        files={"files": ("unitonly867.txt", "UNITONLY rejected bytes.", "text/plain")},
    )
    assert response.status_code == 422, response.text
    assert "UNITONLY_REJECTED_NEVER_ECHO" not in response.text
    async with factory() as db:
        for model in (Document, IngestionJob, DocumentVersion):
            assert await db.scalar(select(func.count()).select_from(model)) == 0
    assert not list(Path(get_settings().STORAGE_ROOT).rglob("*"))


async def test_duplicate_form_metadata_and_complete_file_limits_precede_writes(
    real_client, monkeypatch
):
    staged(monkeypatch)
    client, factory, _ = real_client
    duplicate = await client.post(
        "/api/documents/upload",
        files=[
            ("metadata", (None, "{}")),
            ("metadata", (None, "{}")),
            ("files", ("unitonly867.txt", b"UNITONLY", "text/plain")),
        ],
    )
    assert duplicate.status_code == 422, duplicate.text
    six = await client.post(
        "/api/documents/upload",
        data={"metadata": json.dumps(PUBLIC)},
        files=[
            ("files", (f"unitonly{i}.txt", b"UNITONLY", "text/plain")) for i in range(6)
        ],
    )
    assert six.status_code == 400, six.text
    oversized = await client.post(
        "/api/documents/upload",
        data={"metadata": json.dumps(PUBLIC)},
        files={"files": ("unitonly.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain")},
    )
    assert oversized.status_code == 413, oversized.text
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(Document)) == 0
        assert await db.scalar(select(func.count()).select_from(IngestionJob)) == 0
    assert not list(Path(get_settings().STORAGE_ROOT).rglob("*"))


async def test_five_file_batch_copies_untrusted_metadata_without_granting_access(
    real_client, monkeypatch
):
    staged(monkeypatch)
    client, factory, keys = real_client
    response = await client.post(
        "/api/documents/upload",
        data={"metadata": json.dumps(PUBLIC)},
        files=[
            ("files", (f"unitonly{i}.txt", f"UNITONLY body {i}.", "text/plain"))
            for i in range(5)
        ],
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["documents"]) == len(response.json()["ingestions"]) == 5
    async with factory() as db:
        for doc in (await db.scalars(select(Document))).all():
            assert doc.owner_id == keys["owner"] and doc.workspace_id == "ops-a"
            assert {key: doc.metadata_[key] for key in PUBLIC} == PUBLIC
        assert await db.scalar(select(func.count()).select_from(DocumentVersion)) == 5


async def test_create_job_revalidates_and_only_merges_initial_public_fields(
    connected_db,
):
    from app.models.document import SourceType
    from app.services.document.evidence_metadata import EvidenceMetadataError
    from app.services.ingestion_jobs import create_job

    db, _ = connected_db
    doc = Document(
        title="UNITONLY boundary",
        source_type=SourceType.TEXT,
        owner_id="owner-a",
        workspace_id="ops-a",
        metadata_={"generated_marker": "trusted"},
    )
    db.add(doc)
    await db.commit()
    with pytest.raises(EvidenceMetadataError):
        await create_job(
            db,
            doc,
            {"id": "owner-a"},
            source_path=None,
            evidence_metadata={"owner_id": "UNITONLY-forged"},
        )
    assert doc.metadata_ == {"generated_marker": "trusted"}
    job = await create_job(
        db,
        doc,
        {"id": "owner-a"},
        source_path=None,
        evidence_metadata={"condition": "UNITONLY condition"},
    )
    assert doc.metadata_ == {
        "generated_marker": "trusted",
        "condition": "UNITONLY condition",
    }
    assert job.owner_id == "owner-a" and job.workspace_id == "ops-a"
    doc.version_number = 1
    with pytest.raises(EvidenceMetadataError):
        await create_job(
            db,
            doc,
            {"id": "owner-a"},
            source_path=None,
            kind="update",
            evidence_metadata={"condition": "replacement"},
        )
    assert doc.metadata_["condition"] == "UNITONLY condition"


def test_metadata_schema_is_strict_bounded_and_does_not_coerce():
    from app.services.document.evidence_metadata import (
        EvidenceMetadataError,
        parse_evidence_metadata,
        validate_evidence_metadata,
    )

    assert parse_evidence_metadata('{"condition":null,"synthetic":true}') == {
        "condition": None,
        "synthetic": True,
    }
    assert parse_evidence_metadata("{}") == {}
    for value in (
        {"tags": [True]},
        {"labels": [False]},
        {"roles": ["admin"]},
        {"is_admin": True},
        {"version_number": 1},
        {"declared_source_scope": {}},
        {"_upload_extension": ".exe"},
        {"synthetic": "true"},
    ):
        with pytest.raises(EvidenceMetadataError):
            validate_evidence_metadata(value)
    with pytest.raises(EvidenceMetadataError):
        parse_evidence_metadata('{"description":"' + "é" * 17000 + '"}')
    assert parse_evidence_metadata((" " * (32 * 1024 - 2)) + "{}") == {}
