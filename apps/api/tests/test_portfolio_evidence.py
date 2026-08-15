"""Deterministic offline portfolio-evidence bundle contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATOR = REPO_ROOT / "scripts" / "portfolio_demo.py"
VERIFIER = REPO_ROOT / "scripts" / "verify_portfolio_evidence.py"
GOLDEN = Path(__file__).parent / "fixtures" / "golden" / "portfolio-evidence.json"
REQUIRED_FILES = {
    "manifest.json",
    "report.json",
    "report.md",
    "checksums.sha256",
}


def test_generator_forces_offline_database_before_application_imports() -> None:
    source = GENERATOR.read_text(encoding="utf-8")
    offline_setup = source.index('os.environ["DATABASE_URL"]')
    first_app_import = source.index("from app.db.session import Base")

    assert offline_setup < first_app_import
    assert "sqlite+aiosqlite:///:memory:" in source[:first_app_import]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _rewrite_manifest_and_ledger(output_dir: Path, manifest: dict[str, object]) -> None:
    manifest_bytes = _json_bytes(manifest)
    (output_dir / "manifest.json").write_bytes(manifest_bytes)
    checksums = {
        "manifest.json": _sha256(manifest_bytes),
        "report.json": _sha256((output_dir / "report.json").read_bytes()),
        "report.md": _sha256((output_dir / "report.md").read_bytes()),
    }
    (output_dir / "checksums.sha256").write_bytes(
        "".join(
            f"{digest}  {name}\n" for name, digest in sorted(checksums.items())
        ).encode("utf-8")
    )


def _run(script: Path, *args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *(str(arg) for arg in args)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _generate(output_dir: Path) -> subprocess.CompletedProcess[str]:
    return _run(GENERATOR, "--output-dir", output_dir)


def test_portfolio_demo_matches_golden_and_verifies(tmp_path: Path) -> None:
    output_dir = tmp_path / "evidence"

    generated = _generate(output_dir)

    assert generated.returncode == 0, generated.stderr
    assert {path.name for path in output_dir.iterdir()} == REQUIRED_FILES
    assert json.loads((output_dir / "report.json").read_text(encoding="utf-8")) == (
        json.loads(GOLDEN.read_text(encoding="utf-8"))
    )
    verified = _run(VERIFIER, output_dir)
    assert verified.returncode == 0, verified.stderr
    assert "verified 4 files" in verified.stdout.lower()


def test_two_runs_are_byte_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert _generate(first).returncode == 0
    assert _generate(second).returncode == 0

    first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    second_manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
    assert (
        first_manifest["reproducibility_hash"]
        == second_manifest["reproducibility_hash"]
    )
    assert {name: (first / name).read_bytes() for name in REQUIRED_FILES} == {
        name: (second / name).read_bytes() for name in REQUIRED_FILES
    }


def test_custom_bundle_records_its_normalized_actual_output_location(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "custom-evidence"

    assert _generate(output_dir).returncode == 0
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))

    assert report["execution"]["output_path"] == "<normalized-path>"


def test_normalizer_removes_volatile_and_sensitive_values() -> None:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from portfolio_demo import normalize_evidence

    normalized = normalize_evidence(
        {
            "created_at": "2026-08-15T14:01:02.123456+00:00",
            "workflow_id": "550e8400-e29b-41d4-a716-446655440000",
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "duration_ms": 812.4,
            "path": str(REPO_ROOT / "data" / "source.txt"),
            "source_path": str(REPO_ROOT / "data" / "source.txt"),
            "updated_at": "2026-08-15T14:01:02.123456+00:00",
            "started_at": "2026-08-15T14:01:02.123456+00:00",
            "environment": {
                "OPENAI_API_KEY": "secret",
                "ACCESS_TOKEN": "secret",
                "CI": "true",
            },
            "provider_output": {"request_id": "live-id", "text": "variable"},
            "provider_response": {"request_id": "live-id", "text": "variable"},
            "nested": {
                "authorization": "Bearer secret",
                "access_token": "secret",
                "client_secret": "secret",
                "signing_secret_value": "secret",
                "safe": "kept",
            },
        }
    )

    assert normalized == {
        "created_at": "<normalized-timestamp>",
        "workflow_id": "<normalized-id>",
        "id": "<normalized-id>",
        "duration_ms": 0,
        "path": "<repo>/data/source.txt",
        "source_path": "<repo>/data/source.txt",
        "updated_at": "<normalized-timestamp>",
        "started_at": "<normalized-timestamp>",
        "environment": {
            "ACCESS_TOKEN": "[REDACTED]",
            "CI": "<normalized-env>",
            "OPENAI_API_KEY": "[REDACTED]",
        },
        "provider_output": "<normalized-provider-output>",
        "provider_response": "<normalized-provider-output>",
        "nested": {
            "authorization": "[REDACTED]",
            "access_token": "[REDACTED]",
            "client_secret": "[REDACTED]",
            "signing_secret_value": "[REDACTED]",
            "safe": "kept",
        },
    }


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("missing", "missing required file: report.md"),
        ("malformed", "malformed json: report.json"),
        ("tampered", "checksum mismatch: report.json"),
        ("checksum", "malformed checksum entry"),
        ("checksum-utf8", "malformed checksum file: invalid utf-8"),
        ("coordinated-md", "report markdown does not match report json"),
        ("extra", "unexpected file: extra.txt"),
        ("manifest-artifact", "manifest artifact mismatch"),
        ("manifest-extra", "malformed manifest: unexpected keys"),
        ("manifest-report-only", "reproducibility hash mismatch"),
    ],
)
def test_verifier_fails_clearly_for_invalid_bundles(
    tmp_path: Path, mutation: str, expected_error: str
) -> None:
    output_dir = tmp_path / mutation
    assert _generate(output_dir).returncode == 0

    if mutation == "missing":
        (output_dir / "report.md").unlink()
    elif mutation == "malformed":
        (output_dir / "report.json").write_text("{broken", encoding="utf-8")
    elif mutation == "tampered":
        report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
        report["summary"]["passed"] = 0
        (output_dir / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    elif mutation == "checksum":
        (output_dir / "checksums.sha256").write_text(
            "not-a-checksum report.json\n", encoding="utf-8"
        )
    elif mutation == "checksum-utf8":
        (output_dir / "checksums.sha256").write_bytes(b"\xff\xfe")
    elif mutation == "coordinated-md":
        report_md = (output_dir / "report.md").read_bytes() + b"tampered\n"
        (output_dir / "report.md").write_bytes(report_md)
        manifest_path = output_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["report.md"] = {
            "bytes": len(report_md),
            "sha256": _sha256(report_md),
        }
        _rewrite_manifest_and_ledger(output_dir, manifest)
    elif mutation == "extra":
        (output_dir / "extra.txt").write_text("unexpected", encoding="utf-8")
    else:
        manifest = json.loads(
            (output_dir / "manifest.json").read_text(encoding="utf-8")
        )
        if mutation == "manifest-artifact":
            manifest["artifact"] = "misleading-artifact"
        elif mutation == "manifest-extra":
            manifest["description"] = "misleading metadata"
        else:
            manifest["reproducibility_hash"] = _sha256(
                (output_dir / "report.json").read_bytes()
            )
        _rewrite_manifest_and_ledger(output_dir, manifest)

    verified = _run(VERIFIER, output_dir)
    assert verified.returncode != 0
    assert expected_error in verified.stderr.lower()


def test_checksum_ledger_uses_lf_on_every_platform(tmp_path: Path) -> None:
    output_dir = tmp_path / "evidence"
    assert _generate(output_dir).returncode == 0

    ledger = (output_dir / "checksums.sha256").read_bytes()
    assert b"\r\n" not in ledger
    assert ledger.endswith(b"\n")


def test_generated_artifact_directory_is_gitignored() -> None:
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            "artifacts/portfolio/groundtruth-evidence/report.json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
