"""Current-v2 request provenance; actual retained capture, UNITONLY QA/NLI."""

import pytest
from app.evidence_policy import reading_version
from app.services.linguistic_requirements import plan_request

from tests.test_linguistic_requirements import actual_capture
from tests.test_linguistic_role_consumer import (
    EvidencePolicy,
    add_source,
    fixture,
    install_role_records,
    mirror,
    plan_activity_role,
    produce,
    rebuild_rows,
)


def actual_v2_data():
    question = (
        "For the ordinary Onyx calibration session, identify the lead and deputy."
    )
    capture = actual_capture(question)
    plan = plan_request(question, capture)
    assert plan.resolved_request
    assert plan.record()["reading_profile"] == "contextual_source_v2"
    data = fixture()
    data["question"] = question
    data["source_snapshots"] = {}
    identifier = add_source(
        data,
        "The archivist leads Onyx calibration. "
        "The clerk is deputy for Onyx calibration.",
        1,
    )
    data["request_reconstructor"] = lambda actual, context: plan
    selection = data["selection"]
    selection["request_plan"] = plan.record()
    selection["request_capture"] = capture
    profile = selection["evidence_profile"]
    policy = EvidencePolicy(
        profile["proposal_profile"],
        profile["role_scope_policy"],
        profile["procedure_verification_profile"],
        profile["source_context_policy"],
        "contextual_source_v2",
    )
    effective = {
        req.id: (plan_activity_role(req, policy).prepared("activity"), {})
        for req in plan.requirements
    }
    rebuild_rows(
        data,
        effective,
        {"r1": (identifier, "The archivist"), "r2": (identifier, "The clerk")},
    )
    install_role_records(data, plan.requirements[0])
    data["request_reconstructor"] = None
    return data


def test_current_profile_uses_actual_capture_and_original_workspace_authority():
    data = actual_v2_data()
    actual = produce(data)
    assert (
        actual["certificate"]["contract"]
        == reading_version("contextual_source_v2").output
    )
    assert all(
        row["source_workspace"] is None for row in data["selection"]["requirements"]
    )
    assert all(
        source["workspace_id"] == "ops-a"
        for source in data["source_snapshots"].values()
    )


@pytest.mark.parametrize("mutation", ["missing", "source-workspace", "other-workspace"])
def test_current_profile_cannot_replace_original_constraint_from_source_receipt(
    mutation,
):
    data = actual_v2_data()
    assert produce(data)["answer"]
    row = data["selection"]["requirements"][0]
    if mutation == "missing":
        row.pop("source_workspace")
    else:
        row["source_workspace"] = "ops-a" if mutation == "source-workspace" else "ops-b"
    mirror(data)
    with pytest.raises((ValueError, KeyError)):
        produce(data)
