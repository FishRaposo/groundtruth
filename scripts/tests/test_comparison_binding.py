"""Shared raw/per-arm binding over tiny invented fixtures; no HTTP/model runs."""

import copy
import importlib.util
from argparse import Namespace
from pathlib import Path

import pytest
from app.portfolio import load_corpus
from app.portfolio.representation import compile_corpus
from tests.test_corpus_representation import (
    edit_manifest,
    rewrite_payload,
    write_fixture,
)

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(
        f"binding_{name}", ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def public(corpus):
    return {
        k: v
        for k, v in corpus["manifest"]["comparison_representation"].items()
        if k not in {"common_manifest_text", "common_files"}
    }


def pair(tmp_path):
    source = write_fixture(
        tmp_path / "common", "1. Verify the seal.\n\n2. Record 😀 code."
    )
    edit_manifest(
        source,
        lambda m: m.update(
            schema_version=2, score_contract="coverage-v2", corpus_role="development"
        ),
    )

    def update(rows):
        case = rows[0]
        case.update(
            score_contract="coverage-v2",
            ordered_steps=[["Verify the seal."], ["Record 😀 code."]],
        )
        case["expected_sources"][0]["acceptable_answer_spans"] = [
            "Verify the seal.",
            "Record 😀 code.",
        ]

    rewrite_payload(source, "cases", update)
    rewrite_payload(
        source,
        "profile",
        lambda p: p.update(reader_null_threshold=4, reader_model_revision="test-pin"),
    )
    baseline = compile_corpus(source, tmp_path / "baseline", "legacy-flat-v1")
    candidate = compile_corpus(
        source, tmp_path / "candidate", "connected-paragraphs-v1"
    )
    return load_corpus(source), baseline, candidate


def arguments(arm="candidate", **extra):
    return Namespace(
        split="development",
        selection=None,
        execution_arm=arm,
        require_answer_spans=False,
        expected_refusal_threshold=None,
        expected_reader_null_threshold=None,
        expected_reader_model_revision=None,
        **extra,
    )


def seed_for(corpus):
    return {
        "corpus_manifest_sha256": corpus["manifest"]["manifest_sha256"],
        "comparison_representation": public(corpus),
    }


def header(corpus, arm):
    descriptor = public(corpus)
    return {
        "schema_version": 2,
        "score_contract": "coverage-v2",
        "split": "held_out",
        "execution_arm": arm,
        "span_integrity_required": arm == "candidate",
        "corpus_manifest_sha256": corpus["manifest"]["manifest_sha256"],
        "common_corpus_manifest_sha256": descriptor["origin_common_manifest_sha256"],
        "selection_sha256": "a" * 64,
        "comparison_representation": descriptor,
        "results": {m: {} for m in ("keyword", "vector", "hybrid", "reranked")},
    }


@pytest.mark.parametrize("mutation", ["arm", "missing", "null", "profile", "digest"])
def test_evaluation_preflight_rejects_wrong_arm_or_seed_descriptor(tmp_path, mutation):
    _, baseline, candidate = pair(tmp_path)
    seed = seed_for(candidate)
    args = arguments("baseline" if mutation == "arm" else "candidate")
    if mutation == "missing":
        seed.pop("comparison_representation")
    elif mutation == "null":
        seed["comparison_representation"] = None
    elif mutation == "profile":
        seed["comparison_representation"] = public(baseline)
    elif mutation == "digest":
        seed["comparison_representation"]["common_contract_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        script("evaluate_portfolio_retrieval").evaluation_settings(
            args, candidate, seed
        )


def test_legitimate_projected_headers_accept_disclosed_distinct_manifests(tmp_path):
    _, baseline, candidate = pair(tmp_path)
    before, after = header(baseline, "baseline"), header(candidate, "candidate")
    assert before["corpus_manifest_sha256"] != after["corpus_manifest_sha256"]
    try:
        script("verify_answer_coverage_delivery").validate_headers(before, after)
    except ValueError as exc:
        pytest.fail(f"coherent projected inputs were rejected: {exc}")


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "null",
        "profile",
        "arm",
        "oracle",
        "compiler",
        "source",
        "case",
        "common",
        "origin",
        "top_common",
        "selection",
        "methods",
    ],
)
def test_projected_header_mismatch_cannot_use_different_manifests(tmp_path, mutation):
    _, flat, paragraphs = pair(tmp_path)
    before, after = header(flat, "baseline"), header(paragraphs, "candidate")
    if mutation == "missing":
        after.pop("comparison_representation")
    elif mutation == "null":
        after["comparison_representation"] = None
    elif mutation == "top_common":
        after["common_corpus_manifest_sha256"] = "0" * 64
    elif mutation == "selection":
        after["selection_sha256"] = "0" * 64
    elif mutation == "methods":
        after["results"].pop("vector")
    else:
        key = {
            "profile": "profile",
            "arm": "execution_arm",
            "oracle": "oracle_contract",
            "compiler": "compiler_sha256",
            "source": "common_source_contract_sha256",
            "case": "common_case_contract_sha256",
            "common": "common_contract_sha256",
            "origin": "origin_common_manifest_sha256",
        }[mutation]
        after["comparison_representation"][key] = (
            "unknown" if mutation in {"profile", "arm", "oracle"} else "0" * 64
        )
    with pytest.raises(ValueError):
        script("verify_answer_coverage_delivery").validate_headers(before, after)


def test_projected_evaluation_keeps_explicit_development_overrides(tmp_path):
    _, _, candidate = pair(tmp_path)
    args = arguments(
        expected_proposal_profile="qa_plus_source_patterns_v1",
        expected_role_scope_policy="ordinary_session_activity_v1",
    )
    _, _, settings = script("evaluate_portfolio_retrieval").evaluation_settings(
        args, candidate, seed_for(candidate)
    )
    assert settings["answer_proposal_profile"] == "qa_plus_source_patterns_v1"
    assert settings["role_scope_policy"] == "ordinary_session_activity_v1"
    assert "answer_proposal_profile" not in candidate["profile"]


def test_explicit_null_seed_on_legacy_input_cannot_downgrade(tmp_path):
    common, _, _ = pair(tmp_path)
    seed = {
        "corpus_manifest_sha256": common["manifest"]["manifest_sha256"],
        "comparison_representation": None,
    }
    with pytest.raises(ValueError):
        script("evaluate_portfolio_retrieval").evaluation_settings(
            arguments(), common, seed
        )


def runtime_settings(profile):
    return {
        **profile,
        "answer_proposal_profile": "qa_only_v1",
        "role_scope_policy": "literal_v1",
        "answer_support_mode": "local_nli",
        "support_model_revision": "expected-support",
        "support_min_margin": 3,
        "selection_contract": "requirement-evidence-v2",
    }


def runtime_observation(settings, arm):
    return {
        "mode": "reader" if arm == "candidate" else "lexical",
        "threshold": settings["reader_null_threshold"],
        "revision": settings["reader_model_revision"],
        "contract": settings["selection_contract"],
        "evidence_profile": {
            "contract": "evidence-profile-v1",
            "proposal_profile": settings["answer_proposal_profile"],
            "role_scope_policy": settings["role_scope_policy"],
        },
        "evidence_support": {
            "mode": settings["answer_support_mode"]
            if arm == "candidate"
            else "disabled",
            "revision": settings["support_model_revision"],
            "minimum_entailment_margin": settings["support_min_margin"],
        },
    }


def frozen_selection(tmp_path, common_hash, settings):
    settings = runtime_settings(settings)
    import hashlib
    import json

    stamp = "2026-10-25T00:00:00Z"
    development = {
        "split": "development",
        "corpus_manifest_sha256": "d" * 64,
        "settings": settings,
    }
    freeze = {
        "development_corpus_manifest_sha256": "d" * 64,
        "settings": settings,
        "frozen_at": stamp,
    }
    selection = {
        "schema_version": 2,
        "selection_basis": "development_only",
        "validation_corpus_manifest_sha256": common_hash,
        "development_corpus_manifest_sha256": "d" * 64,
        "settings": settings,
        "frozen_at": stamp,
        "binding_at": "2026-10-25T00:01:00Z",
    }
    for key, value in (
        ("development_report", development),
        ("candidate_freeze", freeze),
    ):
        path = tmp_path / f"{key}.json"
        body = json.dumps(value).encode()
        path.write_bytes(body)
        selection[key + "_path"] = path.name
        selection[key + "_sha256"] = hashlib.sha256(body).hexdigest()
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(selection), encoding="utf-8")
    return path


def test_blind_selection_binds_common_origin_but_keeps_artifact_checks(tmp_path):
    common, _, _ = pair(tmp_path)
    source = tmp_path / "common"
    rewrite_payload(source, "documents", lambda docs: docs[0].update(split="held_out"))
    rewrite_payload(source, "cases", lambda rows: rows[0].update(split="held_out"))
    edit_manifest(
        source, lambda m: m.update(expected_counts={"held_out": {"answerable": 1}})
    )
    common = load_corpus(source)
    candidate = compile_corpus(
        source, tmp_path / "held-candidate", "connected-paragraphs-v1"
    )
    path = frozen_selection(
        tmp_path, common["manifest"]["manifest_sha256"], candidate["profile"]
    )
    args = arguments()
    args.split, args.selection = "held_out", path
    evaluator = script("evaluate_portfolio_retrieval")
    assert (
        evaluator.evaluation_settings(args, candidate, seed_for(candidate))[1][
            "validation_corpus_manifest_sha256"
        ]
        == common["manifest"]["manifest_sha256"]
    )
    args.expected_role_scope_policy = "ordinary_session_activity_v1"
    with pytest.raises(ValueError, match="overrides"):
        evaluator.evaluation_settings(args, candidate, seed_for(candidate))
    args.expected_role_scope_policy = None
    (tmp_path / "development_report.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        evaluator.evaluation_settings(args, candidate, seed_for(candidate))


def blind_pair(tmp_path, candidate_correct=114):
    """One toy source; mechanically repeated rows satisfy the unchanged gate shape."""
    import json

    from app.portfolio.evaluation import score_case, summarize

    pair(tmp_path)
    source = tmp_path / "common"
    categories = {
        "answerable": 120,
        "unanswerable": 40,
        "conflicting_stale": 20,
        "adversarial": 20,
    }
    rewrite_payload(source, "documents", lambda docs: docs[0].update(split="held_out"))

    def expand(rows):
        template = rows[0]
        cases = []
        for category, count in categories.items():
            for index in range(count):
                case = copy.deepcopy(template)
                case.update(
                    id=f"{category}-{index}", split="held_out", category=category
                )
                if category != "answerable":
                    case.update(
                        expected_behavior="refuse",
                        expected_sources=[],
                        required_facts=[],
                        ordered_steps=[],
                        forbidden_sources=[
                            {"document_id": "protocol", "version_number": 1}
                        ],
                    )
                cases.append(case)
        rows[:] = cases

    rewrite_payload(source, "cases", expand)
    edit_manifest(
        source,
        lambda m: m.update(case_count=200, expected_counts={"held_out": categories}),
    )
    common = load_corpus(source)
    baseline = compile_corpus(source, tmp_path / "blind-baseline", "legacy-flat-v1")
    candidate = compile_corpus(
        source, tmp_path / "blind-candidate", "connected-paragraphs-v1"
    )
    selected_path = frozen_selection(
        tmp_path, common["manifest"]["manifest_sha256"], candidate["profile"]
    )
    settings = runtime_settings(candidate["profile"])
    reports = []
    for arm, corpus, correct in (
        ("baseline", baseline, 30),
        ("candidate", candidate, candidate_correct),
    ):
        report = header(corpus, arm)
        report["settings"] = copy.deepcopy(settings)
        import hashlib

        report["selection_sha256"] = hashlib.sha256(
            selected_path.read_bytes()
        ).hexdigest()
        identifier = (
            "11111111-1111-4111-8111-111111111111"
            if arm == "baseline"
            else "22222222-2222-4222-8222-222222222222"
        )
        report["source_document_ids"] = {"protocol": identifier}
        verifier = script("verify_answer_coverage_delivery")
        documents = verifier.portable_documents(report, corpus)
        version = corpus["documents"][0]["versions"][0]
        rows = []
        for case in corpus["cases"]:
            answered = (
                case["category"] == "answerable"
                and int(case["id"].rsplit("-", 1)[-1]) < correct
            )
            body = version["content"]
            response = {
                "question": case["question"],
                "answer": body if answered else None,
                "refused": not answered,
                "outcome": "completed" if answered else "refused",
                "retrieval_trace": {"scores": []},
                "provenance": {"answer_selection": runtime_observation(settings, arm)},
                "sources": [],
            }
            if answered:
                response["sources"] = [
                    {
                        "document_id": identifier,
                        "document_version": 1,
                        "content_hash": version["content_hash"],
                        "quoted_text": body,
                        "answer_spans": [{"start": 0, "end": len(body), "text": body}],
                    }
                ]
            row = score_case(
                case, response, 200, documents, require_answer_spans=arm == "candidate"
            )
            row["observed_response"] = response
            rows.append(row)
        report["results"] = {
            method: {"cases": copy.deepcopy(rows), "summary": summarize(rows)}
            for method in report["results"]
        }
        path = tmp_path / f"{arm}-report.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        reports.append(report)
    return common, baseline, candidate, *reports


def test_comparison_audits_each_exact_view_and_discloses_non_reader_scope(tmp_path):
    common, baseline, candidate, before, after = blind_pair(tmp_path)
    verifier = script("verify_answer_coverage_delivery")
    result = verifier.compare_reports(
        before,
        after,
        corpus=common,
        baseline_corpus=baseline,
        candidate_corpus=candidate,
        selection_path=tmp_path / "selection.json",
    )
    assert result["gate"] == "passed"
    assert result["input_equivalence"]["verified_against_common_sources"] is True
    assert result["input_equivalence"]["reader_only_improvement_claim"] is False
    assert (
        result["portable_evidence"]["baseline"]["corpus_manifest_sha256"]
        == baseline["manifest"]["manifest_sha256"]
    )
    assert (
        result["portable_evidence"]["candidate"]["corpus_manifest_sha256"]
        == candidate["manifest"]["manifest_sha256"]
    )
    arithmetic = verifier.compare_reports(before, after)
    assert arithmetic["comparison_scope"] == "arithmetic_only_not_portable"
    assert arithmetic["input_equivalence"]["verified_against_common_sources"] is False
    with pytest.raises(ValueError, match="both"):
        verifier.compare_reports(before, after, corpus=common)


@pytest.mark.parametrize(
    "damage",
    [
        "quote",
        "hash",
        "span",
        "uuid",
        "versions",
        "negative_context",
        "common_semantics",
    ],
)
def test_portable_projected_comparison_rejects_source_or_observation_damage(
    tmp_path, damage
):
    common, baseline, candidate, before, after = blind_pair(tmp_path)
    if damage == "versions":
        candidate["documents"][0]["versions"].clear()
    elif damage == "common_semantics":
        common["cases"][0]["required_facts"] = [["fabricated fact"]]
    elif damage == "uuid":
        after["source_document_ids"]["protocol"] = (
            "33333333-3333-4333-8333-333333333333"
        )
    else:
        row = after["results"]["reranked"]["cases"][
            0 if damage != "negative_context" else 120
        ]
        response = row["observed_response"]
        if damage == "quote":
            response["sources"][0]["quoted_text"] = " ".join(
                response["sources"][0]["quoted_text"].split()
            )
        elif damage == "hash":
            response["sources"][0]["content_hash"] = "0" * 64
        elif damage == "span":
            response["sources"][0]["answer_spans"][0]["end"] += 1
        else:
            response["provenance"] = {
                "answer_selection": {
                    "contract": "requirement-evidence-v2",
                    "inspected_sources": [
                        {
                            "document_id": after["source_document_ids"]["protocol"],
                            "document_version": 1,
                        }
                    ],
                }
            }
    with pytest.raises(ValueError):
        script("verify_answer_coverage_delivery").compare_reports(
            before,
            after,
            corpus=common,
            baseline_corpus=baseline,
            candidate_corpus=candidate,
            selection_path=tmp_path / "selection.json",
        )


@pytest.mark.parametrize(
    "correct,damage,expected",
    [
        (114, None, 0),
        (113, None, 1),
        (114, "missing", 2),
        (114, "swapped", 2),
        (114, "codepoints", 2),
        (114, "common", 2),
    ],
)
def test_projected_cli_zero_one_two_contract(
    tmp_path, monkeypatch, capsys, correct, damage, expected
):
    import json
    import sys

    blind_pair(tmp_path, correct)
    command = [
        "verify",
        "--baseline",
        str(tmp_path / "baseline-report.json"),
        "--candidate",
        str(tmp_path / "candidate-report.json"),
        "--selection",
        str(tmp_path / "selection.json"),
        "--corpus-dir",
        str(tmp_path / "common"),
    ]
    if damage != "missing":
        left, right = (
            ("blind-candidate", "blind-baseline")
            if damage == "swapped"
            else ("blind-baseline", "blind-candidate")
        )
        command += [
            "--baseline-corpus-dir",
            str(tmp_path / left),
            "--candidate-corpus-dir",
            str(tmp_path / right),
        ]
    if damage == "codepoints":
        rewrite_payload(
            tmp_path / "blind-candidate",
            "documents",
            lambda docs: docs[0]["versions"][0]["comparison_representation"][
                "codepoint_map"
            ][0].update(raw_start=999),
        )
    elif damage == "common":
        rewrite_payload(
            tmp_path / "common",
            "cases",
            lambda rows: rows[0].update(question="Changed common contract"),
        )
    monkeypatch.setattr(sys, "argv", command)
    assert script("verify_answer_coverage_delivery").main() == expected
    output = capsys.readouterr().out
    if expected < 2:
        result = json.loads(output)
        assert result["gate"] == ("passed" if expected == 0 else "failed")
        assert result["portable_evidence"]["candidate"]["verified"] is True


def test_projected_schema_one_input_still_requires_explicit_execution_arm(tmp_path):
    source = write_fixture(tmp_path / "schema-one")
    candidate = compile_corpus(
        source, tmp_path / "candidate", "connected-paragraphs-v1"
    )
    with pytest.raises(ValueError):
        script("evaluate_portfolio_retrieval").evaluation_settings(
            arguments(None), candidate, seed_for(candidate)
        )


@pytest.mark.parametrize(
    "field", ["expected_proposal_profile", "expected_role_scope_policy"]
)
def test_python_development_override_cannot_introduce_unknown_mode(tmp_path, field):
    _, _, candidate = pair(tmp_path)
    args = arguments(**{field: "invented_mode"})
    with pytest.raises(ValueError, match="profile|policy|mode"):
        script("evaluate_portfolio_retrieval").evaluation_settings(
            args, candidate, seed_for(candidate)
        )


def test_report_binding_comes_from_authoritative_view_and_seed_manifest_is_exact(
    tmp_path,
):
    from app.portfolio.comparison import report_binding

    common, _, candidate = pair(tmp_path)
    binding = report_binding(candidate)
    assert binding["comparison_representation"] == public(candidate)
    assert (
        binding["common_corpus_manifest_sha256"]
        == common["manifest"]["manifest_sha256"]
    )
    assert (
        binding["common_corpus_manifest_sha256"]
        != candidate["manifest"]["manifest_sha256"]
    )
    assert "common_files" not in binding["comparison_representation"]
    seed = seed_for(candidate)
    seed["corpus_manifest_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        script("evaluate_portfolio_retrieval").evaluation_settings(
            arguments(), candidate, seed
        )


def test_frozen_settings_cannot_claim_an_unknown_mode(tmp_path):
    pair(tmp_path)
    source = tmp_path / "common"
    rewrite_payload(
        source, "profile", lambda p: p.update(answer_proposal_profile="invented_mode")
    )
    candidate = compile_corpus(
        source, tmp_path / "unknown-mode", "connected-paragraphs-v1"
    )
    with pytest.raises(ValueError, match="mode"):
        script("evaluate_portfolio_retrieval").evaluation_settings(
            arguments(), candidate, seed_for(candidate)
        )


def test_cli_one_arm_directory_is_preflight_error(tmp_path, monkeypatch, capsys):
    import sys

    blind_pair(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify",
            "--baseline",
            str(tmp_path / "baseline-report.json"),
            "--candidate",
            str(tmp_path / "candidate-report.json"),
            "--selection",
            str(tmp_path / "selection.json"),
            "--corpus-dir",
            str(tmp_path / "common"),
            "--baseline-corpus-dir",
            str(tmp_path / "blind-baseline"),
        ],
    )
    assert script("verify_answer_coverage_delivery").main() == 2
    assert "both" in capsys.readouterr().out
