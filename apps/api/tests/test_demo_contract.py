"""Portfolio demo contracts: ``make demo`` runs the real pipeline offline."""

from __future__ import annotations

import importlib.util
import os
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


def _load_demo() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "groundtruth_portfolio_demo", ROOT / "examples" / "run_demo.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def test_demo_selects_the_sentence_that_answers_the_question(
    tmp_path: Path, monkeypatch
) -> None:
    # The executable configures its child runtime before imports. Restore those
    # environment values after this in-process rendering contract as well.
    for key in (
        "DATABASE_URL",
        "OPENAI_API_KEY",
        "APP_ENV",
        "EMBEDDING_MODE",
        "GENERATION_MODE",
    ):
        monkeypatch.setenv(key, os.environ.get(key, ""))
    demo = _load_demo()
    sample = tmp_path / "refund_policy.md"
    sample.write_text(
        "# Refund Policy\n\nCustomers may request a refund within 30 days of "
        "purchase. Refunds are issued to the original payment method within "
        "5 business days. Digital goods are non-refundable once downloaded.",
        encoding="utf-8",
    )
    monkeypatch.setattr(demo, "SAMPLE", sample)
    monkeypatch.setattr(demo, "REPO_ROOT", tmp_path)
    document, outcomes = await demo.run_demo()
    score = outcomes[0].confidence
    answer = next(
        line
        for line in demo.render(document, outcomes).splitlines()
        if line.startswith("   Answer: ")
    )

    assert score >= demo.get_settings().REFUSAL_CONFIDENCE_THRESHOLD
    assert "30 days" in answer
    assert "[1]" in answer
    assert "#" not in answer
