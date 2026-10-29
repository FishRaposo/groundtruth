"""Selected source COPY must replay its own opt-in ownership, not old flags."""

from dataclasses import asdict

from app.services import staged_source_proof as consumer

from tests.test_declared_copy_consumer958 import prepared


def test_source_bound_consumer_independently_rebuilds_selected_copy_ownership():
    snapshot, windows, requirement, _plan, kwargs = prepared()
    envelope = consumer.build_envelope(
        snapshot.body, asdict(snapshot.identity), requirement.topic, windows, **kwargs
    )
    owner = envelope["reference_inventory"]["captured_source_ownership"]
    assert owner["source_governance_profile"] == "requirement_bound_v1"
    assert (
        owner["ownership_scope"] == "complete_literal_selected_source_not_action_truth"
    )
    assert envelope["source_body"] == snapshot.body
    assert envelope["nli_obligations"]
    assert envelope["pending_external_checks"]
