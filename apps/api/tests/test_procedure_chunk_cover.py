"""Mandatory snapshot fragments remain one literal complete-method witness."""

import pytest
from app.models.document import DocumentVersion
from app.services.requirement_contract import PROCEDURE_CONTRACT
from sqlalchemy import select as sql_select

from tests.test_procedure_extent import LONG, seed_procedure, select

pytest_plugins = ["tests.test_connected_contract"]


async def test_top_one_can_expand_snapshot_without_inventing_context_rank(
    connected_db, monkeypatch
):
    db, _ = connected_db
    document, chunks = await seed_procedure(db)
    result = await select(db, chunks[:1], document, monkeypatch)
    assert result.reason is None
    assert len(result.chunks) == 2
    first, continuation = result.chunks
    assert first.relevance_score == 0.9
    assert continuation.relevance_score == 0.0
    assert continuation.metadata["score_status"] == "not_ranked"
    assert continuation.metadata["ranking_score"] is None
    fragments = result.requirements[0]["procedure_completeness"]["fragments"]
    assert [(p["document_start"], p["document_end"]) for p in fragments] == [
        (46, 1203),
        (1203, 1929),
    ]
    assert (
        "".join(p.text for parts in result.passages.values() for p in parts)
        == LONG[46:]
    )


async def test_projection_gap_refuses_instead_of_omitting_a_step(
    connected_db, monkeypatch
):
    db, _ = connected_db
    document, chunks = await seed_procedure(db, LONG, [LONG[:1000], LONG[1400:]])
    result = await select(db, chunks[:1], document, monkeypatch)
    assert result.reason is not None, result.conflicts
    assert result.requirements[0]["reason"] == "procedure_chunk_cover_gap"


async def test_corrupted_immutable_body_cannot_establish_extent(
    connected_db, monkeypatch
):
    db, _ = connected_db
    document, chunks = await seed_procedure(db)
    version = await db.scalar(
        sql_select(DocumentVersion).where(DocumentVersion.document_id == document.id)
    )
    version.normalized_content += " Lost closure."
    await db.commit()
    result = await select(db, chunks, document, monkeypatch)
    assert result.reason is not None
    assert result.requirements[0]["reason"] == "procedure_snapshot_hash_mismatch"


async def test_curated_qa_null_opponent_still_gets_complete_extent_checks(
    connected_db, monkeypatch
):
    db, _ = connected_db
    first, first_chunks = await seed_procedure(db)
    other, other_chunks = await seed_procedure(
        db, LONG.replace("Verify the signed", "Check the signed")
    )
    for document in (first, other):
        document.metadata_ = {**(document.metadata_ or {}), "conflict_group": "harbor"}
    await db.commit()
    chunks = first_chunks + other_chunks
    for chunk in chunks:
        chunk.metadata["conflict_group"] = "harbor"
    result = await select(
        db, chunks, first, monkeypatch, document_ids=[first.id, other.id]
    )
    assert result.reason is not None, [
        (
            r.get("relevant"),
            r.get("subject_scope_excluded_documents"),
            r.get("source_extent_checks"),
        )
        for r in result.conflicts
    ]
    inspections = [
        entry
        for record in result.conflicts
        for entry in record.get("source_extent_checks", [])
    ]
    assert str(other.id) in {entry["document_id"] for entry in inspections}, (
        "QA-null is not permission to omit a curated opponent"
    )
    opponent = next(
        entry for entry in inspections if entry["document_id"] == str(other.id)
    )
    assert opponent["step_count"] == 8
    assert any("reopen" in unit["hypothesis"] for unit in opponent["proof_units"])


async def test_existing_bounded_followup_can_find_a_complete_procedure(
    connected_db, monkeypatch
):
    db, _ = connected_db
    document, _ = await seed_procedure(db)
    result = await select(db, [], document, monkeypatch)
    assert result.reason is None, result.requirements
    assert len(result.followups) == 1 and result.followups[0]["sources"]
    assert result.requirements[0]["procedure_completeness"]["step_count"] == 8


async def configure_late_opponent_change(db, monkeypatch, change="version"):
    """B changes during C's proof, after B's proof and immediate recheck."""
    import uuid

    from app.models.chunk import Chunk
    from app.services.answer_support import SupportAssessment, support_service
    from app.services.document.versioning import DocumentVersionManager

    from tests.test_procedure_extent import external_boundaries

    a, chunks = await seed_procedure(db)
    b, _ = await seed_procedure(db)
    c, _ = await seed_procedure(db)
    for document in (a, b, c):
        document.metadata_ = {
            **(document.metadata_ or {}),
            "conflict_group": "v40-late-opponents",
        }
    for chunk in chunks:
        chunk.metadata["conflict_group"] = "v40-late-opponents"
    await db.commit()
    external_boundaries(monkeypatch)
    state = {"changed": False, "calls": []}

    async def nli(pairs, config=None):
        current = pairs[0].reference_id.split(":", 1)[0] if pairs else None
        state["calls"].append(current)
        if current == str(c.id) and not state["changed"]:
            assert str(b.id) in state["calls"]
            if change == "version":
                body = LONG.replace(
                    "Do not reopen the transfer after closure.",
                    "Reopen the transfer after closure.",
                )
                replacements = [
                    Chunk(
                        id=uuid.uuid4(),
                        document_id=b.id,
                        chunk_index=i,
                        content=text,
                        metadata_={"document_version": 2},
                    )
                    for i, text in enumerate([body[:1292], body[1171:]])
                ]
                db.add_all(replacements)
                await db.flush()
                await DocumentVersionManager(db).create_version(
                    str(b.id), body, replacements, workspace_id="ops-a", document=b
                )
            elif change == "condition":
                b.metadata_ = {**b.metadata_, "condition": "exception"}
            elif change == "group":
                b.metadata_ = {**b.metadata_, "conflict_group": "different-group"}
            elif change == "owner":
                b.owner_id = "someone-else"
            await db.commit()
            state["changed"] = True
        return [
            SupportAssessment("entailment", (-5.0, 5.0, -5.0), 10.0, True, 12)
            for _ in pairs
        ]

    monkeypatch.setattr(support_service, "assess", nli)
    return a, chunks, b, c, state


@pytest.mark.parametrize("change", ["version", "condition", "group", "owner"])
async def test_v40_all_inspected_inputs_remain_current_after_last_proof(
    connected_db, monkeypatch, change
):
    from app.config import Settings
    from app.models.query import QueryRequest
    from app.services.requirement_answers import select_requirement_answer

    from tests.test_procedure_extent import PRINCIPAL, QUESTION

    db, _ = connected_db
    a, chunks, b, c, state = await configure_late_opponent_change(
        db, monkeypatch, change
    )
    config = Settings(
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        GENERATION_MODE="extractive",
        READER_NULL_THRESHOLD=8,
    )

    async def current(chunk):
        return True

    result = await select_requirement_answer(
        db,
        QueryRequest(
            question=QUESTION,
            document_ids=[a.id, b.id, c.id],
            retrieval_method="keyword",
        ),
        PRINCIPAL,
        chunks[:1],
        config,
        validate_current=current,
    )
    assert state["changed"]
    assert result.reason is not None, (
        "Previously inspected B changed while C was proved"
    )
    assert not result.chunks
    assert all(
        not row["inspection_complete"] and not row["requested_fact_agreement"]
        for row in result.conflicts
        if row.get("inspection_method") == PROCEDURE_CONTRACT
    )


async def test_v40_new_authorized_opponent_invalidates_group_snapshot(
    connected_db, monkeypatch
):
    from app.config import Settings
    from app.models.query import QueryRequest
    from app.services.procedure_evidence import check_read_set
    from app.services.requirement_answers import select_requirement_answer

    from tests.test_procedure_extent import PRINCIPAL, QUESTION, external_boundaries

    db, _ = connected_db
    a, chunks = await seed_procedure(db)
    a.metadata_ = {**a.metadata_, "conflict_group": "v40-members"}
    chunks[0].metadata["conflict_group"] = "v40-members"
    await db.commit()
    external_boundaries(monkeypatch)
    request = QueryRequest(question=QUESTION, retrieval_method="keyword")
    config = Settings(
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        GENERATION_MODE="extractive",
    )

    async def current(chunk):
        return True

    result = await select_requirement_answer(
        db, request, PRINCIPAL, chunks[:1], config, validate_current=current
    )
    assert result.reason is None
    other, _ = await seed_procedure(db)
    other.metadata_ = {**other.metadata_, "conflict_group": "v40-members"}
    await db.commit()
    check = await check_read_set(db, PRINCIPAL, request, result.procedure_read_set)
    assert not check["consistent"] and check["changed_groups"] == ["v40-members"]


async def test_v40_collection_filter_membership_is_rechecked(connected_db, monkeypatch):
    from app.config import Settings
    from app.models.collection import Collection, collection_documents
    from app.models.query import QueryRequest
    from app.services.procedure_evidence import check_read_set
    from app.services.requirement_answers import select_requirement_answer
    from sqlalchemy import delete

    from tests.test_procedure_extent import PRINCIPAL, QUESTION, external_boundaries

    db, _ = connected_db
    a, chunks = await seed_procedure(db)
    collection = Collection(name="v40 scope", owner_id="writer")
    db.add(collection)
    await db.flush()
    await db.execute(
        collection_documents.insert().values(
            collection_id=collection.id, document_id=a.id
        )
    )
    await db.commit()
    external_boundaries(monkeypatch)
    request = QueryRequest(
        question=QUESTION, collection_ids=[collection.id], retrieval_method="keyword"
    )
    config = Settings(
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        GENERATION_MODE="extractive",
    )

    async def current(chunk):
        return True

    result = await select_requirement_answer(
        db, request, PRINCIPAL, chunks[:1], config, validate_current=current
    )
    assert result.reason is None
    await db.execute(
        delete(collection_documents).where(
            collection_documents.c.collection_id == collection.id
        )
    )
    await db.commit()
    check = await check_read_set(db, PRINCIPAL, request, result.procedure_read_set)
    assert not check["consistent"] and check["changed_source_ids"]
