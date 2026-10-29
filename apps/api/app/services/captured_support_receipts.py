"""Exact805 retained execution replay primitives; no new numeric semantics."""

import json

from app.services import planning_declarations as source
from app.services.planning_support import (
    NliExecution,
    NliObservation,
    PlanningPair,
    PlanningSupportResult,
    ValidatedAssessment,
    _metadata,
    _numeric,
    _require,
    canonical,
)


def replay_assertions(
    prepared,
    observations: tuple[NliObservation, ...],
    actual_executions: tuple[NliExecution, ...],
):
    _require(
        type(observations) is tuple and type(actual_executions) is tuple,
        "Immutable observations and independently retained "
        "actual execution tuple required",
    )
    expected = {a.id: a for a in prepared.assertions}
    _require(
        len(observations) == len(expected) and len(actual_executions) == len(expected),
        "Complete mandatory observation and actual execution inventory required",
    )
    actual = {}
    execution_ids = set()
    for record in actual_executions:
        _require(
            type(record) is NliExecution
            and type(record.execution_id) is str
            and record.execution_id.strip()
            and len(record.execution_id) <= 256,
            "Typed retained actual execution required",
        )
        _require(
            record.assertion_id in expected
            and record.assertion_id not in actual
            and record.execution_id not in execution_ids,
            "Duplicate or unknown actual execution identity",
        )
        _require(
            type(record.capture_kind) is str
            and record.capture_kind in {"UNITONLY", "runtime_capture"},
            "Execution capture provenance must be explicit",
        )
        actual[record.assertion_id] = record
        execution_ids.add(record.execution_id)
    _require(
        set(actual) == set(expected), "Actual execution assertion membership differs"
    )
    verified = {}
    settings = json.loads(prepared.support_metadata_json)
    for observation in observations:
        _require(
            type(observation) is NliObservation
            and observation.assertion_id in expected
            and observation.assertion_id not in verified,
            "Typed unique actual observation required",
        )
        assertion = expected[observation.assertion_id]
        record = actual[observation.assertion_id]
        _require(
            type(observation.pair) is PlanningPair
            and type(record.pair) is PlanningPair
            and observation.pair == record.pair == assertion.pair,
            "Actual pair does not reconstruct exact source/requirement relation",
        )
        _require(
            observation.execution_id == record.execution_id
            and observation.support_metadata_json == record.support_metadata_json
            and observation.assessment_json == record.assessment_json,
            "Observation differs from independent retained actual execution",
        )
        meta = source._json_object(record.support_metadata_json)
        _require(
            canonical(_metadata(meta)) == prepared.support_metadata_json,
            "Actual model/threshold settings differ from requested pinned settings",
        )
        assessed = _numeric(record.assessment_json, settings)
        _require(
            type(record.pair_tokens) is int
            and record.pair_tokens == assessed["pair_tokens"],
            "Independent actual pair-token count differs",
        )
        verified[assertion.id] = ValidatedAssessment(
            assertion.id,
            record.execution_id,
            record.pair,
            record.support_metadata_json,
            record.assessment_json,
            record.pair_tokens,
            record.capture_kind,
            assessed["supported"],
        )
    _require(set(verified) == set(expected), "Mandatory assessment inventory differs")
    assessments = tuple(verified[a.id] for a in prepared.assertions)
    obligation_ids = tuple(dict.fromkeys(a.obligation_id for a in prepared.assertions))
    supported = tuple(
        identifier
        for identifier in obligation_ids
        if all(
            verified[a.id].supported
            for a in prepared.assertions
            if a.obligation_id == identifier
        )
    )
    accepted = (
        bool(prepared.assertions)
        and not prepared.pending
        and all(a.supported for a in assessments)
    )
    gates = [
        "source_authority_requires_separate_verification",
        "sql_authority_currentness_and_universe_requires_runtime_recheck",
        "catalogue_completeness_policy_requires_separate_verification",
        "answer_facts_output_access_history_require_separate_verification",
        "complete_governing_reference_curated_opposition_replay_required",
    ]
    gates.extend(item.reason for item in prepared.pending)
    if not all(a.supported for a in assessments):
        gates.append("mandatory_planning_relation_not_supported")
    return PlanningSupportResult(
        prepared,
        assessments,
        supported,
        accepted,
        tuple(dict.fromkeys(gates)),
        tuple(sorted({record.capture_kind for record in actual_executions})),
    )
