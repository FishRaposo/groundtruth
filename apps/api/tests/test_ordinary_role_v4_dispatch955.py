"""Real SQLite immutable role archives; no API/model or semantic expansion."""

from copy import deepcopy

import pytest
from app.evidence_policy import EvidencePolicy, reading_version
from app.models.query import QueryRequest
from app.services import linguistic_role_consumer as consumer
from app.services import staged_publication_context as archive
from app.services.request_planning_manifest import (
    check_planning_read_set,
    inspect_planning_manifest,
)
from app.services.role_scope_inspection import (
    check_role_read_set,
    inspect_role_manifest,
)

from tests.test_staged_snapshot_store849 import publish_library, staged

pytest_plugins = ["tests.test_connected_contract"]
PRINCIPAL = {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False}


def profile():
    return EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v4",
        "literal_source_count_v1",
    ).record()


def test_canonical_profile9_selects_registered_ordinary_role_manifest4():
    selected = consumer._selected_version({"evidence_profile": profile()})
    assert selected == reading_version("contextual_source_v4")
    assert selected.role_manifest == "declared-context-role-manifest-v4"


@pytest.mark.parametrize("mutation", ["title", "metadata"])
async def test_v4_role_archive_stays_immutable_while_current_sql_receipt_changes(
    connected_db, monkeypatch, mutation
):
    config = staged(monkeypatch)
    monkeypatch.setattr(config, "EVIDENCE_READING_PROFILE", "contextual_source_v4")
    db, _ = connected_db
    document, version = await publish_library(
        db,
        "The record steward leads Cedar review.",
        title="Published ordinary role",
        metadata={"condition": "published"},
    )
    frozen_chunks = deepcopy(version.chunks)
    projection = archive.validated_projection(version)
    request = QueryRequest(question="Who leads ordinary Cedar review sessions?")
    manifest = await inspect_role_manifest(
        db, PRINCIPAL, request, reading_profile="contextual_source_v4"
    )
    sql = await inspect_planning_manifest(db, PRINCIPAL, request)
    assert manifest.complete and sql.complete
    assert manifest.record()["documents"] == [consumer._record(projection)]
    if mutation == "title":
        document.title = "Mutable ordinary role title"
    else:
        document.metadata_ = {**document.metadata_, "condition": "mutable"}
    await db.commit()
    current = await inspect_role_manifest(
        db, PRINCIPAL, request, reading_profile="contextual_source_v4"
    )
    assert current.record() == manifest.record()
    assert current.sources[0].metadata == projection["metadata"]
    assert [part.metadata for part in current.sources[0].chunks] == [
        part["metadata"] for part in projection["chunks"]
    ]
    assert version.chunks == frozen_chunks
    assert (await check_role_read_set(db, PRINCIPAL, request, manifest.record()))[
        "consistent"
    ]
    assert await check_planning_read_set(db, PRINCIPAL, request, sql.record()) == {
        "consistent": False,
        "reason": "planning_publications_changed",
    }
    selection = {
        "evidence_profile": profile(),
        "request_plan": {"question": request.question},
        "role_scope_read_set": {
            **current.record(),
            "after_proofs": {"consistent": True, "reason": None},
        },
    }
    assert consumer._manifest(selection, {str(document.id): projection}).complete


async def test_v4_current_access_revocation_does_not_become_archive_authority(
    connected_db, monkeypatch
):
    config = staged(monkeypatch)
    monkeypatch.setattr(config, "EVIDENCE_READING_PROFILE", "contextual_source_v4")
    db, _ = connected_db
    document, version = await publish_library(
        db, "The record steward leads Cedar review."
    )
    projection = archive.validated_projection(version)
    request = QueryRequest(question="Who leads ordinary Cedar review sessions?")
    manifest = await inspect_role_manifest(
        db, PRINCIPAL, request, reading_profile="contextual_source_v4"
    )
    document.owner_id = "another-owner"
    await db.commit()
    current = await inspect_role_manifest(
        db, PRINCIPAL, request, reading_profile="contextual_source_v4"
    )
    assert current.complete and current.sources == ()
    assert not (await check_role_read_set(db, PRINCIPAL, request, manifest.record()))[
        "consistent"
    ]
    assert archive.validated_projection(version) == projection


@pytest.mark.parametrize(
    "name", [None, True, "contextual_source_v5", "clause_bound_v1"]
)
def test_unregistered_or_unsupported_role_consumer_profiles_still_reject(name):
    with pytest.raises(ValueError):
        consumer._selected_version(
            {"evidence_profile": {"evidence_reading_profile": name}}
        )


async def test_existing_v2_and_default_keep_mutable_receipts_and_v3_keeps_archive(
    connected_db, monkeypatch
):
    staged(monkeypatch)
    db, _ = connected_db
    document, _ = await publish_library(
        db,
        "The record steward leads Cedar review.",
        metadata={"condition": "published"},
    )
    request = QueryRequest(question="Who leads Cedar review?")
    profiles = ["clause_bound_v1", "contextual_source_v2", "contextual_source_v3"]
    before = {
        name: (
            await inspect_role_manifest(db, PRINCIPAL, request, reading_profile=name)
        ).record()
        for name in profiles
    }
    document.metadata_ = {**document.metadata_, "condition": "mutable"}
    await db.commit()
    after = {
        name: await inspect_role_manifest(db, PRINCIPAL, request, reading_profile=name)
        for name in profiles
    }
    assert before["contextual_source_v3"] == after["contextual_source_v3"].record()
    for name in profiles[:2]:
        assert after[name].sources[0].metadata["condition"] == "mutable"
        assert before[name] != after[name].record()
