"""External compiler/seed/scorer seams over invented inputs only; no API runs."""

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import httpx
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
        f"representation_{name}", ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_manifest_carries_projection_binding_without_embedded_raw_sources(
    tmp_path,
):
    source = write_fixture(tmp_path / "common")
    corpus = compile_corpus(source, tmp_path / "arm", "legacy-flat-v1")
    identity = script("seed_portfolio").corpus_identity(corpus)
    declared = corpus["manifest"]["comparison_representation"]
    expected = {
        key: value
        for key, value in declared.items()
        if key not in {"common_manifest_text", "common_files"}
    }
    assert identity.get("comparison_representation") == expected


@pytest.mark.parametrize("profile", ["legacy-flat-v1", "connected-paragraphs-v1"])
def test_existing_online_and_portable_scorers_accept_exact_arm_view(tmp_path, profile):
    source = write_fixture(tmp_path / "common")
    edit_manifest(
        source,
        lambda m: m.update(
            schema_version=2, score_contract="coverage-v2", corpus_role="development"
        ),
    )
    rewrite_payload(
        source, "cases", lambda rows: rows[0].update(score_contract="coverage-v2")
    )
    corpus = compile_corpus(source, tmp_path / "arm", profile)
    version = corpus["documents"][0]["versions"][0]
    identifier = "11111111-1111-4111-8111-111111111111"
    seed = {
        "documents": {
            "protocol": {
                "document_id": identifier,
                "versions": {"1": {"content_hash": version["content_hash"]}},
            }
        }
    }
    runner = script("evaluate_portfolio_retrieval")
    auditor = script("verify_answer_coverage_delivery")
    documents = runner.map_documents(corpus, seed)
    portable = auditor.portable_documents(
        {"source_document_ids": {"protocol": identifier}}, corpus
    )
    assert documents == portable
    body = version["content"]
    response = {
        "question": corpus["cases"][0]["question"],
        "answer": body,
        "outcome": "completed",
        "refused": False,
        "sources": [
            {
                "document_id": identifier,
                "document_version": 1,
                "content_hash": version["content_hash"],
                "quoted_text": body,
                "answer_spans": [{"start": 0, "end": len(body), "text": body}],
            }
        ],
        "retrieval_trace": {
            "scores": [{"document_id": identifier, "document_version": 1}]
        },
    }
    case = corpus["cases"][0]
    row = runner.build_case_row(
        case, response, 200, documents, require_answer_spans=True
    )
    assert row["answer_quality_passed"] and row["span_integrity_correct"]
    assert auditor.audit_row(row, case, portable, True)["passed"]
    damaged = copy.deepcopy(response)
    damaged["sources"][0]["quoted_text"] += " invented bytes"
    result = runner.build_case_row(
        case, damaged, 200, documents, require_answer_spans=True
    )
    assert not result["citation_integrity_correct"]


def test_compiler_cli_is_explicit_and_never_overwrites(tmp_path):
    source = write_fixture(tmp_path / "common")
    target = tmp_path / "arm"
    command = [
        sys.executable,
        str(ROOT / "scripts/compile_corpus_representation.py"),
        str(source),
        str(target),
        "--profile",
        "legacy-flat-v1",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    descriptor = json.loads(result.stdout)
    assert (
        descriptor["profile"] == "legacy-flat-v1"
        and descriptor["execution_arm"] == "baseline"
    )
    assert "common_files" not in descriptor
    original = (target / "manifest.json").read_bytes()
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert (target / "manifest.json").read_bytes() == original


@pytest.mark.parametrize("mutation", ["missing", "extra", "body", "hash", "current"])
async def test_seed_publication_preflight_remains_strict_without_api(
    tmp_path, mutation
):
    source = write_fixture(tmp_path / "common")
    corpus = compile_corpus(source, tmp_path / "arm", "legacy-flat-v1")
    fixture = corpus["documents"][0]
    identifier = "11111111-1111-4111-8111-111111111111"
    version = fixture["versions"][0]

    def handler(request):
        if request.url.path.endswith("/versions"):
            numbers = (
                [] if mutation == "missing" else [1, 2] if mutation == "extra" else [1]
            )
            return httpx.Response(200, json=[{"version_number": n} for n in numbers])
        payload = {
            "document_id": identifier,
            "version_number": 1,
            "content_hash": version["content_hash"],
            "normalized_content": version["content"],
            "source_status": "current",
        }
        if mutation == "body":
            payload["normalized_content"] += " changed"
        elif mutation == "hash":
            payload["content_hash"] = "0" * 64
        elif mutation == "current":
            payload["source_status"] = "superseded"
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        with pytest.raises(RuntimeError, match="publication|version set"):
            await script("seed_portfolio").verify_publications(
                client, identifier, fixture, {}
            )


def test_external_common_hash_binding_is_required_when_requested(tmp_path):
    source = write_fixture(tmp_path / "common")
    compile_corpus(source, tmp_path / "arm", "legacy-flat-v1")
    with pytest.raises(ValueError, match="[Rr]epresentation"):
        load_corpus(tmp_path / "arm", expected_common_manifest_sha256="0" * 64)
