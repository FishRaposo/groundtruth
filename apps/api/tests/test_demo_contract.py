"""Portfolio demo contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def _load_demo() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "groundtruth_portfolio_demo", ROOT / "examples" / "run_demo.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_selects_the_sentence_that_answers_the_question() -> None:
    demo = _load_demo()
    document = demo.get_parser("refund_policy.md").parse(
        demo.CORPUS, filename="policy.md"
    )
    chunks = demo.chunk_text(
        document.text,
        strategy=demo.ChunkStrategy.STRUCTURAL,
        chunk_size=200,
    )

    answer, score = demo.answer("How many days do I have to request a refund?", chunks)

    assert score >= demo.REFUSAL_THRESHOLD
    assert "30 days" in answer
    assert "[1]" in answer
    assert "#" not in answer
