"""Recorded profile versions cannot silently become historical strict profiles."""

import copy
import importlib.util
from pathlib import Path

import pytest
from app.portfolio.comparison import runtime_configuration_error

SPEC = importlib.util.spec_from_file_location(
    "combined_profile_fixtures",
    Path(__file__).with_name("test_combined_profile_tools.py"),
)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


def strict_context():
    settings, response = fixture.settings(), fixture.response()
    settings["procedure_verification_profile"] = "all_units_nli_v1"
    profile = response["provenance"]["answer_selection"]["evidence_profile"]
    profile["contract"] = "evidence-profile-v1"
    profile.pop("procedure_verification_profile")
    return settings, response


@pytest.mark.parametrize(
    "contract,procedure",
    [
        (None, None),
        ("unknown", None),
        ("unknown", "all_units_nli_v1"),
        ("evidence-profile-v2", None),
        ("evidence-profile-v2", "all_units_nli_v1"),
        ("evidence-profile-v1", "source_declared_procedure_copy_v1"),
        ([], None),
        ({"contract": "evidence-profile-v1"}, None),
    ],
)
def test_present_profile_contract_must_have_a_supported_versioned_discriminator(
    contract, procedure
):
    settings, response = strict_context()
    profile = response["provenance"]["answer_selection"]["evidence_profile"]
    if contract is None:
        profile.pop("contract")
    else:
        profile["contract"] = contract
    if procedure is not None:
        profile["procedure_verification_profile"] = procedure
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


@pytest.mark.parametrize("profile", [None, {}, [], "evidence-profile-v1", False])
def test_present_malformed_profiles_are_never_historical_absence(profile):
    settings, response = strict_context()
    for key in (
        "answer_proposal_profile",
        "role_scope_policy",
        "procedure_verification_profile",
    ):
        settings.pop(key)
    response["provenance"]["answer_selection"]["evidence_profile"] = copy.deepcopy(
        profile
    )
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


@pytest.mark.parametrize(
    "field,value",
    [
        ("proposal_profile", None),
        ("proposal_profile", "unknown"),
        ("role_scope_policy", None),
        ("role_scope_policy", "unknown"),
    ],
)
def test_known_version_cannot_hide_malformed_profile_fields_when_expected_unknown(
    field, value
):
    settings, response = strict_context()
    for key in (
        "answer_proposal_profile",
        "role_scope_policy",
        "procedure_verification_profile",
    ):
        settings.pop(key)
    profile = response["provenance"]["answer_selection"]["evidence_profile"]
    if value is None:
        profile.pop(field)
    else:
        profile[field] = value
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


@pytest.mark.parametrize(
    "expected_key",
    ["answer_proposal_profile", "role_scope_policy", "procedure_verification_profile"],
)
def test_entire_profile_absence_fails_when_any_profile_expectation_is_known(
    expected_key,
):
    settings, response = strict_context()
    for key in (
        "answer_proposal_profile",
        "role_scope_policy",
        "procedure_verification_profile",
    ):
        if key != expected_key:
            settings.pop(key)
    response["provenance"]["answer_selection"].pop("evidence_profile")
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


def test_historical_absence_is_compatible_only_without_profile_expectations():
    settings, response = strict_context()
    for key in (
        "answer_proposal_profile",
        "role_scope_policy",
        "procedure_verification_profile",
    ):
        settings.pop(key)
    response["provenance"]["answer_selection"].pop("evidence_profile")
    assert runtime_configuration_error(response, 200, settings, "candidate") is None


@pytest.mark.parametrize("discriminator", [None, "all_units_nli_v1"])
def test_actual_v1_profile_is_compatible_with_strict_settings(discriminator):
    settings, response = strict_context()
    if discriminator is not None:
        response["provenance"]["answer_selection"]["evidence_profile"][
            "procedure_verification_profile"
        ] = discriminator
    assert runtime_configuration_error(response, 200, settings, "candidate") is None


def test_actual_v2_copy_profile_requires_matching_explicit_expectations():
    assert (
        runtime_configuration_error(
            fixture.response(), 200, fixture.settings(), "candidate"
        )
        is None
    )
