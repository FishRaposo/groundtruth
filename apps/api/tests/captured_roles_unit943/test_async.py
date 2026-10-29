"""New caller/runtime seam, with explicit UNITONLY numeric service doubles."""

import json
from copy import deepcopy

import pytest
from app.services import answer_support
from app.services import captured_plan_binding as binding
from app.services import captured_planning_support as planning
from app.services import captured_role_evidence as role
from app.services.captured_plan_inputs import capture_inputs_v2

from tests.captured_fact_unit939.test_runtime import config, decisions
from tests.captured_inputs_unit932.fixtures import authoritative
from tests.captured_plan_unit937.test_plan import case
from tests.planning_library_unit830.test_support import retained


def runtime_context(name="labels"):
    args = case(name)
    args["support_metadata"] = answer_support.support_service.metadata(config())
    prepared = planning.prepare_planning_assertions(**args)
    observations, executions = retained(prepared)
    args.update(observations=observations, actual_executions=executions)
    plan = binding.reconstruct_captured_plan(**args)
    record = capture_inputs_v2(**args)
    return plan, {
        "question": args["question"],
        "planning_inputs": record,
        "retained_inputs": deepcopy(record),
        "authoritative_snapshots": authoritative(record),
        "require_runtime": False,
    }


@pytest.mark.asyncio
async def test_role_calls_real_fact_adapter_with_frozen_settings_and_unitonly_receipts(
    monkeypatch,
):
    plan, inputs = runtime_context()
    selected = config()

    async def unitonly(pairs, frozen):
        assert frozen.SUPPORT_MIN_MARGIN == 2
        assert pairs and all(pair.premise == pairs[0].premise for pair in pairs)
        selected.SUPPORT_MIN_MARGIN = 0
        return decisions(pairs)

    monkeypatch.setattr(answer_support.support_service, "assess", unitonly)
    evidence = await role.assess_role_evidence(
        selected,
        requirement_id=plan.requirements[0].id,
        execution_capture_kind="UNITONLY",
        **inputs,
    )
    assert evidence.supported and evidence.set_proof is not None
    assert all(row.capture_kind == "UNITONLY" for row in evidence.actual_executions)
    assert all(
        json.loads(row.support_metadata_json)["minimum_entailment_margin"] == 2
        for row in evidence.actual_executions
    )


@pytest.mark.asyncio
async def test_second_role_batch_failure_preserves_completed_raw_channels(monkeypatch):
    plan, inputs = runtime_context("actors-dependent")
    actor = next(r for r in plan.requirements if r.kind == "role_assignment")
    calls = []

    async def unitonly(pairs, frozen):
        calls.append(tuple(pairs))
        if len(calls) == 2:
            raise answer_support.SupportUnavailableError("UNITONLY943 second batch")
        return decisions(pairs)

    monkeypatch.setattr(answer_support.support_service, "assess", unitonly)
    with pytest.raises(answer_support.SupportUnavailableError) as error:
        await role.assess_role_evidence(
            config(),
            requirement_id=actor.id,
            execution_capture_kind="UNITONLY",
            **inputs,
        )
    failure = json.loads(error.value.role_evidence_json)
    assert len(calls) == 2
    assert (
        len(failure["observations"])
        == len(failure["actual_executions"])
        == len(calls[0])
    )
    assert failure["current_fact_failure"]
