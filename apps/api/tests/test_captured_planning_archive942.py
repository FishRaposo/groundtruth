"""Real SQLite boundary; recorded UNITONLY syntax is not model acceptance."""

import json

import pytest
from app.models.query import QueryRequest
from app.services import planning_runtime, request_parser
from app.services import staged_publication_context as archive

from tests.test_planning_declarations import CAT, capture
from tests.test_staged_snapshot_store849 import publish_library, staged

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize("profile", ["contextual_source_v3", "contextual_source_v4"])
async def test_planning_reads_published_title_metadata_and_chunk_projection(
    connected_db, monkeypatch, profile
):
    config = staged(monkeypatch)
    db, _ = connected_db
    body, observed = capture([CAT])
    document, version = await publish_library(
        db, body, title="Published activity", metadata={"condition": "published"}
    )
    document.title = "Mutable display title"
    document.metadata_ = {**document.metadata_, "condition": "mutable"}
    await db.commit()
    monkeypatch.setattr(config, "EVIDENCE_READING_PROFILE", profile)

    async def recorded(raw, config):
        assert raw == body
        return observed

    monkeypatch.setattr(request_parser, "capture_async", recorded)
    inspection = await planning_runtime.inspect_planning_declarations(
        db,
        {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False},
        QueryRequest(question="List activity role labels."),
        config,
    )
    actual = inspection.snapshots[0]
    expected = archive.validated_projection(version)
    assert actual.title == "Published activity"
    assert json.loads(actual.metadata_json) == expected["metadata"]
    assert (
        json.loads(actual.chunks[0].metadata_json) == expected["chunks"][0]["metadata"]
    )


async def test_v4_refuses_missing_published_context_instead_of_mutable_projection(
    connected_db, monkeypatch
):
    config = staged(monkeypatch)
    db, _ = connected_db
    body, observed = capture([CAT])
    _, version = await publish_library(db, body)
    version.chunks = [{**row, "metadata": {}} for row in version.chunks]
    await db.commit()
    monkeypatch.setattr(config, "EVIDENCE_READING_PROFILE", "contextual_source_v4")

    async def recorded(raw, config):
        return observed

    monkeypatch.setattr(request_parser, "capture_async", recorded)
    with pytest.raises(ValueError, match="context"):
        await planning_runtime.inspect_planning_declarations(
            db,
            {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False},
            QueryRequest(question="List activity role labels."),
            config,
        )


async def test_v4_new_publication_captures_an_immutable_archive(
    connected_db, monkeypatch
):
    config = staged(monkeypatch)
    monkeypatch.setattr(config, "EVIDENCE_READING_PROFILE", "contextual_source_v4")
    db, _ = connected_db
    document, version = await publish_library(
        db, "The full authoritative body.", title="Recorded title"
    )
    assert archive.CONTEXT_KEY in version.chunks[0]["metadata"]
    projection = archive.validated_projection(version)
    assert projection["title"] == "Recorded title"
    assert projection["body"] == "The full authoritative body."
    assert projection["document_id"] == str(document.id)


async def test_v4_ingestion_job_records_the_shared_archive_contract(
    connected_db, monkeypatch
):
    from app.services import ingestion_jobs

    config = staged(monkeypatch)
    monkeypatch.setattr(config, "EVIDENCE_READING_PROFILE", "contextual_source_v4")
    monkeypatch.setattr(ingestion_jobs, "settings", config)
    db, _ = connected_db
    document, _ = await publish_library(db, "Stored source.", title="Job source")
    job = await ingestion_jobs.create_job(
        db,
        document,
        {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False},
        source_path=None,
        kind="update",
        metadata={archive.PROFILE_KEY: "forged"},
    )
    assert job.metadata_[archive.PROFILE_KEY] == archive.PROFILE
    assert job.metadata_["source_context_input"]["title"] == "Job source"
