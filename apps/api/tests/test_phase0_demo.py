from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "examples" / "run_demo.py"


def test_demo_prints_one_cited_answer_and_one_refusal(tmp_path: Path) -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "OPENAI_API_KEY"}
    }
    result = subprocess.run(
        [sys.executable, str(DEMO)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    lines = result.stdout.splitlines()
    rows = {
        line.split("  ")[0]: line.split()
        for line in lines
        if line.startswith(("How many days", "What are the salary"))
        and ("ANSWERED" in line or "REFUSED" in line)
    }
    answered = rows["How many days do I have to request a refund?"]
    refused = rows["What are the salary bands?"]
    assert answered[-3:-2] == ["ANSWERED"]
    assert float(answered[-2]) >= 0.5
    assert int(answered[-1]) >= 1
    assert refused[-3:-2] == ["REFUSED"]
    assert float(refused[-2]) < 0.5
    assert refused[-1] == "0"
    assert any(line.startswith("   Answer: ") and "[1]" in line for line in lines)
    assert any(line.startswith("   [1] refund_policy.md") for line in lines)
    assert any(line.startswith("   Refused: ") for line in lines)
    assert lines[-1] == "Demo complete: one cited answer, one refusal."
    # Runs from any directory without writing into it.
    assert list(tmp_path.iterdir()) == []
