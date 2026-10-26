"""Context policy integration with QA/NLI doubles; no model quality evidence."""

import json
from copy import deepcopy

import pytest
from app.models.query import Query
from app.services.answer_support import SupportAssessment, support_service
from app.services.procedure_output import load_snapshots, verify_output

from tests.test_combined_procedure_profile import prepare
from tests.test_procedure_extent import seed_procedure
from tests.test_procedure_http import procedure_client as procedure_client
from tests.test_source_context_policy_v319 import note

pytest_plugins = ["tests.test_connected_contract"]


async def prepare_context(
    procedure_client, monkeypatch, *, tail="", policy="scoped_note_context_v1"
):
    from app.services import connected_query

    client, db, main, payload, calls = await prepare(procedure_client, monkeypatch)
    config = connected_query.settings.model_copy(
        update={"SOURCE_CONTEXT_POLICY": policy}
    )
    monkeypatch.setattr(connected_query, "settings", config)
    monkeypatch.setattr("app.api.queries.settings", config)
    for action in ("retain", "discard"):
        text = note(action=action) + tail
        opponent, _ = await seed_procedure(db, body=text, pieces=[text])
        opponent.metadata_ = {"conflict_group": "unresolved-card-policy"}
        payload["document_ids"].append(str(opponent.id))
    payload["top_k"] = 20
    await db.commit()
    return client, db, main, payload, calls


async def test_context_publication_history_and_contract_fixture(
    procedure_client, monkeypatch
):
    import os
    from pathlib import Path

    client, db, _, payload, calls = await prepare_context(procedure_client, monkeypatch)
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "completed", result
    assert "Context reading:" in result["answer"]
    selection = result["provenance"]["answer_selection"]
    proof = selection["requirements"][0]["procedure_completeness"]
    assert proof["output_certificate"]["contract"] == "procedure-output-cover-v3"
    assert (
        proof["condition_exclusion_inventory"]["contract"]
        == "procedure-condition-exclusion-inventory-v2"
    )
    scopes = selection["conflicts"][0]["source_extent_checks"]
    assert len(scopes) == 2
    assert all(
        row["condition_scope"]["contract"] == "procedure-condition-scope-v2"
        for row in scopes
    )
    assert all(
        "apply only" not in pair.hypothesis
        for pair in calls
        if ":context-scope:" in pair.reference_id
    )
    history = (await client.get(f"/api/queries/{result['id']}")).json()
    assert history["answer"] == result["answer"]
    snapshots = await load_snapshots(db, selection)
    if output := os.environ.get("CONTEXT_POLICY_FIXTURE"):
        Path(output).write_text(
            json.dumps(
                {
                    "evidence_scope": (
                        "ASGI/storage with QA/NLI doubles; not model quality"
                    ),
                    "response": result,
                    "request": payload,
                    "source_snapshots": snapshots,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    assert verify_output(
        selection,
        question=payload["question"],
        answer=result["answer"],
        citations=result["sources"],
        source_snapshots=snapshots,
        query_context=result["retrieval_trace"],
    )


@pytest.mark.parametrize(
    "kind", ["ordinary_tail", "unknown_tail", "subject_nli", "factual_nli", "main_nli"]
)
async def test_context_never_silences_unknown_or_negative_evidence(
    procedure_client, monkeypatch, kind
):
    tail = (
        " For ordinary runs, the operator must remove every token."
        if kind == "ordinary_tail"
        else " Another instruction governs the archive."
        if kind == "unknown_tail"
        else ""
    )
    client, _, _, payload, _ = await prepare_context(
        procedure_client, monkeypatch, tail=tail
    )
    original = support_service.assess

    async def assess(pairs, config=None):
        values = await original(pairs, config=config)
        return [
            SupportAssessment("neutral", (-5, -5, 5), -10, False, 12)
            if (
                (
                    kind == "subject_nli"
                    and pair.reference_id.endswith(":context-scope:scoped_directive")
                )
                or (
                    kind == "factual_nli"
                    and pair.reference_id.endswith(":context-scope:state_definition")
                )
                or (
                    kind == "main_nli"
                    and pair.reference_id.endswith(":paragraph_namespace")
                )
            )
            else value
            for pair, value in zip(pairs, values, strict=True)
        ]

    monkeypatch.setattr(support_service, "assess", assess)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None


@pytest.mark.parametrize(
    "damage",
    [
        "clause",
        "reference",
        "context",
        "pair",
        "assessment",
        "disclosure",
        "profile",
        "body",
        "checks",
    ],
)
async def test_context_certificate_replay_rejects_coupled_producer_tamper(
    procedure_client, monkeypatch, damage
):
    import uuid

    client, db, _, payload, _ = await prepare_context(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    row = await db.get(Query, uuid.UUID(result["id"]))
    provenance = deepcopy(row.provenance)
    selection = provenance["answer_selection"]
    scope = selection["conflicts"][0]["source_extent_checks"][0]["condition_scope"]
    if damage == "clause":
        scope["context_reading"]["clause_inventory"].pop()
    elif damage == "reference":
        scope["context_reading"]["clause_inventory"][9]["references"] = {}
    elif damage == "context":
        scope["context_reading"]["adopted_context"]["resolved_quantifier_domain"] = (
            "every workflow disposition"
        )
    elif damage == "pair":
        scope["semantic_checks"][0]["pair"]["premise"] = "selected fragment"
    elif damage == "assessment":
        scope["semantic_checks"][0]["assessment"]["logits"] = [10, -10, -10]
    elif damage == "disclosure":
        scope["context_reading"]["disclosure"] = ""
    elif damage == "profile":
        selection["evidence_profile"].pop("source_context_policy")
    elif damage == "body":
        scope["context_reading"]["source_body"] += (
            " For every workflow, discard all cards."
        )
    else:
        scope["semantic_checks"].pop()
    proof = selection["requirements"][0]["procedure_completeness"]
    proof["condition_exclusion_inventory"]["exclusions"][0]["condition_scope"] = (
        deepcopy(scope)
    )
    proof["output_certificate"]["condition_exclusion_inventory"] = deepcopy(
        proof["condition_exclusion_inventory"]
    )
    row.provenance = provenance
    await db.commit()
    history = (await client.get(f"/api/queries/{row.id}")).json()
    assert history["answer"] is None and history["evidence_access"] == "unknown"


async def test_context_raw_capture_rejects_alternate_positive_logits(
    procedure_client, monkeypatch
):
    import uuid

    client, db, _, payload, _ = await prepare_context(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    row = await db.get(Query, uuid.UUID(result["id"]))
    provenance = deepcopy(row.provenance)
    selection = provenance["answer_selection"]
    scope = selection["conflicts"][0]["source_extent_checks"][0]["condition_scope"]
    scope["semantic_checks"][0]["assessment"].update(
        logits=[-6, 6, -6], entailment_margin=12
    )
    proof = selection["requirements"][0]["procedure_completeness"]
    proof["condition_exclusion_inventory"]["exclusions"][0]["condition_scope"] = (
        deepcopy(scope)
    )
    proof["output_certificate"]["condition_exclusion_inventory"] = deepcopy(
        proof["condition_exclusion_inventory"]
    )
    row.provenance = provenance
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["answer"] is None and saved["evidence_access"] == "unknown"


async def test_context_history_uses_recorded_policy_and_no_model_assets(
    procedure_client, monkeypatch
):
    from app.services import connected_query

    client, _, _, payload, _ = await prepare_context(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    current = connected_query.settings.model_copy(
        update={
            "SOURCE_CONTEXT_POLICY": "explicit_target_v1",
            "SUPPORT_MODEL_PATH": "missing",
            "SUPPORT_MIN_MARGIN": 4,
        }
    )
    monkeypatch.setattr(connected_query, "settings", current)
    monkeypatch.setattr("app.api.queries.settings", current)

    async def unavailable(*args, **kwargs):
        raise AssertionError("History must not run model inference")

    monkeypatch.setattr(support_service, "assess", unavailable)
    saved = (await client.get(f"/api/queries/{result['id']}")).json()
    assert saved["answer"] == result["answer"]


async def test_context_sse_preserves_disclosure_and_full_evidence(
    procedure_client, monkeypatch
):
    client, _, _, payload, _ = await prepare_context(procedure_client, monkeypatch)
    response = await client.post("/api/queries/stream", json=payload)
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert not any(event["type"] == "error" for event in events), events
    done = next(event for event in events if event["type"] == "done")
    assert "Context reading:" in done["answer"]
    assert (
        done["provenance"]["answer_selection"]["evidence_profile"]["contract"]
        == "evidence-profile-v3"
    )
