"""A confident external model cannot substitute a different or partial fact."""

import uuid
from types import SimpleNamespace

import pytest
from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.answer_reader import (
    ReaderSelection,
    passage_span,
    reader_service,
)
from app.services.answer_support import SupportAssessment, support_service
from sqlalchemy import select

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


def external_models(monkeypatch, value_for_context):
    """Deliberately permissive QA/NLI doubles leave our evidence gates real."""
    config = get_settings().model_copy(
        deep=True,
        update={"ANSWER_SELECTION_MODE": "reader", "ANSWER_SUPPORT_MODE": "local_nli"},
    )
    monkeypatch.setattr("app.services.connected_query.settings", config)

    def prediction(question, context, settings):
        value = value_for_context(question, context)
        if value is None:
            return ReaderSelection(None, {"decision": "no_answer", "null_margin": 10.0})
        start = context.index(value)
        raw = {"start": start, "end": start + len(value), "text": value}
        return ReaderSelection(
            passage_span(context, start, start + len(value)),
            {
                "decision": "answer",
                "null_margin": -9.0,
                "raw_span": raw,
                "raw_candidates": [{**raw, "null_margin": -9.0, "score": 9.0}],
            },
        )

    monkeypatch.setattr(reader_service, "_load", lambda config: None)
    monkeypatch.setattr(reader_service, "_context", prediction)

    async def always_entails(pairs, config=None):
        return [
            SupportAssessment("entailment", (-5.0, 5.0, -5.0), 10.0, True)
            for _ in pairs
        ]

    monkeypatch.setattr(support_service, "assess", always_entails)


async def test_duration_cannot_answer_participant_count_even_if_models_accept(
    real_client, monkeypatch
):
    client, _, _ = real_client
    document = await upload(client, "The Meridian review lasts 12 minutes.")
    external_models(monkeypatch, lambda question, context: "12 minutes")
    response = await client.post(
        "/api/queries",
        json={
            "question": "What is the maximum participant count for Meridian review?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is True
    assert response.json()["answer"] is None


async def test_three_requested_facts_cannot_succeed_with_owner_and_start_only(
    real_client, monkeypatch
):
    client, _, _ = real_client
    documents = [
        await upload(client, text)
        for text in [
            "The record steward leads Meridian review.",
            "The Meridian review session starts at 09:20.",
        ]
    ]
    external_models(
        monkeypatch,
        lambda question, context: (
            "record steward" if "record steward" in context else "09:20"
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": (
                "Who leads Meridian review, and what are its session "
                "start time and duration?"
            ),
            "document_ids": [d["id"] for d in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is True
    assert response.json()["answer"] is None


async def test_owner_and_distinct_deputy_need_both_actual_facts(
    real_client, monkeypatch
):
    client, _, _ = real_client
    documents = [
        await upload(client, text)
        for text in [
            "The record steward leads Meridian review.",
            "The Meridian deputy is the witness clerk, not the record steward.",
        ]
    ]
    external_models(
        monkeypatch,
        lambda question, context: (
            "record steward" if "leads" in context else "witness clerk"
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review, and who is its deputy?",
            "document_ids": [d["id"] for d in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    assert "record steward" in body["answer"] and "witness clerk" in body["answer"]
    assert {s["document_id"] for s in body["sources"]} == {d["id"] for d in documents}


async def test_unrelated_conditional_conflict_cannot_veto_standard_owner(
    real_client, monkeypatch
):
    client, factory, _ = real_client
    documents = [
        await upload(client, text)
        for text in [
            "The record steward leads the standard Meridian review.",
            "For the Meridian exception retest, begin by showing the red marker.",
            "For the Meridian exception retest, begin by showing the blue marker.",
        ]
    ]
    conflict_ids = {uuid.UUID(d["id"]) for d in documents[1:]}
    async with factory() as db:
        for identifier in conflict_ids:
            row = await db.get(Document, identifier)
            row.metadata_ = {
                **(row.metadata_ or {}),
                "conflict_group": "meridian-retest",
            }
        for chunk in (
            await db.scalars(select(Chunk).where(Chunk.document_id.in_(conflict_ids)))
        ).all():
            chunk.metadata_ = {
                **(chunk.metadata_ or {}),
                "conflict_group": "meridian-retest",
            }
        await db.commit()
    external_models(
        monkeypatch,
        lambda question, context: (
            "record steward"
            if "record steward" in context
            else "red marker"
            if "red marker" in context
            else "blue marker"
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads the standard Meridian review?",
            "document_ids": [d["id"] for d in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    assert "record steward" in body["answer"]
    assert {s["document_id"] for s in body["sources"]} == {documents[0]["id"]}


async def test_saved_requirement_evidence_keeps_original_question_range(
    real_client, monkeypatch
):
    client, _, _ = real_client
    document = await upload(client, "The record steward leads Meridian review.")
    external_models(monkeypatch, lambda question, context: "record steward")
    question = "Who leads Meridian review?"
    response = await client.post(
        "/api/queries",
        json={
            "question": question,
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    requirements = body["provenance"]["answer_selection"].get("requirements", [])
    assert len(requirements) == 1
    selected = requirements[0]
    interval = selected["input_range"]
    assert question[interval["start"] : interval["end"]] == selected["original_text"]
    assert selected["status"] == "supported"
    saved = await client.get("/api/queries/" + body["id"])
    assert saved.status_code == 200
    assert (
        saved.json()["provenance"]["answer_selection"]["requirements"] == requirements
    )


async def mark_conflicting(factory, identifiers):
    ids = {uuid.UUID(identifier) for identifier in identifiers}
    async with factory() as db:
        for identifier in ids:
            document = await db.get(Document, identifier)
            document.metadata_ = {
                **(document.metadata_ or {}),
                "conflict_group": "meridian-leader",
            }
        await db.commit()


async def test_opposing_curated_source_outside_initial_top_one_is_inspected(
    real_client, monkeypatch
):
    client, factory, _ = real_client
    documents = [
        await upload(client, text)
        for text in [
            "The record steward leads Meridian review.",
            "The witness clerk leads Meridian review.",
        ]
    ]
    await mark_conflicting(factory, [d["id"] for d in documents])
    external_models(
        monkeypatch,
        lambda question, context: (
            "record steward" if "record steward" in context else "witness clerk"
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review?",
            "top_k": 1,
            "document_ids": [d["id"] for d in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is True
    assert len(body["retrieval_trace"]["scores"]) == 1
    inspected = body["provenance"]["answer_selection"]["inspected_sources"]
    assert {item["document_id"] for item in inspected} == {d["id"] for d in documents}


async def test_additional_conflict_evidence_is_reauthorized_after_revocation(
    real_client, monkeypatch
):
    client, factory, keys = real_client
    documents = [
        await upload(client, text)
        for text in [
            "The record steward leads Meridian review.",
            "The witness clerk leads Meridian review.",
        ]
    ]
    await mark_conflicting(factory, [d["id"] for d in documents])
    external_models(
        monkeypatch,
        lambda question, context: (
            "record steward" if "record steward" in context else "witness clerk"
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review?",
            "top_k": 1,
            "document_ids": [d["id"] for d in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    initial = {row["document_id"] for row in body["retrieval_trace"]["scores"]}
    additional = next(d["id"] for d in documents if d["id"] not in initial)
    async with factory() as db:
        document = await db.get(Document, uuid.UUID(additional))
        document.owner_id = keys["reader"]
        await db.commit()
    history = await client.get("/api/queries/" + body["id"])
    assert history.status_code == 200
    assert history.json()["evidence_access"] == "restricted"
    assert history.json()["provenance"] is None


async def test_dependent_hours_followup_preserves_scope_and_initial_metrics(
    real_client, monkeypatch
):
    client, _, _ = real_client
    documents = [
        await upload(client, text)
        for text in [
            "The record steward leads Meridian review.",
            "The record steward is present from 09:00 to 17:00.",
        ]
    ]
    await upload(client, "The record steward is present from 01:00 to 03:00.")

    def candidate(question, context):
        if "hours" in question.lower():
            return "09:00 to 17:00" if "09:00 to 17:00" in context else None
        return "record steward" if "leads" in context else None

    external_models(monkeypatch, candidate)
    response = await client.post(
        "/api/queries",
        json={
            "question": (
                "Who leads Meridian review, and during which hours "
                "is that role present?"
            ),
            "top_k": 1,
            "document_ids": [d["id"] for d in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    assert "record steward" in body["answer"] and "09:00 to 17:00" in body["answer"]
    assert {s["document_id"] for s in body["sources"]} == {d["id"] for d in documents}
    assert len(body["retrieval_trace"]["scores"]) == 1
    followups = body["provenance"]["answer_selection"]["followup_retrieval"]
    assert followups and followups[0]["method"] == "keyword"
    assert all(
        {x["document_id"] for x in row["sources"]} <= {d["id"] for d in documents}
        for row in followups
    )


async def test_curated_group_needs_an_authorized_applicable_opponent(
    real_client, monkeypatch
):
    client, factory, _ = real_client
    documents = [
        await upload(client, text)
        for text in [
            "The record steward leads the standard Meridian review.",
            "For the Meridian exception review, the witness clerk leads the review.",
        ]
    ]
    await mark_conflicting(factory, [d["id"] for d in documents])
    external_models(
        monkeypatch,
        lambda question, context: (
            "record steward" if "record steward" in context else None
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads the standard Meridian review?",
            "retrieval_method": "keyword",
            "document_ids": [d["id"] for d in documents],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is False


async def test_filtered_curated_opponent_cannot_change_selected_document_answer(
    real_client, monkeypatch
):
    client, factory, _ = real_client
    documents = [
        await upload(client, text)
        for text in [
            "The record steward leads Meridian review.",
            "The witness clerk leads Meridian review.",
        ]
    ]
    await mark_conflicting(factory, [d["id"] for d in documents])
    external_models(monkeypatch, lambda question, context: "record steward")
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review?",
            "retrieval_method": "keyword",
            "document_ids": [documents[0]["id"]],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    assert {
        row["document_id"]
        for row in body["provenance"]["answer_selection"]["inspected_sources"]
    } == {documents[0]["id"]}


async def test_missing_selected_support_assets_cannot_be_a_successful_refusal(
    real_client, monkeypatch
):
    client, _, _ = real_client
    config = get_settings().model_copy(
        deep=True,
        update={
            "ANSWER_SELECTION_MODE": "reader",
            "ANSWER_SUPPORT_MODE": "local_nli",
            "SUPPORT_MODEL_PATH": "",
        },
    )
    monkeypatch.setattr("app.services.connected_query.settings", config)
    monkeypatch.setattr(reader_service, "_load", lambda config: None)
    response = await client.post(
        "/api/queries",
        json={
            "question": "What is the unrecorded review duration?",
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 503, response.text
    history = await client.get("/api/queries")
    rows = history.json()["queries"]
    detail = (await client.get("/api/queries/" + rows[0]["id"])).json()
    assert detail["outcome"] == "error"
    assert detail["refused"] is False
    assert detail["answer"] is None
    assert (
        detail["provenance"]["answer_selection"]["evidence_support"]["mode"]
        == "local_nli"
    )


async def test_answer_copies_only_the_validated_source_clause(real_client, monkeypatch):
    client, _, _ = real_client
    content = (
        "The record steward leads Meridian review. "
        "The office snack budget is 99 credits."
    )
    document = await upload(client, content)
    external_models(monkeypatch, lambda question, context: "record steward")
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    assert "record steward" in body["answer"]
    assert "99 credits" not in body["answer"]
    assert body["sources"][0]["quoted_text"] == content


async def test_two_validated_clauses_keep_separate_exact_spans(
    real_client, monkeypatch
):
    client, _, _ = real_client
    content = (
        "The record steward leads Meridian review. "
        "The office snack budget is 99 credits. "
        "Meridian review lasts 12 minutes."
    )
    document = await upload(client, content)
    external_models(
        monkeypatch,
        lambda question, context: (
            "12 minutes" if "long" in question else "record steward"
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review, and how long does it last?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False
    assert "record steward" in body["answer"] and "12 minutes" in body["answer"]
    assert "99 credits" not in body["answer"]
    source = body["sources"][0]
    assert len(source["answer_spans"]) == 2
    assert all(
        content[span["start"] : span["end"]] == span["text"]
        for span in source["answer_spans"]
    )


async def test_complete_cover_retains_four_cited_documents(real_client, monkeypatch):
    client, _, _ = real_client
    documents = [
        await upload(client, text)
        for text in [
            "The record steward leads Meridian review.",
            "Meridian review lasts 12 minutes.",
            "Meridian review starts on Thursdays.",
            "Meridian review has a maximum participant count of 4.",
        ]
    ]

    def candidate(question, context):
        rules = [
            ("Who", "record steward"),
            ("How long", "12 minutes"),
            ("On which day", "Thursdays"),
            ("count", "4"),
        ]
        return next(
            (
                value
                for framing, value in rules
                if framing in question and value in context
            ),
            None,
        )

    external_models(monkeypatch, candidate)
    response = await client.post(
        "/api/queries",
        json={
            "question": (
                "Who leads Meridian review, how long does it last, "
                "on which day does it start, and what is its "
                "maximum participant count?"
            ),
            "document_ids": [d["id"] for d in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False, body["refusal_reason"]
    assert len(body["sources"]) == 4
    assert {source["document_id"] for source in body["sources"]} == {
        d["id"] for d in documents
    }
    assert [source["citation_index"] for source in body["sources"]] == [1, 2, 3, 4]


async def test_adjacent_required_clauses_preserve_the_copied_sentence(
    real_client, monkeypatch
):
    client, _, _ = real_client
    content = (
        "The record steward leads Meridian review, "
        "and Meridian review lasts 12 minutes."
    )
    document = await upload(client, content)
    external_models(
        monkeypatch,
        lambda question, context: (
            "12 minutes" if "long" in question else "record steward"
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review, and how long does it last?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False, body["refusal_reason"]
    assert content in body["answer"]
    assert body["sources"][0]["answer_spans"][0]["text"] == content


@pytest.mark.parametrize("forged_premise", [False, True])
async def test_every_declared_condition_needs_real_source_support(
    real_client, monkeypatch, forged_premise
):
    client, _, _ = real_client
    content = (
        "For Linden intake, first deny permission to use the blue profile, "
        "then scan the pass, finally record approval."
    )
    document = await upload(client, content)
    external_models(monkeypatch, lambda question, context: "scan the pass")
    condition = "The instructions require using the blue profile."

    def bound(req, context, start, end):
        return SimpleNamespace(
            rejection=None,
            hypothesis="The recorded procedure belongs to Linden intake.",
            premise=context,
            value=context[start:end],
            start=start,
            end=end,
            support_start=0,
            support_end=len(context),
            checks=(
                SimpleNamespace(
                    name="profile",
                    premise="Use the blue profile." if forged_premise else context,
                    hypothesis=condition,
                ),
            ),
        )

    monkeypatch.setattr("app.services.requirement_answers.support_claim", bound)

    async def assess(pairs, config=None):
        return [
            SupportAssessment("contradiction", (5.0, -5.0, -5.0), -10.0, False)
            if pair.hypothesis == condition and not forged_premise
            else SupportAssessment("entailment", (-5.0, 5.0, -5.0), 10.0, True)
            for pair in pairs
        ]

    monkeypatch.setattr(support_service, "assess", assess)
    response = await client.post(
        "/api/queries",
        json={
            "question": (
                "Give the complete procedure for Linden intake with the blue profile."
            ),
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is True
    assert body["answer"] is None and body["sources"] == []
