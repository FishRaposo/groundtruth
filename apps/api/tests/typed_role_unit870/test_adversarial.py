"""Bounded actual-pipeline protocol controls, never model-quality acceptance."""

from copy import deepcopy

import pytest
from app.models.chunk import Chunk
from app.services import connected_query, request_parser, staged_output
from app.services.answer_support import support_service
from app.services.procedure_output import load_snapshots, retained_selection
from sqlalchemy import select

from tests.staged_plan_unit837.fixtures_request import ACTORS
from tests.staged_plan_unit837.fixtures_source import COND, EXTERNAL, UNKNOWN, capture
from tests.staged_role_unit850.test_role_evidence import Backend, backend_context
from tests.test_staged_snapshot_store849 import publish_library

from .fixtures import PROCEDURE, actor_case, composite_case, dependent_case

pytest_plugins = ["tests.test_connected_contract"]


async def test_unsupported_actor_cannot_bind_dependent_availability(
    connected_db, monkeypatch
):
    db, _, principal, request, _, document, _ = await dependent_case(
        connected_db, monkeypatch
    )
    body = await db.scalar(
        select(Chunk.content).where(Chunk.document_id == document.id)
    )
    assert body
    backend = Backend(whole=body)
    with backend_context(backend):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.outcome == "refused"
        assert row.answer is None
        assert any(
            pair.premise == body for pairs in backend.logit_calls for pair in pairs
        )
        assert not any(
            "dependent_availability" in (pair.reference_id or "")
            for pairs in backend.logit_calls
            for pair in pairs
        )


async def test_actor_revoked_after_inference_cannot_publish(connected_db, monkeypatch):
    db, _, principal, request, _, document, _ = await actor_case(
        connected_db, monkeypatch
    )
    original = support_service.assess
    revoked = False

    async def infer_then_revoke(pairs, config=None):
        nonlocal revoked
        decisions = await original(pairs, config)
        if not revoked and any(":rfe-" in (pair.reference_id or "") for pair in pairs):
            document.owner_id = "other-owner"
            await db.commit()
            revoked = True
        return decisions

    monkeypatch.setattr(support_service, "assess", infer_then_revoke)
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert revoked
        assert row.outcome == "refused" and row.answer is None


async def test_unknown_procedure_modifier_is_not_consumed_by_full_extent(
    connected_db, monkeypatch
):
    db, _, principal, request, _, _, _ = await composite_case(connected_db, monkeypatch)
    modified = [
        (word, pos, lemma, dep, head + (head >= 3))
        for word, pos, lemma, dep, head in PROCEDURE
    ]
    modified.insert(3, ("eligible", "ADJ", "eligible", "amod", 4))
    question, observed = capture([ACTORS, modified])
    previous = request_parser.capture_async

    async def syntax(text, config):
        return deepcopy(observed) if text == question else await previous(text, config)

    monkeypatch.setattr(request_parser, "capture_async", syntax)
    request = request.model_copy(update={"question": question})
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.outcome == "refused"
        assert row.answer is None


def _mutate(selection, case):
    row = next(
        row for row in selection["requirements"] if row["kind"] == "role_assignment"
    )
    candidate = next(
        row
        for row in selection["candidates"]
        if row["requirement_id"] == row_id(selection)
    )
    if case == "receipt_tokens":
        candidate["typed_role_execution"]["actual_executions"][0]["pair_tokens"] += 1
    elif case == "actor_value":
        row["witnesses"][0]["value"] = "Unproven actor"
        candidate["typed_role_descriptor"]["value"] = "Unproven actor"
    elif case == "catalogue_member":
        parent = next(
            row for row in selection["requirements"] if row["kind"] == "role_catalogue"
        )
        parent["witnesses"][0]["typed_set_proof"]["members"].pop()
    elif case == "source_offset":
        candidate["proposal"]["document_range"]["start"] += 1
    elif case == "missing_execution":
        candidate["typed_role_execution"]["actual_executions"].pop()


def row_id(selection):
    return next(
        row["id"]
        for row in selection["requirements"]
        if row["kind"] == "role_assignment"
    )


async def test_retained_replay_rejects_receipts_values_members_and_offsets(
    connected_db, monkeypatch
):
    db, _, principal, request, _, _, _ = await actor_case(connected_db, monkeypatch)
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.outcome == "completed"
        assert row.provenance is not None
        selection = row.provenance["answer_selection"]
        snapshots = await load_snapshots(
            db, selection, query_context=row.retrieval_trace
        )
        context = {
            "question": row.question,
            "answer": row.answer,
            "citations": row.sources,
            "source_snapshots": snapshots,
            "query_context": row.retrieval_trace,
        }
        assert staged_output.verify_output(selection, **context)
        for case in (
            "receipt_tokens",
            "actor_value",
            "catalogue_member",
            "source_offset",
            "missing_execution",
        ):
            changed, retained = deepcopy(selection), deepcopy(row.retrieval_trace)
            _mutate(changed, case)
            _mutate(retained_selection(retained), case)
            assert not staged_output.verify_output(
                changed, **{**context, "query_context": retained}
            ), case
        changed = deepcopy(snapshots)
        next(iter(changed.values()))["title"] += " unretained"
        assert not staged_output.verify_output(
            selection, **{**context, "source_snapshots": changed}
        )


@pytest.mark.parametrize(
    "source",
    [UNKNOWN, COND, EXTERNAL],
    ids=["unknown", "qualified_opposition", "reference"],
)
async def test_composite_retains_unowned_source_blockers(
    connected_db, monkeypatch, source
):
    db, _, principal, request, _, _, _ = await composite_case(connected_db, monkeypatch)
    raw, observed = capture([source])
    await publish_library(db, raw)
    previous = request_parser.capture_async

    async def syntax(text, config):
        return deepcopy(observed) if text == raw else await previous(text, config)

    monkeypatch.setattr(request_parser, "capture_async", syntax)
    with backend_context(Backend()):
        row = await connected_query.begin_query(db, request, principal)
        await connected_query.prepare_answer(db, row, request, principal)
        assert row.outcome == "refused"
        assert row.answer is None
        assert row.provenance is not None
        assert not row.provenance["answer_selection"]["request_plan"][
            "resolved_request"
        ]
