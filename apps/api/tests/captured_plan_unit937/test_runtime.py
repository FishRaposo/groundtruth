"""UNITONLY parser/SQL/NLI boundaries: adapter protocol, no real API/models/SQL."""

import asyncio
import json
from unittest.mock import patch

import pytest
from app.config import Settings
from app.models.query import QueryRequest
from app.services import (
    answer_support,
    planning_declarations,
    planning_runtime,
    request_parser,
)
from app.services import captured_planning_runtime as runtime
from sqlalchemy.ext.asyncio import AsyncSession

from tests.planning_library_unit830.test_support import metadata

from .test_plan import case


def config():
    return Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1",
            "ROLE_SCOPE_POLICY": "ordinary_session_activity_v1",
            "PROCEDURE_VERIFICATION_PROFILE": "source_declared_procedure_copy_v1",
            "SOURCE_CONTEXT_POLICY": "scoped_note_context_v2",
            "EVIDENCE_READING_PROFILE": "contextual_source_v4",
            "QUANTITY_VERIFICATION_PROFILE": "literal_source_count_v1",
            "REQUEST_PARSER_MODE": "local_dependency",
            "ANSWER_SELECTION_MODE": "reader",
            "ANSWER_SUPPORT_MODE": "local_nli",
            "GENERATION_MODE": "extractive",
        }
    )


def inspection(args):
    return planning_runtime.PlanningInspection(
        args["manifest"],
        args["snapshots"],
        args["source_captures"],
        planning_declarations.declaration_inventory(
            args["manifest"], args["snapshots"], args["source_captures"]
        ),
        args["sql_read_set_json"],
    )


@pytest.mark.asyncio
async def test_actual_capture_runtime_uses_new_assertions_and_rechecks_after_ni():
    # Defect: calling legacy planning silently produces no captured catalogue pairs.
    args = case()
    trace = []

    async def parse(question, selected):
        trace.append("parser")
        return args["capture"]

    async def inspect(*unused):
        trace.append("inspection")
        return inspection(args)

    async def assess(pairs, selected):
        trace.append("NI")
        return [
            answer_support.SupportAssessment(
                "entailment", (-3.0, 3.0, 0.0), 3.0, True, 40
            )
            for _ in pairs
        ]

    async def recheck(*unused):
        trace.append("SQL_RECHECK")
        return {"consistent": True, "fixture": "UNITONLY_NO_SQL"}

    with (
        patch.object(request_parser, "capture_async", parse),
        patch.object(planning_runtime, "inspect_planning_declarations", inspect),
        patch.object(
            answer_support.support_service, "metadata", lambda unused: metadata()
        ),
        patch.object(answer_support.support_service, "assess", assess),
        patch.object(runtime, "check_planning_read_set", recheck),
    ):
        result = await runtime.prepare_captured_planning(
            AsyncSession(),
            {"id": "owner", "workspace_id": "engineering917", "is_admin": False},
            QueryRequest(question=args["question"]),
            config(),
            execution_capture_kind="UNITONLY",
        )
    assert len(result.support.assertion_set.assertions) == 12
    assert len(result.executions) == len(result.observations) == 12
    assert trace == ["parser", "inspection", "NI", "SQL_RECHECK"]
    assert json.loads(result.sql_recheck_json)["consistent"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "short",
        "extra",
        "no_tokens",
        "bool_tokens",
        "long",
        "lying",
        "metadata",
        "assets",
        "budget",
        "cancel",
        "timeout",
        "revoked",
    ],
)
async def test_runtime_failures_preserve_type_stage_and_never_fallback(failure):
    args = case()
    calls = []

    async def parse(*unused):
        return args["capture"]

    async def inspect(*unused):
        return inspection(args)

    async def assess(pairs, selected):
        calls.append("assess")
        await _assessment_fault(failure)
        token_count = (
            None
            if failure == "no_tokens"
            else True
            if failure == "bool_tokens"
            else 513
            if failure == "long"
            else 40
        )
        logits = (-3.0, 0.0, 3.0) if failure == "lying" else (-3.0, 3.0, 0.0)
        rows = [
            answer_support.SupportAssessment(
                "entailment", logits, 3.0, True, token_count
            )
            for _ in pairs
        ]
        if failure == "short":
            return rows[:-1]
        if failure == "extra":
            return rows + rows[:1]
        return rows

    def meta(selected):
        result = metadata()
        if failure == "metadata" and calls:
            result["minimum_entailment_margin"] = 1
        return result

    async def recheck(*unused):
        calls.append("recheck")
        return {
            "consistent": failure != "revoked",
            "reason": "UNITONLY_current_ACL_changed",
        }

    expected = {
        "cancel": asyncio.CancelledError,
        "timeout": TimeoutError,
        "assets": answer_support.SupportUnavailableError,
        "budget": answer_support.SupportInputBudgetExceeded,
    }.get(failure, ValueError)
    with (
        patch.object(request_parser, "capture_async", parse),
        patch.object(planning_runtime, "inspect_planning_declarations", inspect),
        patch.object(answer_support.support_service, "metadata", meta),
        patch.object(answer_support.support_service, "assess", assess),
        patch.object(runtime, "check_planning_read_set", recheck),
    ):
        with pytest.raises(expected) as caught:
            await runtime.prepare_captured_planning(
                AsyncSession(),
                {"id": "owner", "workspace_id": "engineering917", "is_admin": False},
                QueryRequest(question=args["question"]),
                config(),
                limits=runtime.RuntimeLimits(inference_timeout_seconds=0.05),
                execution_capture_kind="UNITONLY",
            )
    evidence = json.loads(caught.value.__dict__["planning_evidence_json"])
    assert evidence["exception_type"] == expected.__name__
    assert evidence["stage"] == (
        "sql_recheck"
        if failure == "revoked"
        else "reconstruct"
        if failure in {"metadata", "lying", "long"}
        else "assess"
    )
    assert calls.count("assess") == 1
    assert "recheck" not in calls or failure == "revoked"


@pytest.mark.asyncio
async def test_complete_new_context_reconstructs_from_independent_raw_input_transport():
    from app.services.captured_answer_planning import prepare_context
    from app.services.captured_plan_binding import reconstruct_request

    args = case("same-activity-full")

    async def parse(*unused):
        return args["capture"]

    async def inspect(*unused):
        return inspection(args)

    async def assess(pairs, selected):
        return [
            answer_support.SupportAssessment(
                "entailment", (-3.0, 3.0, 0.0), 3.0, True, 40
            )
            for _ in pairs
        ]

    async def recheck(*unused):
        return {"consistent": True, "fixture": "UNITONLY"}

    with (
        patch.object(request_parser, "capture_async", parse),
        patch.object(planning_runtime, "inspect_planning_declarations", inspect),
        patch.object(
            answer_support.support_service, "metadata", lambda unused: metadata()
        ),
        patch.object(answer_support.support_service, "assess", assess),
        patch.object(runtime, "check_planning_read_set", recheck),
    ):
        result = await prepare_context(
            None,
            {"id": "owner", "workspace_id": "engineering917", "is_admin": False},
            QueryRequest(question=args["question"]),
            config(),
            execution_capture_kind="UNITONLY",
        )
    assert result.plan.resolved_request
    assert [r.kind for r in result.requirements] == [
        "role_catalogue",
        "role_assignment",
        "role_assignment",
        "role_assignment",
        "procedure",
    ]
    assert result.inputs()["contract"] == "staged-request-inputs-v2"
    assert len(result.snapshots()) == 4
    assert not result.record()["publication_ready"]
    rebuilt = reconstruct_request(
        result.inputs(),
        question=result.question,
        authoritative_snapshots=result.snapshots(),
        retained_inputs=result.inputs(),
    )
    assert rebuilt.record() == result.record()
    with pytest.raises(ValueError):
        reconstruct_request(
            result.inputs(),
            question=result.question,
            authoritative_snapshots=result.snapshots(),
            retained_inputs=result.inputs(),
            require_runtime=True,
        )


async def _assessment_fault(failure):
    if failure == "assets":
        raise answer_support.SupportUnavailableError("UNITONLY asset failure")
    if failure == "budget":
        raise answer_support.SupportInputBudgetExceeded("UNITONLY budget", (513,))
    if failure == "cancel":
        raise asyncio.CancelledError()
    if failure == "timeout":
        await asyncio.Future()


@pytest.mark.asyncio
async def test_adapter_pair_budget_refuses_before_assessment_and_never_truncates():
    args = case()
    calls = []

    async def parse(*unused):
        return args["capture"]

    async def inspect(*unused):
        return inspection(args)

    async def assess(*unused):
        calls.append("NI")
        raise AssertionError("Pair limit must fail before inference")

    with (
        patch.object(request_parser, "capture_async", parse),
        patch.object(planning_runtime, "inspect_planning_declarations", inspect),
        patch.object(
            answer_support.support_service, "metadata", lambda unused: metadata()
        ),
        patch.object(answer_support.support_service, "assess", assess),
    ):
        with pytest.raises(ValueError, match="no mandatory pairs truncated") as caught:
            await runtime.prepare_captured_planning(
                AsyncSession(),
                {"id": "owner", "workspace_id": "engineering917", "is_admin": False},
                QueryRequest(question=args["question"]),
                config(),
                limits=runtime.RuntimeLimits(max_pairs=4),
                execution_capture_kind="UNITONLY",
            )
    receipt = json.loads(caught.value.__dict__["planning_evidence_json"])
    assert len(receipt["assertion_set"]["assertions"]) == 12
    assert receipt["stage"] == "prepare_assertions" and calls == []
