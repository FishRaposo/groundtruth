"""P148: retain governing clauses and reject contradictory immutable lineage."""

import uuid
from copy import deepcopy
from dataclasses import asdict

import pytest
from app.config import Settings
from app.models.query import Query, QueryRequest
from app.services.requirement_answers import select_requirement_answer
from app.services.requirement_contract import validate_discovery_lineage
from sqlalchemy.orm.attributes import flag_modified

from tests.test_activity_scope_policy import role_models
from tests.test_composite_public_lineage import pattern_answer
from tests.test_connected_contract import upload
from tests.test_procedure_extent import (
    CONTROL,
    PRINCIPAL,
    QUESTION,
    external_boundaries,
    seed_procedure,
)
from tests.test_role_scope_classification import classify

pytest_plugins = ["tests.test_connected_contract", "tests.test_procedure_http"]


# Defect: one recognized role predicate consumes a sentence containing unknown prose.
@pytest.mark.parametrize(
    "tail",
    [
        ", a separate session appointment is required.",
        ", with a separate session appointment required.",
        ", pending a separate appointment for each session.",
        " and a separate session appointment is pending.",
        ", which needs a separate session appointment.",
        " whose session appointment remains pending.",
        ", consult the appointment appendix.",
        ", Meridian review lasts 12 minutes, a separate appointment is pending.",
    ],
)
def test_every_unparsed_governing_tail_remains_unresolved(tail):
    result = classify("The record steward leads Meridian review" + tail)
    assert result["complete"] is False, result
    assert any(
        u["disposition"] == "unresolved" for c in result["contexts"] for u in c["units"]
    )


@pytest.mark.parametrize("separator", [", ", " and ", "; ", ". "])
async def test_public_governing_tail_refuses_without_answer_or_history_certificate(
    real_client, monkeypatch, separator
):
    client, _, _ = real_client
    document = await upload(
        client,
        "The record steward leads Meridian review"
        + separator
        + "a separate session appointment is pending.",
    )
    role_models(monkeypatch)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads ordinary Meridian review sessions?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is True and body["answer"] is None, body
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    assert saved["refused"] is True and saved["answer"] is None


@pytest.mark.parametrize(
    "body",
    [
        "The record steward leads Meridian review, Meridian review lasts 12 minutes.",
        "The record steward leads Meridian review "
        "and Meridian review lasts 12 minutes.",
        "For Meridian review sessions, the lead is the duty supervisor.",
        "For ordinary Meridian review sessions, the lead is the duty supervisor.",
        "The shift clerk is the deputy for Meridian review.",
    ],
)
def test_complete_role_and_separate_typed_attribute_controls_remain_classified(body):
    assert classify(body)["complete"] is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("chunk_id", "00000000-0000-0000-0000-000000000001"),
        ("document_id", "00000000-0000-0000-0000-000000000002"),
        ("document_version", 999),
        ("content_hash", "b" * 64),
    ],
)
async def test_saved_witness_cannot_contradict_proposal_identity(
    real_client, monkeypatch, field, value
):
    client, factory, _ = real_client
    body, _ = await pattern_answer(real_client, monkeypatch)
    async with factory() as db:
        row = await db.get(Query, uuid.UUID(body["id"]))
        provenance = deepcopy(row.provenance)
        provenance["answer_selection"]["requirements"][0]["witnesses"][0][field] = value
        row.provenance = provenance
        flag_modified(row, "provenance")
        await db.commit()
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    assert saved["evidence_access"] == "restricted", saved
    assert saved["answer"] is None and saved["provenance"] is None


async def procedure_selection(connected_db, monkeypatch):
    db, _ = connected_db
    split = CONTROL.index("2.")
    document, chunks = await seed_procedure(
        db, CONTROL, [CONTROL[: split + 10], CONTROL[split:]]
    )
    external_boundaries(monkeypatch)

    async def current(chunk):
        return True

    result = await select_requirement_answer(
        db,
        QueryRequest(question=QUESTION, document_ids=[document.id]),
        PRINCIPAL,
        chunks,
        Settings(
            ANSWER_SELECTION_MODE="reader",
            ANSWER_SUPPORT_MODE="local_nli",
            ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1",
        ),
        validate_current=current,
    )
    assert result.reason is None, result.requirements
    return asdict(result)


async def test_multichunk_qa_pattern_carriers_keep_valid_lineage(
    connected_db, monkeypatch
):
    selection = await procedure_selection(connected_db, monkeypatch)
    witness = selection["requirements"][0]["witnesses"][0]
    assert len(witness["procedure_completeness"]["fragments"]) == 2
    assert {p["origin"] for p in witness["proposals"]} == {
        "qa_reader",
        "source_pattern",
    }
    assert validate_discovery_lineage(selection)["valid"] is True


# Defect: proof document identity and fragment membership may disagree with the carrier.
@pytest.mark.parametrize(
    "mutation", ["proof_document", "proof_version", "proof_hash", "unknown_fragment"]
)
async def test_procedure_proof_identity_and_fragments_match_original_sources(
    connected_db, monkeypatch, mutation
):
    selection = await procedure_selection(connected_db, monkeypatch)
    proof = selection["requirements"][0]["procedure_completeness"]
    if mutation == "unknown_fragment":
        proof["fragments"][-1]["chunk_id"] = str(uuid.uuid4())
    else:
        field = {
            "proof_document": "document_id",
            "proof_version": "document_version",
            "proof_hash": "content_hash",
        }[mutation]
        proof[field] = (
            999
            if field == "document_version"
            else str(uuid.uuid4())
            if field == "document_id"
            else "b" * 64
        )
    assert validate_discovery_lineage(selection)["valid"] is False


async def test_distinct_real_seed_carriers_keep_their_own_immutable_mapping(
    connected_db, monkeypatch
):
    db, _ = connected_db
    # Both original chunks contain the first raw clause; the second supplies the
    # terminal cover. They are different real carriers, not invented chunk IDs.
    first = CONTROL.index("1.")
    split = CONTROL.index("2.")
    document, chunks = await seed_procedure(
        db, CONTROL, [CONTROL[: split + 10], CONTROL[first:]]
    )
    external_boundaries(monkeypatch)

    async def current(chunk):
        return True

    selection = asdict(
        await select_requirement_answer(
            db,
            QueryRequest(question=QUESTION, document_ids=[document.id]),
            PRINCIPAL,
            chunks,
            Settings(
                ANSWER_SELECTION_MODE="reader",
                ANSWER_SUPPORT_MODE="local_nli",
                ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1",
            ),
            validate_current=current,
        )
    )
    assert selection["reason"] is None, selection["requirements"]
    witness = selection["requirements"][0]["witnesses"][0]
    assert len({p["chunk_id"] for p in witness["proposals"]}) == 2
    assert validate_discovery_lineage(selection)["valid"] is True


@pytest.mark.parametrize(
    "field,value",
    [("document_version", True), ("document_id", None), ("content_hash", None)],
)
async def test_witness_identity_cannot_use_missing_or_wrong_typed_fields(
    real_client, monkeypatch, field, value
):
    client, factory, _ = real_client
    body, _ = await pattern_answer(real_client, monkeypatch)
    async with factory() as db:
        row = await db.get(Query, uuid.UUID(body["id"]))
        provenance = deepcopy(row.provenance)
        provenance["answer_selection"]["requirements"][0]["witnesses"][0][field] = value
        row.provenance = provenance
        flag_modified(row, "provenance")
        await db.commit()
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    assert saved["evidence_access"] == "restricted", saved
    assert saved["answer"] is None


@pytest.mark.parametrize(
    "role,value", [("lead", "duty supervisor"), ("deputy", "session witness")]
)
async def test_explicit_session_role_still_precedes_activity_with_typed_context(
    real_client, monkeypatch, role, value
):
    client, _, _ = real_client
    activity = (
        "The record steward leads Meridian review."
        if role == "lead"
        else "The shift clerk is the deputy for Meridian review."
    )
    direct = (
        f"The {value} leads Meridian review sessions."
        if role == "lead"
        else f"The {value} is the deputy for Meridian review sessions."
    )
    documents = [
        await upload(client, text)
        for text in [
            activity,
            direct,
            "For emergency Meridian review sessions, the duration is 12 minutes.",
        ]
    ]
    role_models(monkeypatch)
    question = (
        "Who leads ordinary Meridian review sessions?"
        if role == "lead"
        else "Who is the deputy for ordinary Meridian review sessions?"
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": question,
            "document_ids": [d["id"] for d in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False, body
    assert value in body["answer"]
    assert (
        body["provenance"]["answer_selection"]["requirements"][0][
            "role_scope_interpretation"
        ]["effective_scope"]
        == "session"
    )


async def test_public_multichunk_multi_origin_history_stays_available(
    procedure_client, monkeypatch
):
    from app.services import connected_query

    client, db = procedure_client
    monkeypatch.setattr(
        connected_query,
        "settings",
        connected_query.settings.model_copy(
            update={"ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1"}, deep=True
        ),
    )
    first, split = CONTROL.index("1."), CONTROL.index("2.")
    document, _ = await seed_procedure(
        db, CONTROL, [CONTROL[: split + 10], CONTROL[first:]]
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": QUESTION,
            "document_ids": [str(document.id)],
            "retrieval_method": "keyword",
            "top_k": 2,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "completed", body
    assert len(body["sources"]) == 2
    witness = body["provenance"]["answer_selection"]["requirements"][0]["witnesses"][0]
    assert {p["origin"] for p in witness["proposals"]} == {
        "qa_reader",
        "source_pattern",
    }
    assert len({p["chunk_id"] for p in witness["proposals"]}) == 2
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    assert saved["evidence_access"] == "available", saved
    assert saved["answer"] == body["answer"]


async def test_procedural_witness_cannot_replace_its_projected_fragment_with_raw_only(
    connected_db, monkeypatch
):
    selection = await procedure_selection(connected_db, monkeypatch)
    witness = selection["requirements"][0]["witnesses"][0]
    raw = witness["proposals"][0]
    # Preserve raw coordinates/text consistency while contradicting the full
    # immutable fragment the witness claims to carry for the complete method.
    witness["span"] = {**raw["chunk_range"], "text": raw["text"]}
    witness["document_range"] = raw["document_range"]
    assert validate_discovery_lineage(selection)["valid"] is False


@pytest.mark.parametrize(
    "relative",
    [
        "that needs a separate appointment",
        "while a separate appointment remains pending",
    ],
)
def test_copular_role_value_cannot_absorb_unparsed_relative_or_subordinate_clause(
    relative,
):
    result = classify(
        f"For Meridian review, the lead is the record steward {relative}."
    )
    assert result["complete"] is False, result
