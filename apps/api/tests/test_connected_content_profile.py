"""Connected ingestion preserves literal structure; legacy library stays stable."""

import copy
import hashlib
import re
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus, DocumentVersion, SourceType
from app.models.ingestion import IngestionJob
from app.services.connected_query import citation_status
from app.services.document_intelligence import (
    content_hash,
    deduplicate_chunks,
    normalize_content,
)
from app.services.embedding import embedding_service
from app.services.ingestion_jobs import create_job, process_job
from app.services.retrieval.scoped import (
    embedding_compatible,
    postgres_candidates,
    retrieve_scoped,
    scoped_chunk_statement,
)
from sqlalchemy import JSON, select
from sqlalchemy.dialects import postgresql

pytest_plugins = ["tests.test_connected_contract"]
PROFILE = "connected-paragraphs-v1"
RESTORED = "immutable-snapshot-restore-v1"
STEPS = "Parcel dispatch procedure\n\n" + "\n\n".join(
    f"{i}. Record parcel checkpoint {i} in the dispatch register. "
    "Keep the label beside the sealed parcel until the receiving clerk signs "
    "the register."
    for i in range(1, 8)
)
CODE = (
    '  plan:\n    desk: Élan\n    stages:\n      - emit: "λ → desk"\n\n'
    "  # keep indentation  "
)


async def upload(client, body, name="profile.txt"):
    response = await client.post(
        "/api/documents/upload", files={"files": (name, body.encode(), "text/plain")}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ingestions"][0]["status"] == "completed", payload
    return uuid.UUID(payload["documents"][0]["id"])


async def snapshot(factory, identifier, version=None):
    async with factory() as db:
        doc = await db.get(Document, identifier)
        result = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == identifier,
                DocumentVersion.version_number == (version or doc.version_number),
            )
        )
        return doc, result


@pytest.mark.parametrize("body", [STEPS, CODE])
async def test_actual_durable_upload_preserves_paragraphs_indentation_and_exact_chunks(
    real_client, body
):
    # The old pipeline collapses all paragraph/code structure before publication.
    client, factory, _ = real_client
    identifier = await upload(
        client, "\r\n \r\n" + body.replace("\n", "\r\n") + "\r\n\r\n"
    )
    doc, version = await snapshot(factory, identifier)
    assert version.normalized_content == body
    assert (
        doc.content_hash
        == version.content_hash
        == hashlib.sha256(body.encode()).hexdigest()
    )
    assert doc.metadata_["normalized_content"] == body
    assert doc.metadata_.get("content_profile") == PROFILE
    assert version.chunks and all(item["content"] in body for item in version.chunks)
    assert all(
        item["metadata"].get("content_profile") == PROFILE for item in version.chunks
    )
    if body == STEPS:
        assert len(version.chunks) >= 2
    async with factory() as db:
        job = await db.scalar(
            select(IngestionJob).where(IngestionJob.document_id == identifier)
        )
        assert job.metadata_.get("content_profile") == PROFILE


async def test_paragraph_break_is_part_of_connected_content_identity(real_client):
    client, factory, _ = real_client
    a = await upload(client, "Parcel received.\n\nParcel archived.", "paragraph.txt")
    b = await upload(client, "Parcel received. Parcel archived.", "single.txt")
    assert (await snapshot(factory, a))[1].content_hash != (await snapshot(factory, b))[
        1
    ].content_hash


async def test_update_restore_reindex_keep_historical_body_profile_and_literal_chunks(
    real_client,
):
    client, factory, keys = real_client
    identifier = await upload(client, STEPS)
    _, first = await snapshot(factory, identifier)
    captured = copy.deepcopy(first.chunks)
    response = await client.post(
        f"/api/v1/documents/{identifier}/versions?base_version=1",
        files={
            "file": (
                "changed.txt",
                "Changed parcel procedure.\n\nKeep the signed label.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 200, response.text
    assert (await snapshot(factory, identifier, 1))[1].chunks == captured
    async with factory() as db:
        doc = await db.get(Document, identifier)
        job = await create_job(
            db,
            doc,
            {"id": keys["owner"]},
            source_path=None,
            kind="restore",
            metadata={"restore_version": 1},
        )
        await process_job(job.id)
    doc, restored = await snapshot(factory, identifier)
    assert restored.version_number == 3 and restored.normalized_content == STEPS
    assert [c["content"] for c in restored.chunks] == [c["content"] for c in captured]
    assert doc.metadata_.get("content_profile") == PROFILE
    restored_copy = copy.deepcopy(restored.chunks)
    async with factory() as db:
        doc = await db.get(Document, identifier)
        doc.metadata_ = {**doc.metadata_, "normalized_content": "Mutable wrong body"}
        await db.commit()
        job = await create_job(
            db, doc, {"id": keys["owner"]}, source_path=None, kind="reindex"
        )
        await process_job(job.id)
    doc, reindexed = await snapshot(factory, identifier)
    assert doc.version_number == reindexed.version_number == 3
    assert reindexed.normalized_content == STEPS and reindexed.chunks == restored_copy
    assert doc.metadata_["normalized_content"] == STEPS
    assert (await snapshot(factory, identifier, 1))[1].chunks == captured
    async with factory() as db:
        current = list(
            (
                await db.scalars(select(Chunk).where(Chunk.document_id == identifier))
            ).all()
        )
        assert current and all(
            c.content in STEPS and c.metadata_.get("content_profile") == PROFILE
            for c in current
        )


async def test_unknown_historical_profile_is_restored_exactly_and_reembedded_for_query(
    real_client,
):
    _, factory, keys = real_client
    body = "  Historical routing:\n\n    keep Élan parcel labels\n\nFinish."
    digest = hashlib.sha256(body.encode()).hexdigest()
    async with factory() as db:
        doc = Document(
            title="Historic",
            source_type=SourceType.TEXT,
            status=DocumentStatus.READY,
            owner_id=keys["owner"],
            workspace_id="ops-a",
            version_number=1,
            content_hash=digest,
            metadata_={"normalized_content": body},
        )
        db.add(doc)
        await db.flush()
        old_signature = {
            **embedding_service.signature,
            "chunking": "legacy-semantic-v1",
        }
        split = body.index("\n\nFinish.")
        old_chunks = [
            {
                "id": str(uuid.uuid4()),
                "index": i,
                "content": text,
                "metadata": {
                    "embedding_signature": old_signature,
                    "document_version": 1,
                },
            }
            for i, text in enumerate([body[:split], body[split:]])
        ]
        historical = DocumentVersion(
            document_id=doc.id,
            workspace_id="ops-a",
            version_number=1,
            content_hash=digest,
            normalized_content=body,
            chunks=old_chunks,
        )
        db.add(historical)
        await db.commit()
        identifier = doc.id
        job = await create_job(
            db,
            doc,
            {"id": keys["owner"]},
            source_path=None,
            kind="restore",
            metadata={"restore_version": 1},
        )
        await process_job(job.id)
    doc, restored = await snapshot(factory, identifier)
    assert restored.normalized_content == body
    assert [c["content"] for c in restored.chunks] == [c["content"] for c in old_chunks]
    metadata = restored.chunks[0]["metadata"]
    assert metadata.get("content_profile") is None
    assert metadata["embedding_signature"]["chunking"] == RESTORED
    assert doc.metadata_["embedding_signature"] == metadata["embedding_signature"]
    assert metadata["chunking_provenance"]["source_chunking"] == "legacy-semantic-v1"
    assert (await snapshot(factory, identifier, 1))[1].chunks == old_chunks
    async with factory() as db:
        result = await retrieve_scoped(
            db,
            "routing parcel labels",
            principal={"id": keys["owner"], "workspace_id": "ops-a"},
            document_ids=[identifier],
            method="vector",
            top_k=10,
        )
        assert {c.content for c in result.chunks} == {c["content"] for c in old_chunks}
        for item in restored.chunks:
            assert (
                await citation_status(
                    db,
                    {
                        "document_version": 2,
                        "content_hash": digest,
                        "quoted_text": item["content"],
                    },
                    doc,
                )
                == "current"
            )
        doc = await db.get(Document, identifier)
        job = await create_job(
            db, doc, {"id": keys["owner"]}, source_path=None, kind="reindex"
        )
        await process_job(job.id)
    doc, same = await snapshot(factory, identifier)
    assert doc.version_number == 2 and same.chunks == restored.chunks
    async with factory() as db:
        live = list(
            (
                await db.scalars(
                    select(Chunk)
                    .where(Chunk.document_id == identifier)
                    .order_by(Chunk.chunk_index)
                )
            ).all()
        )
        assert [str(c.id) for c in live] == [c["id"] for c in restored.chunks]
        assert all(
            c.metadata_["embedding_signature"]["chunking"]
            == "immutable-snapshot-reindex-v1"
            for c in live
        )
        result = await retrieve_scoped(
            db,
            "routing parcel labels",
            principal={"id": keys["owner"], "workspace_id": "ops-a"},
            document_ids=[identifier],
            method="vector",
            top_k=10,
        )
        assert {c.content for c in result.chunks} == {c["content"] for c in old_chunks}
        assert (await db.get(DocumentVersion, same.id)).normalized_content == body


async def test_unreembedded_old_vector_is_not_current_even_with_restore_marker(
    real_client,
):
    client, factory, keys = real_client
    identifier = await upload(client, "Parcel routing uses the signed register.")
    async with factory() as db:
        chunk = await db.scalar(select(Chunk).where(Chunk.document_id == identifier))
        chunk.metadata_ = {
            **chunk.metadata_,
            "embedding_signature": {
                **embedding_service.signature,
                "chunking": "legacy-semantic-v1",
            },
            "chunking_provenance": {"method": RESTORED},
        }
        await db.commit()
        with pytest.raises(ValueError, match="reindex"):
            await retrieve_scoped(
                db,
                "routing",
                principal={"id": keys["owner"], "workspace_id": "ops-a"},
                document_ids=[identifier],
                method="vector",
            )


@pytest.mark.parametrize("mode", ["deterministic", "local"])
async def test_explicit_embedding_paths_return_literal_passages(
    real_client, monkeypatch, mode
):
    client, factory, _ = real_client
    if mode == "local":
        monkeypatch.setattr(get_settings(), "EMBEDDING_MODE", "local")
        monkeypatch.setattr(get_settings(), "EMBEDDING_DIMENSIONS", 384)

        def tokenize(text, **kwargs):
            return {"offset_mapping": [m.span() for m in re.finditer(r"\S+", text)]}

        model = SimpleNamespace(
            tokenizer=tokenize,
            max_seq_length=32,
            encode=lambda texts, **kwargs: SimpleNamespace(
                tolist=lambda: [[1.0] + [0.0] * 383 for _ in texts]
            ),
        )
        monkeypatch.setattr(embedding_service, "_get_model", lambda: model)
    identifier = await upload(client, CODE + "\n\n" + STEPS)
    _, version = await snapshot(factory, identifier)
    body = CODE + "\n\n" + STEPS
    assert version.normalized_content == body
    assert all(c["content"] in body for c in version.chunks)
    expected = (
        "minilm-tokenizer-v1" if mode == "local" else "connected-literal-windows-v1"
    )
    assert embedding_service.signature["chunking"] == expected


async def test_nonliteral_chunk_cannot_publish(real_client, monkeypatch):
    client, factory, _ = real_client
    monkeypatch.setattr(
        embedding_service,
        "chunk_content",
        lambda body: ["This text was never in the source"],
    )
    response = await client.post(
        "/api/documents/upload",
        files={"files": ("bad.txt", "Literal parcel text.", "text/plain")},
    )
    assert response.status_code == 200
    ingestion = response.json()["ingestions"][0]
    assert ingestion["status"] == "error" and ingestion["stage"] == "chunk"
    async with factory() as db:
        assert list((await db.scalars(select(DocumentVersion))).all()) == []
        assert list((await db.scalars(select(Chunk))).all()) == []


@pytest.mark.parametrize("damage", [None, "body", "hash", "uncited"])
async def test_citation_status_uses_direct_immutable_body_hash(connected_db, damage):
    db, _ = connected_db
    body = CODE
    digest = hashlib.sha256(body.encode()).hexdigest()
    doc = Document(
        title="Direct body",
        source_type=SourceType.TEXT,
        workspace_id="ops-a",
        version_number=1,
        content_hash=digest,
        status=DocumentStatus.READY,
    )
    db.add(doc)
    await db.flush()
    version = DocumentVersion(
        document_id=doc.id,
        workspace_id="ops-a",
        version_number=1,
        content_hash=digest,
        normalized_content=body,
        chunks=[{"index": 0, "content": body}],
    )
    db.add(version)
    await db.commit()
    if damage == "body":
        version.normalized_content += " changed"
    if damage == "hash":
        version.content_hash = "0" * 64
    source = {
        "document_version": 1,
        "content_hash": digest,
        "quoted_text": body if damage != "uncited" else "Élan",
    }
    assert await citation_status(db, source, doc) == (
        "unknown" if damage else "current"
    )
    if damage is None:
        doc.version_number = 2
        doc.content_hash = "1" * 64
        assert await citation_status(db, source, doc) == "superseded"


async def test_pg_signature_guard_precedes_vector_candidate_limit(monkeypatch):
    # Incompatible rows must not occupy the ANN limit before a Python filter.
    monkeypatch.setattr(
        embedding_service, "embed_query", AsyncMock(return_value=[1.0] * 384)
    )
    # Compile guard structure without installing the optional pgvector runtime;
    # the embedding bind's type shim is not a live vector execution assertion.
    monkeypatch.setattr(
        "app.db.vector_type.Vector384.load_dialect_impl",
        lambda self, dialect: dialect.type_descriptor(JSON()),
    )
    statements = []

    async def execute(statement):
        if hasattr(statement, "_where_criteria"):
            statements.append(statement)
        return SimpleNamespace(all=lambda: [])

    db = SimpleNamespace(execute=execute, scalar=AsyncMock(return_value=False))
    signature = {
        "mode": "local",
        "model": "pinned",
        "revision": "rev",
        "dimension": 384,
        "chunking": "minilm-tokenizer-v1",
    }
    await postgres_candidates(
        db, scoped_chunk_statement(None, None, None), "parcel", signature, 5, "vector"
    )
    assert len(statements) == 2
    for statement in statements:
        compiled = statement.compile(dialect=postgresql.dialect())
        assert signature in compiled.params.values()
        assert {**signature, "chunking": RESTORED} in compiled.params.values()
        assert {
            **signature,
            "chunking": "immutable-snapshot-reindex-v1",
        } in compiled.params.values()
        assert {
            key: signature[key] for key in ("mode", "model", "revision", "dimension")
        } in compiled.params.values()
        assert "chunking_provenance" in str(compiled.params.values())
        assert statement._limit_clause.value == 5


@pytest.mark.parametrize(
    "damage", ["mode", "model", "revision", "dimension", "marker", "encoder"]
)
def test_snapshot_vector_compatibility_needs_exact_current_encoder_and_provenance(
    damage,
):
    signature = {
        "mode": "local",
        "model": "pinned",
        "revision": "current",
        "dimension": 384,
        "chunking": "minilm-tokenizer-v1",
    }
    metadata = {
        "embedding_signature": {**signature, "chunking": RESTORED},
        "chunking_provenance": {
            "method": RESTORED,
            "reembedded_encoder": {
                "mode": "local",
                "model": "pinned",
                "revision": "current",
                "dimension": 384,
            },
        },
    }
    assert embedding_compatible(metadata, signature)
    if damage in {"mode", "model", "revision", "dimension"}:
        metadata["embedding_signature"][damage] = (
            32 if damage == "dimension" else "older"
        )
    elif damage == "marker":
        metadata["chunking_provenance"].pop("method")
    else:
        metadata["chunking_provenance"]["reembedded_encoder"]["revision"] = "older"
    assert not embedding_compatible(metadata, signature)


def test_legacy_library_normalization_and_chunking_are_unchanged(monkeypatch):
    monkeypatch.setattr(get_settings(), "EMBEDDING_MODE", "legacy")
    assert normalize_content("  a\n\n b  ") == "a b"
    assert content_hash("  a\n\n b  ") == hashlib.sha256(b"a b").hexdigest()
    assert deduplicate_chunks(["  a\n b ", "a b"]) == ["a b"]
    assert embedding_service.chunk_content("Alpha step.\n\nBeta step.") == [
        "Alpha step. Beta step."
    ]
