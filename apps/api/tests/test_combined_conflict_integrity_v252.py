"""Actual ASGI/storage integrity probes; external QA/NLI boundaries doubled only."""

import uuid
from copy import deepcopy
from dataclasses import replace

import pytest
from app.models.query import Query, QueryRequest
from app.services.answer_support import support_service

from tests.test_combined_conflict_repair_v244 import setup
from tests.test_procedure_extent import PRINCIPAL
from tests.test_procedure_http import procedure_client as procedure_client

pytest_plugins = ["tests.test_connected_contract"]

DAMAGES = [
    "scope_omitted",
    "all_scopes_omitted",
    "check_omitted",
    "conflicts_omitted",
    "inventory_omitted",
    "inventory_forged_empty",
    "hypothesis",
    "pair_premise",
    "model_settings",
    "model_threshold",
    "pair_budget",
    "pair_budget_boolean",
    "assessment_logits",
    "assessment_margin",
    "opponent_identity",
    "context_omitted",
    "group_member_omitted",
    "profile",
]


def damage_selection(selection, damage):  # noqa: C901 - independent mutation cases
    proof = selection["requirements"][0]["procedure_completeness"]
    conflict = selection["conflicts"][0]
    check = conflict["source_extent_checks"][0]
    scope = check["condition_scope"]
    if damage == "scope_omitted":
        check.pop("condition_scope")
    elif damage == "all_scopes_omitted":
        for row in conflict["source_extent_checks"]:
            row.pop("condition_scope", None)
    elif damage == "check_omitted":
        conflict["source_extent_checks"].pop(0)
    elif damage == "conflicts_omitted":
        selection["conflicts"] = []
    elif damage == "inventory_omitted":
        proof.pop("condition_exclusion_inventory", None)
    elif damage == "inventory_forged_empty":
        proof["condition_exclusion_inventory"] = {
            "contract": "procedure-condition-exclusion-inventory-v1",
            "groups": [],
            "exclusions": [],
        }
        proof["output_certificate"]["condition_exclusion_inventory"] = deepcopy(
            proof["condition_exclusion_inventory"]
        )
    elif damage == "hypothesis":
        scope["hypothesis"] = "The instructions apply to ordinary runs."
    elif damage == "pair_premise":
        scope.setdefault("pair", {})["premise"] = "Only a selected prefix."
    elif damage == "model_settings":
        scope["model_settings"] = {"support": {"model": "unrecognized-model"}}
    elif damage == "model_threshold":
        selection["evidence_support"]["minimum_entailment_margin"] = 4
    elif damage == "pair_budget":
        scope["assessment"]["pair_tokens"] = 513
    elif damage == "pair_budget_boolean":
        scope["assessment"]["pair_tokens"] = True
    elif damage == "assessment_logits":
        scope["assessment"]["logits"] = [10, -10, -10]
    elif damage == "assessment_margin":
        scope["assessment"]["entailment_margin"] = 999
    elif damage == "opponent_identity":
        check["document_id"] = str(uuid.uuid4())
    elif damage == "context_omitted":
        selection["procedure_contexts"] = [
            context
            for context in selection["procedure_contexts"]
            if context.get("origin") != "curated-procedure-inspection"
        ]
    elif damage == "group_member_omitted":
        selection["procedure_read_set"]["groups"][0]["sources"].pop(0)
    else:
        scope.setdefault("model_settings", {})["evidence_profile"] = {
            "procedure_verification_profile": "all_units_nli_v1"
        }


# Defect: mandatory exclusions can be altered/omitted without losing verification.
@pytest.mark.parametrize("damage", DAMAGES)
async def test_saved_exclusion_inventory_is_required_and_source_bound(
    procedure_client, monkeypatch, damage
):
    client, db, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    row = await db.get(Query, uuid.UUID(result["id"]))
    provenance = deepcopy(row.provenance)
    damage_selection(provenance["answer_selection"], damage)
    row.provenance = provenance
    await db.commit()
    stored = (row.answer, deepcopy(row.sources), deepcopy(row.provenance))
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["answer"] is None and saved["sources"] == []
    assert saved["evidence_access"] == "unknown"
    assert saved["retrieval_trace"] is None
    assert set(saved["provenance"]) == {"answer_selection"}
    assert set(saved["provenance"]["answer_selection"]) == {"presentation_verification"}
    assert (
        saved["provenance"]["answer_selection"]["presentation_verification"]["status"]
        == "invalid"
    )
    assert stored == (row.answer, row.sources, row.provenance)


# Defect: the same corrupt rationale may publish after the first stream token.
@pytest.mark.parametrize(
    "damage",
    ["scope_omitted", "hypothesis", "assessment_logits", "inventory_forged_empty"],
)
async def test_prepared_exclusion_tamper_fails_publication(
    procedure_client, monkeypatch, damage
):
    from app.api.queries import stream_query
    from sqlalchemy import select

    _, db, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    assert '"type": "token"' in await anext(response.body_iterator)
    with db.no_autoflush:
        row = await db.scalar(select(Query))
    provenance = deepcopy(row.provenance)
    damage_selection(provenance["answer_selection"], damage)
    row.provenance = provenance
    remaining = "".join([part async for part in response.body_iterator])
    assert '"type": "error"' in remaining and '"type": "done"' not in remaining
    assert row.outcome == "error" and row.answer is None and row.sources == []


# Defect: summary flags can hide incompatible raw logits at publication.
async def test_normal_publication_rejects_inconsistent_exclusion_assessment(
    procedure_client, monkeypatch
):
    client, _, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    original = support_service.assess

    async def malformed(pairs, config=None):
        decisions = await original(pairs, config=config)
        return [
            replace(d, logits=(10, -10, -10))
            if p.reference_id.endswith(":condition-scope")
            else d
            for p, d in zip(pairs, decisions, strict=True)
        ]

    monkeypatch.setattr(support_service, "assess", malformed)
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 503, response.json()


# Defect: history may rerun models or substitute today's threshold.
@pytest.mark.parametrize("recorded_margin", [0, 4])
async def test_valid_exclusion_history_uses_recorded_settings_without_models(
    procedure_client, monkeypatch, recorded_margin
):
    from app.services import connected_query

    client, _, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    recorded = connected_query.settings.model_copy(
        update={"SUPPORT_MIN_MARGIN": recorded_margin}
    )
    monkeypatch.setattr(connected_query, "settings", recorded)
    monkeypatch.setattr("app.api.queries.settings", recorded)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    current = recorded.model_copy(
        update={
            "SUPPORT_MIN_MARGIN": 4 if recorded_margin == 0 else 0,
            "SUPPORT_MODEL_PATH": "missing/historical-assets-must-not-be-read",
        }
    )
    monkeypatch.setattr(connected_query, "settings", current)
    monkeypatch.setattr("app.api.queries.settings", current)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Historical replay must not invoke a model")

    monkeypatch.setattr(support_service, "assess", forbidden)
    saved = (await client.get(f"/api/queries/{result['id']}")).json()
    assert saved["answer"] == result["answer"]
    assert saved["evidence_access"] == "available"


# Defect: pruning a read-set branch may hide retained immutable contexts.
async def test_coherent_exclusion_erasure_cannot_downgrade_to_legacy_certificate(
    procedure_client, monkeypatch
):
    client, db, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    row = await db.get(Query, uuid.UUID(result["id"]))
    provenance = deepcopy(row.provenance)
    selection = provenance["answer_selection"]
    proof = selection["requirements"][0]["procedure_completeness"]
    proof.pop("condition_exclusion_inventory", None)
    proof["output_certificate"].pop("condition_exclusion_inventory", None)
    proof["output_certificate"]["contract"] = "procedure-output-cover-v1"
    selection["conflicts"] = []
    selection["procedure_read_set"]["groups"] = []
    selection["procedure_read_set"]["sources"] = [
        source
        for source in selection["procedure_read_set"]["sources"]
        if source["conflict_group"] is None
    ]
    row.provenance = provenance
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["answer"] is None and saved["evidence_access"] == "unknown"


# Defect: exclusion replay must retain an equivalent ordinary member of the same group.
async def test_equivalent_ordinary_member_and_excluded_peers_remain_supported(
    procedure_client, monkeypatch
):
    client, db, document, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    document.metadata_ = {"conflict_group": "conditional-card-disposition"}
    await db.commit()
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.json()
    result = response.json()
    assert result["outcome"] == "completed", result


# Defect: a client cannot replay a complete curated source with missing chunk content.
async def test_conditional_inventory_exposes_complete_authoritative_contexts(
    procedure_client, monkeypatch
):
    from app.models.document import DocumentVersion
    from sqlalchemy import select

    client, db, _, opponents, payload, _, _ = await setup(procedure_client, monkeypatch)
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.json()
    result = response.json()
    contexts = result["provenance"]["answer_selection"]["requirements"][0][
        "procedure_completeness"
    ]["condition_exclusion_inventory"]["source_contexts"]
    assert {c["source_identity"]["document_id"] for c in contexts} == {
        str(d.id) for d in opponents
    }
    for context in contexts:
        identity = context["source_identity"]
        version = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == uuid.UUID(identity["document_id"]),
                DocumentVersion.version_number == identity["document_version"],
            )
        )
        assert context["source_body"] == version.normalized_content
        assert len(context["chunks"]) == len(version.chunks)
        for emitted, stored in zip(context["chunks"], version.chunks, strict=True):
            assert "content" in emitted, (
                "Canonical chunk content is missing from the actual API"
            )
            assert emitted["content"] == stored["content"]
            assert emitted["chunk_id"] == stored["id"]
            assert emitted["index"] == stored["index"]
            bounds = emitted["document_range"]
            assert (
                context["source_body"][bounds["start"] : bounds["end"]]
                == stored["content"]
            )


# Defect: a coherent last-chunk deletion may leave a falsely complete group manifest.
async def test_coherent_curated_chunk_omission_cannot_shrink_immutable_membership(
    procedure_client, monkeypatch
):
    from tests.test_combined_conflict_repair_v244 import audit_body
    from tests.test_combined_procedure_profile import prepare
    from tests.test_procedure_extent import seed_procedure

    client, db, _, payload, _ = await prepare(procedure_client, monkeypatch)
    for action in ("retain", "discard"):
        text = audit_body(action)
        split = text.index("\n\nThis instruction")
        document, _ = await seed_procedure(
            db, body=text, pieces=[text[:split], text[split:]]
        )
        document.metadata_ = {"conflict_group": "complete-chunk-membership"}
        payload["document_ids"].append(str(document.id))
    await db.commit()
    payload["top_k"] = 20
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    row = await db.get(Query, uuid.UUID(result["id"]))
    provenance = deepcopy(row.provenance)
    selection = provenance["answer_selection"]
    proof = selection["requirements"][0]["procedure_completeness"]
    inventory = proof["condition_exclusion_inventory"]
    omitted = inventory["source_contexts"][0]["chunks"][-1]["chunk_id"]

    def prune(items):
        return [item for item in items if item["chunk_id"] != omitted]

    selection["inspected_sources"] = prune(selection["inspected_sources"])
    selection["procedure_read_set"]["sources"] = prune(
        selection["procedure_read_set"]["sources"]
    )
    selection["procedure_read_set"]["groups"][0]["sources"] = prune(
        selection["procedure_read_set"]["groups"][0]["sources"]
    )
    selection["conflicts"][0]["inspection_sources"] = prune(
        selection["conflicts"][0]["inspection_sources"]
    )
    inventory["inspection_manifest"]["sources"] = prune(
        inventory["inspection_manifest"]["sources"]
    )
    inventory["inspection_manifest"]["groups"][0]["sources"] = prune(
        inventory["inspection_manifest"]["groups"][0]["sources"]
    )
    inventory["groups"][0]["sources"] = prune(inventory["groups"][0]["sources"])
    proof["output_certificate"]["condition_exclusion_inventory"] = deepcopy(inventory)
    row.provenance = provenance
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["answer"] is None and saved["evidence_access"] == "unknown"
