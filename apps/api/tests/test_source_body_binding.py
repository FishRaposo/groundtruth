"""Body mechanics preserve legacy output; callers own versioned plan proof."""

import pytest
from app.evidence_policy import source_copy_version
from app.services import contextual_source_proof as proof

from tests.test_contextual_source_proof import fixture


@pytest.mark.parametrize(
    "policy",
    [None, "source_declared_argument_copy_v1", "ordinary_source_argument_copy_v1"],
)
def test_bound_body_matches_legacy_validated_plan(policy):
    body, identity, windows, plan, _ = fixture()
    record, requirement, use = proof._plan(plan, "Onyx calibration")
    expected = proof.build_envelope(
        body, identity, "Onyx calibration", plan, windows, source_copy_policy=policy
    )
    actual = proof._build_from_bound_request(
        body,
        identity,
        "Onyx calibration",
        record,
        requirement,
        use,
        windows,
        source_copy_version(policy),
        reading_profile="contextual_source_v2",
    )
    assert actual == expected
    assert actual["requirement"] == requirement
    assert actual["source_body"] == body
    assert actual["envelope_range"] == {"start": 0, "end": len(body)}


def test_legacy_entry_still_rejects_unverified_plan():
    body, identity, windows, plan, _ = fixture()
    record = plan.record()
    record["resolved_request"] = False
    with pytest.raises(proof.SourceGuardError):
        proof.build_envelope(body, identity, "Onyx calibration", record, windows)
