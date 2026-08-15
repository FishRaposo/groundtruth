"""Persistent document-version contracts."""

from __future__ import annotations

import uuid

import pytest
from app.db.session import Base
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus, DocumentVersion, SourceType
from app.services.document.versioning import DocumentVersionManager
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def version_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


async def test_version_snapshots_round_trip_and_restore(version_session) -> None:
    document = Document(
        id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
        title="Policy",
        source_type=SourceType.TEXT,
        status=DocumentStatus.READY,
        metadata_={"normalized_content": "original"},
        workspace_id="ws-a",
    )
    version_session.add(document)
    await version_session.commit()

    manager = DocumentVersionManager(version_session)
    first = await manager.create_version(
        str(document.id),
        "original\npolicy",
        [Chunk(document_id=document.id, content="original policy", chunk_index=0)],
        "Initial snapshot",
        workspace_id="ws-a",
    )
    second = await manager.create_version(
        str(document.id),
        "updated\npolicy",
        [Chunk(document_id=document.id, content="updated policy", chunk_index=0)],
        "Policy update",
        workspace_id="ws-a",
    )

    assert isinstance(first, DocumentVersion)
    assert [
        item["version_number"]
        for item in await manager.get_version_history(
            str(document.id), workspace_id="ws-a"
        )
    ] == [2, 1]
    diff = await manager.diff_versions(str(document.id), 1, 2, workspace_id="ws-a")
    assert diff["added_lines"] == 1
    assert diff["removed_lines"] == 1

    restored = await manager.restore_version(str(document.id), 1, workspace_id="ws-a")
    assert restored.content_hash == first.content_hash
    assert restored.metadata_["normalized_content"] == "original\npolicy"
    assert restored.version_number == 3
    assert second.content_hash != restored.content_hash


async def test_version_history_is_workspace_scoped(version_session) -> None:
    document = Document(
        title="Private",
        source_type=SourceType.TEXT,
        status=DocumentStatus.READY,
        workspace_id="ws-a",
    )
    version_session.add(document)
    await version_session.commit()
    manager = DocumentVersionManager(version_session)
    await manager.create_version(str(document.id), "private", [], workspace_id="ws-a")

    assert (
        await manager.get_version_history(str(document.id), workspace_id="ws-b") == []
    )
