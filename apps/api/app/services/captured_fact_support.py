"""Specified-hypothesis model evidence only; facts remain fixed-caller gates."""

import asyncio
import json
import math
import uuid
from dataclasses import asdict, dataclass

from app.config import Settings
from app.services import answer_support
from app.services import captured_fact_context as context
from app.services import planning_support as receipts
from app.services.captured_plan_inputs import decode_inputs_v2
from app.services.planning_declarations import (
    RawRange,
    SourceIdentity,
    canonical,
    digest,
)
from app.services.planning_support import PlanningPair, _metadata
from app.services.request_parser import _native

SCOPE = "specified_hypothesis_model_support_only"
_GATES = (
    "fixed_caller_request_entity_attribute_units_conditions_and_all_raw_proposals",
    "actual_actor_or_dependency_value_binding_and_prior_positive_actor_NI",
    "source_authority_current_SQL_membership_and_reauthorization",
    "complete_reference_closure_and_semantic_opposition_acceptance",
    "fact_answer_output_citation_access_and_history_acceptance",
)


@dataclass(frozen=True)
class FactSupportClaim:
    requirement_id: str
    reference_id: str
    hypothesis: str


@dataclass(frozen=True)
class FactSupportLimits:
    max_claims: int = 16
    inference_timeout_seconds: float = 60.0

    def __post_init__(self):
        if type(self.max_claims) is not int or not 1 <= self.max_claims <= 32:
            raise ValueError("Fact support claim limit must be native integer1..32")
        seconds = self.inference_timeout_seconds
        if (
            type(seconds) not in (int, float)
            or not math.isfinite(seconds)
            or not 0 < seconds <= 120
        ):
            raise ValueError(
                "Fact support timeout must be finite positive seconds<=120"
            )


DEFAULT_LIMITS = FactSupportLimits()


@dataclass(frozen=True)
class FactSupportAssertion:
    id: str
    claim: FactSupportClaim
    channel: str
    pair: PlanningPair
    source_identity: SourceIdentity
    source_range: RawRange


@dataclass(frozen=True)
class PreparedFactSupport:
    governing_context_json: str
    support_metadata_json: str
    claims: tuple[FactSupportClaim, ...]
    assertions: tuple[FactSupportAssertion, ...]
    pending: tuple[str, ...]
    scope: str = "specified_hypothesis_model_support_only"

    @property
    def ready_for_assessment(self):
        return bool(self.assertions) and not self.pending

    def record(self):
        return json.loads(
            canonical(
                {
                    "contract": "captured-fact-support-preparation-v1",
                    **asdict(self),
                    "ready_for_assessment": self.ready_for_assessment,
                    "model_support": "UNASSESSED_NI",
                    "remaining_gates": _GATES,
                }
            )
        )


def _claims(claims, limits):
    if (
        type(limits) is not FactSupportLimits
        or type(claims) is not tuple
        or not 1 <= len(claims) <= limits.max_claims
    ):
        raise ValueError("Bounded immutable typed fact hypothesis inventory required")
    seen = set()
    for claim in claims:
        if type(claim) is not FactSupportClaim:
            raise ValueError(
                "Exact typed fixed-caller fact hypothesis descriptor required"
            )
        for value, maximum in (
            (claim.requirement_id, 256),
            (claim.reference_id, 256),
            (claim.hypothesis, 4096),
        ):
            if type(value) is not str or not value.strip() or len(value) > maximum:
                raise ValueError("Nonempty bounded native hypothesis IDs/text required")
        identity = (claim.requirement_id, claim.reference_id)
        if identity in seen:
            raise ValueError("Duplicate fixed-caller hypothesis identity")
        seen.add(identity)


def prepare_fact_support(
    record,
    *,
    question,
    authoritative_snapshots,
    retained_inputs,
    source_identity,
    selected_clause,
    claims,
    expected_support_metadata,
    limits=DEFAULT_LIMITS,
):
    _claims(claims, limits)
    decoded = decode_inputs_v2(
        record,
        question=question,
        authoritative_snapshots=authoritative_snapshots,
        retained_inputs=retained_inputs,
    )
    if decoded.evidence_profile["evidence_reading_profile"] != "contextual_source_v4":
        raise ValueError("Explicit profilev4/input2 required")
    if set(authoritative_snapshots) != {
        row.identity.document_id for row in decoded.arguments["snapshots"]
    }:
        raise ValueError("Independent source API scope differs from retained universe")
    settings = _metadata(expected_support_metadata)
    if canonical(_metadata(decoded.arguments["support_metadata"])) != canonical(
        settings
    ):
        raise ValueError(
            "Raw input support settings differ from expected frozen metadata"
        )
    result = context.reconstruct_fact_context(
        decoded, source_identity=source_identity, selected_clause=selected_clause
    )
    assertions = []
    if result["ready_for_assessment"]:
        for claim in claims:
            for channel, window in (
                ("local", result["governing_context"]["selected_clause"]),
                ("context", result["context"]),
            ):
                pair = PlanningPair(
                    window["text"],
                    claim.hypothesis,
                    claim.requirement_id,
                    claim.reference_id + ":" + channel,
                )
                identifier = "cfs-" + digest(
                    {
                        "context": digest(result),
                        "claim": asdict(claim),
                        "channel": channel,
                        "pair": asdict(pair),
                        "settings": settings,
                    }
                )
                assertions.append(
                    FactSupportAssertion(
                        identifier,
                        claim,
                        channel,
                        pair,
                        SourceIdentity(
                            **result["governing_context"]["source_identity"]
                        ),
                        RawRange(**window),
                    )
                )
    return PreparedFactSupport(
        canonical(result),
        canonical(settings),
        claims,
        tuple(assertions),
        tuple(result["pending"]),
    )


@dataclass(frozen=True)
class FactSupportResult:
    prepared: PreparedFactSupport
    assessments: tuple[receipts.ValidatedAssessment, ...]
    model_supported: bool | None
    scope: str = SCOPE
    remaining_gates: tuple[str, ...] = _GATES

    def record(self):
        return json.loads(
            canonical({"contract": "captured-fact-model-support-v1", **asdict(self)})
        )


def reconstruct_fact_support(
    record, *, observations, actual_executions, require_runtime=True, **arguments
):
    prepared = prepare_fact_support(record, **arguments)
    if type(require_runtime) is not bool:
        raise ValueError("Explicit runtime receipt policy required")
    expected = {row.id: row for row in prepared.assertions}
    if (
        type(observations) is not tuple
        or type(actual_executions) is not tuple
        or (
            len(observations) != len(expected)
            or len(actual_executions) != len(expected)
        )
    ):
        raise ValueError(
            "Complete immutable observation and retained execution inventory required"
        )
    retained = _execution_inventory(actual_executions, expected, require_runtime)
    verified = {}
    settings = json.loads(prepared.support_metadata_json)
    for observation in observations:
        if (
            type(observation) is not receipts.NliObservation
            or observation.assertion_id not in expected
            or observation.assertion_id in verified
        ):
            raise ValueError("Typed unique expected observation required")
        execution = retained[observation.assertion_id]
        assertion = expected[observation.assertion_id]
        _replay_pair(observation, execution, assertion, prepared.support_metadata_json)
        numeric = receipts._numeric(execution.assessment_json, settings)
        if (
            type(execution.pair_tokens) is not int
            or execution.pair_tokens != numeric["pair_tokens"]
        ):
            raise ValueError("Exact independently retained token count required")
        verified[assertion.id] = receipts.ValidatedAssessment(
            assertion.id,
            execution.execution_id,
            execution.pair,
            execution.support_metadata_json,
            execution.assessment_json,
            execution.pair_tokens,
            execution.capture_kind,
            numeric["supported"],
        )
    if set(verified) != set(expected):
        raise ValueError("Mandatory fact hypothesis inventory differs")
    assessments = tuple(verified[a.id] for a in prepared.assertions)
    model_supported = (
        all(a.supported for a in assessments) if prepared.ready_for_assessment else None
    )
    gates = (
        _GATES
        + prepared.pending
        + (
            ()
            if model_supported is not False
            else ("specified_hypothesis_not_model_supported",)
        )
    )
    return FactSupportResult(
        prepared, assessments, model_supported, remaining_gates=gates
    )


def _execution_inventory(executions, expected, require_runtime):
    retained, ids = {}, set()
    for row in executions:
        if type(row) is not receipts.NliExecution:
            raise ValueError("Typed separately retained NLI execution required")
        try:
            _native(asdict(row))
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError("Native retained execution required") from exc
        if (
            type(row.execution_id) is not str
            or not row.execution_id.strip()
            or len(row.execution_id) > 256
            or row.execution_id in ids
            or row.assertion_id not in expected
            or row.assertion_id in retained
        ):
            raise ValueError("Actual execution IDs or assertion membership differ")
        if row.capture_kind not in {"runtime_capture", "UNITONLY"} or (
            require_runtime and row.capture_kind != "runtime_capture"
        ):
            raise ValueError(
                "Actual runtime capture required; UNITONLY is not runtime evidence"
            )
        retained[row.assertion_id] = row
        ids.add(row.execution_id)
    if set(retained) != set(expected):
        raise ValueError("Full retained execution assertion inventory required")
    return retained


def _replay_pair(observation, execution, assertion, expected_metadata_json):
    try:
        _native(asdict(observation))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Native exact observation required") from exc
    if (
        type(observation.pair) is not PlanningPair
        or type(execution.pair) is not PlanningPair
        or observation.pair != execution.pair
        or execution.pair != assertion.pair
    ):
        raise ValueError(
            "Actual pair differs from independently reconstructed source/hypothesis"
        )
    if (
        observation.execution_id != execution.execution_id
        or observation.support_metadata_json != execution.support_metadata_json
        or observation.assessment_json != execution.assessment_json
    ):
        raise ValueError("Observation differs from separate retained execution")
    actual = receipts.source._json_object(execution.support_metadata_json)
    if canonical(_metadata(actual)) != expected_metadata_json:
        raise ValueError("Actual pinned model/revision/threshold metadata differs")


@dataclass(frozen=True)
class FactSupportEvidence:
    prepared: PreparedFactSupport
    observations: tuple[receipts.NliObservation, ...]
    actual_executions: tuple[receipts.NliExecution, ...]
    result: FactSupportResult
    requested_support_metadata_json: str
    actual_support_metadata_json: str | None

    @property
    def assessments(self):
        return self.result.assessments

    @property
    def model_supported(self):
        return self.result.model_supported

    def record(self):
        return json.loads(
            canonical({"contract": "captured-fact-support-runtime-v1", **asdict(self)})
        )


async def assess_fact_support(
    record,
    *,
    config,
    limits=DEFAULT_LIMITS,
    execution_capture_kind="runtime_capture",
    **arguments,
):
    prepared, observations, executions = None, (), ()
    requested_json, actual_json = None, None
    returned_count, boundary_json = None, None
    stage = "inputs"
    try:
        if type(config) is not Settings or type(limits) is not FactSupportLimits:
            raise ValueError(
                "Actual Settings snapshot and typed fact support limits required"
            )
        if type(execution_capture_kind) is not str or execution_capture_kind not in {
            "runtime_capture",
            "UNITONLY",
        }:
            raise ValueError("Explicit actual execution capture provenance required")
        selected_config = config.model_copy(deep=True)
        if selected_config.EVIDENCE_READING_PROFILE != "contextual_source_v4":
            raise ValueError("Fact support runtime only accepts explicitly selected v4")
        frozen_record, frozen = _freeze_inputs(record, arguments, limits)
        stage = "prepare"
        requested_json = canonical(
            answer_support.support_service.metadata(selected_config)
        )
        requested = json.loads(requested_json)
        prepared = prepare_fact_support(
            frozen_record, **frozen, expected_support_metadata=requested, limits=limits
        )
        if prepared.ready_for_assessment:
            pairs = tuple(
                answer_support.SupportPair(**asdict(row.pair))
                for row in prepared.assertions
            )
            stage = "assess"
            async with asyncio.timeout(limits.inference_timeout_seconds):
                decisions = await answer_support.support_service.assess(
                    list(pairs), selected_config
                )
            # No await occurs before exact detached boundary/metadata receipts.
            stage = "capture"
            actual_json = canonical(
                answer_support.support_service.metadata(selected_config)
            )
            returned_count, boundary_json = _boundary_snapshot(decisions, len(pairs))
            executions = _capture_executions(
                prepared, pairs, decisions, actual_json, execution_capture_kind
            )
            observations = tuple(
                receipts.NliObservation(
                    row.assertion_id,
                    row.execution_id,
                    PlanningPair(**asdict(row.pair)),
                    row.support_metadata_json,
                    row.assessment_json,
                )
                for row in executions
            )
        else:
            actual_json = requested_json
        stage = "reconstruct"
        result = reconstruct_fact_support(
            frozen_record,
            **frozen,
            expected_support_metadata=requested,
            observations=observations,
            actual_executions=executions,
            require_runtime=execution_capture_kind == "runtime_capture",
            limits=limits,
        )
        return FactSupportEvidence(
            prepared, observations, executions, result, requested_json, actual_json
        )
    except (Exception, asyncio.CancelledError) as exc:
        exc.__dict__["fact_support_evidence_json"] = canonical(
            {
                "contract": "captured-fact-support-failure-v1",
                "scope": SCOPE,
                "stage": stage,
                "exception_type": type(exc).__name__,
                "prepared": prepared.record() if prepared is not None else None,
                "requested_support_metadata_json": requested_json,
                "actual_support_metadata_json": actual_json,
                "returned_decision_count": returned_count,
                "boundary_assessments_json": boundary_json,
                "observations": [asdict(row) for row in observations],
                "actual_executions": [asdict(row) for row in executions],
            }
        )
        raise


def _freeze_inputs(record, arguments, limits):
    if set(arguments) != {
        "question",
        "authoritative_snapshots",
        "retained_inputs",
        "source_identity",
        "selected_clause",
        "claims",
    }:
        raise ValueError(
            "Fixed raw input/source/claim arguments required; no readiness callbacks"
        )
    _claims(arguments["claims"], limits)
    values = {key: value for key, value in arguments.items() if key != "claims"}
    for key, expected in (
        ("source_identity", SourceIdentity),
        ("selected_clause", RawRange),
    ):
        if type(values[key]) is expected:
            values[key] = asdict(values[key])
    _native({"record": record, "arguments": values})
    frozen = json.loads(canonical({"record": record, "arguments": values}))
    frozen["arguments"]["claims"] = arguments["claims"]
    return frozen["record"], frozen["arguments"]


def _boundary_snapshot(decisions, maximum):
    if type(decisions) not in (list, tuple):
        return None, None
    count = len(decisions)
    if count > maximum or not all(
        type(row) is answer_support.SupportAssessment for row in decisions
    ):
        return count, None
    try:
        return count, canonical([asdict(row) for row in decisions])
    except (ValueError, TypeError, RecursionError):
        return count, None


def _capture_executions(prepared, pairs, decisions, metadata_json, capture_kind):
    if type(decisions) not in (list, tuple) or len(decisions) != len(pairs):
        raise ValueError(
            "Actual support decision inventory differs from mandatory pairs"
        )
    settings = json.loads(prepared.support_metadata_json)
    prefix, actual = str(uuid.uuid4()), []
    for index, (assertion, pair, decision) in enumerate(
        zip(prepared.assertions, pairs, decisions, strict=True)
    ):
        if (
            type(decision) is not answer_support.SupportAssessment
            or type(decision.logits) is not tuple
        ):
            raise ValueError("Typed exact existing NLI assessment required")
        if type(decision.label) is not str or type(decision.supported) is not bool:
            raise ValueError("Native NLI label/decision required")
        raw = canonical(asdict(decision))
        numeric = receipts._numeric(raw, settings)
        if type(pair) is not answer_support.SupportPair or asdict(pair) != asdict(
            assertion.pair
        ):
            raise ValueError(
                "Actual frozen submitted pair differs from source/hypothesis"
            )
        actual.append(
            receipts.NliExecution(
                prefix + ":" + str(index),
                assertion.id,
                PlanningPair(**asdict(pair)),
                metadata_json,
                raw,
                numeric["pair_tokens"],
                capture_kind,
            )
        )
    return tuple(actual)
