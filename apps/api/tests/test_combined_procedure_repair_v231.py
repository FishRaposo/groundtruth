"""Evidence-boundary repair controls; actual ASGI/SQL, external model doubles."""

import uuid
from copy import deepcopy
from datetime import timedelta

import pytest
from app.models.query import Query, QueryRequest
from app.services.answer_requirements import plan_requirements
from app.services.connected_query import scoped_memory

from tests.test_combined_procedure_profile import closed_role_free_body, prepare
from tests.test_declared_paragraph_procedure import PARAGRAPHS, QUESTION
from tests.test_procedure_extent import LONG, PRINCIPAL, seed_procedure
from tests.test_procedure_extent import QUESTION as NUMBERED
from tests.test_procedure_http import procedure_client as procedure_client

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize(
    "topic",
    [
        "ordinary opaque Harbor docket worksheets with no seal",
        "ordinary Harbor docket worksheets opaque with no seal",
        "Emergency Harbor docket worksheets with no seal",
        "ordinary Harbor docket worksheets only after midnight with no seal",
        "ordinary Harbor rockets worksheets with no seal",
        "ordinary Harbor docket trays with no seal",
        "ordinary Harbor docket worksheets with no sticker",
        "ordinary Harbor docket worksheets with no seal after midnight",
    ],
)
async def test_numbered_topic_must_be_wholly_source_declared(
    procedure_client, monkeypatch, topic
):
    question = "Give the complete ordered method for " + topic + "."
    client, _, _, payload, _ = await prepare(
        procedure_client, monkeypatch, text=LONG, question=question
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None


@pytest.mark.parametrize(
    "topic",
    [
        "ordinary Harbor docket worksheets with no seal",
        "ordinary Harbor docket worksheet with no seal",
        "ordinary Harbor docket with no seal",
        "ordinary Harbor docket worksheet bearing no seal",
    ],
)
async def test_source_worksheet_class_and_full_condition_remain_supported(
    procedure_client, monkeypatch, topic
):
    question = "Give the complete ordered method for " + topic + "."
    client, _, _, payload, calls = await prepare(
        procedure_client, monkeypatch, text=LONG, question=question
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    proof = result["provenance"]["answer_selection"]["requirements"][0][
        "procedure_completeness"
    ]
    assert any(
        u["kind"] == "bound_condition" and u["verification_method"] == "nli_entailment"
        for u in proof["proof_units"]
    )
    assert len(calls) >= 3


@pytest.mark.parametrize("topic", ["Larch transfer", "ordinary Larch transfers"])
async def test_standard_heading_only_uses_literal_namespace_or_full_applicability(
    procedure_client, monkeypatch, topic
):
    from tests.test_composite_procedures import BODY

    question = "Give the complete ordered method for " + topic + "."
    client, _, _, payload, _ = await prepare(
        procedure_client, monkeypatch, text=BODY, question=question
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result


async def role_result(procedure_client, monkeypatch, text, *, mixed=False):
    from app.services import connected_query

    question = (
        QUESTION + " " if mixed else ""
    ) + "Who leads ordinary Larch review sessions?"
    client, db, document, payload, _ = await prepare(
        procedure_client, monkeypatch, text=text, question=question
    )
    config = connected_query.settings.model_copy(
        update={"ROLE_SCOPE_POLICY": "ordinary_session_activity_v1"}
    )
    monkeypatch.setattr(connected_query, "settings", config)
    monkeypatch.setattr("app.api.queries.settings", config)
    fact = "The records clerk leads Larch review."
    other, _ = await seed_procedure(db, body=fact, pieces=[fact])
    payload["document_ids"] = [str(document.id), str(other.id)]
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    "clause",
    [
        "Record the card, the green tag presides over ordinary runs.",
        "Record the card, select dana for the ordinary run.",
        "Record the card, with the red badge acting instead.",
        "Record the card, when the red badge acts instead.",
        "Record the card, the green tag is the person-role for ordinary runs.",
    ],
)
async def test_each_comma_clause_must_have_a_complete_non_role_classification(
    procedure_client, monkeypatch, clause
):
    text = closed_role_free_body().replace(PARAGRAPHS[1], clause)
    result = await role_result(procedure_client, monkeypatch, text, mixed=True)
    inspection = result["provenance"]["answer_selection"]["requirements"][1][
        "role_scope_inspection"
    ]
    assert inspection["complete"] is False
    assert result["outcome"] == "refused"


@pytest.mark.parametrize(
    "tail",
    [
        "The yellow tag presides over ordinary runs.",
        "Select dana for the ordinary run.",
        "For ordinary runs, the red tag acts instead.",
        "The person-role for an ordinary run is dana.",
    ],
)
async def test_colon_discovery_does_not_consume_unknown_governing_sentences(
    procedure_client, monkeypatch, tail
):
    result = await role_result(
        procedure_client,
        monkeypatch,
        "Larch review: check the card and record the count. " + tail,
    )
    inspection = result["provenance"]["answer_selection"]["requirements"][0][
        "role_scope_inspection"
    ]
    assert inspection["complete"] is False
    assert result["outcome"] == "refused"


@pytest.mark.parametrize(
    "text",
    [
        "Larch review: check the card and record the count.",
        "Larch review: copy the label, count the cards, and close the tray.",
    ],
)
async def test_whole_closed_physical_colon_control_remains_irrelevant_to_roles(
    procedure_client, monkeypatch, text
):
    result = await role_result(procedure_client, monkeypatch, text)
    assert result["outcome"] == "completed", result
    assert "records clerk" in result["answer"] and "Activity scope:" in result["answer"]


@pytest.mark.parametrize("damage", ["answer", "negative_nli"])
async def test_recent_memory_uses_verified_saved_v3_presentation(
    procedure_client, monkeypatch, damage
):
    client, db, _, payload, _ = await prepare(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    row = await db.get(Query, uuid.UUID(result["id"]))
    if damage == "answer":
        row.answer += "\nUNTRUSTED_ACTOR_CONTEXT"
    else:
        provenance = deepcopy(row.provenance)
        provenance["answer_selection"]["requirements"][0]["procedure_completeness"][
            "proof_units"
        ][0].update(label="neutral", supported=False)
        row.provenance = provenance
    await db.commit()
    original = (row.answer, deepcopy(row.provenance))
    next_row = Query(
        id=uuid.uuid4(), question="Continue", conversation_id=row.conversation_id
    )
    request = QueryRequest(
        question="Continue", conversation_id=row.conversation_id, memory_policy="recent"
    )
    messages = await scoped_memory(db, next_row, request, PRINCIPAL)
    assert messages == []
    assert (row.answer, row.provenance) == original


@pytest.mark.parametrize("damage", ["corrupt", "revoked"])
async def test_recent_memory_keeps_valid_legacy_and_refusal_pairs(
    procedure_client, monkeypatch, damage
):
    client, db, document, payload, _ = await prepare(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    row = await db.get(Query, uuid.UUID(result["id"]))
    legacy = Query(
        question="Legacy user question",
        answer="Legacy supported text",
        outcome="completed",
        owner_id="writer",
        workspace_id="ops-a",
        conversation_id=row.conversation_id,
        sources=[],
        created_at=row.created_at + timedelta(seconds=1),
    )
    refusal = Query(
        question="Unsupported user question",
        answer=None,
        outcome="refused",
        refused=True,
        refusal_reason="No supporting evidence",
        owner_id="writer",
        workspace_id="ops-a",
        conversation_id=row.conversation_id,
        sources=[],
        created_at=row.created_at + timedelta(seconds=2),
    )
    db.add_all([legacy, refusal])
    await db.commit()
    assert legacy.created_at < refusal.created_at
    next_row = Query(
        id=uuid.uuid4(), question="Continue", conversation_id=row.conversation_id
    )
    request = QueryRequest(
        question="Continue",
        conversation_id=row.conversation_id,
        memory_policy="recent",
        memory_max_tokens=2000,
    )
    before = await scoped_memory(db, next_row, request, PRINCIPAL)
    assert any(m["content"] == result["answer"] for m in before)
    if damage == "corrupt":
        row.answer += " UNVERIFIED_CONTEXT"
    else:
        document.owner_id = "someone-else"
    await db.commit()
    after = await scoped_memory(db, next_row, request, PRINCIPAL)
    assert [m["content"] for m in after] == [
        legacy.question,
        legacy.answer,
        refusal.question,
        refusal.refusal_reason,
    ]


@pytest.mark.parametrize(
    "clause",
    [
        "Copy the signed card, compare the counts, and close the tray.",
        "Place one token in the tray, with the checked rim facing the slot.",
    ],
)
async def test_complete_physical_commands_and_spatial_adjuncts_remain_classified(
    procedure_client, monkeypatch, clause
):
    text = closed_role_free_body().replace(PARAGRAPHS[1], clause)
    result = await role_result(procedure_client, monkeypatch, text, mixed=True)
    assert result["outcome"] == "completed", result
    assert clause in result["answer"]


@pytest.mark.parametrize("placement", ["prefix", "suffix"])
async def test_saved_numbered_scope_cannot_be_coherently_regrafted(
    procedure_client, monkeypatch, placement
):
    client, db, _, payload, _ = await prepare(
        procedure_client, monkeypatch, text=LONG, question=NUMBERED
    )
    result = (await client.post("/api/queries", json=payload)).json()
    row = await db.get(Query, uuid.UUID(result["id"]))
    changed = NUMBERED.replace(
        "Harbor docket worksheets",
        "opaque Harbor docket worksheets"
        if placement == "prefix"
        else "Harbor docket worksheets opaque",
    )
    requirement = plan_requirements(changed)[0]
    provenance = deepcopy(row.provenance)
    record = provenance["answer_selection"]["requirements"][0]
    record.update(
        original_text=changed,
        input_range={"start": requirement.input_start, "end": requirement.input_end},
    )
    proof = record["procedure_completeness"]
    proof["request_binding"].update(
        question=changed,
        original_text=changed,
        input_range=record["input_range"],
        topic=requirement.topic,
    )
    for units in (proof["proof_units"], proof["required_inventory"]["units"]):
        next(u for u in units if u["name"] == "requested_scope")["hypothesis"] = (
            f"The complete procedure is for {requirement.topic}."
        )
    proof["output_certificate"]["request_binding"] = deepcopy(proof["request_binding"])
    proof["output_certificate"]["required_inventory"] = deepcopy(
        proof["required_inventory"]
    )
    row.question, row.provenance = changed, provenance
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["answer"] is None and saved["evidence_access"] == "unknown"
    assert row.answer == result["answer"] and row.provenance == provenance
