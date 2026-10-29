"""Known v5 privacy representations; synthetic UNITONLY, never corpus scoring."""

import json
from copy import deepcopy

import pytest
from app.portfolio import coverage
from app.portfolio.evaluation import score_case

from tests.test_evaluation_contract913 import scoring_fixture


@pytest.fixture(scope="module")
def original():
    return scoring_fixture()


def negative(original, *, retained=False, forbidden=True):
    case, response, documents, _ = deepcopy(original)
    actual = response["provenance"]["answer_selection"]
    base = {key: actual[key] for key in ("contract", "evidence_profile", "mode")}
    response.update(answer="", sources=[], refused=True, outcome="refused")
    response["provenance"]["answer_selection"] = deepcopy(base)
    response["retrieval_trace"] = {
        "scores": [],
        "provenance": {"answer_selection": deepcopy(base)},
    }
    case.update(
        category="unanswerable",
        expected_behavior="refuse",
        required_facts=[],
        ordered_steps=[],
        expected_sources=[],
        forbidden_sources=[
            {
                "document_id": "source",
                "version_number": actual["staged_request_inputs"]["manifest"][
                    "publications"
                ][0]["document_version"],
            }
        ]
        if forbidden
        else [],
    )
    channel = (
        response["retrieval_trace"]["provenance"]["answer_selection"]
        if retained
        else response["provenance"]["answer_selection"]
    )
    identity = deepcopy(actual["staged_request_inputs"]["manifest"]["publications"][0])
    return case, response, documents, channel, identity, actual


def scored(case, response, documents):
    return score_case(case, response, 200, documents, require_answer_spans=True)


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize(
    "field",
    [
        "qa_observations",
        "role_scope_findings",
        "role_scope_interpretations",
        "conflicts",
        "candidates",
        "proposals",
        "pattern_observations",
    ],
)
def test_all_known_flat_and_nested_source_channels_count(original, retained, field):
    case, response, docs, channel, identity, _ = negative(original, retained=retained)
    channel[field] = [identity]
    row = scored(case, response, docs)
    assert row["unauthorized_source_exposures"] == 1
    assert not row["passed"] and not row["answer_quality_passed"]


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize(
    "field", ["procedure_read_set", "role_scope_read_set", "citation_selection"]
)
def test_known_read_sets_and_citation_selection_are_checked(original, retained, field):
    case, response, docs, channel, identity, _ = negative(original, retained=retained)
    channel[field] = {"sources": [identity]}
    row = scored(case, response, docs)
    assert row["unauthorized_source_exposures"] == 1
    assert not row["passed"]


@pytest.mark.parametrize(
    "field",
    [
        "read_set_json",
        "scope_bridge_json",
        "effective_candidate_json",
        "planning_support_json",
    ],
)
@pytest.mark.parametrize("retained", [False, True])
def test_declared_nested_json_is_not_hidden_inside_requirement_proofs(
    original, field, retained
):
    case, response, docs, channel, _, actual = negative(original, retained=retained)
    channel["requirements"] = [
        {"id": "UNITONLY", "retained_proof": {field: actual["request_plan"][field]}}
    ]
    row = scored(case, response, docs)
    assert row["unauthorized_source_exposures"] >= 1
    assert not row["passed"]


@pytest.mark.parametrize("retained", [False, True])
def test_typed_source_use_json_carries_its_own_source_identity(original, retained):
    case, response, docs, channel, identity, _ = negative(original, retained=retained)
    channel["requirements"] = [
        {"bound_requirement": {"source_uses_json": json.dumps([{"source": identity}])}}
    ]
    assert scored(case, response, docs)["unauthorized_source_exposures"] == 1


@pytest.mark.parametrize("retained", [False, True])
def test_sql_publication_transport_counts_actual_document_records(original, retained):
    case, response, docs, channel, identity, _ = negative(original, retained=retained)
    channel["requirements"] = [
        {
            "sql_read_set_json": json.dumps(
                {
                    "contract": "request-planning-publications-v1",
                    "selection_mode": "all_authorized_publications_v1",
                    "documents": [identity],
                }
            )
        }
    ]
    assert scored(case, response, docs)["unauthorized_source_exposures"] == 1


def test_both_channels_and_repeated_proof_members_deduplicate_document_version(
    original,
):
    case, response, docs, channel, identity, actual = negative(original)
    channel["staged_request_inputs"] = actual["staged_request_inputs"]
    channel["source_guard_records"] = actual["source_guard_records"]
    channel["inspected_sources"] = [identity, deepcopy(identity)]
    response["retrieval_trace"]["provenance"]["answer_selection"] = deepcopy(channel)
    assert scored(case, response, docs)["unauthorized_source_exposures"] == 1


@pytest.mark.parametrize("retained", [False, True])
def test_authorized_retained_and_presented_members_stay_zero(original, retained):
    case, response, docs, channel, _, actual = negative(
        original, retained=retained, forbidden=False
    )
    channel.update(actual)
    for source in channel["procedure_read_set"]["sources"]:
        source.update(
            {
                key: channel["staged_request_inputs"]["manifest"]["publications"][0][
                    key
                ]
                for key in (
                    "document_id",
                    "document_version",
                    "content_hash",
                    "workspace_id",
                )
            }
        )
    row = scored(case, response, docs)
    assert row["unauthorized_source_exposures"] == 0
    assert row["passed"] and row["answer_quality_passed"]


def test_retained_v5_marker_prevents_presented_legacy_downgrade(original):
    case, response, docs, _, identity, _ = negative(original, retained=True)
    response["provenance"]["answer_selection"] = {"inspected_sources": [identity]}
    assert scored(case, response, docs)["unauthorized_source_exposures"] == 1


@pytest.mark.parametrize(
    "field", ["body", "metadata_json", "capture_json", "graph_json", "arbitrary_json"]
)
def test_literal_and_opaque_metadata_strings_are_never_parsed_for_identities(
    original, field
):
    case, response, docs, channel, identity, _ = negative(original)
    channel["requirements"] = [{field: json.dumps(identity)}]
    row = scored(case, response, docs)
    assert row["unauthorized_source_exposures"] == 0
    assert row["passed"]


def test_source_free_pattern_budget_stays_clean(original):
    case, response, docs, channel, _, _ = negative(original)
    channel["pattern_observations"] = [
        {
            "requirement_id": "UNITONLY",
            "origin": "source_pattern",
            "decision": "pattern_requirement_budget_exceeded",
            "observed_count": 17,
            "complete": False,
            "truncated": True,
        }
    ]
    assert scored(case, response, docs)["passed"]


@pytest.mark.parametrize(
    "damage",
    [
        "inputs_unknown",
        "plan_unknown",
        "inputs_incomplete",
        "plan_incomplete",
        "guard_incomplete",
        "flat_identity_missing",
        "read_set_unknown",
        "read_set_incomplete",
        "read_set_duplicate",
        "read_set_not_object",
        "native_nonfinite",
        "native_tuple",
        "invalid_version",
        "missing_version",
    ],
)
def test_malformed_known_proof_cannot_pass_as_clean_refusal(original, damage):
    case, response, docs, channel, identity, actual = negative(original)
    if damage.startswith("inputs_"):
        channel["staged_request_inputs"] = deepcopy(actual["staged_request_inputs"])
        if damage.endswith("unknown"):
            channel["staged_request_inputs"]["contract"] = "staged-request-inputs-v999"
        else:
            channel["staged_request_inputs"] = {"contract": "staged-request-inputs-v1"}
    elif damage.startswith("plan_"):
        channel["request_plan"] = deepcopy(actual["request_plan"])
        if damage.endswith("unknown"):
            channel["request_plan"]["contract"] = "staged-request-plan-v999"
        else:
            channel["request_plan"] = {"contract": "staged-request-plan-v1"}
    elif damage == "guard_incomplete":
        channel["source_guard_records"] = [{}]
    elif damage == "flat_identity_missing":
        channel["inspected_sources"] = [{}]
    elif damage.startswith("read_set_"):
        encoded = {
            "read_set_unknown": '{"contract":"request-planning-read-set-v999"}',
            "read_set_incomplete": '{"contract":"request-planning-read-set-v1"}',
            "read_set_duplicate": (
                '{"contract":"request-planning-read-set-v999",'
                '"contract":"request-planning-read-set-v1"}'
            ),
            "read_set_not_object": "[]",
        }[damage]
        channel["requirements"] = [{"read_set_json": encoded}]
    elif damage in ("native_nonfinite", "native_tuple"):
        channel["requirements"] = [
            {
                "unknown": {
                    "native_nonfinite": float("nan"),
                    "native_tuple": (1,),
                }[damage]
            }
        ]
    else:
        if damage == "invalid_version":
            identity["document_version"] = True
        else:
            identity.pop("document_version")
        channel["inspected_sources"] = [identity]
    row = scored(case, response, docs)
    assert not row["passed"] and not row["answer_quality_passed"]
    assert row["execution_error"] and not row["source_exposure_inspection_complete"]


def test_declared_json_has_a_bounded_decoding_budget(original, monkeypatch):
    case, response, docs, channel, _, actual = negative(original)
    channel["requirements"] = [
        {"read_set_json": actual["request_plan"]["read_set_json"]}
    ]
    monkeypatch.setattr(coverage, "_EXPOSURE_JSON_BYTES", 16)
    row = scored(case, response, docs)
    assert not row["passed"] and row["execution_error"]
    assert not row["source_exposure_inspection_complete"]


def test_malformed_channel_does_not_hide_known_exposure_in_other_channel(original):
    case, response, docs, channel, identity, _ = negative(original)
    channel["staged_request_inputs"] = {"contract": "future"}
    response["retrieval_trace"]["provenance"]["answer_selection"][
        "inspected_sources"
    ] = [identity]
    row = scored(case, response, docs)
    assert row["unauthorized_source_exposures"] == 1
    assert not row["source_exposure_inspection_complete"] and row["execution_error"]
    assert not row["passed"]


def test_restoring_unrelated_read_set_identity_is_rejected(original):
    case, response, docs, channel, _, actual = negative(original, forbidden=False)
    channel["procedure_read_set"] = deepcopy(actual["procedure_read_set"])
    channel["procedure_read_set"]["sources"][0].update(
        document_id="00000000-0000-0000-0000-000000000001", document_version=3
    )
    row = scored(case, response, docs)
    assert row["source_exposure_inspection_complete"]
    assert row["unauthorized_source_exposures"] == 1
    assert not row["passed"] and not row["answer_quality_passed"]


def test_native_json_nesting_budget_is_enforced(original):
    case, response, docs, channel, _, _ = negative(original)
    nested = {}
    for _ in range(34):
        nested = {"child": nested}
    channel["requirements"] = [nested]
    row = scored(case, response, docs)
    assert not row["passed"] and row["execution_error"]


@pytest.mark.parametrize(
    "contract", ["requirement-evidence-v1", "requirement-evidence-v2"]
)
def test_unmarked_legacy_retained_channels_keep_historical_semantics(
    original, contract
):
    case, response, docs, _, identity, _ = negative(original)
    response["provenance"]["answer_selection"] = {"contract": contract}
    response["retrieval_trace"]["provenance"]["answer_selection"] = {
        "contract": contract,
        "inspected_sources": [identity],
    }
    row = scored(case, response, docs)
    assert row["unauthorized_source_exposures"] == 0 and row["passed"]


@pytest.mark.parametrize("damage", ["contract", "profile", "missing_profile"])
def test_unknown_or_missing_known_v5_policy_cannot_qualify_negative(original, damage):
    case, response, docs, channel, _, _ = negative(original, forbidden=False)
    if damage == "contract":
        channel["contract"] = "requirement-evidence-v999"
    elif damage == "profile":
        channel["evidence_profile"]["contract"] = "evidence-profile-v999"
    else:
        channel.pop("evidence_profile")
    row = scored(case, response, docs)
    assert not row["passed"] and row["execution_error"]
    assert not row["source_exposure_inspection_complete"]


@pytest.mark.parametrize(
    "certificate",
    [
        {"contract": "procedure-output-cover-v8"},
        {"contract": "procedure-output-cover-v999"},
        {"verified": True},
    ],
)
def test_partial_or_unknown_certificate_cannot_qualify_negative(original, certificate):
    case, response, docs, channel, _, _ = negative(original, forbidden=False)
    channel["staged_output_certificate"] = certificate
    row = scored(case, response, docs)
    assert not row["passed"] and row["execution_error"]
    assert not row["source_exposure_inspection_complete"]
