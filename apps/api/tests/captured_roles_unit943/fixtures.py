"""No models, SQL, or runtime attestation: actual syntax and UNITONLY logits."""

from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

from app.services.captured_plan_inputs import capture_inputs_v2

from tests.captured_inputs_unit932.fixtures import authoritative
from tests.captured_plan_unit937.test_adversarial import supported
from tests.planning_library_unit830.test_support import retained


def context(name="labels"):
    args, plan = supported(name)
    record = capture_inputs_v2(**args)
    return plan, {
        "question": args["question"],
        "planning_inputs": record,
        "retained_inputs": deepcopy(record),
        "authoritative_snapshots": authoritative(record),
        "require_runtime": False,
    }


def factual_receipts(prepared, kind="positive"):
    """Explicit UNITONLY logits, never a model/tokenizer execution."""
    observations, executions = retained(
        SimpleNamespace(
            assertions=prepared.checks,
            support_metadata_json=prepared.support_metadata_json,
        ),
        kind,
    )
    prefix = "UNITONLY943:" + prepared.bound_requirement.id + ":"
    return (
        tuple(
            replace(r, execution_id=prefix + str(i)) for i, r in enumerate(observations)
        ),
        tuple(
            replace(r, execution_id=prefix + str(i)) for i, r in enumerate(executions)
        ),
    )


def fact(inputs, identifier, kind="positive"):
    from app.services import captured_role_evidence as role

    prepared = role.prepare_role_evidence(requirement_id=identifier, **inputs)
    observations, executions = factual_receipts(prepared, kind)
    return role.reconstruct_role_evidence(
        requirement_id=identifier,
        proposal_id=prepared.proposals[0].proposal_id,
        observations=observations,
        actual_executions=executions,
        **inputs,
    )


def labels_selection():
    """All actual labels requirements, only simulated numeric NI receipts."""
    from app.services import captured_role_consumer as consumer

    plan, inputs = context("labels")
    evidence = {r.id: fact(inputs, r.id) for r in plan.requirements}
    views = [consumer.view(e) for e in evidence.values()]
    selection = {
        "candidates": [consumer.candidate(e) for e in evidence.values()],
        "proposals": [p for _, g, _, _, _ in views for p in g["origins"]],
        "pattern_observations": [o for _, _, o, _, _ in views],
        "qa_observations": [],
    }
    return plan, inputs, selection, evidence
