"""Actual654 CPU request capture; synthetic source, no NLI/quality claim."""

import json
from pathlib import Path

from app.services.linguistic_requirements import plan_request
from app.services.requirement_binding import support_claim


def requirement():
    data = json.loads(
        (
            Path(__file__).parent / "fixtures/quantity-request-capture-v654.json"
        ).read_text()
    )
    return plan_request(data["question"], data["capture"]).requirements[0]


def test_fronted_activity_scope_survives_count_hypothesis():
    req = requirement()
    body = "There are 4 tokens assigned to Copper alignment."
    start = body.index("4")
    claim = support_claim(
        req, body, start, start + 1, reading_profile="contextual_source_v2"
    )
    assert claim.rejection is None
    assert claim.hypothesis == "The token count for Copper alignment is 4"
    assert claim.value == "4" and claim.premise == body


def test_legacy_contract_does_not_gain_new_fronted_count_grammar():
    req = requirement()
    body = "There are 4 tokens assigned to Copper alignment."
    start = body.index("4")
    claim = support_claim(
        req, body, start, start + 1, reading_profile="contextual_source_v1"
    )
    assert claim.rejection is not None
