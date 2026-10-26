"""Verify observed artifact integrity without turning a failed quality gate green."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"keyword", "vector", "hybrid", "reranked"}


def digest(path: Path, *, source: bool = False) -> str:
    body = (
        path.read_text(encoding="utf-8").replace("\r\n", "\n").encode()
        if source
        else path.read_bytes()
    )
    return hashlib.sha256(body).hexdigest()


def inside(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("Evidence manifest path escapes its configured root")
    return target


def load(root: Path, name: str) -> dict:
    text = inside(root, name).read_text(encoding="utf-8")
    if re.search(r"\bgt_[a-f0-9]{48}\b", text):
        raise ValueError("A raw disposable API key entered public evidence")
    return json.loads(text)


def verify_manifest(directory: Path) -> dict:
    manifest = load(directory, "manifest.json")
    if manifest.get("schema_version") != 1:
        raise ValueError("Unknown connected evidence schema")
    for name, expected in manifest["files"].items():
        if digest(inside(directory, name)) != expected:
            raise ValueError(f"Evidence checksum mismatch: {name}")
    for name, expected in manifest["current_source_sha256_utf8_lf"].items():
        if digest(inside(ROOT, name), source=True) != expected:
            raise ValueError(f"Current source changed after observation: {name}")
    return manifest


def verify_quality(directory: Path, manifest: dict) -> None:
    development = load(directory, "development-final.json")
    selection = load(directory, "selection-final.json")
    held = load(directory, "held-out-final.json")
    if (
        digest(directory / "development-final.json")
        != selection["development_report_sha256"]
    ):
        raise ValueError("Frozen development report changed")
    if digest(directory / "selection-final.json") != held["selection_sha256"]:
        raise ValueError("Held-out selection fingerprint changed")
    if selection["selection_basis"] != "development_only":
        raise ValueError("Selection was not declared development-only")
    if datetime.fromisoformat(selection["frozen_at"]) >= datetime.fromisoformat(
        held["created_at"]
    ):
        raise ValueError("Selection chronology is invalid")
    if {development["split"], held["split"]} != {"development", "held_out"}:
        raise ValueError("Evaluation split metadata is inconsistent")
    verify_case_counts(development, 20, selection)
    verify_case_counts(held, 80, selection)
    if not all(result["summary"]["failed"] > 0 for result in held["results"].values()):
        raise ValueError("The original failed held-out result was replaced")
    if manifest["first_quality_gate"] != {"status": "failed", "exit_code": 1}:
        raise ValueError("A failed quality gate must remain explicitly failed")


def verify_case_counts(report: dict, count: int, selection: dict) -> None:
    if set(report["results"]) != METHODS:
        raise ValueError("Evaluation method set changed")
    if report["corpus_manifest_sha256"] != selection["corpus_manifest_sha256"]:
        raise ValueError("Evaluation corpus fingerprint differs")
    for result in report["results"].values():
        rows = result["cases"]
        summary = result["summary"]
        passed = sum(row["passed"] for row in rows)
        if len(rows) != count or len({row["case_id"] for row in rows}) != count:
            raise ValueError("Evaluation count or case identity changed")
        if summary["passed"] != passed or summary["failed"] != count - passed:
            raise ValueError("Evaluation summary disagrees with recorded cases")


def verify_runtime(directory: Path) -> None:
    connected = load(directory, "connected-workflow.json")
    restart = load(directory, "restart.json")
    browser = load(directory, "frontend-gates.json")
    if connected["overlapping_requests"] != 20 or connected["application_errors"] != 0:
        raise ValueError("Connected concurrency evidence is incomplete")
    if restart["restart_of"] != connected["observed_at"]:
        raise ValueError("Restart evidence refers to another workflow")
    if (
        browser["sample_browser"]["passed"] != 3
        or not browser["sample_browser"]["zero_api_external_requests"]
    ):
        raise ValueError("Offline browser evidence is incomplete")
    if (
        browser["connected_browser"]["passed"] != 3
        or browser["connected_browser"]["successful_api_mocks"]
    ):
        raise ValueError("Real connected browser evidence is incomplete")


def verify(directory: Path) -> None:
    manifest = verify_manifest(directory)
    verify_quality(directory, manifest)
    verify_runtime(directory)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, default=ROOT / "docs/evidence/portfolio"
    )
    args = parser.parse_args()
    try:
        verify(args.directory)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Connected evidence verification failed: {exc}")
        return 1
    print("Artifact integrity verified; first quality gate remains FAILED (exit1).")
    print(
        "This does not certify model quality, PostgreSQL/Redis or production capacity."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
