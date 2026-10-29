"""New-only request-local planning context; no answer/history publication."""

import json
from dataclasses import dataclass
from typing import Literal

from app.services import planning_declarations as source
from app.services.captured_plan_binding import CapturedRequestPlan, reconstruct_request
from app.services.captured_plan_inputs import capture_inputs_v2
from app.services.captured_planning_runtime import (
    DEFAULT_ADAPTER_LIMITS,
    prepare_captured_planning,
)
from app.services.staged_answer_planning import recheck_inputs, source_snapshots


@dataclass(frozen=True)
class CapturedAnswerContext:
    plan: CapturedRequestPlan
    inputs_json: str
    snapshots_json: str

    @property
    def requirements(self):
        return self.plan.requirements

    @property
    def uses(self):
        return self.plan.uses

    @property
    def question(self):
        return self.plan.question

    @property
    def resolved_request(self):
        return self.plan.resolved_request

    def record(self):
        return self.plan.record()

    def inputs(self):
        return json.loads(self.inputs_json)

    def snapshots(self):
        return json.loads(self.snapshots_json)


async def prepare_context(
    db,
    principal,
    request,
    config,
    *,
    limits=DEFAULT_ADAPTER_LIMITS,
    execution_capture_kind: Literal["runtime_capture", "UNITONLY"] = "runtime_capture",
):
    evidence = await prepare_captured_planning(
        db,
        principal,
        request,
        config,
        limits=limits,
        execution_capture_kind=execution_capture_kind,
    )
    inspection = evidence.inspection
    inputs = capture_inputs_v2(
        question=evidence.question,
        capture=json.loads(evidence.request_capture_json),
        manifest=inspection.universe,
        snapshots=inspection.snapshots,
        source_captures=inspection.captures,
        support_metadata=json.loads(evidence.requested_support_metadata_json),
        sql_read_set_json=inspection.sql_read_set_json,
        observations=evidence.observations,
        actual_executions=evidence.executions,
        evidence_profile=json.loads(evidence.evidence_profile_json),
    )
    actual = source_snapshots(inspection)
    plan = reconstruct_request(
        inputs,
        question=evidence.question,
        authoritative_snapshots=actual,
        retained_inputs=inputs,
        require_runtime=execution_capture_kind == "runtime_capture",
    )
    return CapturedAnswerContext(
        plan, source.canonical(inputs), source.canonical(actual)
    )


__all__ = ["CapturedAnswerContext", "prepare_context", "recheck_inputs"]
