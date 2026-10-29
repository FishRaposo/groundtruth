"""The new opt-in quote requires a plan; legacy scope proposals stay unchanged."""

import json
from dataclasses import asdict, replace

from app.evidence_policy import recorded_evidence_policy
from app.services.role_scope_policy import plan_activity_role

from tests.test_activity_role_eligibility998 import actual, transport_plan
from tests.test_native_given_context1002 import boundary


def test_explicit_quote_plan_preserves_the_original_pp_interpretation_record():
    plan = transport_plan()
    policy = recorded_evidence_policy(json.loads(plan.evidence_profile_json))
    for original in plan.requirements:
        if original.kind not in {"owner", "deputy"}:
            continue
        prior = plan_activity_role(
            original, replace(policy, procedure_scope_profile="requested_scope_v1")
        )
        current = plan_activity_role(original, policy, request_plan=plan)
        assert prior is not None and current is not None
        assert asdict(prior) == asdict(current)
        assert prior.record("activity") == current.record("activity")
        assert prior.record("session") == current.record("session")
        assert plan_activity_role(original, policy) is None


def test_native_given_context_cannot_activate_without_its_original_plan():
    record, requirements, _ = boundary()
    policy = recorded_evidence_policy(json.loads(record["evidence_profile_json"]))
    for original in requirements:
        if original.kind not in {"owner", "deputy"}:
            continue
        assert plan_activity_role(original, policy) is None
        interpreted = plan_activity_role(original, policy, request_plan=record)
        assert interpreted is not None
        assert record["question"].split(". Give", 1)[0] in interpreted.disclosure()


def test_fixture_still_uses_the_exact_actual_scope_and_conditions():
    plan = transport_plan()
    assert plan.question == actual()["plan"]["question"]
    assert any(use.condition_ast for use in plan.uses)
