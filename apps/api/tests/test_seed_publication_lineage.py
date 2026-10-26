"""Seeder exercises the real ASGI ingestion/version APIs and immutable reads."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from app.main import app
from app.models.document import DocumentVersion
from sqlalchemy import select

pytest_plugins = ["tests.test_connected_contract"]

SPEC = importlib.util.spec_from_file_location(
    "seed_lineage", Path(__file__).resolve().parents[3] / "scripts/seed_portfolio.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def version(number, raw, canonical):
    return {
        "version_number": number,
        "content": canonical,
        "content_hash": hashlib.sha256(canonical.encode()).hexdigest(),
        "input_content": raw,
        "input_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }


async def seed_local(real_client, tmp_path, monkeypatch):
    _, factory, _ = real_client
    corpus = {
        "manifest": {
            "schema_version": 1,
            "manifest_sha256": "frozen-test-manifest",
            "principals": {"author": {"workspace_id": "ops-a", "role": "member"}},
        },
        "documents": [
            {
                "id": "dev-rollback",
                "title": "Lineage fixture",
                "owner": "author",
                "workspace_id": "ops-a",
                "visibility": "private",
                "metadata": {},
                "versions": [
                    version(1, "\nShared upload one.\n", "Shared upload one."),
                    version(2, "\nShared upload two.\n", "Shared upload two."),
                ],
            }
        ],
    }
    monkeypatch.setattr(MODULE, "load_corpus", lambda _: corpus)
    monkeypatch.setattr(MODULE, "AsyncSessionLocal", factory)
    original_client = httpx.AsyncClient

    def client(**kwargs):
        return original_client(transport=httpx.ASGITransport(app=app), **kwargs)

    monkeypatch.setattr(MODULE.httpx, "AsyncClient", client)
    output = tmp_path / "private-seed.json"
    await MODULE.seed("http://127.0.0.1:8402", output)
    return json.loads(output.read_text()), corpus


async def test_seeder_uploads_shared_raw_bytes_instead_of_canonical_projection(
    real_client, tmp_path, monkeypatch
):
    manifest, _ = await seed_local(real_client, tmp_path, monkeypatch)
    assert manifest["seed_status"] == "complete"
    uploaded = {path.read_bytes() for path in (tmp_path / "uploads").rglob("*.txt")}
    assert uploaded == {b"\nShared upload one.\n", b"\nShared upload two.\n"}


async def test_seed_manifest_records_each_actual_immutable_publication(
    real_client, tmp_path, monkeypatch
):
    manifest, _ = await seed_local(real_client, tmp_path, monkeypatch)
    doc = manifest["documents"]["dev-rollback"]
    observed = doc.get("verified_publications")
    assert isinstance(observed, list) and len(observed) == 2
    assert [v["version_number"] for v in observed] == [1, 2]
    assert all(v["body_verified"] and v["input_sha256"] for v in observed)
    assert doc["observed_version_numbers"] == [1, 2]


async def test_seed_runtime_profile_is_observed_from_server_not_tool_environment(
    real_client, tmp_path, monkeypatch
):
    # A separately versioned baseline server may use a different chunker than
    # the current external seeding harness. Tool settings are not observations.
    monkeypatch.setattr(
        MODULE,
        "embedding_service",
        SimpleNamespace(
            signature={
                "mode": "invented-tool-mode",
                "chunking": "invented-tool-chunker",
            }
        ),
    )
    manifest, _ = await seed_local(real_client, tmp_path, monkeypatch)
    assert manifest["profile"]["embedding"]["mode"] == "deterministic"
    assert (
        manifest["profile"]["embedding"]["chunking"] == "connected-literal-windows-v1"
    )
    assert manifest["runtime_observation"]["source"] == "GET /api/health"
    assert (
        manifest["runtime_observation"]["metadata"]["embedding"]
        == manifest["profile"]["embedding"]
    )


@pytest.mark.parametrize("mutation", ["body", "hash", "missing", "extra"])
async def test_earlier_snapshot_corruption_stops_seed_before_completion(
    real_client, tmp_path, monkeypatch, mutation
):
    # A correct latest publication must not conceal corrupt or extra history.
    _, factory, _ = real_client
    original_verify = MODULE.verify_publications

    async def corrupted(client, identifier, fixture, headers):
        import uuid

        async with factory() as db:
            first = await db.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.document_id == uuid.UUID(identifier),
                    DocumentVersion.version_number == 1,
                )
            )
            if mutation == "body":
                first.normalized_content = "Altered historical body."
            elif mutation == "hash":
                first.content_hash = "0" * 64
            elif mutation == "missing":
                await db.delete(first)
            else:
                db.add(
                    DocumentVersion(
                        document_id=first.document_id,
                        workspace_id=first.workspace_id,
                        version_number=3,
                        normalized_content="Unexpected extra publication.",
                        content_hash=hashlib.sha256(
                            b"Unexpected extra publication."
                        ).hexdigest(),
                        chunks=[],
                    )
                )
            await db.commit()
        return await original_verify(client, identifier, fixture, headers)

    monkeypatch.setattr(MODULE, "verify_publications", corrupted)
    with pytest.raises(RuntimeError, match="[Pp]ublication|version set"):
        await seed_local(real_client, tmp_path, monkeypatch)
    manifest = json.loads((tmp_path / "private-seed.json").read_text())
    assert manifest["seed_status"] == "incomplete"
    assert manifest["documents"] == {}
