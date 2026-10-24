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


def _coverage_case_and_response():
    # A topic-only answer with the right immutable citation must not pass.
    case = {
        "id": "v2-fact",
        "score_contract": "coverage-v2",
        "principal": "operator-a",
        "category": "answerable",
        "expected_behavior": "answer",
        "expected_sources": [
            {
                "document_id": "relay",
                "version_number": 2,
                "quoted_text": "Relay maintenance lasts 11 minutes.",
                "acceptable_answer_spans": ["11 minutes"],
            }
        ],
        "forbidden_sources": [],
        "required_facts": [["11 minutes"]],
        "ordered_steps": [],
    }
    docs = {
        "relay": {
            "document_id": "uuid-relay",
            "visibility": "public",
            "workspace_id": "ops-a",
            "owner": "operator-a",
            "principals": {"operator-a": {"workspace_id": "ops-a", "role": "owner"}},
            "versions": {
                "2": {
                    "content_hash": "hash-relay",
                    "content": "Relay maintenance lasts 11 minutes.",
                }
            },
        }
    }
    response = {
        "answer": "Relay maintenance lasts 11 minutes.",
        "refused": False,
        "sources": [
            {
                "document_id": "uuid-relay",
                "document_version": 2,
                "content_hash": "hash-relay",
                "quoted_text": "Relay maintenance lasts 11 minutes.",
            }
        ],
    }
    return case, response, docs


def test_coverage_facts_reject_topic_only_answer_with_valid_citation():
    case, response, docs = _coverage_case_and_response()
    # Keep the full quote in the answer, but contradict the required authored fact.
    case["expected_sources"][0]["quoted_text"] = "Relay maintenance"
    response["answer"] = "Relay maintenance lasts 45 minutes."
    assert score_case(case, response, 200, docs)["passed"] is False


def test_coverage_accepts_whole_chunk_baseline_without_reader_spans():
    case, response, docs = _coverage_case_and_response()
    result = score_case(case, response, 200, docs)
    assert result["passed"] is True
    assert result.get("answer_contract_correct") is True


def test_coverage_rejects_reversed_required_procedure_steps():
    case, response, docs = _coverage_case_and_response()
    content = "First close the inlet. Then open the drain."
    case["expected_sources"][0].update(
        quoted_text="the", acceptable_answer_spans=["close the inlet", "open the drain"]
    )
    case["required_facts"] = [["close the inlet"], ["open the drain"]]
    case["ordered_steps"] = [["close the inlet"], ["open the drain"]]
    docs["relay"]["versions"]["2"]["content"] = content
    response["sources"][0]["quoted_text"] = content
    response["answer"] = "First open the drain. Then close the inlet."
    assert score_case(case, response, 200, docs)["passed"] is False


def test_coverage_rejects_corrupt_unicode_reader_span_but_keeps_quality_separate():
    case, response, docs = _coverage_case_and_response()
    response["sources"][0]["answer_spans"] = [{"start": 0, "end": 2, "text": "11"}]
    result = score_case(case, response, 200, docs)
    assert result["passed"] is False
    assert result.get("answer_contract_correct") is True
    assert result.get("span_integrity_correct") is False


def _write_coverage_fixture(tmp_path):
    import hashlib

    case, _, _ = _coverage_case_and_response()
    case.update(
        split="development",
        family="relay-maintenance",
        principal="operator-a",
        document_ids=None,
    )
    case["expected_sources"][0]["content_hash"] = hashlib.sha256(
        b"Relay maintenance lasts 11 minutes."
    ).hexdigest()
    document = {
        "id": "relay",
        "title": "Relay maintenance",
        "family": "relay-maintenance",
        "split": "development",
        "visibility": "public",
        "workspace_id": "ops-a",
        "owner": "operator-a",
        "current_version_number": 2,
        "metadata": {},
        "versions": [
            {
                "version_number": 1,
                "content": "Retired relay instruction.",
                "content_hash": hashlib.sha256(
                    b"Retired relay instruction."
                ).hexdigest(),
            },
            {
                "version_number": 2,
                "content": "Relay maintenance lasts 11 minutes.",
                "content_hash": hashlib.sha256(
                    b"Relay maintenance lasts 11 minutes."
                ).hexdigest(),
            },
        ],
    }
    values = {
        "documents.json": [document],
        "cases.json": [case],
        "profile.json": {"top_k": 5, "refusal_threshold": 0.35},
    }
    manifest = {
        "schema_version": 2,
        "revision": "test-v2",
        "score_contract": "coverage-v2",
        "corpus_role": "development",
        "document_count": 1,
        "case_count": 1,
        "principals": {"operator-a": {"workspace_id": "ops-a", "role": "owner"}},
        "expected_counts": {"development": {"answerable": 1}},
        "files": {},
    }
    for name, value in values.items():
        body = (json.dumps(value) + "\n").encode()
        (tmp_path / name).write_bytes(body)
        manifest["files"][name] = hashlib.sha256(body).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def test_coverage_loader_accepts_grounded_version_two_contract(tmp_path):
    _write_coverage_fixture(tmp_path)
    try:
        corpus = load_corpus(tmp_path)
    except ValueError as exc:
        pytest.fail(f"Valid version-two source contract rejected: {exc}")
    assert corpus["cases"][0]["required_facts"] == [["11 minutes"]]


def test_coverage_loader_rejects_unfounded_required_fact_after_rehash(tmp_path):
    import hashlib

    manifest = _write_coverage_fixture(tmp_path)
    path = tmp_path / "cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    cases[0]["required_facts"] = [["45 minutes"]]
    path.write_text(json.dumps(cases), encoding="utf-8")
    manifest["files"]["cases.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="required fact"):
        load_corpus(tmp_path)


def test_coverage_rejects_source_correctness_when_an_extra_citation_is_corrupt():
    case, response, docs = _coverage_case_and_response()
    response["sources"].append(
        {
            "document_id": "unknown",
            "document_version": 1,
            "quoted_text": "11 minutes",
            "content_hash": "forged",
        }
    )
    assert score_case(case, response, 200, docs)["passed"] is False


def test_coverage_candidate_requires_spans_but_baseline_quality_is_identical():
    case, response, docs = _coverage_case_and_response()
    baseline = score_case(case, response, 200, docs)
    candidate = score_case(case, response, 200, docs, require_answer_spans=True)
    assert (
        baseline["answer_contract_correct"]
        is candidate["answer_contract_correct"]
        is True
    )
    assert baseline["passed"] is True
    assert candidate["passed"] is False
    assert candidate["span_integrity_correct"] is False


def test_coverage_accepts_unicode_codepoint_span_and_rejects_utf16_offset():
    case, response, docs = _coverage_case_and_response()
    content = "📦 Relay maintenance lasts 11 minutes."
    docs["relay"]["versions"]["2"]["content"] = content
    response["sources"][0]["quoted_text"] = content
    response["sources"][0]["answer_spans"] = [
        {"start": 26, "end": 36, "text": "11 minutes"}
    ]
    assert (
        score_case(case, response, 200, docs, require_answer_spans=True)["passed"]
        is True
    )
    response["sources"][0]["answer_spans"][0].update(start=27, end=37)
    assert (
        score_case(case, response, 200, docs, require_answer_spans=True)["passed"]
        is False
    )


def test_coverage_loader_rejects_expected_hash_after_asset_rehash(tmp_path):
    import hashlib

    manifest = _write_coverage_fixture(tmp_path)
    path = tmp_path / "cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    cases[0]["expected_sources"][0]["content_hash"] = "forged"
    path.write_text(json.dumps(cases), encoding="utf-8")
    manifest["files"]["cases.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="source content hash"):
        load_corpus(tmp_path)


def test_coverage_selection_binds_distinct_frozen_corpora_without_rewriting_candidate(
    tmp_path,
):
    import hashlib
    import runpy

    read_selection = runpy.run_path(
        str(
            Path(__file__).resolve().parents[3]
            / "scripts/evaluate_portfolio_retrieval.py"
        )
    )["read_selection"]
    development = {
        "split": "development",
        "corpus_manifest_sha256": "dev-corpus",
        "settings": {
            "top_k": 5,
            "refusal_threshold": 0.35,
            "reader_null_threshold": -4,
        },
    }
    (tmp_path / "development.json").write_text(
        json.dumps(development), encoding="utf-8"
    )
    freeze = {
        "frozen_at": "2026-10-24T10:00:00Z",
        "development_corpus_manifest_sha256": "dev-corpus",
        "settings": development["settings"],
    }
    freeze_path = tmp_path / "candidate-freeze.json"
    freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
    selection = {
        "schema_version": 2,
        "selection_basis": "development_only",
        "development_corpus_manifest_sha256": "dev-corpus",
        "validation_corpus_manifest_sha256": "blind-corpus",
        "development_report_path": "development.json",
        "development_report_sha256": hashlib.sha256(
            (tmp_path / "development.json").read_bytes()
        ).hexdigest(),
        "candidate_freeze_path": "candidate-freeze.json",
        "candidate_freeze_sha256": hashlib.sha256(freeze_path.read_bytes()).hexdigest(),
        "settings": development["settings"],
        "frozen_at": freeze["frozen_at"],
        "binding_at": "2026-10-24T11:00:00Z",
    }
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(selection), encoding="utf-8")
    try:
        result = read_selection("held_out", path, "blind-corpus")
    except ValueError as exc:
        pytest.fail(
            f"Frozen development selection cannot bind distinct blind corpus: {exc}"
        )
    assert result["settings"]["reader_null_threshold"] == -4
    freeze["settings"]["reader_null_threshold"] = 12
    freeze_path.write_text(json.dumps(freeze), encoding="utf-8")
    with pytest.raises(ValueError, match="freeze checksum"):
        read_selection("held_out", path, "blind-corpus")


def test_packaged_coverage_development_is_grounded_and_family_independent():
    import app.portfolio

    corpus = load_corpus(
        Path(app.portfolio.__file__).parent / "assets" / "coverage-development"
    )
    assert Counter(case["category"] for case in corpus["cases"]) == {
        "answerable": 48,
        "unanswerable": 16,
        "conflicting_stale": 8,
        "adversarial": 8,
    }
    assert {case["split"] for case in corpus["cases"]} == {"development"}
    original_families = {doc["family"] for doc in load_corpus()["documents"]}
    assert original_families.isdisjoint(doc["family"] for doc in corpus["documents"])
    assert all(
        case["document_ids"] is None
        for case in corpus["cases"]
        if case["category"] == "answerable"
    )
    docs = {
        doc["id"]: {
            "document_id": doc["id"],
            "visibility": doc["visibility"],
            "workspace_id": doc["workspace_id"],
            "owner": doc["owner"],
            "principals": corpus["manifest"]["principals"],
            "versions": {str(v["version_number"]): v for v in doc["versions"]},
        }
        for doc in corpus["documents"]
    }
    for case in corpus["cases"]:
        sources = [
            {
                "document_id": source["document_id"],
                "document_version": source["version_number"],
                "content_hash": source["content_hash"],
                "quoted_text": docs[source["document_id"]]["versions"][
                    str(source["version_number"])
                ]["content"],
            }
            for source in case["expected_sources"]
        ]
        response = {
            "answer": "\n".join(source["quoted_text"] for source in sources) or None,
            "sources": sources,
            "refused": case["expected_behavior"] != "answer",
        }
        status = 403 if case["expected_behavior"] == "deny" else 200
        result = score_case(case, response, status, docs)
        assert result["passed"], case["id"]


def test_coverage_baseline_accepts_frozen_reader_settings_without_reader_fields():
    import runpy

    script = (
        Path(__file__).resolve().parents[3] / "scripts/evaluate_portfolio_retrieval.py"
    )
    check_configuration = runpy.run_path(str(script))["check_response_configuration"]
    settings = {
        "refusal_threshold": 0.35,
        "reader_null_threshold": -4,
        "reader_model_revision": "frozen",
    }
    row = {"passed": True, "answer_quality_passed": True, "execution_error": False}
    check_configuration(
        row, {"retrieval_trace": {"refusal_threshold": 0.35}}, 200, settings, "baseline"
    )
    assert row["passed"] is True
    check_configuration(
        row,
        {"retrieval_trace": {"refusal_threshold": 0.35}},
        200,
        settings,
        "candidate",
    )
    assert row["passed"] is False
    assert row["answer_quality_passed"] is False
    assert row["execution_error"] is True


def test_coverage_false_refusal_fails_quality_without_fabricated_span_failure():
    case, _, docs = _coverage_case_and_response()
    result = score_case(
        case,
        {"refused": True, "answer": None, "sources": []},
        200,
        docs,
        require_answer_spans=True,
    )
    assert result["answer_quality_passed"] is False
    assert result["span_integrity_correct"] is True


def test_coverage_error_outcome_is_execution_error_even_with_http_success():
    case, _, docs = _coverage_case_and_response()
    result = score_case(
        case, {"outcome": "error", "answer": None, "sources": []}, 200, docs
    )
    assert result["passed"] is False
    assert result["execution_error"] is True


def test_coverage_detects_a_different_private_document_than_case_forbids():
    import runpy

    import app.portfolio

    corpus = load_corpus(
        Path(app.portfolio.__file__).parent / "assets" / "coverage-development"
    )
    map_documents = runpy.run_path(
        str(
            Path(__file__).resolve().parents[3]
            / "scripts/evaluate_portfolio_retrieval.py"
        )
    )["map_documents"]
    seed = {
        "documents": {
            doc["id"]: {
                "document_id": doc["id"],
                "versions": {
                    str(v["version_number"]): {"content_hash": v["content_hash"]}
                    for v in doc["versions"]
                },
            }
            for doc in corpus["documents"]
        }
    }
    seed["documents"]["pottery-locker"].update(
        visibility="public", workspace_id="ops-a", owner="operator-a"
    )
    docs = map_documents(corpus, seed)
    assert docs["pottery-locker"]["visibility"] == "private"
    assert docs["pottery-locker"]["workspace_id"] == "ops-b"
    case = next(case for case in corpus["cases"] if case["id"] == "coverage-dev-074")
    leaked = next(doc for doc in corpus["documents"] if doc["id"] == "pottery-locker")[
        "versions"
    ][-1]
    response = {
        "refused": True,
        "outcome": "refused",
        "answer": None,
        "sources": [
            {
                "document_id": "pottery-locker",
                "document_version": 1,
                "content_hash": leaked["content_hash"],
                "quoted_text": leaked["content"],
            }
        ],
        "retrieval_trace": {
            "scores": [{"document_id": "pottery-locker", "document_version": 1}]
        },
    }
    result = score_case(case, response, 200, docs, require_answer_spans=True)
    assert result["passed"] is False
    assert result["answer_quality_passed"] is False
    assert result["unauthorized_source_exposures"] == 1


def test_coverage_unknown_trace_source_fails_closed_even_beyond_top_five():
    case, response, docs = _coverage_case_and_response()
    response["retrieval_trace"] = {
        "scores": [{"document_id": "uuid-relay", "document_version": 2}] * 5
        + [{"document_id": "unmapped-private-source", "document_version": 1}]
    }
    result = score_case(case, response, 200, docs)
    assert result["passed"] is False
    assert result["unauthorized_source_exposures"] == 1


def test_coverage_matching_group_label_cannot_authorize_a_private_source():
    case, _, docs = _coverage_case_and_response()
    case.update(
        category="adversarial",
        expected_behavior="refuse",
        expected_sources=[],
        required_facts=[],
        ordered_steps=[],
        principal="viewer-a",
    )
    docs["relay"].update(
        visibility="private",
        workspace_id="ops-a",
        owner="operator-a",
        metadata={"group_ids": ["operations"]},
        principals={
            "operator-a": {
                "workspace_id": "ops-a",
                "role": "owner",
                "group_ids": ["operations"],
            },
            "viewer-a": {
                "workspace_id": "ops-a",
                "role": "viewer",
                "group_ids": ["operations"],
            },
        },
    )
    response = {
        "refused": True,
        "answer": None,
        "sources": [],
        "retrieval_trace": {
            "scores": [{"document_id": "uuid-relay", "document_version": 2}]
        },
    }
    result = score_case(case, response, 200, docs)
    assert result["passed"] is False
    assert result["unauthorized_source_exposures"] == 1


@pytest.mark.parametrize(
    ("alias", "visibility", "workspace", "owner", "allowed"),
    [
        ("operator-a", "private", "ops-a", "operator-a", True),
        ("viewer-a", "private", "ops-a", "operator-a", False),
        ("admin-a", "private", "ops-a", "operator-a", True),
        ("viewer-a", "public", "ops-a", "operator-a", True),
        ("viewer-a", "organization", "ops-a", "operator-a", True),
        ("operator-a", "public", "ops-b", "custodian-b", False),
        ("operator-a", "organization", "ops-b", "custodian-b", False),
        ("admin-a", "private", "ops-b", "custodian-b", False),
        ("undeclared", "public", "ops-a", "operator-a", False),
    ],
)
def test_coverage_source_authority_uses_workspace_owner_and_visibility(
    alias, visibility, workspace, owner, allowed
):
    case, _, docs = _coverage_case_and_response()
    case.update(
        category="adversarial",
        expected_behavior="refuse",
        expected_sources=[],
        required_facts=[],
        ordered_steps=[],
        principal=alias,
    )
    docs["relay"].update(
        visibility=visibility,
        workspace_id=workspace,
        owner=owner,
        principals={
            "operator-a": {"workspace_id": "ops-a", "role": "owner"},
            "viewer-a": {"workspace_id": "ops-a", "role": "viewer"},
            "admin-a": {"workspace_id": "ops-a", "role": "admin"},
            "custodian-b": {"workspace_id": "ops-b", "role": "owner"},
        },
    )
    response = {
        "refused": True,
        "answer": None,
        "sources": [],
        "retrieval_trace": {
            "scores": [{"document_id": "uuid-relay", "document_version": 2}]
        },
    }
    result = score_case(case, response, 200, docs)
    assert result["passed"] is allowed
    assert result["unauthorized_source_exposures"] == (0 if allowed else 1)


def test_coverage_missing_canonical_permissions_fails_closed():
    case, response, docs = _coverage_case_and_response()
    del docs["relay"]["principals"]
    result = score_case(case, response, 200, docs)
    assert result["passed"] is False
    assert result["unauthorized_source_exposures"] == 1


def test_coverage_row_preserves_observed_answer_citations_but_excludes_credentials():
    import runpy

    script = (
        Path(__file__).resolve().parents[3] / "scripts/evaluate_portfolio_retrieval.py"
    )
    row_builder = runpy.run_path(str(script)).get("build_case_row")
    assert callable(row_builder), "Evaluation needs a v2 raw-response row builder"
    case, response, docs = _coverage_case_and_response()
    response.update(
        id="query-fixture",
        question="How long is maintenance?",
        outcome="completed",
        evidence_access="accessible",
        execution_mode="local",
        headers={"X-API-Key": "secret-credential"},
        api_key="secret-credential",
        exception="raw exception secret-credential",
    )
    response["sources"][0]["answer_spans"] = [
        {"start": 0, "end": 35, "text": "Relay maintenance lasts 11 minutes."}
    ]
    response["provenance"] = {
        "answer_selection": {"mode": "reader"},
        "api_key": "nested-secret",
        "request_headers": {"Authorization": "nested-secret"},
    }
    row = row_builder(case, response, 200, docs, require_answer_spans=False)
    observed = row["observed_response"]
    assert observed["answer"] == "Relay maintenance lasts 11 minutes."
    assert (
        observed["sources"][0]["quoted_text"] == "Relay maintenance lasts 11 minutes."
    )
    assert observed["sources"][0]["answer_spans"] == [
        {"start": 0, "end": 35, "text": "Relay maintenance lasts 11 minutes."}
    ]
    assert observed["id"] == "query-fixture"
    assert observed["provenance"] == {"answer_selection": {"mode": "reader"}}
    assert "secret-credential" not in json.dumps(observed)
    assert "nested-secret" not in json.dumps(observed)
    response["sources"][0]["quoted_text"] = "mutated caller value"
    assert (
        observed["sources"][0]["quoted_text"] == "Relay maintenance lasts 11 minutes."
    )


def test_legacy_row_builder_keeps_historical_report_shape():
    import runpy

    script = (
        Path(__file__).resolve().parents[3] / "scripts/evaluate_portfolio_retrieval.py"
    )
    row_builder = runpy.run_path(str(script)).get("build_case_row")
    assert callable(row_builder), "Evaluation needs a shared case row builder"
    case, response, docs = _coverage_case_and_response()
    del case["score_contract"]
    row = row_builder(case, response, 200, docs, require_answer_spans=False)
    assert row == score_case(case, response, 200, docs)
    assert "observed_response" not in row


def test_coverage_public_document_mapping_excludes_seed_credentials_and_permissions():
    import runpy

    script = (
        Path(__file__).resolve().parents[3] / "scripts/evaluate_portfolio_retrieval.py"
    )
    public_mapping = runpy.run_path(str(script)).get("public_source_document_ids")
    assert callable(public_mapping), (
        "Portable v2 reports require a public document-ID mapping"
    )
    mapped = {
        "logical-source": {
            "document_id": "actual-document-uuid",
            "api_key": "must-not-escape",
            "principals": {"operator-a": {"api_key": "private-key"}},
            "visibility": "private",
            "versions": {"1": {"content": "source"}},
        }
    }
    assert public_mapping(mapped) == {"logical-source": "actual-document-uuid"}
