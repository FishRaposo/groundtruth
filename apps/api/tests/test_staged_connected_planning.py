"""Connected dispatch exercises typed source-planning with UNITONLY inference."""

import json
from copy import deepcopy

import pytest
from app.config import Settings
from app.evidence_policy import EvidencePolicy
from app.models.query import QueryRequest
from app.services import staged_answer_planning as staged
from app.services.requirement_answers import select_requirement_answer
from app.services.staged_plan_binding import reconstruct_staged_plan
from app.services.staged_plan_replay import capture_inputs

from tests.staged_plan_unit837.test_binding import args


@pytest.mark.asyncio
async def test_unresolved_staged_request_keeps_actual_inputs_without_reader(
    monkeypatch,
):
    actual = args(negative=True)
    plan = reconstruct_staged_plan(**actual)
    assert not plan.resolved_request
    inputs = capture_inputs(**actual)
    context = staged.StagedAnswerContext(plan, json.dumps(inputs), "{}")
    calls = []

    async def prepare(db, principal, request, config):
        calls.append((db, principal, request.question))
        return context

    monkeypatch.setattr(staged, "prepare_context", prepare)
    from app.services import answer_reader

    async def no_reader(*a, **k):
        raise AssertionError("Unresolved request cannot execute reader")

    monkeypatch.setattr(answer_reader.reader_service, "select_atomic", no_reader)
    request = QueryRequest(question=actual["question"])
    policy = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v3",
    )
    result = await select_requirement_answer(
        None, request, {}, [], Settings(), validate_current=no_reader, policy=policy
    )
    assert calls == [(None, {}, request.question)]
    assert result.reason and "unresolved" in result.reason.lower()
    assert result.request_plan == plan.record()
    assert result.request_capture == actual["capture"]
    assert result.staged_request_inputs == inputs
    assert result.staged_request_inputs is not inputs
    detached = deepcopy(result.staged_request_inputs)
    detached["approved"] = True
    assert "approved" not in result.staged_request_inputs
    assert result.chunks == () and result.spans == {}


def test_actual_adapter_input_snapshot_survives_mutable_presentation_changes():
    from app.services.connected_query import execution_context, execution_provenance
    from app.services.requirement_answers import RequirementAnswer

    original = {"contract": "staged-request-inputs-v1", "question": "original"}
    result = RequirementAnswer(
        (),
        {},
        [],
        [],
        [],
        [],
        [],
        "UNITONLY refusal",
        staged_request_inputs=deepcopy(original),
        staged_execution_capture_json=json.dumps(original),
    )
    selection = {"staged_request_inputs": {**original, "question": "altered"}}
    context = execution_context(selection, result)
    retained = context["provenance"]["answer_selection"]["staged_request_inputs"]
    assert retained == original
    assert selection["staged_request_inputs"]["question"] == "altered"
    context["provenance"]["answer_selection"]["presentation_verification"] = {
        "status": "verified"
    }
    refreshed = execution_provenance(
        {"answer_selection": selection}, retained_trace=context
    )
    assert refreshed["answer_selection"]["staged_request_inputs"] == original
    assert refreshed["answer_selection"]["staged_request_inputs"] is not retained
    legacy = {"answer_selection": {"contract": "requirement-evidence-v4"}}
    assert execution_provenance(legacy) is legacy
