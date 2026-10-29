import json
from copy import deepcopy
from dataclasses import asdict, replace

import pytest
from app.services import answer_support
from app.services import captured_fact_support as support
from app.services import planning_support as receipts
from app.services.planning_declarations import canonical

from .fixtures import case


@pytest.fixture(scope="module")
def inputs():
    record, args = case()
    args["claims"] = (
        support.FactSupportClaim(
            "UNITONLY-r",
            "UNITONLY-reference",
            "The coordinator role for Cedar inspection is Rowan.",
        ),
    )
    return record, args


def retained(prepared):
    observations, executions = [], []
    assessment = canonical(
        asdict(replace(answer_support._assessment([-3, 3, 0], 2.0), pair_tokens=40))
    )
    for index, assertion in enumerate(prepared.assertions):
        execution = receipts.NliExecution(
            "UNITONLY939:" + str(index),
            assertion.id,
            receipts.PlanningPair(**asdict(assertion.pair)),
            prepared.support_metadata_json,
            assessment,
            40,
            "UNITONLY",
        )
        executions.append(execution)
        observations.append(
            receipts.NliObservation(
                execution.assertion_id,
                execution.execution_id,
                receipts.PlanningPair(**asdict(execution.pair)),
                execution.support_metadata_json,
                execution.assessment_json,
            )
        )
    return tuple(observations), tuple(executions)


def replay(inputs, observations=None, executions=None, **kwargs):
    record, args = deepcopy(inputs)
    if observations is None or executions is None:
        observations, executions = retained(
            support.prepare_fact_support(record, **args)
        )
    return support.reconstruct_fact_support(
        record,
        **args,
        observations=observations,
        actual_executions=executions,
        require_runtime=False,
        **kwargs,
    )


def test_complete_independent_receipts_only_support_the_specified_model_hypotheses(
    inputs,
):
    result = replay(inputs)
    assert result.model_supported is True
    assert len(result.assessments) == 2
    assert result.scope == "specified_hypothesis_model_support_only"
    assert (
        "fact_answer_output_citation_access_and_history_acceptance"
        in result.remaining_gates
    )


@pytest.mark.parametrize(
    "damage",
    [
        "missing_observation",
        "missing_execution",
        "extra_execution",
        "duplicate_id",
        "unknown_assertion",
        "pair",
        "hypothesis",
        "metadata",
        "tokens",
        "raw_supported",
        "raw_margin",
        "capture_kind",
        "execution_id",
    ],
)
def test_full_inventory_pairs_metadata_numeric_and_ids_are_required(inputs, damage):
    record, args = deepcopy(inputs)
    observations, executions = retained(support.prepare_fact_support(record, **args))
    if damage in {"missing_observation", "missing_execution", "extra_execution"}:
        observations = (
            observations[:-1] if damage == "missing_observation" else observations
        )
        executions = (
            executions[:-1]
            if damage == "missing_execution"
            else (
                (*executions, executions[0])
                if damage == "extra_execution"
                else executions
            )
        )
    elif damage == "duplicate_id":
        executions = (
            replace(executions[0], execution_id=executions[1].execution_id),
            *executions[1:],
        )
    elif damage == "unknown_assertion":
        executions = (replace(executions[0], assertion_id="unknown"), *executions[1:])
    elif damage in ("pair", "hypothesis"):
        pair = replace(
            executions[0].pair,
            **(
                {"premise": "shortened actor-only string"}
                if damage == "pair"
                else {"hypothesis": "unrelated"}
            ),
        )
        executions = (replace(executions[0], pair=pair), *executions[1:])
        observations = (replace(observations[0], pair=pair), *observations[1:])
    elif damage == "metadata":
        metadata = json.loads(executions[0].support_metadata_json)
        metadata["revision"] = "unapproved"
        executions = (
            replace(executions[0], support_metadata_json=canonical(metadata)),
            *executions[1:],
        )
        observations = (
            replace(observations[0], support_metadata_json=canonical(metadata)),
            *observations[1:],
        )
    elif damage == "tokens":
        executions = (replace(executions[0], pair_tokens=True), *executions[1:])
    elif damage in ("raw_supported", "raw_margin"):
        raw = json.loads(executions[0].assessment_json)
        raw.update(
            {"logits": [3, 0, -3]}
            if damage == "raw_supported"
            else {"entailment_margin": 100}
        )
        executions = (
            replace(executions[0], assessment_json=canonical(raw)),
            *executions[1:],
        )
        observations = (
            replace(observations[0], assessment_json=canonical(raw)),
            *observations[1:],
        )
    elif damage == "capture_kind":
        executions = (
            replace(executions[0], capture_kind="producer_verified"),
            *executions[1:],
        )
    else:
        observations = (
            replace(observations[0], execution_id="different-retained-call"),
            *observations[1:],
        )
    with pytest.raises(ValueError):
        replay(inputs, observations, executions)


def test_unitonly_receipts_cannot_enter_runtime_replay(inputs):
    record, args = deepcopy(inputs)
    observations, executions = retained(support.prepare_fact_support(record, **args))
    with pytest.raises(ValueError):
        support.reconstruct_fact_support(
            record,
            **args,
            observations=observations,
            actual_executions=executions,
            require_runtime=True,
        )
