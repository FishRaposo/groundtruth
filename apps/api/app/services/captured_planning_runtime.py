"""Capture source-relation support through existing parser/SQL/NLI boundaries.

No answer plan, permission grant, publication, history write, or lexical fallback.
The returned receipts are RAM-only until a separate owner chooses persistence.
"""

import asyncio
import json
import math
import uuid
from dataclasses import asdict, dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.evidence_policy import resolve_evidence_policy
from app.models.query import QueryRequest
from app.services import answer_support, planning_runtime, request_parser
from app.services import captured_planning_support as consumer
from app.services.access_control.scope import Principal
from app.services.captured_plan_inputs import _profile
from app.services.request_planning_manifest import check_planning_read_set

canonical = consumer.canonical


@dataclass(frozen=True)
class RuntimeLimits:
    """Adapter safety bounds only; central policy remains the integration owner's."""

    max_pairs: int = 128
    inference_timeout_seconds: float = 60.0

    def __post_init__(self):
        if type(self.max_pairs) is not int or not 1 <= self.max_pairs <= 128:
            raise ValueError("adapter_pair_limit must be exact int1..128")
        timeout = self.inference_timeout_seconds
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError(
                "adapter inference timeout must be positive finite numeric"
            )


DEFAULT_ADAPTER_LIMITS = RuntimeLimits()


@dataclass(frozen=True)
class CapturedPlanningEvidence:
    question: str
    request_capture_json: str
    inspection: planning_runtime.PlanningInspection
    requested_support_metadata_json: str
    actual_support_metadata_json: str
    executions: tuple[consumer.NliExecution, ...]
    observations: tuple[consumer.NliObservation, ...]
    support: consumer.CapturedPlanningSupport
    sql_recheck_json: str
    adapter_limits: RuntimeLimits
    scope: str = "captured_planning_source_relations_only"
    evidence_profile_json: str = "{}"

    def record(self):
        return json.loads(
            canonical({"contract": "captured-planning-runtime-v1", **asdict(self)})
        )


def _decision_boundary_snapshot(
    decisions: list[answer_support.SupportAssessment]
    | tuple[answer_support.SupportAssessment, ...],
) -> tuple[int | None, str | None]:
    returned_decision_count = None
    boundary_assessments_json = None
    if type(decisions) in (list, tuple):
        returned_decision_count = len(decisions)
        if all(type(row) is answer_support.SupportAssessment for row in decisions):
            boundary_assessments_json = canonical([asdict(row) for row in decisions])
    return returned_decision_count, boundary_assessments_json


def _retained_execution_receipts(
    assertions: tuple[consumer.PlanningAssertion, ...],
    requested_pairs: tuple[answer_support.SupportPair, ...],
    decisions: list[answer_support.SupportAssessment],
    actual_metadata_json: str,
    execution_capture_kind: Literal["runtime_capture", "UNITONLY"],
) -> tuple[consumer.NliExecution, ...]:
    if type(decisions) not in (list, tuple) or len(decisions) != len(requested_pairs):
        raise ValueError("Actual NLI decision inventory differs from mandatory pairs")
    retained = []
    execution_prefix = str(uuid.uuid4())
    for index, (assertion, pair, decision) in enumerate(
        zip(assertions, requested_pairs, decisions, strict=True)
    ):
        if type(decision) is not answer_support.SupportAssessment:
            raise ValueError("Typed existing NLI assessment required")
        if asdict(pair) != asdict(assertion.pair):
            raise ValueError("Actual execution pair differs from prepared assertion")
        pair_tokens = decision.pair_tokens
        if type(pair_tokens) is not int:
            raise ValueError("Actual NLI pair token count must be an exact integer")
        retained.append(
            consumer.NliExecution(
                execution_prefix + ":" + str(index),
                assertion.id,
                consumer.PlanningPair(**asdict(pair)),
                actual_metadata_json,
                canonical(asdict(decision)),
                pair_tokens,
                execution_capture_kind,
            )
        )
    return tuple(retained)


async def prepare_captured_planning(
    db: AsyncSession,
    principal: Principal,
    request: QueryRequest,
    config: Settings,
    *,
    limits: RuntimeLimits = DEFAULT_ADAPTER_LIMITS,
    execution_capture_kind: Literal["runtime_capture", "UNITONLY"] = "runtime_capture",
) -> CapturedPlanningEvidence:
    """Run the actual boundaries and replay exact retained decisions.

    UNITONLY is explicit provenance for externally substituted test boundaries;
    it supplies no authority. There is no success callback or returned plan input.
    Cancellation/errors propagate with a partial immutable JSON evidence string.
    """
    if type(limits) is not RuntimeLimits:
        raise ValueError("Typed adapter limits required")
    if type(execution_capture_kind) is not str or execution_capture_kind not in {
        "runtime_capture",
        "UNITONLY",
    }:
        raise ValueError("Explicit execution capture provenance required")
    # Freeze mutable request settings/scope before the first await. No credentials
    # are serialized: only the existing public NLI metadata enters receipts.
    selected_config = config.model_copy(deep=True)
    selected_request = request.model_copy(deep=True)
    selected_principal = json.loads(canonical(principal))
    profile, _ = _profile(resolve_evidence_policy(selected_config))
    question = selected_request.question
    stage = "request_capture"
    capture_json = None
    inspection = None
    prepared = None
    requested_metadata_json = None
    actual_metadata_json = None
    executions = ()
    observations = ()
    returned_decision_count = None
    boundary_assessments_json = None
    sql_recheck = None
    try:
        capture_json = canonical(
            await request_parser.capture_async(question, selected_config)
        )
        capture = json.loads(capture_json)
        stage = "planning_inspection"
        inspection = await planning_runtime.inspect_planning_declarations(
            db, selected_principal, selected_request, selected_config
        )
        if type(inspection) is not planning_runtime.PlanningInspection:
            raise ValueError("Actual typed SQL planning inspection required")
        stage = "prepare_assertions"
        requested_metadata_json = canonical(
            answer_support.support_service.metadata(selected_config)
        )
        requested_metadata = json.loads(requested_metadata_json)
        arguments = {
            "question": question,
            "evidence_profile": profile,
            "capture": capture,
            "manifest": inspection.universe,
            "snapshots": inspection.snapshots,
            "source_captures": inspection.captures,
            "support_metadata": requested_metadata,
            "sql_read_set_json": inspection.sql_read_set_json,
        }
        prepared = consumer.prepare_planning_assertions(**arguments)
        if len(prepared.assertions) > limits.max_pairs:
            raise ValueError(
                "adapter_pair_limit exceeded; no mandatory pairs truncated"
            )
        if prepared.assertions:
            # Build pairs exclusively from the reconstructed source/requirement
            # assertion set. The service controls assets, tokenizer and thresholds.
            requested_pairs = tuple(
                answer_support.SupportPair(**asdict(a.pair))
                for a in prepared.assertions
            )
            stage = "assess"
            async with asyncio.timeout(limits.inference_timeout_seconds):
                decisions = await answer_support.support_service.assess(
                    list(requested_pairs), selected_config
                )
            # No await or producer observation occurs between service return and
            # the detached exact settings/decision/pair snapshots below.
            actual_metadata_json = canonical(
                answer_support.support_service.metadata(selected_config)
            )
            returned_decision_count, boundary_assessments_json = (
                _decision_boundary_snapshot(decisions)
            )
            executions = _retained_execution_receipts(
                prepared.assertions,
                requested_pairs,
                decisions,
                actual_metadata_json,
                execution_capture_kind,
            )
            # The observation channel is separate from the caller's frozen trace.
            # Replay compares both against the independently reconstructed pairs.
            observations = tuple(
                consumer.NliObservation(
                    row.assertion_id,
                    row.execution_id,
                    consumer.PlanningPair(**asdict(row.pair)),
                    row.support_metadata_json,
                    row.assessment_json,
                )
                for row in executions
            )
        else:
            actual_metadata_json = requested_metadata_json
        stage = "reconstruct"
        supported = consumer.reconstruct_planning_support(
            **arguments, observations=observations, actual_executions=executions
        )
        stage = "sql_recheck"
        # This is the actual complete authorized-publication SQL reinspection,
        # after inference. The pure779 read_set is not an authorization receipt.
        sql_recheck = await check_planning_read_set(
            db,
            selected_principal,
            selected_request,
            json.loads(inspection.sql_read_set_json),
        )
        if type(sql_recheck) is not dict or sql_recheck.get("consistent") is not True:
            reason = (
                sql_recheck.get("reason")
                if type(sql_recheck) is dict
                else "invalid_sql_recheck"
            )
            raise ValueError("Planning SQL read set changed: " + str(reason))
        return CapturedPlanningEvidence(
            question,
            capture_json,
            inspection,
            requested_metadata_json,
            actual_metadata_json,
            executions,
            observations,
            supported,
            canonical(sql_recheck),
            limits,
            evidence_profile_json=canonical(profile),
        )
    except (Exception, asyncio.CancelledError) as exc:
        # Preserve failure/cancellation type. This is evidence, never a successful
        # currentness certificate; no automatic disk or history writes occur.
        exc.planning_evidence_json = canonical(
            {
                "contract": "captured-planning-runtime-failure-v1",
                "stage": stage,
                "exception_type": type(exc).__name__,
                "question": question,
                "request_capture_json": capture_json,
                "inspection": asdict(inspection) if inspection else None,
                "assertion_set": prepared.record() if prepared else None,
                "requested_support_metadata_json": requested_metadata_json,
                "actual_support_metadata_json": actual_metadata_json,
                "executions": [asdict(row) for row in executions],
                "observations": [asdict(row) for row in observations],
                "returned_decision_count": returned_decision_count,
                "boundary_assessments_json": boundary_assessments_json,
                "sql_recheck": sql_recheck,
            }
        )
        raise
