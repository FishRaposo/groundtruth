"""Verify a GroundTruth portfolio evidence bundle without network or services."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from portfolio_demo import render_markdown, reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE = REPO_ROOT / "artifacts" / "portfolio" / "groundtruth-evidence"
GOLDEN = (
    REPO_ROOT
    / "apps"
    / "api"
    / "tests"
    / "fixtures"
    / "golden"
    / "portfolio-evidence.json"
)
REQUIRED_FILES = {
    "checksums.sha256",
    "manifest.json",
    "report.json",
    "report.md",
}
CHECKSUM_PATTERN = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9_.-]+)$")


class VerificationError(RuntimeError):
    """A clear, user-facing evidence verification failure."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise VerificationError(f"malformed JSON: {path.name}") from exc


def _load_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise VerificationError("malformed checksum file: invalid UTF-8") from exc
    for line_number, line in enumerate(lines, 1):
        match = CHECKSUM_PATTERN.fullmatch(line)
        if match is None:
            raise VerificationError(f"malformed checksum entry at line {line_number}")
        digest, name = match.groups()
        if name in checksums:
            raise VerificationError(f"duplicate checksum entry: {name}")
        checksums[name] = digest
    return checksums


def verify_bundle(bundle: Path) -> None:  # noqa: C901
    """Validate structure, JSON, checksums, manifest, golden parity, and proof hash."""
    if not bundle.is_dir():
        raise VerificationError(f"evidence directory not found: {bundle}")
    present = {path.name for path in bundle.iterdir() if path.is_file()}
    for name in sorted(REQUIRED_FILES - present):
        raise VerificationError(f"missing required file: {name}")
    for name in sorted(present - REQUIRED_FILES):
        raise VerificationError(f"unexpected file: {name}")

    report = _load_json(bundle / "report.json")
    manifest = _load_json(bundle / "manifest.json")
    checksums = _load_checksums(bundle / "checksums.sha256")
    expected_checksum_files = {"manifest.json", "report.json", "report.md"}
    if set(checksums) != expected_checksum_files:
        raise VerificationError("checksum inventory mismatch")
    for name in sorted(expected_checksum_files):
        if _sha256(bundle / name) != checksums[name]:
            raise VerificationError(f"checksum mismatch: {name}")

    if not isinstance(manifest, dict):
        raise VerificationError("malformed manifest: expected object")
    expected_manifest_keys = {
        "artifact",
        "files",
        "reproducibility_hash",
        "schema_version",
    }
    if set(manifest) != expected_manifest_keys:
        raise VerificationError("malformed manifest: unexpected keys")
    if manifest.get("artifact") != "groundtruth-evidence":
        raise VerificationError("manifest artifact mismatch")
    if manifest.get("schema_version") != 1:
        raise VerificationError("malformed manifest: unsupported schema")
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, dict) or set(manifest_files) != {
        "report.json",
        "report.md",
    }:
        raise VerificationError("manifest inventory mismatch")
    for name in sorted(manifest_files):
        entry = manifest_files[name]
        if not isinstance(entry, dict):
            raise VerificationError(f"malformed manifest entry: {name}")
        if set(entry) != {"bytes", "sha256"}:
            raise VerificationError(f"malformed manifest entry keys: {name}")
        if entry.get("sha256") != _sha256(bundle / name):
            raise VerificationError(f"manifest checksum mismatch: {name}")
        if entry.get("bytes") != (bundle / name).stat().st_size:
            raise VerificationError(f"manifest size mismatch: {name}")

    if report != _load_json(GOLDEN):
        raise VerificationError("report does not match golden fixture")
    if (bundle / "report.md").read_text(encoding="utf-8") != render_markdown(report):
        raise VerificationError("report Markdown does not match report JSON")
    bundle_hash = reproducibility_hash(
        {
            "report.json": (bundle / "report.json").read_bytes(),
            "report.md": (bundle / "report.md").read_bytes(),
        }
    )
    if manifest.get("reproducibility_hash") != bundle_hash:
        raise VerificationError("reproducibility hash mismatch")
    summary = report.get("summary") if isinstance(report, dict) else None
    if not isinstance(summary, dict) or summary.get("failed") != 0:
        raise VerificationError("report contains failed checks")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify deterministic GroundTruth portfolio evidence."
    )
    parser.add_argument("bundle", nargs="?", type=Path, default=DEFAULT_BUNDLE)
    args = parser.parse_args()
    try:
        verify_bundle(args.bundle.resolve())
    except (OSError, VerificationError) as exc:
        print(f"verification failed: {exc}", file=sys.stderr)
        return 1
    print("Verified 4 files: manifest, report JSON/Markdown, and checksums.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
