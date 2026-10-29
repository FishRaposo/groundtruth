"""Projected actual1023 failure; restored producer role statuses are not API success."""

import gzip
import json
from copy import deepcopy
from pathlib import Path

import pytest
from app.evidence_policy import recorded_evidence_policy
from app.services.requirement_contract import validate_role_scope_evidence


@pytest.fixture
def selection():
    path = Path(__file__).parent / "fixtures" / "role-certificate1030.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def _bounded(selection):
    return next(
        unit
        for context in selection["role_scope_findings"][0]["contexts"]
        for unit in context["units"]
        if unit["disposition"] == "non_role_assertion_under_bounded_inspection"
    )


def test_actual_selected_v4_bounded_inspection_is_truthful_lineage(selection):
    before = deepcopy(selection)
    assert validate_role_scope_evidence(selection) == {
        "status": "recorded",
        "valid": True,
    }
    assert selection == before


@pytest.mark.parametrize(
    "mutation",
    [
        "method",
        "captures",
        "relatedness",
        "claim",
        "unknown",
        "missing_unit",
        "window",
        "duplicate",
    ],
)
def test_bounded_role_lineage_does_not_accept_forged_or_missing_proofs(
    selection, mutation
):
    finding = selection["role_scope_findings"][0]
    unit = _bounded(selection)
    if mutation == "method":
        finding["inspection_method"] = "unknown"
    elif mutation == "captures":
        finding["source_closures"] = []
    elif mutation == "relatedness":
        unit["semantic_relatedness"] = "entailed"
    elif mutation == "claim":
        unit["explicit_inspection"] = "source_has_no_roles"
    elif mutation == "unknown":
        unit["disposition"] = "unknown"
    elif mutation == "missing_unit":
        finding["contexts"][0]["units"].pop(0)
    elif mutation == "window":
        finding["source_closures"][0]["source_capture"]["source_windows"] = []
    else:
        finding["source_closures"].append(deepcopy(finding["source_closures"][0]))
    assert validate_role_scope_evidence(selection)["valid"] is False


def test_bounded_role_type_cannot_be_transplanted_into_unselected_history(selection):
    from dataclasses import replace

    policy = recorded_evidence_policy(selection["evidence_profile"])
    selection["evidence_profile"] = replace(
        policy,
        source_governance_profile="all_sources_v1",
        procedure_scope_profile="requested_scope_v1",
    ).record()
    assert validate_role_scope_evidence(selection)["valid"] is False
