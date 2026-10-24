"""Historical observations must verify against recorded source, not repaired code."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "e19006c9e8f1a11ef4930e24ed88128e765b6bf5"


def test_original_observations_verify_against_the_frozen_source_revision():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/verify_connected_evidence.py"),
            "--source-revision",
            BASELINE,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FAILED" in result.stdout


def test_unavailable_historical_source_cannot_be_claimed_verified():
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/verify_connected_evidence.py"),
            "--source-revision",
            "0000000000000000000000000000000000000000",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "verification failed" in result.stdout
