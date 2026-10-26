"""Retained query authority must survive coherent producer graph deletion."""

import uuid
from copy import deepcopy

import pytest
from app.models.query import Query
from app.reader_catalog import ROBERTA

from tests.test_combined_conflict_repair_v244 import setup
from tests.test_procedure_http import procedure_client as procedure_client

pytest_plugins = ["tests.test_connected_contract"]


def walk(value, visit):
    if isinstance(value, dict):
        visit(value)
        for child in list(value.values()):
            walk(child, visit)
    elif isinstance(value, list):
        for child in value:
            walk(child, visit)


def erase(selection):
    removed = {
        entry["source_identity"]["document_id"]
        for entry in selection["requirements"][0]["procedure_completeness"][
            "condition_exclusion_inventory"
        ]["exclusions"]
    }
    selection["conflicts"] = []
    selection["procedure_read_set"]["groups"] = []
    for key in ("inspected_sources", "procedure_contexts"):
        selection[key] = [s for s in selection[key] if s["document_id"] not in removed]
    selection["procedure_read_set"]["sources"] = [
        s
        for s in selection["procedure_read_set"]["sources"]
        if s["document_id"] not in removed
    ]

    def remove(item):
        if item.get("contract") == "complete-immutable-procedure-v3":
            item.pop("condition_exclusion_inventory", None)
        if item.get("contract") == "procedure-output-cover-v2":
            item.pop("condition_exclusion_inventory", None)
            item["contract"] = "procedure-output-cover-v1"

    walk(selection, remove)


# Defect: deleting claimed scope must not override separately retained capture.
@pytest.mark.parametrize(
    "damage", ["scope_and_graph", "captured_threshold", "captured_reader"]
)
async def test_retained_trace_binds_original_scope_and_model_capture(
    procedure_client, monkeypatch, damage
):
    client, db, document, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    row = await db.get(Query, uuid.UUID(result["id"]))
    original_trace = deepcopy(row.retrieval_trace)
    provenance = deepcopy(row.provenance)
    selection = provenance["answer_selection"]
    if damage == "scope_and_graph":
        erase(selection)
        selection["procedure_read_set"]["document_ids"] = [str(document.id)]
    elif damage == "captured_threshold":

        def alter(item):
            if "minimum_entailment_margin" in item:
                item["minimum_entailment_margin"] = 4

        walk(selection, alter)
    else:

        def alter(item):
            if item.get("mode") == "reader" and "model" in item:
                item.update(model=ROBERTA.model, revision=ROBERTA.revision)

        walk(selection, alter)
    row.provenance = provenance
    await db.commit()
    stored = (row.answer, deepcopy(row.sources), deepcopy(row.provenance))
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert row.retrieval_trace == original_trace
    assert saved["answer"] is None and saved["evidence_access"] == "unknown"
    assert saved["provenance"] == {
        "answer_selection": {
            "presentation_verification": {
                "status": "invalid",
                "reason": (
                    "Recorded procedure presentation integrity could not be verified."
                ),
            }
        }
    }
    assert stored == (row.answer, row.sources, row.provenance)


# Defect: derived presentation/health stamps are not immutable execution settings.
async def test_retained_trace_ignores_only_derived_presentation_stamps(
    procedure_client, monkeypatch
):
    client, db, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    row = await db.get(Query, uuid.UUID(result["id"]))
    provenance = deepcopy(row.provenance)
    selection = provenance["answer_selection"]
    selection["presentation_verification"] = {"status": "verified", "reason": None}
    selection["readiness"] = "ready"
    selection["evidence_support"]["readiness"] = "ready"
    row.provenance = provenance
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert (
        saved["answer"] == result["answer"] and saved["evidence_access"] == "available"
    )


# Defect: a missing presentation proof must still dispatch via retained v3 capture.
async def test_retained_v3_requirements_prevent_empty_presentation_legacy_fallback(
    procedure_client, monkeypatch
):
    from app.services.procedure_output import load_snapshots
    from app.services.requirement_contract import procedure_completeness

    client, db, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    snapshots = await load_snapshots(db, result["provenance"]["answer_selection"])
    assert (
        procedure_completeness(
            {},
            question=result["question"],
            answer=result["answer"],
            citations=result["sources"],
            source_snapshots=snapshots,
            query_context=result["retrieval_trace"],
        )
        is False
    )


# Defect: unrelated oracle candidates must not be turned into inspected sources.
async def test_unrelated_oracle_documents_do_not_change_captured_cover1(
    procedure_client, monkeypatch
):
    from app.models.document import DocumentVersion
    from app.services.procedure_output import load_snapshots, verify_output
    from sqlalchemy import select

    from tests.test_combined_conflict_repair_v244 import audit_body
    from tests.test_combined_procedure_profile import prepare
    from tests.test_procedure_extent import seed_procedure

    client, db, _, payload, _ = await prepare(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    selection = result["provenance"]["answer_selection"]
    assert (
        selection["requirements"][0]["procedure_completeness"]["output_certificate"][
            "contract"
        ]
        == "procedure-output-cover-v1"
    )
    snapshots = await load_snapshots(db, selection)
    text = audit_body()
    other, _ = await seed_procedure(db, body=text, pieces=[text])
    version = await db.scalar(
        select(DocumentVersion).where(DocumentVersion.document_id == other.id)
    )
    snapshots[str(other.id)] = {
        "document_id": str(other.id),
        "document_version": version.version_number,
        "content_hash": version.content_hash,
        "workspace_id": version.workspace_id,
        "body": version.normalized_content,
        "chunks": version.chunks,
        "metadata": {"conflict_group": "uninspected-independent-group"},
    }
    for context in (None, result["retrieval_trace"]):
        assert verify_output(
            selection,
            question=result["question"],
            answer=result["answer"],
            citations=result["sources"],
            source_snapshots=snapshots,
            query_context=context,
        )


# Defect: omitted metadata cannot prove scoped conditional-source absence.
async def test_scoped_snapshot_unknown_group_cannot_silently_downgrade(
    procedure_client, monkeypatch
):
    from app.services.procedure_output import load_snapshots, verify_output

    client, db, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    selection = deepcopy(result["provenance"]["answer_selection"])
    snapshots = await load_snapshots(db, selection)
    assert all(snapshot["metadata"] == {} for snapshot in snapshots.values())
    erase(selection)
    assert (
        verify_output(
            selection,
            question=result["question"],
            answer=result["answer"],
            citations=result["sources"],
            source_snapshots=snapshots,
        )
        is False
    )


# Defect: known metadata-only historical traces must not invalidate literal cover-v1.
async def test_metadata_only_legacy_trace_preserves_recorded_cover1(
    procedure_client, monkeypatch
):
    from tests.test_combined_procedure_profile import prepare

    client, db, _, payload, _ = await prepare(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    row = await db.get(Query, uuid.UUID(result["id"]))
    trace = deepcopy(row.retrieval_trace)
    trace.pop("provenance", None)
    row.retrieval_trace = trace
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert (
        saved["answer"] == result["answer"] and saved["evidence_access"] == "available"
    )


# Defect: legacy classification cannot erase the retained retrieved-source footprint.
async def test_pruned_capture_still_rejects_retained_legacy_score_members(
    procedure_client, monkeypatch
):
    client, db, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    row = await db.get(Query, uuid.UUID(result["id"]))
    provenance = deepcopy(row.provenance)
    erase(provenance["answer_selection"])
    row.provenance = provenance
    trace = deepcopy(row.retrieval_trace)
    trace.pop("provenance", None)
    row.retrieval_trace = trace
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["answer"] is None and saved["evidence_access"] == "unknown"


# Defect: tooling's compact legacy trace is valid context, not an API DTO.
async def test_compact_metadata_trace_is_supported_by_pure_cover1_replay(
    procedure_client, monkeypatch
):
    from app.services.procedure_output import load_snapshots, verify_output

    from tests.test_combined_procedure_profile import prepare

    client, db, _, payload, _ = await prepare(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    selection = result["provenance"]["answer_selection"]
    snapshots = await load_snapshots(db, selection)
    compact = {"scores": result["retrieval_trace"]["scores"], "refusal_threshold": None}
    assert verify_output(
        selection,
        question=result["question"],
        answer=result["answer"],
        citations=result["sources"],
        source_snapshots=snapshots,
        query_context=compact,
    )
