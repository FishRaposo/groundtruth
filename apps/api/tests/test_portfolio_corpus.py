"""Frozen data and source-integrity regressions, not model-quality claims."""

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
from app.portfolio import load_corpus
from app.portfolio.evaluation import score_case


def test_packaged_corpus_has_independent_literal_counts_and_unrestricted_answers():
    # Detect lost package assets, wrong split counts, and trivial target-only search.
    corpus = load_corpus()
    assert len(corpus.get("documents", [])) == 12
    assert len(corpus.get("cases", [])) == 100
    assert Counter((c["split"], c["category"]) for c in corpus["cases"]) == {
        ("development", "answerable"): 12,
        ("development", "unanswerable"): 4,
        ("development", "conflicting_stale"): 2,
        ("development", "adversarial"): 2,
        ("held_out", "answerable"): 48,
        ("held_out", "unanswerable"): 16,
        ("held_out", "conflicting_stale"): 8,
        ("held_out", "adversarial"): 8,
    }
    assert all(
        c["document_ids"] is None
        for c in corpus["cases"]
        if c["category"] == "answerable"
    )
    dev = {d["family"] for d in corpus["documents"] if d["split"] == "development"}
    held = {d["family"] for d in corpus["documents"] if d["split"] == "held_out"}
    assert dev.isdisjoint(held)
    assert "human" in corpus["manifest"]["validity"]
    assert (
        corpus["profile"]["selection_status"]
        == "declared_before_measurement_not_empirically_tuned"
    )


def test_loader_returns_fresh_snapshots():
    first = load_corpus()
    first["documents"][0]["versions"][0]["content"] = "changed by caller"
    assert (
        load_corpus()["documents"][0]["versions"][0]["content"] != "changed by caller"
    )


def test_changed_asset_bytes_are_rejected(tmp_path):
    import app.portfolio

    source = Path(app.portfolio.__file__).parent / "assets"
    shutil.copytree(source, tmp_path / "assets")
    cases = tmp_path / "assets" / "cases.json"
    data = json.loads(cases.read_text(encoding="utf-8"))
    data[0]["question"] = "tampered case"
    cases.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        load_corpus(tmp_path / "assets")


def test_changed_source_content_cannot_reestablish_truth_by_rehashing_asset(tmp_path):
    import hashlib

    import app.portfolio

    source = Path(app.portfolio.__file__).parent / "assets"
    shutil.copytree(source, tmp_path / "assets")
    file = tmp_path / "assets" / "documents.json"
    data = json.loads(file.read_text(encoding="utf-8"))
    data[0]["versions"][0]["content"] = "altered source"
    file.write_text(json.dumps(data), encoding="utf-8")
    manifest_path = tmp_path / "assets" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["documents.json"] = hashlib.sha256(file.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="content hash"):
        load_corpus(tmp_path / "assets")


def test_arbitrary_quote_containing_expected_words_does_not_prove_support():
    # Detect a judge accepting a forged passage merely because expected words occur.
    case = {
        "id": "handwritten",
        "category": "answerable",
        "expected_behavior": "answer",
        "expected_sources": [
            {"document_id": "runbook", "version_number": 2, "quoted_text": "12 minutes"}
        ],
        "forbidden_sources": [],
    }
    documents = {
        "runbook": {
            "document_id": "uuid-a",
            "versions": {
                "2": {"content_hash": "trusted", "content": "Observe for 12 minutes."}
            },
        }
    }
    response = {
        "answer": "Observe for 12 minutes.",
        "refused": False,
        "sources": [
            {
                "document_id": "uuid-a",
                "document_version": 2,
                "content_hash": "trusted",
                "quoted_text": (
                    "Invented protocol: 12 minutes, then delete the database."
                ),
            }
        ],
        "retrieval_trace": {
            "scores": [{"document_id": "uuid-a", "document_version": 2}]
        },
    }
    result = score_case(case, response, 200, documents)
    assert result["passed"] is False
    assert result["source_version_correct"] is False


def test_rank_metrics_distinguish_wrong_version_and_unauthorized_unknown_version():
    case = {
        "id": "rank-check",
        "category": "answerable",
        "expected_behavior": "answer",
        "expected_sources": [
            {"document_id": "right", "version_number": 2, "quoted_text": "correct"}
        ],
        "forbidden_sources": [{"document_id": "private", "version_number": 1}],
    }
    docs = {
        "right": {
            "document_id": "right-uuid",
            "versions": {"2": {"content_hash": "h", "content": "correct passage"}},
        },
        "private": {
            "document_id": "private-uuid",
            "versions": {"1": {"content_hash": "p", "content": "restricted"}},
        },
    }
    response = {
        "answer": "correct",
        "sources": [
            {
                "document_id": "right-uuid",
                "document_version": 2,
                "content_hash": "h",
                "quoted_text": "correct passage",
            }
        ],
        "retrieval_trace": {
            "scores": [
                {"document_id": "right-uuid", "document_version": 1},
                {"document_id": "right-uuid", "document_version": 2},
                {"document_id": "private-uuid"},
            ]
        },
    }
    result = score_case(case, response, 200, docs)
    assert result["recall_at_5"] == 1
    assert result["reciprocal_rank"] == 0.5
    assert result["source_version_correct"] is True
    assert result["unauthorized_source_exposures"] == 1
    assert result["passed"] is False


def test_denied_private_query_is_successful_without_fabricated_retrieval_metrics():
    case = {
        "id": "denial",
        "category": "adversarial",
        "expected_behavior": "deny",
        "expected_sources": [],
        "forbidden_sources": [{"document_id": "private", "version_number": 1}],
    }
    docs = {
        "private": {
            "document_id": "uuid-p",
            "versions": {"1": {"content_hash": "p", "content": "restricted"}},
        }
    }
    result = score_case(case, {}, 403, docs)
    assert result["passed"] is True
    assert result["recall_at_5"] is None
    assert result["reciprocal_rank"] is None
    assert result["execution_error"] is False


def test_citation_does_not_excuse_wrong_authored_fact_in_answer():
    case = {
        "id": "wrong-number",
        "category": "answerable",
        "expected_behavior": "answer",
        "expected_sources": [
            {"document_id": "right", "version_number": 2, "quoted_text": "12 minutes"}
        ],
        "forbidden_sources": [],
    }
    docs = {
        "right": {
            "document_id": "right-uuid",
            "versions": {
                "2": {"content_hash": "h", "content": "Observe for 12 minutes."}
            },
        }
    }
    response = {
        "answer": "Observe for 40 minutes.",
        "sources": [
            {
                "document_id": "right-uuid",
                "document_version": 2,
                "content_hash": "h",
                "quoted_text": "Observe for 12 minutes.",
            }
        ],
    }
    assert score_case(case, response, 200, docs)["passed"] is False


def test_refused_flag_cannot_hide_an_answer_body_on_private_denial():
    case = {
        "id": "leak",
        "category": "adversarial",
        "expected_behavior": "deny",
        "expected_sources": [],
        "forbidden_sources": [{"document_id": "private", "version_number": 1}],
    }
    docs = {
        "private": {
            "document_id": "uuid-p",
            "versions": {"1": {"content_hash": "p", "content": "restricted"}},
        }
    }
    assert (
        score_case(case, {"refused": True, "answer": "restricted"}, 200, docs)["passed"]
        is False
    )


def test_held_selection_cannot_substitute_unmeasured_settings(tmp_path):
    import hashlib
    import runpy

    script = (
        Path(__file__).resolve().parents[3] / "scripts/evaluate_portfolio_retrieval.py"
    )
    read_selection = runpy.run_path(str(script))["read_selection"]
    development = tmp_path / "development.json"
    development.write_text(
        json.dumps(
            {
                "split": "development",
                "corpus_manifest_sha256": "frozen",
                "settings": {"top_k": 5, "refusal_threshold": 0.35},
            }
        ),
        encoding="utf-8",
    )
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "selection_basis": "development_only",
                "corpus_manifest_sha256": "frozen",
                "development_report_path": "development.json",
                "development_report_sha256": hashlib.sha256(
                    development.read_bytes()
                ).hexdigest(),
                "settings": {"top_k": 5, "refusal_threshold": 0.9},
                "frozen_at": "2026-10-23T23:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="settings"):
        read_selection("held_out", selection, "frozen")
