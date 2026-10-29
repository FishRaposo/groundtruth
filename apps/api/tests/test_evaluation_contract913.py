"""UNITONLY scorer contract compatibility, never real quality measurements."""

from copy import deepcopy

import pytest
from app.evidence_policy import EvidencePolicy
from app.portfolio.comparison import (
    evidence_profile_matches,
    runtime_configuration_error,
)
from app.portfolio.coverage import canonical_source_snapshot
from app.portfolio.evaluation import score_case
from app.services import staged_output

from tests.test_staged_complete_output import complete_fixture


def policy(reading="contextual_source_v3", quantity="legacy_v1"):
    return EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        reading,
        quantity,
    )


def current_runtime():
    selected = policy().record()
    settings = {
        "reader_null_threshold": 4,
        "reader_model_revision": "UNITONLY-reader",
        "answer_proposal_profile": "qa_plus_source_patterns_v1",
        "role_scope_policy": "ordinary_session_activity_v1",
        "procedure_verification_profile": "source_declared_procedure_copy_v1",
        "source_context_policy": "scoped_note_context_v2",
        "evidence_reading_profile": "contextual_source_v3",
        "quantity_verification_profile": "legacy_v1",
        "answer_selection_mode": "reader",
        "generation_mode": "extractive",
        "answer_support_mode": "local_nli",
        "support_model_revision": "UNITONLY-support",
        "support_min_margin": 2,
        "selection_contract": "requirement-evidence-v5",
    }
    selection = {
        "mode": "reader",
        "threshold": 4,
        "revision": "UNITONLY-reader",
        "contract": "requirement-evidence-v5",
        "evidence_profile": selected,
        "evidence_support": {
            "mode": "local_nli",
            "revision": "UNITONLY-support",
            "minimum_entailment_margin": 2,
        },
    }
    return settings, {
        "execution_mode": "extractive",
        "provenance": {"generation_mode": "extractive", "answer_selection": selection},
        "retrieval_trace": {"refusal_threshold": None},
    }


def scoring_fixture():
    selection, context = complete_fixture()
    from hashlib import sha256

    observed = next(iter(context["source_snapshots"].values()))
    read_sources = [
        {
            **{
                key: observed[key]
                for key in (
                    "document_id",
                    "document_version",
                    "content_hash",
                    "workspace_id",
                )
            },
            "chunk_id": chunk["id"],
            "chunk_hash": sha256(chunk["content"].encode("utf-8")).hexdigest(),
            "condition": observed["metadata"].get("condition"),
            "conflict_group": observed["metadata"].get("conflict_group"),
        }
        for chunk in observed["chunks"]
    ]
    for channel in (
        selection,
        context["query_context"]["provenance"]["answer_selection"],
    ):
        channel["procedure_read_set"]["sources"] = deepcopy(read_sources)
    actual = staged_output.build_output(selection, **context)
    selection[staged_output.CERTIFICATE_FIELD] = actual["certificate"]
    snapshot = deepcopy(next(iter(context["source_snapshots"].values())))
    number = snapshot["document_version"]
    document = {
        "document_id": snapshot["document_id"],
        "versions": {
            str(number): {
                "version_number": number,
                "content_hash": snapshot["content_hash"],
                "content": snapshot["body"],
            }
        },
        "source_snapshots": {str(number): snapshot},
        "owner": "author",
        "workspace_id": snapshot["workspace_id"],
        "visibility": "private",
        "principals": {"author": {"workspace_id": snapshot["workspace_id"]}},
    }
    case = {
        "id": "UNITONLY-913",
        "category": "answerable",
        "score_contract": "coverage-v2",
        "expected_behavior": "answer",
        "question": context["question"],
        "principal": "author",
        "required_facts": [["Frobnicate the token"]],
        "ordered_steps": [["Frobnicate the token"]],
        "forbidden_sources": [],
        "expected_sources": [
            {
                "document_id": "source",
                "version_number": number,
                "content_hash": snapshot["content_hash"],
                "quoted_text": "Frobnicate the token.",
                "acceptable_answer_spans": ["Frobnicate the token."],
            }
        ],
    }
    response = {
        "question": context["question"],
        "answer": actual["answer"],
        "sources": actual["citations"],
        "refused": False,
        "outcome": "answered",
        "provenance": {"generation_mode": "extractive", "answer_selection": selection},
        "retrieval_trace": context["query_context"],
    }
    return case, response, {"source": document}, context


def test_canonical_current_runtime_profile_matches_frozen_settings():
    settings, response = current_runtime()
    assert runtime_configuration_error(response, 200, settings, "candidate") is None


def test_current_procedure_is_scored_by_independent_full_output_replay():
    case, response, documents, _ = scoring_fixture()
    row = score_case(case, response, 200, documents, require_answer_spans=True)
    assert row["procedure_completeness_correct"] is True
    assert row["required_facts_correct"] and row["ordered_steps_correct"]
    assert row["passed"] and row["answer_quality_passed"]


def test_full_independent_source_observation_survives_canonical_mapping():
    _, _, documents, _ = scoring_fixture()
    doc = documents["source"]
    snapshot = next(iter(doc["source_snapshots"].values()))
    version = next(iter(doc["versions"].values()))
    mapped = canonical_source_snapshot(
        doc["document_id"], version, snapshot, doc["workspace_id"]
    )
    for key in ["snapshot_id", "title", "metadata", "chunks"]:
        assert mapped.get(key) == snapshot[key]


@pytest.mark.parametrize(
    "reading,quantity,contract",
    [
        ("contextual_source_v1", "legacy_v1", "requirement-evidence-v3"),
        ("contextual_source_v2", "legacy_v1", "requirement-evidence-v4"),
        ("contextual_source_v2", "literal_source_count_v1", "requirement-evidence-v4"),
        ("contextual_source_v3", "legacy_v1", "requirement-evidence-v5"),
        ("contextual_source_v3", "literal_source_count_v1", "requirement-evidence-v5"),
    ],
)
def test_registry_profiles_match_their_exact_recorded_settings(
    reading, quantity, contract
):
    selected = policy(reading, quantity).record()
    selection = {"contract": contract, "evidence_profile": selected}
    settings = {
        "answer_proposal_profile": "qa_plus_source_patterns_v1",
        "role_scope_policy": "ordinary_session_activity_v1",
        "procedure_verification_profile": "source_declared_procedure_copy_v1",
        "source_context_policy": "scoped_note_context_v2",
        "evidence_reading_profile": reading,
        "quantity_verification_profile": quantity,
        "selection_contract": contract,
    }
    assert evidence_profile_matches(selection, settings)


@pytest.mark.parametrize(
    "field,value",
    [
        ("contract", "evidence-profile-v9"),
        ("requirement_contract", "requirement-evidence-v4"),
        ("request_plan_contract", "staged-request-plan-v2"),
        ("output_contract", "procedure-output-cover-v6"),
        ("scope_document_limit", 128.0),
        ("request_parser_contract", "disabled"),
        ("pattern_limits", {"per_source_requirement": 999, "per_requirement": 16}),
        ("evidence_reading_profile", "contextual_source_v999"),
        ("unexpected", True),
        ("proposal_profile", "qa_only_v1"),
        ("role_scope_policy", "literal_v1"),
    ],
)
def test_new_profile_metadata_cannot_be_accepted_by_version_or_prefix(field, value):
    settings, response = current_runtime()
    response["provenance"]["answer_selection"]["evidence_profile"][field] = value
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


@pytest.mark.parametrize(
    "field,value",
    [
        ("evidence_reading_profile", "contextual_source_v2"),
        ("quantity_verification_profile", "literal_source_count_v1"),
        ("request_parser_mode", "bounded"),
        ("selection_contract", "requirement-evidence-v4"),
    ],
)
def test_recorded_profile_cannot_override_explicit_frozen_settings(field, value):
    settings, response = current_runtime()
    settings[field] = value
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


def test_mixed_selection_and_profile_versions_are_rejected():
    settings, response = current_runtime()
    response["provenance"]["answer_selection"]["contract"] = "requirement-evidence-v4"
    settings["selection_contract"] = "requirement-evidence-v4"
    assert runtime_configuration_error(response, 200, settings, "candidate") is not None


@pytest.mark.parametrize(
    "damage",
    [
        "certificate",
        "retained",
        "body",
        "title",
        "metadata",
        "chunk",
        "authority_missing",
        "profile",
    ],
)
def test_new_producer_claims_never_replace_independent_output_reconstruction(damage):
    case, response, documents, _ = scoring_fixture()
    selection = response["provenance"]["answer_selection"]
    snapshot = next(iter(documents["source"]["source_snapshots"].values()))
    if damage == "certificate":
        selection[staged_output.CERTIFICATE_FIELD] = {"verified": True}
    elif damage == "retained":
        response["retrieval_trace"]["provenance"]["answer_selection"][
            "staged_request_inputs"
        ]["question"] += " altered"
    elif damage == "body":
        snapshot["body"] += " altered"
    elif damage == "title":
        snapshot["title"] += " altered"
    elif damage == "metadata":
        snapshot["metadata"] = {"invented": True}
    elif damage == "chunk":
        snapshot["chunks"][0]["metadata"] = {"invented": True}
    elif damage == "authority_missing":
        documents["source"].pop("source_snapshots")
    else:
        selection["evidence_profile"]["contract"] = "evidence-profile-v999"
    row = score_case(case, response, 200, documents, require_answer_spans=True)
    assert row["procedure_completeness_correct"] is False
    assert not row["passed"] and not row["answer_quality_passed"]


@pytest.mark.parametrize("wrong_label", ["fact", "order"])
def test_valid_integrity_does_not_fabricate_common_fact_or_order_quality(wrong_label):
    case, response, documents, _ = scoring_fixture()
    if wrong_label == "fact":
        case["required_facts"] = [["Invented counter"]]
    else:
        case["ordered_steps"] = [["Frobnicate the token"], ["This complete routine"]]
    row = score_case(case, response, 200, documents, require_answer_spans=True)
    assert row["procedure_completeness_correct"] is True
    assert (
        not row["answer_contract_correct"]
        and not row["answer_quality_passed"]
        and not row["passed"]
    )


def test_new_negative_quality_remains_separate_from_positive_output_proof():
    case, response, documents, _ = scoring_fixture()
    case.update(
        expected_behavior="refuse",
        category="unanswerable",
        expected_sources=[],
        required_facts=[],
        ordered_steps=[],
    )
    response.update(refused=True, outcome="refused", answer=None, sources=[])
    row = score_case(case, response, 200, documents, require_answer_spans=True)
    assert row["passed"] and row["answer_quality_passed"]
    assert row["answer_contract_correct"] is None


def test_online_and_portable_source_mapping_keep_full_independent_replay_inputs():
    from scripts.tests.test_combined_profile_tools import script

    case, response, documents, _ = scoring_fixture()
    doc = documents["source"]
    snapshot = next(iter(doc["source_snapshots"].values()))
    corpus = {
        "manifest": {"schema_version": 2, "principals": doc["principals"]},
        "documents": [
            {
                "id": "source",
                "versions": list(doc["versions"].values()),
                "owner": "author",
                "workspace_id": doc["workspace_id"],
                "visibility": "private",
            }
        ],
    }
    seed = {
        "documents": {
            "source": {
                "document_id": doc["document_id"],
                "versions": {
                    key: {"content_hash": value["content_hash"]}
                    for key, value in doc["versions"].items()
                },
                "verified_publications": [snapshot],
            }
        }
    }
    evaluator = script("evaluate_portfolio_retrieval")
    auditor = script("verify_answer_coverage_delivery")
    mapped = evaluator.map_documents(corpus, seed)
    assert score_case(case, response, 200, mapped, require_answer_spans=True)["passed"]
    report = {
        "source_document_ids": {"source": doc["document_id"]},
        "source_manifest": evaluator.public_source_manifest(mapped),
    }
    portable = auditor.portable_documents(report, corpus)
    assert score_case(case, response, 200, portable, require_answer_spans=True)[
        "passed"
    ]


@pytest.mark.parametrize("missing", ["snapshot_id", "title", "metadata"])
def test_missing_authority_is_never_filled_from_response(
    missing,
):
    case, response, documents, _ = scoring_fixture()
    doc = documents["source"]
    snapshot = deepcopy(next(iter(doc["source_snapshots"].values())))
    snapshot.pop(missing)
    mapped = canonical_source_snapshot(
        doc["document_id"],
        next(iter(doc["versions"].values())),
        snapshot,
        doc["workspace_id"],
    )
    assert "snapshot_id" not in mapped and "title" not in mapped
    doc["source_snapshots"] = {str(mapped["document_version"]): mapped}
    assert (
        score_case(case, response, 200, documents, require_answer_spans=True)[
            "procedure_completeness_correct"
        ]
        is False
    )


@pytest.mark.parametrize(
    "damage", ["snapshot_id", "title", "metadata", "id_alias", "chunk_metadata"]
)
def test_present_full_observation_corruption_is_not_legacy_fallback(damage):
    _, _, documents, _ = scoring_fixture()
    doc = documents["source"]
    snapshot = deepcopy(next(iter(doc["source_snapshots"].values())))
    if damage == "snapshot_id":
        snapshot["snapshot_id"] = True
    elif damage == "title":
        snapshot["title"] = None
    elif damage == "metadata":
        snapshot["metadata"] = None
    elif damage == "id_alias":
        snapshot["id"] = "00000000-0000-0000-0000-000000000999"
    else:
        snapshot["chunks"][0].pop("metadata")
    with pytest.raises(ValueError):
        canonical_source_snapshot(
            doc["document_id"],
            next(iter(doc["versions"].values())),
            snapshot,
            doc["workspace_id"],
        )


def test_actual_version_id_alias_and_metadata_are_detached():
    _, _, documents, _ = scoring_fixture()
    doc = documents["source"]
    snapshot = deepcopy(next(iter(doc["source_snapshots"].values())))
    identifier = snapshot.pop("snapshot_id")
    snapshot["id"] = identifier
    snapshot["metadata"] = {"unitonly": ["retained"]}
    snapshot["chunks"][0]["metadata"] = {"unitonly": ["retained"]}
    mapped = canonical_source_snapshot(
        doc["document_id"],
        next(iter(doc["versions"].values())),
        snapshot,
        doc["workspace_id"],
    )
    assert mapped["snapshot_id"] == identifier
    snapshot["metadata"]["unitonly"].append("changed")
    snapshot["chunks"][0]["metadata"]["unitonly"].append("changed")
    assert mapped["metadata"] == {"unitonly": ["retained"]}
    assert mapped["chunks"][0]["metadata"] == {"unitonly": ["retained"]}
