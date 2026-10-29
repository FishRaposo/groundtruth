"""Actual SQLite authority/candidate predicates must precede the body limit."""

import hashlib
import uuid
from copy import deepcopy

import pytest
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus, DocumentVersion, SourceType
from app.models.query import QueryRequest
from app.services.declared_source_scope import source_cover
from app.services.role_scope_inspection import (
    check_role_read_set,
    inspect_role_manifest,
)

pytest_plugins = ["tests.test_connected_contract"]
PRINCIPAL = {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False}


async def publish(
    db, number, body, *, owner="owner-a", workspace="ops-a", indexed=True
):
    identifier = uuid.UUID(int=number)
    digest = hashlib.sha256(body.encode()).hexdigest()
    identity = {
        "document_id": str(identifier),
        "document_version": 1,
        "content_hash": digest,
        "workspace_id": workspace,
    }
    metadata = (
        {"declared_source_scope": source_cover(body, identity)} if indexed else {}
    )
    doc = Document(
        id=identifier,
        title="Synthetic scope fixture",
        source_type=SourceType.TEXT,
        status=DocumentStatus.READY,
        workspace_id=workspace,
        owner_id=owner,
        version_number=1,
        content_hash=digest,
        chunk_count=1,
        metadata_=metadata,
    )
    chunk = Chunk(
        id=uuid.uuid4(),
        document_id=identifier,
        content=body,
        chunk_index=0,
        metadata_={
            "document_version": 1,
            "content_hash": digest,
            "workspace_id": workspace,
        },
    )
    db.add_all(
        [
            doc,
            chunk,
            DocumentVersion(
                document_id=identifier,
                workspace_id=workspace,
                version_number=1,
                content_hash=digest,
                normalized_content=body,
                chunks=[
                    {
                        "id": str(chunk.id),
                        "index": 0,
                        "content": body,
                        "metadata": chunk.metadata_,
                    }
                ],
            ),
        ]
    )
    return doc


async def test_authorized_scope_candidates_are_selected_in_sql_before_limit(
    connected_db,
):
    db, _ = connected_db
    for n in range(1, 141):
        await publish(db, n, f"The records steward leads Variant{n} review.")
    target = await publish(db, 1000, "The records steward leads Meridian review.")
    unknown = await publish(
        db, 1001, "Follow the qualification appendix.", indexed=False
    )
    await publish(
        db, 1002, "The custodian leads Meridian review.", owner="someone-else"
    )
    await publish(db, 1003, "The custodian leads Meridian review.", workspace="ops-b")
    await db.commit()
    result = await inspect_role_manifest(
        db,
        PRINCIPAL,
        QueryRequest(question="Who leads Meridian review?"),
        reading_profile="contextual_source_v1",
    )
    assert result.complete is True
    assert {s.identity["document_id"] for s in result.sources} == {
        str(target.id),
        str(unknown.id),
    }
    assert len(result.read_set["index_universe"]) == 142
    assert result.read_set["limits"]["documents"] == 128


async def test_missing_or_forged_cover_is_unknown_not_an_exclusion(connected_db):
    db, _ = connected_db
    doc = await publish(db, 1000, "The records steward leads Meridian review.")
    forged = dict(doc.metadata_["declared_source_scope"])
    forged["units"] = []
    doc.metadata_ = {"declared_source_scope": forged}
    await db.commit()
    result = await inspect_role_manifest(
        db,
        PRINCIPAL,
        QueryRequest(question="Who leads Zinc review?"),
        reading_profile="contextual_source_v1",
    )
    assert result.complete is True
    assert len(result.sources) == 1
    assert result.sources[0].identity["document_id"] == str(doc.id)


async def test_scope_index_universe_is_rechecked_not_only_selected_bodies(connected_db):
    db, _ = connected_db
    await publish(db, 1, "The records steward leads Meridian review.")
    await publish(db, 2, "The page steward leads Zinc review.")
    await db.commit()
    request = QueryRequest(question="Who leads Meridian review?")
    result = await inspect_role_manifest(
        db, PRINCIPAL, request, reading_profile="contextual_source_v1"
    )
    assert result.complete
    assert (await check_role_read_set(db, PRINCIPAL, request, result.record()))[
        "consistent"
    ]
    await publish(db, 3, "Each session requires a separate nomination.")
    await db.commit()
    assert (await check_role_read_set(db, PRINCIPAL, request, result.record())) == {
        "consistent": False,
        "reason": "role_scope_inspection_changed",
    }


@pytest.mark.parametrize("workspace", ["ops-b", None])
async def test_index_identity_requires_the_actual_current_workspace(
    connected_db, workspace
):
    db, _ = connected_db
    body = "The records steward leads Meridian review."
    doc = await publish(db, 1, body)
    identity = {
        "document_id": str(doc.id),
        "document_version": 1,
        "content_hash": doc.content_hash,
    }
    if workspace is not None:
        identity["workspace_id"] = workspace
    doc.metadata_ = {"declared_source_scope": source_cover(body, identity)}
    await db.commit()
    manifest = await inspect_role_manifest(
        db,
        PRINCIPAL,
        QueryRequest(question="Who leads Zinc review?"),
        reading_profile="contextual_source_v1",
    )
    assert manifest.complete and len(manifest.sources) == 1


@pytest.mark.parametrize(
    "path,value",
    [
        (("documents", 0, "document_version"), True),
        (("index_universe", 0, "document_version"), 1.0),
        (("limits", "documents"), 64.0),
    ],
)
async def test_contextual_read_set_is_strictly_typed_json(connected_db, path, value):
    db, _ = connected_db
    await publish(db, 1, "The records steward leads Meridian review.")
    await db.commit()
    request = QueryRequest(question="Who leads Meridian review?")
    manifest = await inspect_role_manifest(
        db, PRINCIPAL, request, reading_profile="contextual_source_v1"
    )
    captured = deepcopy(manifest.record())
    target = captured
    for field in path[:-1]:
        target = target[field]
    target[path[-1]] = value
    assert (await check_role_read_set(db, PRINCIPAL, request, captured))[
        "consistent"
    ] is False
