"""Dependency-free adapter for EvalForge-shaped local JSON fixtures."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from app.internal.vendor_core.evaljudge import get_judge
from pydantic import BaseModel, Field, model_validator


class EvaluationCase(BaseModel):
    """One portable evaluation case."""

    id: str = Field(min_length=1)
    input: str = Field(min_length=1)
    expected: str | None = None
    actual: str = ""
    judges: list[str] = Field(default_factory=lambda: ["semantic_match"])
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationSuite(BaseModel):
    """Small EvalForge-compatible suite envelope."""

    name: str = Field(min_length=1)
    tests: list[EvaluationCase]

    @model_validator(mode="after")
    def unique_test_ids(self) -> EvaluationSuite:
        seen: set[str] = set()
        for case in self.tests:
            if case.id in seen:
                raise ValueError(f"duplicate test id: {case.id}")
            seen.add(case.id)
        return self


def load_evalforge_fixture(path: str | Path) -> EvaluationSuite:
    """Load a local JSON suite without importing EvalForge."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        return EvaluationSuite.model_validate(data)
    except ValueError as exc:
        if "duplicate test id:" in str(exc):
            duplicate = str(exc).split("duplicate test id:", 1)[1].split("[", 1)[0]
            raise ValueError(f"duplicate test id:{duplicate}".strip()) from exc
        raise


class GroundTruthEvaluationAdapter:
    """Run vendored deterministic judges over a portable local fixture."""

    async def evaluate(self, suite: EvaluationSuite) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for case in suite.tests:
            judge_results = []
            for judge_name in case.judges:
                judge = get_judge(judge_name)
                result = await judge.evaluate(
                    expected=case.expected,
                    actual=case.actual,
                    context={"input": case.input, **case.metadata},
                )
                judge_results.append(result.model_dump(mode="json"))
            passed = bool(judge_results) and all(
                result["passed"] for result in judge_results
            )
            results.append({"id": case.id, "passed": passed, "judges": judge_results})

        passed_count = sum(1 for result in results if result["passed"])
        return {
            "schema_version": 1,
            "suite": suite.name,
            "summary": {
                "passed": passed_count,
                "failed": len(results) - passed_count,
                "total": len(results),
            },
            "tests": results,
        }

    def evaluate_sync(self, suite: EvaluationSuite) -> dict[str, Any]:
        """Synchronous CLI convenience wrapper."""
        return asyncio.run(self.evaluate(suite))
