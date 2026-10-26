"""Actual HTTP/storage; only external QA/NLI model boundaries are doubled."""

from dataclasses import replace

import pytest
from app.services.answer_support import (
    SupportAssessment,
    SupportInputBudgetExceeded,
    SupportUnavailableError,
    support_service,
)

from tests.test_combined_procedure_profile import prepare
from tests.test_declared_paragraph_procedure import PARAGRAPHS
from tests.test_procedure_extent import seed_procedure
from tests.test_procedure_http import procedure_client as procedure_client

pytest_plugins = ["tests.test_connected_contract"]


def audit_body(action="retain", *, condition="postponed audit", tail=""):
    return (
        f"Lumen token bench: conditional record disposition {action}\n\n"
        f"For the Lumen token bench {condition} marked with a diamond, "
        f"the operator must {action} the marked card.\n\n"
        "This instruction applies only to the stated marked audit condition. "
        "An ordinary unflagged run remains governed by its complete "
        "operation procedure. Cards without that combination do not fall "
        "within this instruction's condition." + tail
    )


async def setup(  # noqa: C901 - external model success/error boundary cases
    procedure_client, monkeypatch, *, texts=None, mode="entailment"
):
    client, db, document, payload, calls = await prepare(procedure_client, monkeypatch)
    opponents = []
    for text in texts or [audit_body(), audit_body("discard")]:
        other, _ = await seed_procedure(db, body=text, pieces=[text])
        other.metadata_ = {"conflict_group": "conditional-card-disposition"}
        opponents.append(other)
    await db.commit()
    payload["document_ids"] += [str(d.id) for d in opponents]
    payload["top_k"] = 20
    normal_assess = support_service.assess
    scope_pairs = []

    async def assess(pairs, config=None):
        decisions = []
        for pair in pairs:
            if pair.reference_id.endswith(":condition-scope"):
                scope_pairs.append(pair)
                if mode == "budget":
                    raise SupportInputBudgetExceeded("test full input budget", (601,))
                if mode == "unavailable":
                    raise SupportUnavailableError("test missing local model")
                if mode == "incomplete":
                    return []
                decision = SupportAssessment("entailment", (-5, 5, -5), 10, True, 81)
                if mode == "neutral" or "For ordinary runs" in pair.premise:
                    decision = SupportAssessment("neutral", (-5, -5, 5), -10, False, 81)
                elif mode == "contradiction":
                    decision = SupportAssessment(
                        "contradiction", (5, -5, -5), -10, False, 81
                    )
                elif mode == "oversize":
                    decision = replace(decision, pair_tokens=513)
                decisions.append(decision)
            else:
                decisions.extend(await normal_assess([pair], config=config))
        return decisions

    monkeypatch.setattr(support_service, "assess", assess)
    return client, db, document, opponents, payload, calls, scope_pairs


# Defect: a title hides the excluded condition from conflict inspection.
async def test_excluded_curated_conditions_preserve_complete_answer_and_history(
    procedure_client, monkeypatch
):
    client, db, document, opponents, payload, calls, pairs = await setup(
        procedure_client, monkeypatch
    )
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "completed", result.get("refusal_reason")
    assert "\n\n".join(PARAGRAPHS) in result["answer"]
    selection = result["provenance"]["answer_selection"]
    conflict = selection["conflicts"][0]
    assert conflict["inspection_complete"] and not conflict["relevant"]
    assert set(conflict["subject_scope_excluded_documents"]) == {
        str(d.id) for d in opponents
    }
    assert len(pairs) == 2 and len(calls) >= 2
    assert {p.premise for p in pairs} == {audit_body(), audit_body("discard")}
    assert {s["document_id"] for s in conflict["inspection_sources"]} == {
        str(d.id) for d in opponents
    }
    for check in conflict["source_extent_checks"]:
        assert check["status"] == "irrelevant"
        scope = check["condition_scope"]
        assert scope["reason"] == "verified_excluded_source_condition"
        assert scope["assessment"]["label"] == "entailment"
        assert scope["assessment"]["pair_tokens"] == 81
        assert scope["premise_range"]["start"] == 0
    saved = (await client.get(f"/api/queries/{result['id']}")).json()
    assert saved["answer"] == result["answer"]
    assert (
        saved["provenance"]["answer_selection"]["conflicts"] == selection["conflicts"]
    )
    opponents[0].owner_id = "foreign-owner"
    await db.commit()
    revoked = (await client.get(f"/api/queries/{result['id']}")).json()
    assert revoked["evidence_access"] == "restricted"
    assert revoked["answer"] is None and revoked["sources"] == []


# Defect: a leading excluded condition must not override whole-body applicability.
@pytest.mark.parametrize(
    "mode",
    ["neutral", "contradiction", "oversize", "budget", "unavailable", "incomplete"],
)
async def test_unverified_exclusive_applicability_never_excludes(
    procedure_client, monkeypatch, mode
):
    client, _, _, _, payload, _, pairs = await setup(
        procedure_client, monkeypatch, mode=mode
    )
    response = await client.post("/api/queries", json=payload)
    result = response.json()
    if mode in {"unavailable", "incomplete"}:
        assert response.status_code == 503, result
    else:
        assert response.status_code == 200 and result["outcome"] == "refused"
        assert result["answer"] is None
    assert pairs, "Whole immutable body applicability was never assessed"


# Defect: matching/unknown conditions and ordinary-governing tails disappear.
@pytest.mark.parametrize(
    "text",
    [
        audit_body(condition="ordinary unflagged run"),
        audit_body(condition="postponed audit unless the permit is approved"),
        audit_body(condition="postponed audit or ordinary unflagged run"),
        audit_body(
            tail=" For ordinary runs, the operator must remove every token "
            "before counting."
        ),
    ],
)
async def test_unknown_or_mixed_conditions_remain_blocking(
    procedure_client, monkeypatch, text
):
    client, _, _, _, payload, _, _ = await setup(
        procedure_client, monkeypatch, texts=[text, audit_body("discard")]
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None


# Defect: QA-null genuine complete opponents must remain structurally inspected.
async def test_genuine_ordinary_opponent_still_blocks_with_no_qa_answer(
    procedure_client, monkeypatch
):
    from tests.test_declared_paragraph_procedure import body

    client, db, document, payload, calls = await prepare(procedure_client, monkeypatch)
    changed = body().replace("Place one token", "Place two tokens")
    other, _ = await seed_procedure(db, body=changed, pieces=[changed])
    document.metadata_ = other.metadata_ = {
        "conflict_group": "ordinary-procedure-opposition"
    }
    await db.commit()
    payload["document_ids"].append(str(other.id))
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None
    assert len(calls) == 4


# Defect: v3 curated membership was omitted from the post-inference read set.
async def test_new_curated_member_during_scope_inference_invalidates_answer(
    procedure_client, monkeypatch
):
    from tests.test_declared_paragraph_procedure import body

    client, db, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    original_assess = support_service.assess
    added = []

    async def add_member(pairs, config=None):
        if not added and any(
            p.reference_id.endswith(":condition-scope") for p in pairs
        ):
            text = body().replace("Place one token", "Place two tokens")
            newcomer, _ = await seed_procedure(db, body=text, pieces=[text])
            newcomer.metadata_ = {"conflict_group": "conditional-card-disposition"}
            added.append(newcomer)
            await db.commit()
        return await original_assess(pairs, config=config)

    monkeypatch.setattr(support_service, "assess", add_member)
    # Omit an explicit allowlist: new authorized group members must be observed.
    payload.pop("document_ids")
    result = (await client.post("/api/queries", json=payload)).json()
    assert added
    assert result["outcome"] == "refused" and result["answer"] is None
    selection = result["provenance"]["answer_selection"]
    assert selection["procedure_read_set"]["after_proofs"]["consistent"] is False
    assert selection["procedure_read_set"]["after_proofs"]["changed_groups"] == [
        "conditional-card-disposition"
    ]
    assert selection["conflicts"][0]["inspection_complete"] is False


# Defect: body-derived exclusions must not override explicit governing metadata.
async def test_explicit_metadata_condition_cannot_be_overridden_by_body_exclusion(
    procedure_client, monkeypatch
):
    client, db, _, opponents, payload, _, _ = await setup(procedure_client, monkeypatch)
    opponents[0].metadata_ = {
        **opponents[0].metadata_,
        "condition": "Lumen token bench",
    }
    await db.commit()
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None


# Defect: exclusion rules must use source declarations, not particular audit labels.
async def test_source_declared_other_excluded_class_and_independent_nli(
    procedure_client, monkeypatch
):
    from tests.test_declared_paragraph_procedure import body

    text = body().replace("postponed audit", "delayed inspection")
    client, db, document, payload, calls = await prepare(
        procedure_client, monkeypatch, text=text
    )
    other_text = audit_body(condition="delayed inspection")
    other, _ = await seed_procedure(db, body=other_text, pieces=[other_text])
    other.metadata_ = {"conflict_group": "another-condition-class"}
    await db.commit()
    payload["document_ids"].append(str(other.id))
    payload["top_k"] = 20
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result.get("refusal_reason")
    assert len(calls) == 3
    assert calls[-1].premise == other_text
    assert "delayed inspection" in calls[-1].hypothesis
    assert "postponed audit" not in calls[-1].hypothesis


# Defect: unknown prefaces and foreign namespaces cannot inherit the group's scope.
@pytest.mark.parametrize(
    "text",
    [
        "An unstated permit governs this run.\n\n" + audit_body(),
        audit_body().replace("Lumen token bench", "Cedar ticket desk"),
        audit_body(condition="unclassified run"),
    ],
)
async def test_unknown_opponent_scope_is_not_inherited(
    procedure_client, monkeypatch, text
):
    client, _, _, _, payload, _, _ = await setup(
        procedure_client, monkeypatch, texts=[text, audit_body("discard")]
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None


# Defect: successful exclusion must not bypass independent procedure NLI.
async def test_main_procedure_nli_negative_still_refuses(procedure_client, monkeypatch):
    client, _, _, _, payload, _, _ = await setup(procedure_client, monkeypatch)
    original = support_service.assess

    async def negative_namespace(pairs, config=None):
        if any(p.reference_id.endswith(":paragraph_namespace") for p in pairs):
            return [
                SupportAssessment("neutral", (-5, -5, 5), -10, False, 12) for _ in pairs
            ]
        return await original(pairs, config=config)

    monkeypatch.setattr(support_service, "assess", negative_namespace)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None


# Defect: changed opponent authorization during applicability inference may publish.
async def test_opponent_revoked_during_scope_inference_never_publishes(
    procedure_client, monkeypatch
):
    client, db, _, opponents, payload, _, _ = await setup(procedure_client, monkeypatch)
    original = support_service.assess

    async def revoke(pairs, config=None):
        if any(p.reference_id.endswith(":condition-scope") for p in pairs):
            opponents[0].owner_id = "foreign-owner"
            await db.commit()
        return await original(pairs, config=config)

    monkeypatch.setattr(support_service, "assess", revoke)
    response = await client.post("/api/queries", json=payload)
    result = response.json()
    assert response.status_code != 200 or result["outcome"] != "completed"
    assert result.get("answer") is None
