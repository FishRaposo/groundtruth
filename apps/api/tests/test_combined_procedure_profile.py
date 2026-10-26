"""Actual ASGI/storage contracts; only QA and NLI model boundaries are doubles."""

import json
from copy import deepcopy

import pytest
from app.models.query import Query
from app.services.requirement_contract import procedure_completeness

from tests.test_declared_paragraph_procedure import PARAGRAPHS, QUESTION, body
from tests.test_procedure_extent import external_boundaries, seed_procedure
from tests.test_procedure_http import procedure_client as procedure_client

pytest_plugins = ["tests.test_connected_contract"]


async def export_extra(result, payload, db, name):
    import os
    from pathlib import Path

    from app.services.procedure_output import load_snapshots

    if directory := os.environ.get("COMBINED_EXTRA_FIXTURE_DIR"):
        Path(directory, name + ".json").write_text(
            json.dumps(
                {
                    "model_evidence_scope": (
                        "Actual ASGI/storage; QA/NLI boundary doubles, "
                        "no model-quality claim."
                    ),
                    "response": result,
                    "request": payload,
                    "source_snapshots": await load_snapshots(
                        db, result["provenance"]["answer_selection"]
                    ),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


async def prepare(
    procedure_client, monkeypatch, *, text=None, question=QUESTION, pieces=None
):
    from app.services import connected_query

    client, db = procedure_client
    config = connected_query.settings.model_copy(
        update={
            "ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1",
            "PROCEDURE_VERIFICATION_PROFILE": "source_declared_procedure_copy_v1",
        }
    )
    monkeypatch.setattr("app.services.connected_query.settings", config)
    monkeypatch.setattr("app.api.queries.settings", config)
    monkeypatch.setattr("app.middleware.rate_limit.settings", config)
    calls = external_boundaries(monkeypatch, qa_null=True)
    text = text or body()
    document, _ = await seed_procedure(db, body=text, pieces=pieces or [text])
    payload = {
        "question": question,
        "document_ids": [str(document.id)],
        "retrieval_method": "keyword",
        "top_k": 1,
    }
    return client, db, document, payload, calls


# Defect: profile dispatch still sends every imperative through NLI and emits v2.
async def test_combined_actual_http_methods_and_output_certificate(
    procedure_client, monkeypatch
):
    client, db, document, payload, calls = await prepare(procedure_client, monkeypatch)
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "completed", result
    selection = result["provenance"]["answer_selection"]
    proof = selection["requirements"][0]["procedure_completeness"]
    assert proof["contract"] == "complete-immutable-procedure-v3"
    assert len(calls) == 2
    assert {u["verification_method"] for u in proof["proof_units"]} == {
        "nli_entailment",
        "exact_source_structure",
        "exact_source_copy",
    }
    assert (
        sum(u["verification_method"] == "nli_entailment" for u in proof["proof_units"])
        == 2
    )
    for unit in proof["proof_units"]:
        if unit["verification_method"] != "nli_entailment":
            assert (
                not {"label", "logits", "entailment_margin", "pair_tokens"}
                & unit.keys()
            )
    assert proof["output_certificate"]["contract"] == "procedure-output-cover-v1"
    assert "\n\n".join(PARAGRAPHS) in result["answer"]
    assert selection["presentation_verification"]["status"] == "verified"
    assert procedure_completeness(selection) is False
    saved = (await client.get(f"/api/queries/{result['id']}")).json()
    assert saved["answer"] == result["answer"]
    stream = await client.post("/api/queries/stream", json=payload)
    events = [
        json.loads(line[6:])
        for line in stream.text.splitlines()
        if line.startswith("data: ")
    ]
    done = next(e for e in events if e["type"] == "done")
    assert done["answer"] == result["answer"]
    assert document.owner_id == "writer"
    import os
    from pathlib import Path

    from app.services.procedure_output import load_snapshots

    if output := os.environ.get("COMBINED_FIXTURE_OUTPUT"):
        Path(output).write_text(
            json.dumps(
                {
                    "model_evidence_scope": (
                        "Actual ASGI/storage response; QA/NLI external boundary "
                        "doubles only. No model-quality evidence."
                    ),
                    "response": result,
                    "request": payload,
                    "source_snapshots": await load_snapshots(db, selection),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


# Defect: valid source proof could bless edited history instead of actual output.
@pytest.mark.parametrize(
    "damage",
    [
        "answer",
        "citation",
        "inventory",
        "certificate",
        "source",
        "proof_contract",
        "lineage",
    ],
)
async def test_combined_corrupt_saved_answer_withheld_without_rewriting_record(
    procedure_client, monkeypatch, damage
):
    import uuid

    from app.models.document import DocumentVersion
    from sqlalchemy import select

    client, db, document, payload, _ = await prepare(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    row = await db.get(Query, uuid.UUID(result["id"]))
    if damage == "answer":
        row.answer = row.answer.replace(PARAGRAPHS[1], "Place two tokens in the tray.")
    elif damage == "citation":
        sources = deepcopy(row.sources)
        sources[0]["quoted_text"] += " fabricated"
        row.sources = sources
    elif damage == "source":
        version = await db.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
        version.normalized_content += " fabricated"
    else:
        provenance = deepcopy(row.provenance)
        proof = provenance["answer_selection"]["requirements"][0][
            "procedure_completeness"
        ]
        if damage == "lineage":
            proof["raw_seed"]["proposal_id"] = "fabricated"
        elif damage == "proof_contract":
            proof["contract"] = "complete-immutable-procedure-v999"
        elif damage == "inventory":
            proof["proof_units"].pop()
        else:
            proof["output_certificate"] = {
                "contract": "procedure-output-cover-v1",
                "valid": True,
            }
        row.provenance = provenance
    await db.commit()
    stored = (row.answer, deepcopy(row.sources), deepcopy(row.provenance))
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["answer"] is None and saved["sources"] == []
    assert saved["outcome"] == "completed"
    assert saved["evidence_access"] == "unknown"
    assert (
        saved["provenance"]["answer_selection"]["presentation_verification"]["status"]
        == "invalid"
    )
    assert (row.answer, row.sources, row.provenance) == stored


# Defect: complete exact copy could bypass negative NLI or unconsumed conditions.
async def test_combined_negative_nli_and_unknown_request_refuse(
    procedure_client, monkeypatch
):
    client, _, _, payload, _ = await prepare(procedure_client, monkeypatch)
    external_boundaries(monkeypatch, reject=lambda pair: True, qa_null=True)
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None
    external_boundaries(monkeypatch, qa_null=True)
    payload["question"] = (
        QUESTION.rstrip(".") + ", provided the hidden permit is approved."
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None


@pytest.mark.parametrize("multichunk", [False, True])
async def test_combined_numbered_multichunk_preserves_legacy_literal_output(
    procedure_client, monkeypatch, multichunk
):
    from tests.test_procedure_extent import LONG
    from tests.test_procedure_extent import QUESTION as NUMBERED_QUESTION

    client, db, _, payload, calls = await prepare(
        procedure_client,
        monkeypatch,
        text=LONG,
        question=NUMBERED_QUESTION,
        pieces=[LONG[:1292], LONG[1171:]] if multichunk else None,
    )
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "completed", result
    assert result["answer"] == "Source extracts (not model-generated):\n\n" + LONG[
        46:
    ] + (" [1] [2]" if multichunk else " [1]")
    proof = result["provenance"]["answer_selection"]["requirements"][0][
        "procedure_completeness"
    ]
    assert proof["contract"] == "complete-immutable-procedure-v3"
    assert len(calls) == 3  # Namespace, applicability, independent no-seal condition.
    import os
    from pathlib import Path

    from app.services.procedure_output import load_snapshots

    if (
        output := os.environ.get("COMBINED_NUMBERED_FIXTURE_OUTPUT")
    ) and not multichunk:
        Path(output).write_text(
            json.dumps(
                {
                    "model_evidence_scope": (
                        "Actual ASGI/storage response; QA/NLI external boundary "
                        "doubles only. No model-quality evidence."
                    ),
                    "response": result,
                    "request": payload,
                    "source_snapshots": await load_snapshots(
                        db, result["provenance"]["answer_selection"]
                    ),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


async def test_combined_two_procedures_remain_separate_complete_blocks(
    procedure_client, monkeypatch
):
    second_question = QUESTION.replace("Lumen token bench", "Marble token stand")
    question = QUESTION + " " + second_question
    client, db, first, payload, _ = await prepare(
        procedure_client, monkeypatch, question=question
    )
    text = (
        body()
        .replace("Lumen token bench", "Marble token stand")
        .replace("one token", "three tokens")
    )
    second, _ = await seed_procedure(db, body=text, pieces=[text])
    payload["document_ids"] = [str(first.id), str(second.id)]
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "completed", result
    assert len(result["sources"]) == 2
    selection = result["provenance"]["answer_selection"]
    assert len(selection["requirements"]) == 2
    await export_extra(result, payload, db, "fixture-multiple-v3")
    assert all(
        r["procedure_completeness"]["contract"] == "complete-immutable-procedure-v3"
        for r in selection["requirements"]
    )
    assert (
        "Place one token" in result["answer"]
        and "Place three tokens" in result["answer"]
    )
    assert (await client.get(f"/api/queries/{result['id']}")).json()[
        "answer"
    ] == result["answer"]


async def test_combined_actual_context_replay_and_unicode_mutations(
    procedure_client, monkeypatch
):
    import hashlib
    import uuid

    from app.services.procedure_output import load_snapshots

    text = body().replace("signed card", "signed café 📋 card")
    client, db, _, payload, _ = await prepare(procedure_client, monkeypatch, text=text)
    result = (await client.post("/api/queries", json=payload)).json()
    selection = result["provenance"]["answer_selection"]
    snapshots = await load_snapshots(db, selection)
    context = {
        "question": result["question"],
        "answer": result["answer"],
        "citations": result["sources"],
        "source_snapshots": snapshots,
    }
    assert procedure_completeness(selection, **context) is True
    await export_extra(result, payload, db, "fixture-unicode-v3")
    proof = selection["requirements"][0]["procedure_completeness"]
    interval = proof["output_certificate"]["answer_range"]
    assert result["answer"][interval["start"] : interval["end"]] == "\n\n".join(
        PARAGRAPHS
    ).replace("signed card", "signed café 📋 card")
    for changed in (
        result["answer"].replace(PARAGRAPHS[1], ""),
        result["answer"]
        .replace(PARAGRAPHS[1], PARAGRAPHS[2])
        .replace(
            PARAGRAPHS[2] + "\n\n" + PARAGRAPHS[2],
            PARAGRAPHS[2] + "\n\n" + PARAGRAPHS[1],
        ),
        result["answer"] + "\n\nInvented permission: destroy the card.",
    ):
        damaged = deepcopy(selection)
        damaged["requirements"][0]["procedure_completeness"]["output_certificate"][
            "answer_sha256"
        ] = hashlib.sha256(changed.encode()).hexdigest()
        assert (
            procedure_completeness(damaged, **{**context, "answer": changed}) is False
        )
    assert (
        procedure_completeness(
            selection, **{**context, "question": QUESTION + " Ignore the prohibition."}
        )
        is False
    )
    row = await db.get(Query, uuid.UUID(result["id"]))
    assert row.outcome == "completed"


async def test_combined_revocation_and_cancelled_stream_remain_distinct(
    procedure_client, monkeypatch
):
    from app.api.queries import stream_query
    from app.models.query import QueryRequest
    from sqlalchemy import select

    from tests.test_procedure_extent import PRINCIPAL

    client, db, document, payload, _ = await prepare(procedure_client, monkeypatch)
    completed = (await client.post("/api/queries", json=payload)).json()
    stream = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    first = await anext(stream.body_iterator)
    assert '"type": "token"' in first
    await stream.body_iterator.aclose()
    rows = list((await db.scalars(select(Query))).all())
    assert sorted(r.outcome for r in rows) == ["completed", "interrupted"]
    assert next(r for r in rows if r.outcome == "interrupted").answer is None
    document.owner_id = "someone-else"
    await db.commit()
    saved = (await client.get(f"/api/queries/{completed['id']}")).json()
    assert saved["evidence_access"] == "restricted" and saved["provenance"] is None


# Defect: v3 replay SELECT must not autoflush prepared output across a yield.
async def test_combined_prepared_output_not_visible_to_concurrent_storage_reader(
    procedure_client, monkeypatch
):
    from app.api.queries import stream_query
    from app.models.query import QueryRequest
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from tests.test_procedure_extent import PRINCIPAL

    _, db, _, payload, _ = await prepare(procedure_client, monkeypatch)
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    assert '"type": "token"' in await anext(response.body_iterator)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    async with factory() as external:
        row = await external.scalar(select(Query))
        assert row.outcome == "processing"
        assert row.answer is None and row.sources == []
    await response.body_iterator.aclose()


async def test_combined_invalid_prepared_output_is_error_not_success(
    procedure_client, monkeypatch
):
    from app.api.queries import stream_query
    from app.models.query import QueryRequest
    from sqlalchemy import select

    from tests.test_procedure_extent import PRINCIPAL

    _, db, _, payload, _ = await prepare(procedure_client, monkeypatch)
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    assert '"type": "token"' in await anext(response.body_iterator)
    with db.no_autoflush:
        row = await db.scalar(select(Query))
    row.answer += "\nUnverified instruction."
    remaining = "".join([part async for part in response.body_iterator])
    assert '"type": "error"' in remaining and '"type": "done"' not in remaining
    assert row.outcome == "error" and row.answer is None and row.sources == []


@pytest.mark.parametrize("change", ["unknown_tail", "external_dependency", "mode"])
async def test_combined_unresolved_source_and_wrong_mode_refuse(
    procedure_client, monkeypatch, change
):
    text = body()
    question = QUESTION
    if change == "unknown_tail":
        text += "\n\nClose the separate gate before completion."
    elif change == "external_dependency":
        text = text.replace(
            PARAGRAPHS[1], "Follow the mandatory inspection procedure in Appendix R."
        )
    else:
        question = question.replace("ordinary procedure", "standard procedure")
    client, _, _, payload, _ = await prepare(
        procedure_client, monkeypatch, text=text, question=question
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None


async def test_combined_unavailable_model_is_error_and_saved_history_needs_no_model(
    procedure_client, monkeypatch
):
    import uuid

    from app.services.answer_support import SupportUnavailableError, support_service
    from sqlalchemy import select

    client, db, _, payload, _ = await prepare(procedure_client, monkeypatch)
    completed = (await client.post("/api/queries", json=payload)).json()

    async def unavailable(*args, **kwargs):
        raise SupportUnavailableError("Invented unavailable configured asset")

    monkeypatch.setattr(support_service, "assess", unavailable)
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 503
    rows = list((await db.scalars(select(Query))).all())
    assert sorted(row.outcome for row in rows) == ["completed", "error"]
    saved = (await client.get(f"/api/queries/{completed['id']}")).json()
    assert saved["answer"] == completed["answer"]
    assert (await db.get(Query, uuid.UUID(completed["id"]))).outcome == "completed"


async def test_combined_profile_preserves_independent_fact_only_queries(
    procedure_client, monkeypatch
):
    client, _, _, payload, calls = await prepare(
        procedure_client,
        monkeypatch,
        text="The records clerk leads Larch review.",
        question="Who leads Larch review?",
    )
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "completed" and "records clerk" in result["answer"]
    assert calls
    assert (await client.get(f"/api/queries/{result['id']}")).json()[
        "answer"
    ] == result["answer"]


async def test_combined_standard_heading_and_undeclared_narrative(
    procedure_client, monkeypatch
):
    from tests.test_composite_procedures import BODY
    from tests.test_composite_procedures import QUESTION as STANDARD_QUESTION

    client, _, _, payload, _ = await prepare(
        procedure_client, monkeypatch, text=BODY, question=STANDARD_QUESTION
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    payload["question"] = "Give the full procedure for the Lumen token bench."
    narrative = (
        "Lumen token bench: fold the fabric, stitch the seam, and rinse the tray."
    )
    _, db = procedure_client
    document, _ = await seed_procedure(db, body=narrative, pieces=[narrative])
    payload["document_ids"] = [str(document.id)]
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused"


@pytest.mark.parametrize(
    "template",
    [
        (
            "Give the entire ordinary procedure for the Lumen token "
            "bench, in order, including its "
            "prerequisites, parameters, prohibitions, and closure."
        ),
        (
            "How do I carry out the complete ordinary routine at the Lumen "
            "token bench? Quote the full ordered "
            "instructions, from prerequisites through final closure."
        ),
        (
            "Provide all instructions for an ordinary Lumen token bench run, "
            "retaining their order and every "
            "prerequisite, measurement, prohibition, and closing action."
        ),
        (
            "I need the full ordinary Lumen token bench procedure, including "
            "the opening conditions, exact settings, "
            "forbidden actions, and last reconciliation step."
        ),
    ],
)
async def test_combined_closed_request_forms_retain_all_thirteen_obligations(
    procedure_client, monkeypatch, template
):
    paragraphs = (
        *PARAGRAPHS,
        "Check the tray label.",
        "Retain the signed card.",
        "Return the tray key.",
    )
    text = body(paragraphs, count="seven", ordinal="seventh")
    client, _, _, payload, calls = await prepare(
        procedure_client, monkeypatch, text=text, question=template
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    proof = result["provenance"]["answer_selection"]["requirements"][0][
        "procedure_completeness"
    ]
    assert proof["mandatory_proof_count"] == len(proof["proof_units"]) == 13
    assert len(calls) == 2


@pytest.mark.parametrize("disclose", [False, True])
async def test_combined_procedure_other_fact_and_scope_disclosure_survive(
    procedure_client, monkeypatch, disclose
):
    from app.services import connected_query

    suffix = (
        "Who leads ordinary Larch review sessions?"
        if disclose
        else "Who leads Larch review?"
    )
    source_text, procedure_question = body(), QUESTION
    if disclose:
        source_text = closed_role_free_body()
    client, db, document, payload, calls = await prepare(
        procedure_client,
        monkeypatch,
        text=source_text,
        question=procedure_question + " " + suffix,
    )
    if disclose:
        config = connected_query.settings.model_copy(
            update={"ROLE_SCOPE_POLICY": "ordinary_session_activity_v1"}
        )
        monkeypatch.setattr("app.services.connected_query.settings", config)
        monkeypatch.setattr("app.api.queries.settings", config)
    fact = "The records clerk leads Larch review."
    other, _ = await seed_procedure(db, body=fact, pieces=[fact])
    payload["document_ids"] = [str(document.id), str(other.id)]
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "completed", json.dumps(
        result["provenance"]["answer_selection"]["requirements"]
    )
    assert (
        "Obtain the signed card." in result["answer"]
        if disclose
        else "\n\n".join(PARAGRAPHS) in result["answer"]
    ) and "records clerk" in result["answer"]
    assert ("Activity scope:" in result["answer"]) is disclose
    await export_extra(
        result, payload, db, "fixture-disclosure-v3" if disclose else "fixture-mixed-v3"
    )
    assert len(calls) >= 3
    assert (await client.get(f"/api/queries/{result['id']}")).json()[
        "answer"
    ] == result["answer"]


async def test_combined_source_change_between_stream_fragments_refuses(
    procedure_client, monkeypatch
):
    from app.api.queries import stream_query
    from app.models.document import Document
    from app.models.query import QueryRequest
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from tests.test_procedure_extent import PRINCIPAL

    client, db, document, payload, _ = await prepare(procedure_client, monkeypatch)
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    assert '"type": "token"' in await anext(response.body_iterator)
    factory = async_sessionmaker(db.bind, expire_on_commit=False)
    async with factory() as external:
        await external.execute(
            update(Document)
            .where(Document.id == document.id)
            .values(metadata_={"condition": "exception"})
        )
        await external.commit()
    remaining = "".join([part async for part in response.body_iterator])
    assert '"type": "refused"' in remaining and '"type": "done"' not in remaining
    row = await db.scalar(select(Query))
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert (
        saved["outcome"] == "refused"
        and saved["answer"] is None
        and saved["sources"] == []
    )


async def test_combined_mixed_factual_extract_cannot_be_replaced_by_other_literal(
    procedure_client, monkeypatch
):
    import uuid

    from app.services.procedure_output import render_extractive

    client, db, document, payload, _ = await prepare(
        procedure_client, monkeypatch, question=QUESTION + " Who leads Larch review?"
    )
    fact = (
        "The records clerk leads Larch review. "
        "The archivist leads unrelated Rook review."
    )
    other, _ = await seed_procedure(db, body=fact, pieces=[fact])
    payload["document_ids"] = [str(document.id), str(other.id)]
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    row = await db.get(Query, uuid.UUID(result["id"]))
    provenance, citations = deepcopy(row.provenance), deepcopy(row.sources)
    selection = provenance["answer_selection"]
    citation = next(c for c in citations if c["document_id"] == str(other.id))
    first = fact.index("The archivist")
    citation["answer_spans"] = [
        {"start": first, "end": len(fact), "text": fact[first:]}
    ]
    proof = selection["requirements"][0]["procedure_completeness"]
    groups = [
        {
            "requirement_id": "r1",
            "text": "\n\n".join(PARAGRAPHS),
            "chunk_ids": [p["chunk_id"] for p in proof["fragments"]],
            "fragments": [
                {
                    "chunk_id": p["chunk_id"],
                    "start": p["chunk_start"],
                    "end": p["chunk_end"],
                }
                for p in proof["fragments"]
            ],
        }
    ]
    answer, _ = render_extractive(citations, groups)
    import hashlib

    proof["output_certificate"]["answer_sha256"] = hashlib.sha256(
        answer.encode()
    ).hexdigest()
    row.answer, row.sources, row.provenance = answer, citations, provenance
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["answer"] is None and saved["evidence_access"] == "unknown"


def closed_role_free_body():
    text = body(("Obtain the signed card.", *PARAGRAPHS[1:]))
    return text.replace("The activity owner is the records clerk.\n\n", "").split(
        "\n\nAfter the final paragraph", 1
    )[0]


@pytest.mark.parametrize(
    "damage",
    [
        "preface",
        "alias",
        "appointment",
        "owner",
        "responsibility",
        "tail",
        "whole_role",
        "actor_alias",
        "coordinated_alias",
    ],
)
async def test_combined_role_disclosure_cannot_hide_unclassified_governing_material(
    procedure_client, monkeypatch, damage
):
    from app.services import connected_query

    text = closed_role_free_body()
    variants = {
        "preface": (
            "For ordinary Larch review sessions, "
            "the holder of the red badge acts instead.\n\n"
        ),
        "actor_alias": "Record the card and Mira replaces Rowan for ordinary runs.",
        "coordinated_alias": (
            "Record the card and the red badge replaces the blue "
            "badge for ordinary runs."
        ),
        "alias": "Record Mira as the person-role for ordinary sessions.",
        "appointment": "Select the newly appointed facilitator for ordinary sessions.",
        "owner": "Set the owner of each ordinary session to Mira.",
        "responsibility": "Record Mira as responsible for ordinary sessions.",
        "tail": "\n\nFor ordinary Larch review sessions, Mira has final authority.",
        "whole_role": "\n\nMira presides over ordinary Larch review sessions.",
    }
    if damage == "preface":
        text = text.replace(
            "Complete ordinary procedure",
            variants[damage] + "Complete ordinary procedure",
        )
    elif damage in {"tail", "whole_role"}:
        text += variants[damage]
    else:
        text = text.replace(PARAGRAPHS[1], variants[damage])
    client, db, document, payload, _ = await prepare(
        procedure_client,
        monkeypatch,
        text=text,
        question=QUESTION + " Who leads ordinary Larch review sessions?",
    )
    config = connected_query.settings.model_copy(
        update={"ROLE_SCOPE_POLICY": "ordinary_session_activity_v1"}
    )
    monkeypatch.setattr("app.services.connected_query.settings", config)
    monkeypatch.setattr("app.api.queries.settings", config)
    fact = "The records clerk leads Larch review."
    other, _ = await seed_procedure(db, body=fact, pieces=[fact])
    payload["document_ids"] = [str(document.id), str(other.id)]
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "refused" and result["answer"] is None
    assert (
        result["provenance"]["answer_selection"]["requirements"][1][
            "role_scope_inspection"
        ]["complete"]
        is False
    )


async def test_combined_coherent_numbered_omission_cannot_change_canonical_boundary(
    procedure_client, monkeypatch
):
    import hashlib
    import uuid

    from tests.test_procedure_extent import LONG
    from tests.test_procedure_extent import QUESTION as NUMBERED

    client, db, _, payload, _ = await prepare(
        procedure_client, monkeypatch, text=LONG, question=NUMBERED
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed"
    row = await db.get(Query, uuid.UUID(result["id"]))
    provenance, citations = deepcopy(row.provenance), deepcopy(row.sources)
    proof = provenance["answer_selection"]["requirements"][0]["procedure_completeness"]
    cut = proof["step_ranges"][-1]["start"]
    proof["step_ranges"].pop()
    proof["step_ranges"][-1]["end"] = cut
    proof["step_count"] -= 1
    proof["extent"]["end"] = cut
    proof["closure"] = {
        "kind": "independent_section",
        "end": cut,
        "boundary_range": {"start": cut, "end": cut + 2},
    }
    proof["proof_units"] = [
        u for u in proof["proof_units"] if u["source_range"]["start"] < cut
    ]
    proof["mandatory_proof_count"] = len(proof["proof_units"])
    names = {u["name"] for u in proof["proof_units"]}
    proof["structure_edges"] = [
        e for e in proof["structure_edges"] if e["target"] in names
    ]
    inventory = proof["required_inventory"]
    inventory["extent"]["end"] = cut
    inventory["step_ranges"] = deepcopy(proof["step_ranges"])
    inventory["units"] = [u for u in inventory["units"] if u["name"] in names]
    inventory["structure_edges"] = deepcopy(proof["structure_edges"])
    proof["fragments"][0]["chunk_end"] = cut
    proof["fragments"][0]["document_end"] = cut
    literal = LONG[proof["extent"]["start"] : cut]
    citations[0]["answer_spans"] = [
        {"start": proof["extent"]["start"], "end": cut, "text": literal}
    ]
    row.answer = "Source extracts (not model-generated):\n\n" + literal + " [1]"
    certificate = proof["output_certificate"]
    certificate["required_inventory"] = deepcopy(inventory)
    certificate["instruction_range"]["end"] = cut
    certificate["answer_range"]["end"] = certificate["answer_range"]["start"] + len(
        literal
    )
    certificate["citation_mapping"][0]["chunk_end"] = cut
    certificate["citation_mapping"][0]["document_end"] = cut
    certificate["answer_sha256"] = hashlib.sha256(row.answer.encode()).hexdigest()
    row.provenance, row.sources = provenance, citations
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["answer"] is None and saved["evidence_access"] == "unknown"
    assert saved["outcome"] == "completed"


async def test_combined_saved_v3_reloads_through_fresh_session_and_asgi_client(
    procedure_client, monkeypatch
):
    from app.db.session import get_db
    from app.main import app
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import async_sessionmaker

    client, db, _, payload, _ = await prepare(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    factory = async_sessionmaker(db.bind, expire_on_commit=False)

    async def restarted_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = restarted_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://restart"
    ) as restarted:
        saved = (await restarted.get(f"/api/queries/{result['id']}")).json()
    assert saved["answer"] == result["answer"] and saved["sources"] == result["sources"]
    assert (
        saved["provenance"]["answer_selection"]["presentation_verification"]["status"]
        == "verified"
    )


@pytest.mark.parametrize("opposing", [False, True])
async def test_combined_curated_opponents_keep_methods_and_conflict_gate(
    procedure_client, monkeypatch, opposing
):
    client, db, document, payload, calls = await prepare(procedure_client, monkeypatch)
    text = body().replace("Place one token", "Place two tokens") if opposing else body()
    other, _ = await seed_procedure(db, body=text, pieces=[text])
    for doc in (document, other):
        doc.metadata_ = {"conflict_group": "combined-closed-procedure"}
    await db.commit()
    payload["document_ids"] = [str(document.id), str(other.id)]
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == ("refused" if opposing else "completed"), result.get(
        "refusal_reason"
    )
    assert len(calls) == 4
    if opposing:
        assert result["answer"] is None and result["sources"] == []


@pytest.mark.parametrize("separator", ["\u0085", "\u001c"])
async def test_combined_numbered_python_whitespace_is_literal(
    procedure_client, monkeypatch, separator
):
    from tests.test_procedure_extent import LONG
    from tests.test_procedure_extent import QUESTION as NUMBERED

    text = LONG.replace("1. Verify", "1." + separator + "Verify")
    client, db, _, payload, _ = await prepare(
        procedure_client, monkeypatch, text=text, question=NUMBERED
    )
    result = (await client.post("/api/queries", json=payload)).json()
    assert result["outcome"] == "completed", result
    assert separator in result["answer"]
    await export_extra(
        result, payload, db, "fixture-numbered-space-" + hex(ord(separator))[2:] + "-v3"
    )


async def test_combined_malformed_saved_inventory_is_safe_unknown(
    procedure_client, monkeypatch
):
    import uuid

    client, db, _, payload, _ = await prepare(procedure_client, monkeypatch)
    result = (await client.post("/api/queries", json=payload)).json()
    row = await db.get(Query, uuid.UUID(result["id"]))
    provenance = deepcopy(row.provenance)
    provenance["answer_selection"]["requirements"] = "malformed"
    row.provenance = provenance
    await db.commit()
    response = await client.get(f"/api/queries/{row.id}")
    assert response.status_code == 200
    saved = response.json()
    assert saved["answer"] is None and saved["evidence_access"] == "unknown"
    assert (
        saved["provenance"]["answer_selection"]["presentation_verification"]["status"]
        == "invalid"
    )
    assert row.provenance == provenance
