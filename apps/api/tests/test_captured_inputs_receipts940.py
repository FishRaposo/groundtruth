"""Finite receipt containers retain every raw row; never traverse iterables."""

import json
from copy import deepcopy
from dataclasses import asdict

import pytest
from app.services import captured_plan_inputs as transport
from app.services import planning_support as support

from tests.captured_inputs_unit932.fixtures import arguments, authoritative, profile


class MustNotIterate:
    def __iter__(self):
        raise AssertionError("Unsupported receipt container was iterated")


class ListSubclass(list):
    def __iter__(self):
        raise AssertionError("Receipt subclass must not override finite traversal")


class TupleSubclass(tuple):
    def __iter__(self):
        raise AssertionError("Receipt subclass must not override finite traversal")


@pytest.mark.parametrize("field", ["observations", "actual_executions"])
@pytest.mark.parametrize(
    "container",
    [MustNotIterate, ListSubclass, TupleSubclass, dict, set, str, lambda: None],
    ids=["iterable", "list-subclass", "tuple-subclass", "dict", "set", "str", "none"],
)
def test_unsupported_receipt_containers_reject_before_iteration(field, container):
    args = arguments()
    args[field] = container()
    with pytest.raises(ValueError, match="receipt containers"):
        transport.capture_inputs_v2(**args, evidence_profile=profile())


def receipts():
    observations, executions = [], []
    for number in (1, 2):
        identity = f"UNITONLY940-unassessed-{number}"
        pair = support.PlanningPair(identity, identity, identity, identity)
        assessment = json.dumps({"unassessed_raw_value": number})
        observations.append(
            support.NliObservation(identity, identity, pair, "{}", assessment)
        )
        executions.append(
            support.NliExecution(
                identity, identity, pair, "{}", assessment, number, "UNITONLY940"
            )
        )
    return observations, executions


@pytest.mark.parametrize("observation_type", [list, tuple], ids=["list", "tuple"])
@pytest.mark.parametrize("execution_type", [list, tuple], ids=["list", "tuple"])
def test_finite_containers_keep_all_receipts_order_and_unassessed_values(
    observation_type, execution_type
):
    observations, executions = receipts()
    args = arguments()
    args.update(
        observations=observation_type(observations),
        actual_executions=execution_type(executions),
    )
    before = deepcopy(args)
    record = transport.capture_inputs_v2(**args, evidence_profile=profile())
    assert record["observations"] == [asdict(row) for row in observations]
    assert record["actual_executions"] == [asdict(row) for row in executions]
    decoded = transport.decode_inputs_v2(
        record,
        question=args["question"],
        authoritative_snapshots=authoritative(record),
        retained_inputs=deepcopy(record),
    )
    assert decoded.arguments["observations"] == tuple(observations)
    assert decoded.arguments["actual_executions"] == tuple(executions)
    assert args == before
    assert not decoded.request_productions["complete_plan"]
    assert not decoded.source_productions["full_plan_accepted"]
    observations.clear()
    executions.clear()
    assert len(record["observations"]) == len(record["actual_executions"]) == 2
