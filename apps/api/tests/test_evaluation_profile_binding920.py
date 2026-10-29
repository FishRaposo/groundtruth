"""UNITONLY new-contract profile binding; historical profiles stay historical."""

import pytest
from app.evidence_policy import EvidencePolicy
from app.portfolio.comparison import (
    evidence_profile_matches,
    runtime_configuration_error,
)

from tests.test_evaluation_contract913 import current_runtime

READINGS = (
    ("contextual_source_v1", "requirement-evidence-v3"),
    ("contextual_source_v2", "requirement-evidence-v4"),
    ("contextual_source_v3", "requirement-evidence-v5"),
)


def runtime(reading="contextual_source_v3", *, quantity="legacy_v1", full=False):
    settings, response = current_runtime()
    policy = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        reading,
        quantity,
    )
    selection = response["provenance"]["answer_selection"]
    selection["contract"] = policy.requirement_contract
    selection["evidence_profile"] = policy.record()
    settings.update(
        selection_contract=policy.requirement_contract,
        evidence_reading_profile=reading,
        quantity_verification_profile=quantity,
        request_parser_mode=(
            "bounded" if reading == "contextual_source_v1" else "local_dependency"
        ),
    )
    if not full:
        for key in (
            "evidence_reading_profile",
            "quantity_verification_profile",
            "request_parser_mode",
        ):
            settings.pop(key)
    return settings, response, selection


@pytest.mark.parametrize("reading,contract", READINGS)
@pytest.mark.parametrize("full", [False, True])
@pytest.mark.parametrize(
    "damage", ["legacy_profile", "profile_missing", "reading_missing"]
)
def test_new_selection_cannot_downgrade_to_legacy_profile(
    reading, contract, full, damage
):
    settings, response, selection = runtime(reading, full=full)
    assert selection["contract"] == contract
    if damage == "legacy_profile":
        selection["evidence_profile"] = EvidencePolicy(
            "qa_plus_source_patterns_v1",
            "ordinary_session_activity_v1",
            "source_declared_procedure_copy_v1",
            "scoped_note_context_v2",
        ).record()
    elif damage == "profile_missing":
        selection.pop("evidence_profile")
    else:
        selection["evidence_profile"].pop("evidence_reading_profile")
    assert not evidence_profile_matches(selection, settings)
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


@pytest.mark.parametrize(
    "reading,quantity",
    [(reading, "legacy_v1") for reading, _ in READINGS]
    + [
        ("contextual_source_v2", "literal_source_count_v1"),
        ("contextual_source_v3", "literal_source_count_v1"),
    ],
)
def test_canonical_new_profiles_pass_without_optional_frozen_fields(reading, quantity):
    settings, response, _ = runtime(reading, quantity=quantity)
    assert runtime_configuration_error(response, 200, settings, "candidate") is None


@pytest.mark.parametrize("reading,contract", READINGS)
@pytest.mark.parametrize(
    "field",
    [
        "requirement_contract",
        "request_plan_contract",
        "scope_cover_contract",
        "role_manifest_contract",
        "procedure_contract",
        "output_contract",
        "scope_document_limit",
        "pattern_registry_contract",
    ],
)
def test_new_profile_requires_complete_protocol_record(reading, contract, field):
    settings, response, selection = runtime(reading)
    assert selection["contract"] == contract
    selection["evidence_profile"].pop(field)
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


@pytest.mark.parametrize("reading", ["contextual_source_v2", "contextual_source_v3"])
@pytest.mark.parametrize("field", ["request_parser_mode", "request_parser_contract"])
def test_dependency_profiles_require_parser_protocol_fields(reading, field):
    settings, response, selection = runtime(reading)
    selection["evidence_profile"].pop(field)
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


@pytest.mark.parametrize("reading", ["contextual_source_v2", "contextual_source_v3"])
@pytest.mark.parametrize(
    "field", ["quantity_binding_contract", "quantity_verification_profile"]
)
def test_count_profiles_cannot_omit_quantity_protocol_fields(reading, field):
    settings, response, selection = runtime(reading, quantity="literal_source_count_v1")
    selection["evidence_profile"].pop(field)
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


@pytest.mark.parametrize("reading,contract", READINGS)
def test_new_contract_and_reading_identity_must_agree_without_frozen_controls(
    reading, contract
):
    _, response, selection = runtime(reading)
    selection["contract"] = (
        "requirement-evidence-v4"
        if contract == "requirement-evidence-v5"
        else "requirement-evidence-v5"
    )
    assert not evidence_profile_matches(selection, {})
    assert (
        runtime_configuration_error(
            response, 200, {}, "candidate", require_reader=False
        )
        is not None
    )


@pytest.mark.parametrize(
    "contract", ["requirement-evidence-v1", "requirement-evidence-v2"]
)
@pytest.mark.parametrize(
    "field", ["origin_contract", "pattern_registry_contract", "pattern_limits"]
)
def test_historical_metadata_limits_are_preserved(contract, field):
    settings, response, selection = runtime()
    selection["contract"] = contract
    settings["selection_contract"] = contract
    selection["evidence_profile"] = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
    ).record()
    selection["evidence_profile"][field] = "inherited-unvalidated-metadata"
    assert runtime_configuration_error(response, 200, settings, "candidate") is None


@pytest.mark.parametrize(
    "contract", ["requirement-evidence-v1", "requirement-evidence-v2"]
)
def test_historical_absence_and_minimal_profile_compatibility_are_preserved(contract):
    selection = {"contract": contract}
    assert evidence_profile_matches(selection, {})
    selection["evidence_profile"] = {
        "contract": "evidence-profile-v1",
        "proposal_profile": "qa_plus_source_patterns_v1",
        "role_scope_policy": "ordinary_session_activity_v1",
    }
    assert evidence_profile_matches(selection, {})
