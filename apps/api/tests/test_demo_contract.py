"""Portfolio demo contracts: ``make demo`` runs the real pipeline offline."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / "examples" / "run_demo.py"

PIPELINE_SERVICES = {
    "app.services.ingestion",
    "app.services.retrieval",
    "app.services.reranking",
    "app.services.refusal",
    "app.services.generation",
    "app.services.citation",
}


def test_demo_imports_the_api_pipeline_services() -> None:
    tree = ast.parse(DEMO.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert PIPELINE_SERVICES <= imported
    # The demo must not carry its own retriever or threshold.
    assert not any(module.endswith("embeddings") for module in imported)
    assert "REFUSAL_THRESHOLD" not in DEMO.read_text(encoding="utf-8")


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
    assert any(line.startswith("   [1] refund_policy.md") for line in lines)
    assert any(line.startswith("   Refused: ") for line in lines)
    assert lines[-1] == "Demo complete: one cited answer, one refusal."
    # Runs from any directory without writing into it.
    assert list(tmp_path.iterdir()) == []
