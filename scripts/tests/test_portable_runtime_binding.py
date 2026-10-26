"""Actual selection-file authority over invented portable records; no API/model."""

import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "runtime_binding_fixtures", ROOT / "scripts/tests/test_comparison_binding.py"
)
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)


@pytest.fixture(scope="module")
def protocol(tmp_path_factory):
    path = tmp_path_factory.mktemp("runtime-protocol")
    FIXTURE.blind_pair(path)
    return path


@pytest.fixture
def evidence(protocol, tmp_path):
    path = tmp_path / "records"
    shutil.copytree(protocol, path)
    from app.portfolio.comparison import load_views

    common, baseline, candidate = load_views(
        path / "common", path / "blind-baseline", path / "blind-candidate"
    )
    before = json.loads((path / "baseline-report.json").read_bytes())
    after = json.loads((path / "candidate-report.json").read_bytes())
    return path, common, baseline, candidate, before, after


def compare(evidence, **extra):
    path, common, baseline, candidate, before, after = evidence
    return FIXTURE.script("verify_answer_coverage_delivery").compare_reports(
        before,
        after,
        corpus=common,
        baseline_corpus=baseline,
        candidate_corpus=candidate,
        selection_path=path / "selection.json",
        **extra,
    )


def relabel_selection(path, before, after):
    digest = hashlib.sha256((path / "selection.json").read_bytes()).hexdigest()
    before["selection_sha256"] = after["selection_sha256"] = digest


def test_actual_selection_and_matching_runtime_are_both_verified(evidence):
    result = compare(evidence)
    assert result["gate"] == "passed"
    assert result["frozen_runtime_verified"] is True
    assert result["portable_evidence"]["candidate"]["runtime_verification"] == {
        "verified": True,
        "scope": "actual_frozen_selection",
        "checked_http_200_rows": 800,
    }


@pytest.mark.parametrize(
    "field",
    [
        "mode",
        "threshold",
        "revision",
        "evidence_profile",
        "evidence_support",
        "contract",
    ],
)
def test_missing_required_observed_runtime_fails_closed(evidence, field):
    *_, after = evidence
    for method in after["results"].values():
        row = method["cases"][0]
        row["observed_response"]["provenance"]["answer_selection"].pop(field)
        row["provenance"] = copy.deepcopy(row["observed_response"]["provenance"])
    with pytest.raises(ValueError, match="runtime"):
        compare(evidence)


def test_online_and_portable_use_same_runtime_authority(evidence):
    path, _, _, _, _, after = evidence
    row = after["results"]["keyword"]["cases"][0]
    response = row["observed_response"]
    response["provenance"]["answer_selection"]["threshold"] = -999
    settings = json.loads((path / "selection.json").read_bytes())["settings"]
    online = {"passed": True, "answer_quality_passed": True}
    FIXTURE.script("evaluate_portfolio_retrieval").check_response_configuration(
        online, response, 200, settings, "candidate"
    )
    assert online["execution_error"] is True
    with pytest.raises(ValueError, match="runtime"):
        compare(evidence)


@pytest.mark.parametrize(
    "damage",
    [
        "absent",
        "wrong-sha",
        "null",
        "list",
        "common",
        "development",
        "settings",
        "order",
        "partial",
        "claimed-partial",
    ],
)
def test_sha_label_and_report_claims_cannot_authorize_selected_runtime(
    evidence, damage
):
    path, _, _, _, before, after = evidence
    selection = path / "selection.json"
    value = json.loads(selection.read_bytes())
    if damage == "absent":
        selection.unlink()
    elif damage == "wrong-sha":
        after["selection_sha256"] = before["selection_sha256"] = "f" * 64
    elif damage in {"null", "list"}:
        selection.write_text(
            json.dumps(None if damage == "null" else []), encoding="utf-8"
        )
        relabel_selection(path, before, after)
    elif damage == "development":
        (path / "development_report.json").write_text("{}", encoding="utf-8")
    elif damage == "claimed-partial":
        after["settings"].pop("support_model_revision")
    else:
        if damage == "common":
            value["validation_corpus_manifest_sha256"] = "0" * 64
        elif damage == "settings":
            value["settings"]["reader_model_revision"] = "forged-reader"
            before["settings"]["reader_model_revision"] = after["settings"][
                "reader_model_revision"
            ] = "forged-reader"
        elif damage == "partial":
            value["settings"].pop("support_model_revision")
            for key in ("development_report", "candidate_freeze"):
                artifact_path = path / value[key + "_path"]
                artifact = json.loads(artifact_path.read_bytes())
                artifact["settings"].pop("support_model_revision")
                artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
                value[key + "_sha256"] = hashlib.sha256(
                    artifact_path.read_bytes()
                ).hexdigest()
            before["settings"].pop("support_model_revision")
            after["settings"].pop("support_model_revision")
        else:
            value["binding_at"] = "2026-10-24T00:00:00Z"
        selection.write_text(json.dumps(value), encoding="utf-8")
        relabel_selection(path, before, after)
    with pytest.raises((ValueError, OSError)):
        compare(evidence)


def cli_command(path):
    return [
        sys.executable,
        "-B",
        str(ROOT / "scripts/verify_answer_coverage_delivery.py"),
        "--baseline",
        str(path / "baseline-report.json"),
        "--candidate",
        str(path / "candidate-report.json"),
        "--corpus-dir",
        str(path / "common"),
        "--baseline-corpus-dir",
        str(path / "blind-baseline"),
        "--candidate-corpus-dir",
        str(path / "blind-candidate"),
        "--selection",
        str(path / "selection.json"),
    ]


@pytest.mark.parametrize("arm", ["baseline", "candidate"])
@pytest.mark.parametrize("value", [None, [], "sk-private-test-do-not-echo", 42])
def test_actual_cli_rejects_malformed_report_shapes_without_traceback(
    evidence, arm, value
):
    path, *_ = evidence
    (path / f"{arm}-report.json").write_text(json.dumps(value), encoding="utf-8")
    result = subprocess.run(
        cli_command(path),
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr + result.stdout
    assert "sk-private-test-do-not-echo" not in result.stderr + result.stdout


@pytest.mark.parametrize(
    "damage",
    [
        "partial-methods",
        "method-list",
        "settings-null",
        "settings-list",
        "wrong-arm",
        "missing-selection",
    ],
)
def test_actual_cli_shapes_and_missing_authority_are_error_two(evidence, damage):
    path, _, _, _, _, after = evidence
    if damage == "partial-methods":
        after["results"].pop("vector")
    elif damage == "method-list":
        after["results"]["vector"] = []
    elif damage == "settings-null":
        after["settings"] = None
    elif damage == "settings-list":
        after["settings"] = []
    elif damage == "wrong-arm":
        after["execution_arm"] = "baseline"
    (path / "candidate-report.json").write_text(json.dumps(after), encoding="utf-8")
    command = cli_command(path)
    if damage == "missing-selection":
        command = command[:-2]
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 2
    assert "Traceback" not in result.stderr + result.stdout


def test_actual_cli_with_frozen_artifact_preserves_success_zero(evidence):
    path, *_ = evidence
    result = subprocess.run(
        cli_command(path), cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["frozen_runtime_verified"] is True


def test_legacy_and_arithmetic_interfaces_are_honestly_runtime_unverified():
    spec = importlib.util.spec_from_file_location(
        "legacy_runtime_fixture", ROOT / "scripts/tests/test_answer_coverage_gate.py"
    )
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    corpus, before = old.portable_fixture("baseline", 30)
    _, after = old.portable_fixture("candidate", 114)
    verifier = FIXTURE.script("verify_answer_coverage_delivery")
    legacy = verifier.compare_reports(before, after, corpus=corpus)
    assert legacy["gate"] == "passed"
    assert legacy["comparison_scope"] == "legacy_sources_only_runtime_unverified"
    assert legacy["frozen_runtime_verified"] is False
    assert (
        legacy["portable_evidence"]["candidate"]["runtime_verification"]["verified"]
        is False
    )
    arithmetic = verifier.compare_reports(before, after)
    assert arithmetic["comparison_scope"] == "arithmetic_only_not_portable"
    assert arithmetic["frozen_runtime_verified"] is False


def test_actual_cli_with_matching_runtime_preserves_gate_failure_one(tmp_path):
    path = tmp_path / "gatefail"
    path.mkdir()
    FIXTURE.blind_pair(path, candidate_correct=113)
    result = subprocess.run(
        cli_command(path), cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 1, result.stdout + result.stderr
    value = json.loads(result.stdout)
    assert value["gate"] == "failed" and value["frozen_runtime_verified"] is True


def test_standalone_projected_audit_cannot_certify_without_selection(evidence):
    _, common, _, candidate, _, after = evidence
    with pytest.raises(ValueError, match="selection"):
        FIXTURE.script("verify_answer_coverage_delivery").audit_report(
            after, candidate, common_corpus=common
        )


def test_cli_missing_linked_artifact_does_not_echo_private_path(evidence):
    path, _, _, _, before, after = evidence
    selection = json.loads((path / "selection.json").read_bytes())
    selection["development_report_path"] = "sk-private-test-do-not-echo"
    (path / "selection.json").write_text(json.dumps(selection), encoding="utf-8")
    relabel_selection(path, before, after)
    for arm, report in (("baseline", before), ("candidate", after)):
        (path / f"{arm}-report.json").write_text(json.dumps(report), encoding="utf-8")
    result = subprocess.run(
        cli_command(path), cwd=ROOT, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 2
    assert "sk-private-test-do-not-echo" not in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
