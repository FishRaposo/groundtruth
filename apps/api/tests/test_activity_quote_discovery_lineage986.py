"""Recorded quote interpretation must survive strict discovery metadata replay."""

from copy import deepcopy
from dataclasses import replace
from functools import cache

import pytest
from app.evidence_policy import recorded_evidence_policy
from app.services.requirement_contract import validate_discovery_lineage

from tests.test_captured_proposal_lineage948 import selection


@cache
def quote_selection():
    value = selection()
    policy = replace(
        recorded_evidence_policy(value["evidence_profile"]),
        source_governance_profile="requirement_bound_v1",
        procedure_scope_profile="activity_quote_v1",
    )
    value["evidence_profile"] = policy.record()
    return value


def test_canonical_recorded_activity_quote_does_not_fail_discovery_lineage():
    assert validate_discovery_lineage(quote_selection()) == {
        "status": "recorded",
        "valid": True,
    }


@pytest.mark.parametrize(
    "damage",
    ["unknown", "missing_contract", "missing_profile", "extra", "mixed_old", "origin"],
)
def test_quote_profile_and_origin_damage_still_fail_closed(damage):
    value = deepcopy(quote_selection())
    profile = value["evidence_profile"]
    if damage == "unknown":
        profile["procedure_scope_profile"] = "unknown"
    elif damage == "missing_contract":
        del profile["procedure_scope_contract"]
    elif damage == "missing_profile":
        del profile["procedure_scope_profile"]
    elif damage == "extra":
        profile["unknown_interpretation"] = True
    elif damage == "mixed_old":
        profile["procedure_scope_profile"] = "requested_scope_v1"
    else:
        value["proposals"][0]["pattern_id"] = "unrecognized-pattern"
    assert validate_discovery_lineage(value)["valid"] is False
