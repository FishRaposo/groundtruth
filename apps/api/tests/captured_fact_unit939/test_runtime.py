import asyncio
import json
from dataclasses import replace

import pytest
from app.config import Settings
from app.services import answer_support
from app.services import captured_fact_support as support

from tests.staged_plan_unit837.fixtures_source import ASSIGN, COND

from .fixtures import case


def config():
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        GENERATION_MODE="extractive",
        ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1",
        ROLE_SCOPE_POLICY="ordinary_session_activity_v1",
        PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1",
        SOURCE_CONTEXT_POLICY="scoped_note_context_v2",
        EVIDENCE_READING_PROFILE="contextual_source_v4",
        REQUEST_PARSER_MODE="local_dependency",
        SUPPORT_MIN_MARGIN=2.0,
        SUPPORT_MODEL_PATH="UNITONLY939_NO_ACTUAL_MODEL",
    )


def arguments(groups=None):
    record, args = case(groups)
    args.pop("expected_support_metadata")
    args["claims"] = (
        support.FactSupportClaim(
            "UNITONLY-r",
            "UNITONLY-reference",
            "The coordinator role for Cedar inspection is Rowan.",
        ),
    )
    return record, args


def decisions(pairs):
    return [
        replace(answer_support._assessment([-3, 3, 0], 2.0), pair_tokens=40)
        for _ in pairs
    ]


async def test_direct_boundary_receipts_use_exact_fixed_pairs_and_frozen_config(
    monkeypatch,
):
    record, args = arguments()
    selected = config()
    calls = []

    async def model_boundary(pairs, frozen):
        calls.append((tuple(pairs), frozen.SUPPORT_MIN_MARGIN))
        assert frozen is not selected
        assert all(pair.premise == args["selected_clause"]["text"] for pair in pairs)
        assert all(pair.hypothesis == args["claims"][0].hypothesis for pair in pairs)
        selected.SUPPORT_MIN_MARGIN = 0
        return decisions(pairs)

    monkeypatch.setattr(answer_support.support_service, "assess", model_boundary)
    evidence = await support.assess_fact_support(
        record, **args, config=selected, execution_capture_kind="UNITONLY"
    )
    assert len(calls) == 1 and calls[0][1] == 2.0
    assert evidence.model_supported is True and len(evidence.assessments) == 2
    assert len(evidence.observations) == len(evidence.actual_executions) == 2
    assert all(row.capture_kind == "UNITONLY" for row in evidence.actual_executions)
    assert (
        json.loads(evidence.actual_support_metadata_json)["minimum_entailment_margin"]
        == 2.0
    )
    assert evidence.observations[0].pair is not evidence.actual_executions[0].pair


async def test_pending_context_never_calls_model_boundary(monkeypatch):
    record, args = arguments([ASSIGN, COND])

    async def forbidden(*_):
        raise AssertionError("Pending context must not call NI")

    monkeypatch.setattr(answer_support.support_service, "assess", forbidden)
    evidence = await support.assess_fact_support(
        record, **args, config=config(), execution_capture_kind="UNITONLY"
    )
    assert evidence.model_supported is None
    assert evidence.actual_executions == evidence.observations == ()


@pytest.mark.parametrize("damage", ["count", "tokens", "supported", "metadata"])
async def test_actual_returned_cardinality_tokens_logits_and_metadata_fail_closed(
    monkeypatch, damage
):
    record, args = arguments()

    async def model_boundary(pairs, frozen):
        actual = decisions(pairs)
        if damage == "count":
            return actual[:-1]
        if damage == "tokens":
            actual[0] = replace(actual[0], pair_tokens=True)
        elif damage == "supported":
            actual[0] = replace(actual[0], logits=(3.0, 0.0, -3.0))
        else:
            frozen.SUPPORT_MIN_MARGIN = 3.0
        return actual

    monkeypatch.setattr(answer_support.support_service, "assess", model_boundary)
    with pytest.raises(ValueError) as error:
        await support.assess_fact_support(
            record, **args, config=config(), execution_capture_kind="UNITONLY"
        )
    failure = json.loads(error.value.fact_support_evidence_json)
    assert failure["exception_type"] == "ValueError"
    assert failure["scope"] == "specified_hypothesis_model_support_only"


async def test_model_unavailability_type_and_stage_survive(monkeypatch):
    record, args = arguments()

    async def unavailable(*_):
        raise answer_support.SupportUnavailableError("UNITONLY939 unavailable")

    monkeypatch.setattr(answer_support.support_service, "assess", unavailable)
    with pytest.raises(answer_support.SupportUnavailableError) as error:
        await support.assess_fact_support(
            record, **args, config=config(), execution_capture_kind="UNITONLY"
        )
    assert json.loads(error.value.fact_support_evidence_json)["stage"] == "assess"


async def test_timeout_cancels_the_direct_boundary_and_preserves_timeout(monkeypatch):
    record, args = arguments()
    cancelled = asyncio.Event()

    async def waits(*_):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(answer_support.support_service, "assess", waits)
    with pytest.raises(TimeoutError) as error:
        await support.assess_fact_support(
            record,
            **args,
            config=config(),
            execution_capture_kind="UNITONLY",
            limits=support.FactSupportLimits(inference_timeout_seconds=0.01),
        )
    assert cancelled.is_set()
    assert json.loads(error.value.fact_support_evidence_json)["stage"] == "assess"


async def test_caller_cancellation_propagates_without_success_receipts(monkeypatch):
    record, args = arguments()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def waits(*_):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(answer_support.support_service, "assess", waits)
    task = asyncio.create_task(
        support.assess_fact_support(
            record, **args, config=config(), execution_capture_kind="UNITONLY"
        )
    )
    await asyncio.wait_for(started.wait(), 0.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError) as error:
        await task
    assert cancelled.is_set()
    failure = json.loads(error.value.fact_support_evidence_json)
    assert failure["actual_executions"] == [] and failure["observations"] == []
