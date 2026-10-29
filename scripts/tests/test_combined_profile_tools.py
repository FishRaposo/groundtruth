"""Public tooling contracts over invented sources; no server or model quality claim."""

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import httpx
import pytest
from app.portfolio.comparison import (
    check_measured_settings,
    check_response_configuration,
    validate_runtime_settings,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILE = "source_declared_procedure_copy_v1"
DOC = "11111111-1111-4111-8111-111111111111"
CHUNK = "22222222-2222-4222-8222-222222222222"


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def settings():
    return {
        "top_k": 5,
        "reader_null_threshold": 4,
        "reader_model_revision": "reader-pin",
        "answer_proposal_profile": "qa_only_v1",
        "role_scope_policy": "literal_v1",
        "answer_support_mode": "local_nli",
        "support_model_revision": "support-pin",
        "support_min_margin": 3,
        "selection_contract": "requirement-evidence-v2",
        "procedure_verification_profile": PROFILE,
        "answer_selection_mode": "reader",
        "generation_mode": "extractive",
    }


def response():
    expected = settings()
    return {
        "execution_mode": "extractive",
        "retrieval_trace": {"refusal_threshold": None},
        "provenance": {
            "generation_mode": "extractive",
            "answer_selection": {
                "mode": "reader",
                "threshold": 4,
                "revision": "reader-pin",
                "contract": "requirement-evidence-v2",
                "evidence_profile": {
                    "contract": "evidence-profile-v2",
                    "proposal_profile": "qa_only_v1",
                    "role_scope_policy": "literal_v1",
                    "procedure_verification_profile": PROFILE,
                },
                "evidence_support": {
                    "mode": "local_nli",
                    "revision": "support-pin",
                    "minimum_entailment_margin": expected["support_min_margin"],
                },
            },
        },
    }


@pytest.mark.parametrize("actual", [None, "all_units_nli_v1", "invented"])
def test_actual_profile_must_match_explicit_new_profile(actual):
    observed = response()
    profile = observed["provenance"]["answer_selection"]["evidence_profile"]
    if actual is None:
        profile.pop("procedure_verification_profile")
    else:
        profile["procedure_verification_profile"] = actual
    row = {"passed": True, "answer_quality_passed": True, "execution_error": False}
    check_response_configuration(row, observed, 200, settings(), "candidate")
    assert row.get("configuration_error") and row["execution_error"]
    assert not row["passed"] and not row["answer_quality_passed"]


def test_unrecorded_new_profile_cannot_expand_legacy_strict_run():
    expected = settings()
    expected.pop("procedure_verification_profile")
    row = {"passed": True}
    check_response_configuration(row, response(), 200, expected, "candidate")
    assert row.get("configuration_error") and not row["passed"]


@pytest.mark.parametrize("contract", [None, "evidence-profile-v1", "unknown"])
def test_new_runtime_profile_must_use_its_recorded_profile_contract(contract):
    observed = response()
    profile = observed["provenance"]["answer_selection"]["evidence_profile"]
    if contract is None:
        profile.pop("contract")
    else:
        profile["contract"] = contract
    row = {"passed": True}
    check_response_configuration(row, observed, 200, settings(), "candidate")
    assert row.get("configuration_error") and not row["passed"]


def test_legacy_runtime_generation_mode_remains_readable():
    expected = settings()
    expected.pop("procedure_verification_profile")
    expected["generation_mode"] = "legacy"
    assert validate_runtime_settings(expected, complete=True) == expected


@pytest.mark.parametrize("mutation", ["missing", "execution", "provenance"])
def test_actual_new_profile_requires_observed_extractive_generation(mutation):
    observed = response()
    if mutation == "missing":
        observed.pop("execution_mode")
        observed["provenance"].pop("generation_mode")
    elif mutation == "execution":
        observed["execution_mode"] = "llm"
    else:
        observed["provenance"]["generation_mode"] = "llm"
    row = {"passed": True}
    check_response_configuration(row, observed, 200, settings(), "candidate")
    assert row.get("configuration_error") and not row["passed"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("procedure_verification_profile", "invented"),
        ("answer_selection_mode", None),
        ("answer_selection_mode", "lexical"),
        ("generation_mode", None),
        ("generation_mode", "llm"),
        ("answer_support_mode", "disabled"),
    ],
)
def test_frozen_new_profile_rejects_unknown_or_incompatible_engines(field, value):
    expected = settings()
    if value is None:
        expected.pop(field)
    else:
        expected[field] = value
    with pytest.raises(ValueError, match="profile|reader|extractive|engine"):
        validate_runtime_settings(expected, complete=True)


def test_legacy_strict_settings_and_response_remain_compatible():
    expected = settings()
    for field in (
        "procedure_verification_profile",
        "answer_selection_mode",
        "generation_mode",
    ):
        expected.pop(field)
    observed = response()
    observed["provenance"]["answer_selection"]["evidence_profile"] = {
        "contract": "evidence-profile-v1",
        "proposal_profile": "qa_only_v1",
        "role_scope_policy": "literal_v1",
    }
    assert validate_runtime_settings(expected, complete=True) == expected
    row = {"passed": True}
    check_response_configuration(row, observed, 200, expected, "candidate")
    assert row == {"passed": True}


@pytest.mark.parametrize("selected,measured", [(PROFILE, None), (None, PROFILE)])
def test_selected_profile_cannot_expand_or_discard_measured_profile(selected, measured):
    selection = {"settings": {}}
    development = {"settings": {}}
    if selected is not None:
        selection["settings"]["procedure_verification_profile"] = selected
    if measured is not None:
        development["settings"]["procedure_verification_profile"] = measured
    with pytest.raises(ValueError, match="settings|profile"):
        check_measured_settings(selection, development)


def test_evaluator_new_profile_override_is_explicit_and_development_only():
    evaluator = script("evaluate_portfolio_retrieval")
    args = Namespace(
        split="development",
        expected_refusal_threshold=None,
        expected_reader_null_threshold=None,
        expected_reader_model_revision=None,
        expected_procedure_verification_profile=PROFILE,
        expected_answer_selection_mode="reader",
        expected_generation_mode="extractive",
    )
    expected = {}
    evaluator.apply_setting_overrides(args, expected, True)
    assert expected == {
        "procedure_verification_profile": PROFILE,
        "answer_selection_mode": "reader",
        "generation_mode": "extractive",
    }
    args.split = "held_out"
    with pytest.raises(ValueError, match="development"):
        evaluator.apply_setting_overrides(args, {}, True)


def test_evaluator_cli_exposes_new_profile_and_engine_expectations():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/evaluate_portfolio_retrieval.py"),
            "--help",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--expected-procedure-verification-profile" in result.stdout
    assert "--expected-answer-selection-mode" in result.stdout
    assert "--expected-generation-mode" in result.stdout


def fixture():
    body = "Aster Protocol\n\n1. Verify the seal.\n\n2. Record the code."
    version = {
        "version_number": 1,
        "content": body,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
    }
    document = {
        "id": "aster",
        "workspace_id": "ops-a",
        "owner": "author",
        "visibility": "private",
        "metadata": {},
        "versions": [version],
    }
    corpus = {
        "documents": [document],
        "manifest": {
            "schema_version": 2,
            "principals": {"author": {"workspace_id": "ops-a"}},
        },
    }
    observation = {
        "version_number": 1,
        "content_hash": version["content_hash"],
        "body_verified": True,
        "chunks": [{"id": CHUNK, "index": 0, "content": body}],
        "metadata": {"api_key": "NEVER-PUBLIC", "condition": "test"},
    }
    seed = {
        "documents": {
            "aster": {
                "document_id": DOC,
                "versions": {"1": {"content_hash": version["content_hash"]}},
                "verified_publications": [observation],
            }
        }
    }
    return corpus, seed


def test_oracle_bound_snapshots_survive_sanitized_portable_roundtrip():
    corpus, seed = fixture()
    evaluator = script("evaluate_portfolio_retrieval")
    docs = evaluator.map_documents(corpus, seed)
    manifest_builder = getattr(evaluator, "public_source_manifest", lambda _: {})
    manifest = manifest_builder(docs)
    assert manifest.get("contract") == "canonical-source-observations-v1"
    assert "NEVER-PUBLIC" not in str(manifest)
    assert "body" not in str(manifest)
    report = {"source_document_ids": {"aster": DOC}, "source_manifest": manifest}
    portable = script("verify_answer_coverage_delivery").portable_documents(
        report, corpus
    )
    assert portable == docs
    snapshots = docs["aster"].get("source_snapshots", {})
    assert (
        snapshots.get("1", {}).get("body")
        == corpus["documents"][0]["versions"][0]["content"]
    )
    assert (
        snapshots["1"]["chunks"]
        == seed["documents"]["aster"]["verified_publications"][0]["chunks"]
    )


@pytest.mark.parametrize(
    "mutation", ["chunk", "index", "id", "hash", "version", "body", "workspace"]
)
def test_online_oracle_binding_rejects_corrupt_canonical_observations(mutation):
    corpus, seed = fixture()
    observed = seed["documents"]["aster"]["verified_publications"][0]
    if mutation == "chunk":
        observed["chunks"][0]["content"] = "Invented instruction."
    elif mutation == "index":
        observed["chunks"][0]["index"] = True
    elif mutation == "id":
        observed["chunks"][0]["id"] = "not-a-uuid"
    elif mutation == "hash":
        observed["content_hash"] = "0" * 64
    elif mutation == "version":
        observed["version_number"] = 2
    elif mutation == "workspace":
        observed["workspace_id"] = "other"
    else:
        observed["body"] = "Invented body."
    with pytest.raises(ValueError, match="snapshot|observation|chunk|source"):
        script("evaluate_portfolio_retrieval").map_documents(corpus, seed)


@pytest.mark.parametrize("mutation", ["chunk_version_type", "version_alias"])
def test_snapshot_identity_types_and_version_aliases_cannot_disagree(mutation):
    corpus, seed = fixture()
    observation = seed["documents"]["aster"]["verified_publications"][0]
    if mutation == "chunk_version_type":
        observation["chunks"][0]["metadata"] = {"document_version": True}
    else:
        observation["document_version"] = 1
        observation["version_number"] = 2
    with pytest.raises(ValueError, match="snapshot|observation|source"):
        script("evaluate_portfolio_retrieval").map_documents(corpus, seed)


async def test_seeder_retains_authenticated_canonical_chunk_observations():
    corpus, seed = fixture()
    source = corpus["documents"][0]
    observed = seed["documents"]["aster"]["verified_publications"][0]

    def handler(request):
        assert request.headers["X-API-Key"] == "test-private-key"
        if request.url.path.endswith("/versions"):
            return httpx.Response(200, json=[{"version_number": 1}])
        return httpx.Response(
            200,
            json={
                "document_id": DOC,
                "version_number": 1,
                "source_status": "current",
                "normalized_content": source["versions"][0]["content"],
                "content_hash": observed["content_hash"],
                "chunks": copy.deepcopy(observed["chunks"]),
                "metadata": copy.deepcopy(observed["metadata"]),
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        observations, _ = await script("seed_portfolio").verify_publications(
            client,
            DOC,
            source,
            {"X-API-Key": "test-private-key"},
        )
    assert observations[0].get("chunks") == observed["chunks"]
    assert "NEVER-PUBLIC" not in str(observations)


def actual_response_context():
    """Projection of backend ASGI/storage output; external QA/NLI were doubles."""
    payload = json.loads(
        (Path(__file__).parent / "fixtures/procedure-copy-v3.json").read_text(
            encoding="utf-8"
        )
    )
    observed = payload["response"]
    source = next(iter(payload["source_snapshots"].values()))
    version = {
        "version_number": source["document_version"],
        "content_hash": source["content_hash"],
        "content": source["body"],
    }
    document = {
        "id": "lumen",
        "workspace_id": source["workspace_id"],
        "owner": "author",
        "visibility": "private",
        "metadata": {},
        "versions": [version],
    }
    corpus = {
        "documents": [document],
        "manifest": {
            "schema_version": 2,
            "principals": {"author": {"workspace_id": source["workspace_id"]}},
        },
    }
    seed = {
        "documents": {
            "lumen": {
                "document_id": source["document_id"],
                "versions": {"1": {"content_hash": source["content_hash"]}},
                "verified_publications": [source],
            }
        }
    }
    case = {
        "id": "lumen-case",
        "score_contract": "coverage-v2",
        "category": "answerable",
        "expected_behavior": "answer",
        "question": payload["request"]["question"],
        "principal": "author",
        "required_facts": [["obtain the signed card"]],
        "ordered_steps": [],
        "forbidden_sources": [],
        "expected_sources": [
            {
                "document_id": "lumen",
                "version_number": 1,
                "content_hash": source["content_hash"],
                "quoted_text": "obtain the signed card",
                "acceptable_answer_spans": ["obtain the signed card"],
            }
        ],
    }
    return corpus, seed, case, observed


def test_real_v3_output_replays_through_online_and_portable_public_tools():
    corpus, seed, case, observed = actual_response_context()
    evaluator = script("evaluate_portfolio_retrieval")
    docs = evaluator.map_documents(corpus, seed)
    row = evaluator.build_case_row(case, observed, 200, docs, require_answer_spans=True)
    assert row["procedure_completeness_correct"] is True and row["passed"]
    auditor = script("verify_answer_coverage_delivery")
    report = {
        "source_document_ids": {"lumen": docs["lumen"]["document_id"]},
        "source_manifest": evaluator.public_source_manifest(docs),
    }
    portable = auditor.portable_documents(report, corpus)
    assert auditor.audit_row(row, case, portable, True)["passed"]


@pytest.mark.parametrize(
    "mutation",
    ["answer", "self_hash", "question", "citation", "missing_chunks", "chunk_id"],
)
def test_v3_scoring_uses_actual_output_and_oracle_bound_chunk_identities(mutation):
    corpus, seed, case, observed = actual_response_context()
    evaluator = script("evaluate_portfolio_retrieval")
    docs = evaluator.map_documents(corpus, seed)
    if mutation in ("answer", "self_hash"):
        observed["answer"] += " Forged afterword."
        if mutation == "self_hash":
            proof = observed["provenance"]["answer_selection"]["requirements"][0][
                "procedure_completeness"
            ]
            proof["output_certificate"]["answer_sha256"] = hashlib.sha256(
                observed["answer"].encode()
            ).hexdigest()
    elif mutation == "question":
        case["question"] += " Also give the emergency procedure."
    elif mutation == "citation":
        observed["sources"][0]["chunk_id"] = CHUNK
    elif mutation == "missing_chunks":
        docs["lumen"].pop("source_snapshots")
    else:
        docs["lumen"]["source_snapshots"]["1"]["chunks"][0]["id"] = CHUNK
    row = evaluator.build_case_row(case, observed, 200, docs, require_answer_spans=True)
    assert row["required_facts_correct"] is True
    assert row["procedure_completeness_correct"] is False
    assert not row["passed"] and not row["answer_quality_passed"]


@pytest.mark.parametrize(
    "mutation", ["hash", "chunk", "body", "context", "document_id"]
)
def test_portable_source_manifest_cannot_override_frozen_source_authority(mutation):
    from app.portfolio.coverage import source_manifest_hash

    corpus, seed, _, _ = actual_response_context()
    evaluator = script("evaluate_portfolio_retrieval")
    docs = evaluator.map_documents(corpus, seed)
    manifest = evaluator.public_source_manifest(docs)
    report = {
        "source_document_ids": {"lumen": docs["lumen"]["document_id"]},
        "source_manifest": manifest,
    }
    observation = manifest["documents"]["lumen"][0]
    if mutation == "hash":
        observation["content_hash"] = "0" * 64
    elif mutation == "chunk":
        observation["chunks"][0]["content"] += " Forged instruction."
    elif mutation == "body":
        observation["body"] = "Invented body."
    elif mutation == "document_id":
        observation["document_id"] = DOC
    else:
        observation["captured_scope"] = {"title": "Invented scope"}
    # Even a recalculated public digest is not independent source authority.
    report["source_manifest_sha256"] = source_manifest_hash(manifest)
    with pytest.raises(ValueError, match="snapshot|observation|source"):
        script("verify_answer_coverage_delivery").portable_documents(report, corpus)


def test_portable_rescore_rejects_tampered_answer_with_otherwise_valid_fact_score():
    corpus, seed, case, observed = actual_response_context()
    evaluator = script("evaluate_portfolio_retrieval")
    docs = evaluator.map_documents(corpus, seed)
    row = evaluator.build_case_row(case, observed, 200, docs, require_answer_spans=True)
    row["observed_response"]["answer"] += " Forged afterword."
    with pytest.raises(ValueError, match="disagrees"):
        script("verify_answer_coverage_delivery").audit_row(row, case, docs, True)
