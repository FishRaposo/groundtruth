"""New-input identity enumeration must preserve access checks for all bodies."""

import json
import uuid
from copy import deepcopy

import pytest
from app.models.document import Document
from app.models.query import Query
from app.services import staged_publication_context as archive
from app.services.connected_query import add_staged_contexts
from app.services.staged_snapshot_store import load_staged_snapshots

from tests.test_connected_contract import upload
from tests.test_staged_snapshot_store849 import channels, publish_library, staged
from tests.test_staged_snapshot_store849 import tmp_path as tmp_path

pytest_plugins = ["tests.test_connected_contract"]


async def test_new_input_identity_enumeration_loads_database_archive(
    connected_db, monkeypatch
):
    staged(monkeypatch)
    db, _ = connected_db
    document, version = await publish_library(db, "The immutable evidence body.")
    selection, retained = channels(version)
    for record in (selection, retained["provenance"]["answer_selection"]):
        record["staged_request_inputs"]["contract"] = "staged-request-inputs-v2"
    ids = set()
    add_staged_contexts(selection, ids)
    assert ids == {document.id}
    snapshots = await load_staged_snapshots(db, selection, query_context=retained)
    assert snapshots == {str(document.id): archive.validated_projection(version)}


@pytest.mark.parametrize("channel", ["presented", "retained"])
async def test_new_input_saved_refusal_reauthorizes_noncited_source(
    real_client, channel
):
    client, factory, keys = real_client
    marker = "UNITONLY_PRIVATE_INPUT2_BODY"
    source = await upload(client, marker)
    response = await client.post(
        "/api/queries",
        json={
            "question": "What is the unspecified payment?",
            "document_ids": [source["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200
    identifier = response.json()["id"]
    selection = {
        "contract": "requirement-evidence-v5",
        "inspected_sources": [],
        "requirements": [],
        "candidates": [],
        "procedure_contexts": [],
    }
    inputs = {
        "contract": "staged-request-inputs-v2",
        "snapshots": [{"identity": {"document_id": source["id"]}, "body": marker}],
        "manifest": {"publications": [{"document_id": source["id"]}]},
    }
    # Identity-only transport exercises access enumeration, not semantic proof.
    async with factory() as db:
        row = await db.get(Query, uuid.UUID(identifier))
        row.outcome, row.refused, row.answer, row.sources = "refused", True, None, []
        row.provenance = {"answer_selection": deepcopy(selection)}
        if channel == "presented":
            row.provenance["answer_selection"]["staged_request_inputs"] = inputs
        else:
            row.retrieval_trace = {
                **(row.retrieval_trace or {}),
                "provenance": {
                    "answer_selection": {**selection, "staged_request_inputs": inputs}
                },
            }
        await db.commit()
    accessible = await client.get(f"/api/queries/{identifier}")
    assert accessible.status_code == 200
    assert accessible.json()["evidence_access"] == "available"
    assert marker in accessible.text
    async with factory() as db:
        document = await db.get(Document, uuid.UUID(source["id"]))
        document.owner_id = keys["reader"]
        await db.commit()
    for path in (
        f"/api/queries/{identifier}",
        f"/api/conversations/{accessible.json()['conversation_id']}",
    ):
        saved = await client.get(path)
        assert saved.status_code == 200
        assert marker not in saved.text and source["id"] not in saved.text
        result = saved.json()
        if "queries" in result:
            result = result["queries"][0]
        assert result["evidence_access"] == "restricted"
        assert result["answer"] is None and result["sources"] == []
        assert result["provenance"] is None and result["retrieval_trace"] is None
    async with factory() as db:
        row = await db.get(Query, uuid.UUID(identifier))
        assert marker in json.dumps(
            row.provenance if channel == "presented" else row.retrieval_trace
        )
