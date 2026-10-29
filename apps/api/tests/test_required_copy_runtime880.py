"""Actual SQLite resolver/readset/runtime; cached syntax, UNITONLY QA/NLI."""

import copy
import json
import uuid
from dataclasses import asdict

import pytest
from app.evidence_policy import EvidencePolicy, reading_version
from app.models.chunk import ChunkWithScore
from app.models.query import QueryRequest
from app.services import linguistic_procedure_runtime as runtime
from app.services import (
    planning_runtime,
    request_parser,
    staged_plan_binding,
    staged_plan_replay,
    staged_source_proof,
)
from app.services.answer_reader import ReaderSelection
from app.services.answer_support import SupportAssessment, support_service
from app.services.contextual_source_proof import SourceGuardError
from app.services.staged_answer_planning import StagedAnswerContext, source_snapshots

from tests.required_copy_fixtures880 import CAPTURES
from tests.test_contextual_scope_sql import PRINCIPAL
from tests.test_staged_snapshot_store849 import publish_library, staged

pytest_plugins = ["tests.test_connected_contract"]


async def prepared(connected_db, monkeypatch):
    db, _ = connected_db
    config = staged(monkeypatch)
    root, _ = await publish_library(
        db, CAPTURES["root"]["annotation"]["raw_text"], title="UNITONLY root"
    )
    target, _ = await publish_library(
        db, CAPTURES["appendix"]["annotation"]["raw_text"], title="Appendix Alpha"
    )
    await db.commit()

    async def capture(text, settings):
        return next(c for c in CAPTURES.values() if c["annotation"]["raw_text"] == text)

    monkeypatch.setattr(request_parser, "capture_async", capture)
    question = CAPTURES["question"]["annotation"]["raw_text"]
    request = QueryRequest(question=question)
    inspection = await planning_runtime.inspect_planning_declarations(
        db, PRINCIPAL, request, config
    )
    # The module verifier caches load-error identity for the process; a staged
    # record must capture the clean readiness this fixture's config implies.
    monkeypatch.setattr(support_service, "_error_identity", None)
    metadata = support_service.metadata(config)
    args = {
        "question": question,
        "capture": CAPTURES["question"],
        "manifest": inspection.universe,
        "snapshots": inspection.snapshots,
        "source_captures": inspection.captures,
        "support_metadata": metadata,
        "sql_read_set_json": inspection.sql_read_set_json,
        "observations": (),
        "actual_executions": (),
    }
    ctx = StagedAnswerContext(
        staged_plan_binding.reconstruct_staged_plan(**args),
        json.dumps(staged_plan_replay.capture_inputs(**args)),
        json.dumps(source_snapshots(inspection)),
    )
    actual = ctx.snapshots()[str(root.id)]
    raw = actual["chunks"][0]
    member = ChunkWithScore(
        id=uuid.UUID(raw["id"]),
        document_id=root.id,
        content=raw["content"],
        chunk_index=raw["index"],
        relevance_score=0.0,
        metadata={
            **raw["metadata"],
            "document_version": actual["document_version"],
            "content_hash": actual["content_hash"],
            "workspace_id": actual["workspace_id"],
        },
    )
    return db, config, request, ctx, member, target


async def run(connected_db, monkeypatch, change="none"):
    db, config, request, ctx, member, target = await prepared(connected_db, monkeypatch)
    calls = []

    async def qa(*args, **kwargs):
        return [ReaderSelection(None, {"decision": "no_answer", "null_margin": 9.0})]

    async def nli(pairs, *args, **kwargs):
        calls.extend(pairs)
        if change == "revoke":
            target.owner_id = "other-owner"
            await db.commit()
        if change == "title":
            target.title = "A changed target"
            await db.commit()
        if change == "length":
            return []
        if change == "cancel":
            import asyncio

            raise asyncio.CancelledError()
        return [
            SupportAssessment("entailment", (-1.0, 5.0, 0.0), 5.0, True, 64)
            if change != "reject"
            else SupportAssessment("neutral", (0.0, 0.0, 5.0), -5.0, False, 64)
            for _ in pairs
        ]

    monkeypatch.setattr(runtime.reader_service, "select_atomic", qa)
    monkeypatch.setattr(runtime.support_service, "assess", nli)

    async def current(_):
        return True

    candidates, inspected, contexts = [], {member.id: member}, []
    found = await runtime.find_procedure_witnesses(
        db,
        request,
        PRINCIPAL,
        ctx.requirements[0],
        config,
        candidates,
        inspected,
        contexts,
        current,
        request_plan=ctx,
        source_window_cache={},
        seeds=[member],
        reading_profile="contextual_source_v3",
    )
    return found, candidates, ctx, calls


async def test_actual_runtime_two_sources_exact_pairs_and_receipts(
    connected_db, monkeypatch
):
    found, candidates, ctx, calls = await run(connected_db, monkeypatch)
    assert len(found) == 1
    witness = found[0]
    required = witness.completeness["required_copy"]
    assert witness.value == "\n\n".join(d["body"] for d in required["documents"])
    assert len({chunk.document_id for chunk, _ in witness.fragments}) == 2
    assert [span.text for _, span in witness.fragments] == [
        d["body"] for d in required["documents"]
    ]
    record = next(
        c["source_guard_record"] for c in candidates if "source_guard_record" in c
    )
    assert [asdict(p) for p in calls] == [
        e["pair"] for e in record["required_copy_execution"]["executions"]
    ]
    assert (
        record["required_copy_execution"]["service_metadata_before"]
        == ctx.inputs()["support_metadata"]
    )


@pytest.mark.parametrize("change", ["revoke", "title", "reject"])
async def test_runtime_acl_readset_change_or_rejected_relation_refuses(
    connected_db, monkeypatch, change
):
    found, _, _, calls = await run(connected_db, monkeypatch, change)
    assert calls and not found


async def test_runtime_incomplete_nli_results_and_cancellation_are_execution_failures(
    connected_db, monkeypatch
):
    with pytest.raises(ValueError, match="decision inventory"):
        await run(connected_db, monkeypatch, "length")


async def test_runtime_cancellation_is_not_a_partial_witness(connected_db, monkeypatch):
    import asyncio

    with pytest.raises(asyncio.CancelledError):
        await run(connected_db, monkeypatch, "cancel")


async def test_source_replay_requires_retained_execution_and_exact_relation(
    connected_db, monkeypatch
):
    found, candidates, ctx, _ = await run(connected_db, monkeypatch)
    records = [
        row["source_guard_record"] for row in candidates if "source_guard_record" in row
    ]
    policy = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v3",
    )
    selection = {
        "contract": reading_version("contextual_source_v3").requirement,
        "evidence_profile": policy.record(),
        "evidence_support": records[0]["required_copy_execution"]["support_metadata"],
        "source_guard_records": records,
        "candidates": candidates,
    }
    root = records[0]["source_identity"]["document_id"]
    args = {
        "requirement": ctx.requirements[0],
        "snapshot": ctx.snapshots()[root],
        "question": ctx.question,
        "planning_inputs": ctx.inputs(),
        "retained_inputs": ctx.inputs(),
        "authoritative_snapshots": ctx.snapshots(),
        "retained_records": copy.deepcopy(records),
    }
    proof = staged_source_proof.reconstruct_source_guard(selection, **args)
    assert proof["supported"] and proof["method"] == "required_copy_v1"
    assert proof["required_copy"]["rendered_text"] == found[0].value
    with pytest.raises(SourceGuardError, match="retained"):
        staged_source_proof.reconstruct_source_guard(
            selection, **{**args, "retained_records": None}
        )
    changed = copy.deepcopy(selection)
    changed["source_guard_records"][0]["required_copy_execution"]["executions"][0][
        "pair"
    ]["hypothesis"] += " changed"
    with pytest.raises(SourceGuardError):
        staged_source_proof.reconstruct_source_guard(changed, **args)
