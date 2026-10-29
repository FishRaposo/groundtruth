"""V2 exact context references plus unchanged semantic/access/output gates."""

import json
from copy import deepcopy

import pytest
from app.services.procedure_output import load_snapshots, verify_output

from tests.test_procedure_http import procedure_client as procedure_client
from tests.test_source_context_integration_v319 import prepare_context

pytest_plugins = ["tests.test_connected_contract"]


async def prepare_v2(procedure_client, monkeypatch, **kwargs):
    return await prepare_context(
        procedure_client, monkeypatch, policy="scoped_note_context_v2", **kwargs
    )


async def test_v2_publication_fixture_and_history(procedure_client, monkeypatch):
    import os
    from pathlib import Path

    client, db, _, payload, calls = await prepare_v2(procedure_client, monkeypatch)
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "completed", result
    assert "card and cover references" in result["answer"]
    selection = result["provenance"]["answer_selection"]
    assert selection["evidence_profile"]["contract"] == "evidence-profile-v4"
    proof = selection["requirements"][0]["procedure_completeness"]
    assert proof["output_certificate"]["contract"] == "procedure-output-cover-v4"
    assert (
        proof["condition_exclusion_inventory"]["contract"]
        == "procedure-condition-exclusion-inventory-v3"
    )
    for check in selection["conflicts"][0]["source_extent_checks"]:
        scope = check["condition_scope"]
        assert scope["contract"] == "procedure-condition-scope-v3"
        assert len(scope["semantic_checks"]) == 22
        assert len(scope["reference_obligations"]) == 1
    assert not any(
        pair.reference_id.endswith(":card_reference_identity") for pair in calls
    )
    snapshots = await load_snapshots(db, selection)
    assert verify_output(
        selection,
        question=payload["question"],
        answer=result["answer"],
        citations=result["sources"],
        source_snapshots=snapshots,
        query_context=result["retrieval_trace"],
    )
    saved = (await client.get(f"/api/queries/{result['id']}")).json()
    assert saved["answer"] == result["answer"]
    if output := os.environ.get("CONTEXT_REFERENCE_FIXTURE"):
        Path(output).write_text(
            json.dumps(
                {
                    "evidence_scope": (
                        "ASGI/storage with QA/NLI doubles; no model quality"
                    ),
                    "response": result,
                    "request": payload,
                    "source_snapshots": snapshots,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def mutate_reference_scope(scope, damage):  # noqa: C901 - independent adversarial mutations
    exact = scope["reference_obligations"][0]
    plan = exact["reference_plan"]
    if damage == "event-card-collapse":
        event = next(row for row in plan["entities"] if row["id"] == "event")
        card = next(row for row in plan["entities"] if row["id"] == "card")
        event.update(type=card["type"], source_range=deepcopy(card["source_range"]))
    elif damage == "cover-owner":
        next(row for row in plan["entities"] if row["id"] == "cover")["cover_of"] = (
            "event"
        )
    elif damage == "conjunction-loss":
        plan["guard"]["members"].pop()
    elif damage == "guard-disjunction":
        plan["guard"]["connective"] = "or"
    elif damage == "generic-card-collapse":
        plan["generic_card_predicate"]["variable_role"] = "card"
    elif damage == "raw-domain-strengthening":
        plan["domains"][0]["raw"]["literal"] = "only card dispositions"
    elif damage == "reference-range-shift":
        plan["reference_occurrences"][0]["source_range"]["start"] += 1
    elif damage == "target-type":
        plan["reference_occurrences"][0]["target_type"] = "physical_card"
    elif damage == "coherent-edge-prune":
        plan["reference_occurrences"].pop()
        plan["required_reference_count"] -= 1
    elif damage == "fake-nli-identity":
        exact.update(
            verification_method="nli_entailment",
            label="entailment",
            logits=[-5, 5, -5],
            entailment_margin=10,
            pair_tokens=12,
        )
    elif damage == "unknown-method":
        exact["contract"] = "context-reference-structure-v9"
    elif damage == "extra-exact-key":
        exact["pair"] = {"premise": "fake inference"}
    elif damage == "missing-linkage":
        scope["reference_obligations"] = []
        scope["obligation_plan"]["obligations"].pop()
        scope["obligation_plan"]["mandatory_obligation_count"] = 22
        scope["obligation_plan"]["mandatory_exact_reference_count"] = 0
    elif damage == "missing-slot":
        plan["binding_slots"].pop()
    elif damage == "boolean-cardinality":
        plan["reference_occurrences"][0]["cardinality"] = True
    elif damage == "float-cardinality":
        plan["reference_occurrences"][0]["cardinality"] = 1.0
    elif damage == "float-nli-range":
        scope["semantic_checks"][0]["premise_range"]["start"] = float(
            scope["semantic_checks"][0]["premise_range"]["start"]
        )
    elif damage == "boolean-offset":
        plan["source_range"]["start"] = False
    elif damage == "float-count":
        scope["obligation_plan"]["mandatory_exact_reference_count"] = 1.0
    elif damage == "unknown-plan":
        scope["obligation_plan"]["contract"] = "source-note-obligation-plan-v9"
    elif damage == "restamp-v1":
        scope["contract"] = "procedure-condition-scope-v2"
        scope.pop("reference_obligations")
        scope.pop("obligation_plan")
    else:
        raise AssertionError(damage)


@pytest.mark.parametrize(
    "damage",
    [
        "event-card-collapse",
        "cover-owner",
        "conjunction-loss",
        "guard-disjunction",
        "generic-card-collapse",
        "raw-domain-strengthening",
        "reference-range-shift",
        "target-type",
        "coherent-edge-prune",
        "fake-nli-identity",
        "unknown-method",
        "extra-exact-key",
        "missing-linkage",
        "missing-slot",
        "boolean-cardinality",
        "float-cardinality",
        "boolean-offset",
        "float-nli-range",
        "float-count",
        "unknown-plan",
        "restamp-v1",
    ],
)
async def test_d342_coherent_producer_and_capture_tamper_fails_canonical_replay(
    procedure_client, monkeypatch, damage
):
    client, db, _, payload, _ = await prepare_v2(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    selection = deepcopy(result["provenance"]["answer_selection"])
    source_snapshots = await load_snapshots(db, selection)
    scope = selection["conflicts"][0]["source_extent_checks"][0]["condition_scope"]
    mutate_reference_scope(scope, damage)
    proof = selection["requirements"][0]["procedure_completeness"]
    exclusion = next(
        row
        for row in proof["condition_exclusion_inventory"]["exclusions"]
        if row["source_identity"]["document_id"]
        == selection["conflicts"][0]["source_extent_checks"][0]["document_id"]
    )
    exclusion["condition_scope"] = deepcopy(scope)
    proof["output_certificate"]["condition_exclusion_inventory"] = deepcopy(
        proof["condition_exclusion_inventory"]
    )
    captured = deepcopy(result["retrieval_trace"])
    captured["provenance"]["answer_selection"] = deepcopy(selection)
    assert not verify_output(
        selection,
        question=payload["question"],
        answer=result["answer"],
        citations=result["sources"],
        source_snapshots=source_snapshots,
        query_context=captured,
    )


@pytest.mark.parametrize(
    "failure",
    [
        "activity_subject",
        "actor_applicability",
        "classification_identity",
        "classification_mark",
        "negative_condition_tuple",
        "reader_choice_prohibition",
        "paragraph_namespace",
        "unavailable",
        "incomplete",
        "budget",
    ],
)
async def test_valid_exact_reference_never_substitutes_for_nli_or_model_failure(
    procedure_client, monkeypatch, failure
):
    from app.services.answer_support import (
        SupportAssessment,
        SupportInputBudgetExceeded,
        SupportUnavailableError,
        support_service,
    )

    client, _, _, payload, _ = await prepare_v2(procedure_client, monkeypatch)
    original = support_service.assess

    async def assess(pairs, config=None):
        if any(":context-scope:" in pair.reference_id for pair in pairs):
            if failure == "unavailable":
                raise SupportUnavailableError("explicit missing support model test")
            if failure == "incomplete":
                return []
            if failure == "budget":
                raise SupportInputBudgetExceeded("explicit token budget test", (513,))
        values = await original(pairs, config=config)
        return [
            SupportAssessment("neutral", (-5, -5, 5), -10, False, 12)
            if pair.reference_id.endswith(":" + failure)
            else value
            for pair, value in zip(pairs, values, strict=True)
        ]

    monkeypatch.setattr(support_service, "assess", assess)
    response = await client.post("/api/queries", json=payload)
    result = response.json()
    assert result.get("answer") is None
    if failure in {"unavailable", "incomplete"}:
        assert response.status_code == 503
    else:
        assert response.status_code == 200 and result["outcome"] == "refused"


async def test_legacy_v1_neutral_identity_cannot_be_upgraded_during_history(
    procedure_client, monkeypatch
):
    from app.services import connected_query
    from app.services.answer_support import SupportAssessment, support_service

    client, _, _, payload, _ = await prepare_context(
        procedure_client, monkeypatch, policy="scoped_note_context_v1"
    )
    original = support_service.assess

    async def neutral_identity(pairs, config=None):
        values = await original(pairs, config=config)
        return [
            SupportAssessment("neutral", (-5, -5, 5), -10, False, 12)
            if pair.reference_id.endswith(":card_reference_identity")
            else value
            for pair, value in zip(pairs, values, strict=True)
        ]

    monkeypatch.setattr(support_service, "assess", neutral_identity)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused"
    selection = result["provenance"]["answer_selection"]
    assert (
        selection["evidence_profile"]["source_context_policy"]
        == "scoped_note_context_v1"
    )
    config = connected_query.settings.model_copy(
        update={"SOURCE_CONTEXT_POLICY": "scoped_note_context_v2"}
    )
    monkeypatch.setattr(connected_query, "settings", config)
    monkeypatch.setattr("app.api.queries.settings", config)

    async def no_inference(*args, **kwargs):
        raise AssertionError("Historical refusal must not run new plan or models")

    monkeypatch.setattr(support_service, "assess", no_inference)
    saved = (await client.get(f"/api/queries/{result['id']}")).json()
    assert saved["outcome"] == "refused" and saved["answer"] is None


@pytest.mark.parametrize(
    "damage",
    [
        "positive-assessment",
        "capture-plan-prune",
        "profile-prune",
        "actual-disclosure-hide",
    ],
)
async def test_v2_history_binds_capture_plan_nli_profile_and_actual_disclosure(
    procedure_client, monkeypatch, damage
):
    import uuid

    from app.models.query import Query

    client, db, _, payload, _ = await prepare_v2(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    row = await db.get(Query, uuid.UUID(result["id"]))
    if damage == "capture-plan-prune":
        trace = deepcopy(row.retrieval_trace)
        trace["provenance"]["answer_selection"]["conflicts"][0]["source_extent_checks"][
            0
        ]["condition_scope"]["obligation_plan"]["obligations"].pop()
        row.retrieval_trace = trace
    elif damage == "actual-disclosure-hide":
        row.answer = row.answer.replace("card and cover references", "references")
    else:
        provenance = deepcopy(row.provenance)
        selection = provenance["answer_selection"]
        if damage == "profile-prune":
            selection["evidence_profile"].pop("source_context_policy")
        else:
            scope = selection["conflicts"][0]["source_extent_checks"][0][
                "condition_scope"
            ]
            scope["semantic_checks"][0]["assessment"].update(
                logits=[-6, 6, -6], entailment_margin=12
            )
            proof = selection["requirements"][0]["procedure_completeness"]
            target = next(
                exclusion
                for exclusion in proof["condition_exclusion_inventory"]["exclusions"]
                if exclusion["source_identity"]["document_id"]
                == selection["conflicts"][0]["source_extent_checks"][0]["document_id"]
            )
            target["condition_scope"] = deepcopy(scope)
            proof["output_certificate"]["condition_exclusion_inventory"] = deepcopy(
                proof["condition_exclusion_inventory"]
            )
        row.provenance = provenance
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["answer"] is None and saved["evidence_access"] == "unknown"
    assert saved["sources"] == [] and saved["retrieval_trace"] is None
    assert "audit cover card" not in json.dumps(saved)


async def test_non_cited_opponent_revocation_withholds_all_typed_literals(
    procedure_client, monkeypatch
):
    import uuid

    from app.models.document import Document

    client, db, _, payload, _ = await prepare_v2(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed"
    opponent = await db.get(Document, uuid.UUID(payload["document_ids"][1]))
    opponent.owner_id = "foreign-owner"
    await db.commit()
    saved = (await client.get(f"/api/queries/{result['id']}")).json()
    assert saved["answer"] is None and saved["evidence_access"] == "restricted"
    assert saved["sources"] == [] and saved["retrieval_trace"] is None
    assert "audit cover card" not in json.dumps(saved)
    assert "card_reference_linkage" not in json.dumps(saved)


async def test_v2_sse_and_history_keep_typed_method_and_disclosure(
    procedure_client, monkeypatch
):
    client, _, _, payload, _ = await prepare_v2(procedure_client, monkeypatch)
    response = await client.post("/api/queries/stream", json=payload)
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert not any(event["type"] == "error" for event in events)
    done = next(event for event in events if event["type"] == "done")
    assert "card and cover references" in done["answer"]
    saved = (await client.get(f"/api/queries/{done['id']}")).json()
    assert saved["answer"] == done["answer"]
