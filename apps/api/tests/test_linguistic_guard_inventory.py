"""Every retained assessed procedure guard must participate in actual replay."""

from copy import deepcopy

import pytest

from tests.test_contextual_mixed_output import consumer_fixture, mirror, produce


@pytest.mark.parametrize(
    "change", ["unbound_source", "unknown_requirement", "duplicate"]
)
def test_extra_assessed_guard_records_cannot_escape_authoritative_replay(change):
    data = consumer_fixture()
    orphan = deepcopy(data["selection"]["source_guard_records"][0])
    if change == "unbound_source":
        orphan["source_identity"]["document_id"] = "unbound-assessed-source"
        orphan["nli_assessments"][0]["assessment"]["pair_tokens"] = True
    elif change == "unknown_requirement":
        orphan["requirement_id"] = "not-in-the-request"
    data["selection"]["source_guard_records"].append(orphan)
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_valid_but_unbound_source_guard_still_needs_an_authoritative_snapshot():
    from app.services.contextual_source_proof import build_envelope
    from app.services.linguistic_requirements import plan_request

    data = consumer_fixture()
    selection = data["selection"]
    plan = plan_request(data["question"], selection["request_capture"])
    orphan = deepcopy(selection["source_guard_records"][0])
    orphan["source_identity"]["document_id"] = "00000000-0000-0000-0000-000000000099"
    snapshot = next(iter(data["source_snapshots"].values()))
    inventory = build_envelope(
        snapshot["body"],
        orphan["source_identity"],
        plan.requirements[0].topic,
        plan,
        orphan["source_windows"],
    )
    assessment = deepcopy(orphan["nli_assessments"][0]["assessment"])
    orphan["envelope_inventory"] = inventory
    orphan["nli_assessments"] = [
        {**row, "assessment": deepcopy(assessment)}
        for row in inventory["nli_obligations"]
    ]
    selection["source_guard_records"].append(orphan)
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)
