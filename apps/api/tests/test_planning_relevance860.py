"""Actual SQLite v3 runtime caller; UNITONLY parser and NLI backend boundaries."""

import json
from copy import deepcopy
from dataclasses import asdict

import pytest
from app.config import get_settings
from app.models.query import QueryRequest
from app.services import answer_support, request_parser
from app.services.staged_plan_replay import capture_inputs, reconstruct_request
from app.services.staged_planning_runtime import prepare_staged_planning
from app.services.staged_role_evidence import assess_role_evidence
from app.support_catalog import NLI

from tests.staged_plan_unit837.fixtures_request import ACTORS
from tests.staged_plan_unit837.fixtures_source import ASSIGN, CAT, NAME, capture
from tests.staged_role_unit850.test_role_evidence import Backend, backend_context
from tests.test_staged_snapshot_store849 import publish_library, staged

pytest_plugins = ["tests.test_connected_contract"]

ROUTINE = [
    [
        ("This", "DET", "this", "det", 1),
        ("note", "NOUN", "note", "nsubj", 2),
        ("applies", "VERB", "apply", "ROOT", 2),
        ("to", "ADP", "to", "prep", 2),
        ("Larch", "PROPN", "Larch", "compound", 5),
        ("inspection", "NOUN", "inspection", "pobj", 3),
        (".", "PUNCT", ".", "punct", 2),
    ],
    [
        ("Move", "VERB", "move", "ROOT", 0),
        ("the", "DET", "the", "det", 2),
        ("card", "NOUN", "card", "dobj", 0),
        (".", "PUNCT", ".", "punct", 0),
    ],
]


async def _published_case(connected_db, monkeypatch):
    staged(monkeypatch)
    settings = get_settings()
    for key, value in {
        "ANSWER_SUPPORT_MODE": "local_nli",
        "SUPPORT_MODEL_REVISION": NLI.revision,
        "SUPPORT_MODEL_PATH": "UNITONLY860-no-assets",
        "SUPPORT_MIN_MARGIN": 2.0,
    }.items():
        monkeypatch.setattr(settings, key, value)
    db, _ = connected_db
    observer = [
        ("observer", pos, "observer", dep, head)
        if word == "coordinator"
        else ("Juniper", pos, "Juniper", dep, head)
        if word == "Rowan"
        else (word, pos, lemma, dep, head)
        for word, pos, lemma, dep, head in ASSIGN
    ]
    recorder = [
        ("recorder", pos, "recorder", dep, head)
        if word == "coordinator"
        else ("Meadow", pos, "Meadow", dep, head)
        if word == "Rowan"
        else (word, pos, lemma, dep, head)
        for word, pos, lemma, dep, head in ASSIGN
    ]
    body, source_cap = capture([NAME, CAT, ASSIGN, observer, recorder])
    routine, routine_cap = capture(ROUTINE)
    question, request_cap = capture([ACTORS])
    doc, _ = await publish_library(db, body)
    other, _ = await publish_library(db, routine)
    caps = {body: source_cap, routine: routine_cap, question: request_cap}

    async def syntax(raw, config):
        return deepcopy(caps[raw])

    monkeypatch.setattr(request_parser, "capture_async", syntax)
    return db, settings, doc, other, question, request_cap


async def test_actual_public_v3_runtime_selects_role_without_erasing_other_routine(
    connected_db, monkeypatch
):
    db, settings, doc, other, question, request_cap = await _published_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        legacy = await prepare_staged_planning(
            db,
            {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False},
            QueryRequest(question=question),
            settings.model_copy(
                update={"EVIDENCE_READING_PROFILE": "contextual_source_v2"}
            ),
            execution_capture_kind="UNITONLY",
        )
        assert not legacy.support.accepted
        assert len(legacy.inspection.snapshots) == 2
        evidence = await prepare_staged_planning(
            db,
            {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False},
            QueryRequest(question=question),
            settings,
            execution_capture_kind="UNITONLY",
        )
        assert evidence.support.accepted, evidence.support.remaining_gates
        inspection = evidence.inspection
        assert len(inspection.snapshots) == len(inspection.captures) == 2
        inputs = capture_inputs(
            question=question,
            capture=request_cap,
            manifest=inspection.universe,
            snapshots=inspection.snapshots,
            source_captures=inspection.captures,
            support_metadata=json.loads(evidence.requested_support_metadata_json),
            sql_read_set_json=inspection.sql_read_set_json,
            observations=evidence.observations,
            actual_executions=evidence.executions,
        )
        authoritative = {
            row.identity.document_id: {
                **asdict(row.identity),
                "title": row.title,
                "body": row.body,
                "metadata": json.loads(row.metadata_json),
                "chunks": [
                    {
                        "id": chunk.chunk_id,
                        "index": chunk.ordinal,
                        "content": chunk.literal.text,
                        "metadata": json.loads(chunk.metadata_json),
                    }
                    for chunk in row.chunks
                ],
            }
            for row in inspection.snapshots
        }
        plan = reconstruct_request(
            inputs,
            question=question,
            retained_inputs=deepcopy(inputs),
            authoritative_snapshots=authoritative,
            require_runtime=False,
        )
        assert plan.resolved_request
        assert json.loads(plan.scope_bridge_json)["excluded"] == [str(other.id)]
        assert {row["identity"]["document_id"] for row in inputs["snapshots"]} == {
            str(doc.id),
            str(other.id),
        }
        requirement = next(
            row for row in plan.requirements if row.kind == "role_assignment"
        )
        result = await assess_role_evidence(
            settings,
            question=question,
            requirement_id=requirement.id,
            planning_inputs=inputs,
            retained_inputs=deepcopy(inputs),
            authoritative_snapshots=authoritative,
            require_runtime=False,
            execution_capture_kind="UNITONLY",
        )
        assert result.supported and result.facts[0].value == "Rowan"
        assert json.loads(result.prepared.inventory_json)["blockers"]
        assert json.loads(result.prepared.read_set_json)["snapshot_reads"]


async def test_excluded_non_cited_source_still_participates_in_actual_sql_recheck(
    connected_db, monkeypatch
):
    db, settings, _, other, question, _ = await _published_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        actual_assess = answer_support.support_service.assess

        async def revoke_after_actual_inference(pairs, config):
            decisions = await actual_assess(pairs, config)
            other.owner_id = "UNITONLY-revoked-owner"
            await db.commit()
            return decisions

        monkeypatch.setattr(
            answer_support.support_service, "assess", revoke_after_actual_inference
        )
        with pytest.raises(ValueError, match="Planning SQL read set changed") as caught:
            await prepare_staged_planning(
                db,
                {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False},
                QueryRequest(question=question),
                settings,
                execution_capture_kind="UNITONLY",
            )
    failure = json.loads(caught.value.planning_evidence_json)
    assert failure["stage"] == "sql_recheck"
    assert not failure["sql_recheck"]["consistent"]
    assert len(failure["inspection"]["snapshots"]) == 2
    effective = json.loads(failure["assertion_set"]["effective_plan_json"])
    selection = json.loads(effective["candidate_selection_json"])
    assert selection["excluded_source_ids"] == [str(other.id)]
    assert len(json.loads(selection["read_set_json"])["snapshot_reads"]) == 2
