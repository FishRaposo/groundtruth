"""Reauthorize non-cited planning material in actual SQLite/API history."""

import json
import uuid
from copy import deepcopy

import pytest
from app.models.document import Document
from app.models.query import Query

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize("channel", ["presented", "retained"])
async def test_revoked_non_cited_planning_source_withholds_saved_refusal(
    real_client, channel
):
    client, factory, keys = real_client
    marker = "UNITONLY_NONCITED_PRIVATE_PLANNING_CONTENT"
    private = await upload(client, marker)
    public = await upload(client, "Staging rollback requires eleven minutes.")
    response = await client.post(
        "/api/queries",
        json={
            "question": "What is the unsupported staging payment?",
            "document_ids": [public["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    identifier = response.json()["id"]
    async with factory() as db:
        row = await db.get(Query, uuid.UUID(identifier))
        row.outcome, row.refused, row.answer, row.sources = "refused", True, None, []
        row.provenance = {
            **(row.provenance or {}),
            "answer_selection": {
                "contract": "requirement-evidence-v5",
                "inspected_sources": [],
                "requirements": [],
                "candidates": [],
                "procedure_contexts": [],
            },
        }
        record = {
            "contract": "staged-request-inputs-v1",
            "snapshots": [{"identity": {"document_id": private["id"]}, "body": marker}],
            "manifest": {"publications": [{"document_id": private["id"]}]},
        }
        if channel == "presented":
            row.provenance["answer_selection"]["staged_request_inputs"] = record
        else:
            row.retrieval_trace = {
                **(row.retrieval_trace or {}),
                "provenance": {
                    "answer_selection": {
                        **deepcopy(row.provenance["answer_selection"]),
                        "staged_request_inputs": record,
                    }
                },
            }
        await db.commit()
    before = await client.get(f"/api/queries/{identifier}")
    assert before.status_code == 200 and before.json()["evidence_access"] == "available"
    assert marker in before.text
    async with factory() as db:
        doc = await db.get(Document, uuid.UUID(private["id"]))
        doc.owner_id = keys["reader"]
        await db.commit()
    for path in [
        f"/api/queries/{identifier}",
        f"/api/conversations/{before.json()['conversation_id']}",
    ]:
        saved = await client.get(path)
        assert saved.status_code == 200
        assert marker not in saved.text and private["id"] not in saved.text
        body = saved.json()
        result = body["queries"][0] if "queries" in body else body
        assert result["evidence_access"] == "restricted"
        assert result["answer"] is None and result["sources"] == []
        assert result["provenance"] is None and result["retrieval_trace"] is None
    async with factory() as db:
        row = await db.get(Query, uuid.UUID(identifier))
        assert marker in json.dumps(
            row.provenance if channel == "presented" else row.retrieval_trace
        )


@pytest.mark.parametrize("change", ["title", "new-publication", "revoked"])
async def test_staged_publication_rechecks_all_authorized_sql_inputs(
    real_client, change
):
    from app.models.query import QueryRequest
    from app.services.planning_declarations import canonical
    from app.services.request_planning_manifest import inspect_planning_manifest
    from app.services.staged_answer_planning import recheck_inputs

    client, factory, keys = real_client
    source = await upload(client, "UNITONLY publication snapshot for review.")
    principal = {"id": keys["owner"], "workspace_id": "ops-a", "is_admin": False}
    request = QueryRequest(question="UNITONLY complete authorized planning universe")
    async with factory() as db:
        manifest = await inspect_planning_manifest(db, principal, request)
        assert manifest.complete
        inputs = {"sql_read_set_json": canonical(manifest.record())}
        before = await recheck_inputs(db, principal, request.question, inputs)
        assert before == {"consistent": True, "reason": None}
    if change == "new-publication":
        await upload(client, "UNITONLY second publication was added after inference.")
    else:
        async with factory() as db:
            doc = await db.get(Document, uuid.UUID(source["id"]))
            if change == "title":
                doc.title = "Changed captured title"
            else:
                doc.owner_id = keys["reader"]
            await db.commit()
    async with factory() as db:
        after = await recheck_inputs(db, principal, request.question, inputs)
        assert after == {"consistent": False, "reason": "planning_publications_changed"}
