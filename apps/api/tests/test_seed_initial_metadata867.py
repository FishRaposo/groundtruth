"""Actual seeder/ASGI/SQLite calls over new generic UNITONLY source fixtures."""

import hashlib
import importlib.util
import json
from email.parser import BytesParser
from email.policy import default
from pathlib import Path

import httpx
import pytest
from app.main import app
from app.models.document import Document, DocumentVersion
from app.services.staged_publication_context import CONTEXT_KEY, validated_projection
from sqlalchemy import select

from tests.test_staged_snapshot_store849 import staged
from tests.test_staged_snapshot_store849 import tmp_path as tmp_path

pytest_plugins = ["tests.test_connected_contract"]
SPEC = importlib.util.spec_from_file_location(
    "seed_metadata867",
    Path(__file__).resolve().parents[3] / "scripts/seed_portfolio.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def version(number, raw):
    content = raw.strip()
    return {
        "version_number": number,
        "content": content,
        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
        "input_content": raw,
        "input_sha256": hashlib.sha256(raw.encode()).hexdigest(),
    }


@pytest.mark.parametrize("profile", ["clause_bound_v1", "contextual_source_v3"])
async def test_real_seed_keeps_initial_fields_and_publication_history(
    real_client, tmp_path, monkeypatch, profile
):
    if profile == "contextual_source_v3":
        staged(monkeypatch)
    _, factory, _ = real_client
    metadata = {
        "condition": "UNITONLY ordinary policy",
        "conflict_group": "UNITONLY-policy",
        "fixture_kind": "UNITONLY-generic",
        "description": "UNITONLY source declaration",
        "tags": ["UNITONLY"],
        "labels": {"purpose": "UNITONLY"},
    }
    fixture = {
        "id": "UNITONLY867-generic",
        "title": "UNITONLY accepted fixture title",
        "owner": "author",
        "workspace_id": "ops-a",
        "visibility": "organization",
        "metadata": metadata,
        "versions": [
            version(1, "\nUNITONLY first publication.\n"),
            version(2, "\nUNITONLY second publication.\n"),
        ],
    }
    corpus = {
        "manifest": {
            "schema_version": 2,
            "revision": "UNITONLY867",
            "manifest_sha256": "UNITONLY867-no-frozen-corpus",
            "principals": {"author": {"workspace_id": "ops-a", "role": "member"}},
            "browser": {
                "question": "UNITONLY view?",
                "expected_quote": "UNITONLY second publication.",
                "document_id": fixture["id"],
            },
        },
        "documents": [fixture],
        "cases": [
            {
                "expected_behavior": "answer",
                "question": "UNITONLY view?",
                "expected_sources": [
                    {
                        "document_id": fixture["id"],
                        "acceptable_answer_spans": ["UNITONLY second publication."],
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(MODULE, "load_corpus", lambda _: corpus)
    monkeypatch.setattr(MODULE, "AsyncSessionLocal", factory)
    original = httpx.AsyncClient
    observations = []

    async def inspect_request(request):
        if request.url.path != "/api/documents/upload":
            return
        raw = await request.aread()
        content_type = request.headers["content-type"]
        message = BytesParser(policy=default).parsebytes(
            ("Content-Type: " + content_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode()
            + raw
        )
        parts = {
            part.get_param("name", header="content-disposition"): {
                "filename": part.get_filename(),
                "content": part.get_payload(decode=True),
            }
            for part in message.iter_parts()
        }
        observations.append(parts)

    def actual_client(**kwargs):
        return original(
            transport=httpx.ASGITransport(app=app),
            event_hooks={"request": [inspect_request]},
            **kwargs,
        )

    monkeypatch.setattr(MODULE.httpx, "AsyncClient", actual_client)
    output = tmp_path / "unitonly-private-seed.json"
    await MODULE.seed("http://127.0.0.1:8402", output)
    manifest = json.loads(output.read_text())
    assert manifest["seed_status"] == "complete"
    assert len(observations) == 1
    parts = observations[0]
    expected = {**metadata, "portfolio_logical_id": fixture["id"], "synthetic": True}
    assert parts["title"]["content"] == fixture["title"].encode()
    assert (
        parts["metadata"]["content"]
        == json.dumps(
            expected, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    )
    assert parts["files"]["filename"] == fixture["id"] + ".txt"
    assert parts["files"]["content"] == fixture["versions"][0]["input_content"].encode()
    identifier = manifest["documents"][fixture["id"]]["document_id"]
    import uuid

    async with factory() as db:
        doc = await db.get(Document, uuid.UUID(identifier))
        versions = list(
            (
                await db.scalars(
                    select(DocumentVersion)
                    .where(DocumentVersion.document_id == doc.id)
                    .order_by(DocumentVersion.version_number)
                )
            ).all()
        )
        assert [row.version_number for row in versions] == [1, 2]
        assert [row.content_hash for row in versions] == [
            row["content_hash"] for row in fixture["versions"]
        ]
        assert doc.title == fixture["title"]
        assert {key: doc.metadata_[key] for key in expected} == expected
        if profile == "contextual_source_v3":
            for row in versions:
                projection = validated_projection(row)
                assert projection["title"] == fixture["title"]
                assert {
                    key: projection["metadata"][key] for key in expected
                } == expected
            # Same complete metadata before and after the compatibility overlay.
            assert validated_projection(versions[-1])["metadata"] == doc.metadata_
        else:
            assert all(CONTEXT_KEY not in row.chunks[0]["metadata"] for row in versions)
