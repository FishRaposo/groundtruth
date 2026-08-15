# Vendored from FishRaposo/operator-shared-core v1.3.0.
# Source commit: dbf276a7708da65b55e1f10b35af634b300d1f07.
"""Eval-judge base, registry, deterministic simulation, and drift detection.

A ``Judge`` ABC producing a uniform ``JudgeResult``, a registry, a small set of
generally useful built-in judges (semantic match, citation presence, refusal), a
deterministic ``SimulatedEvaluator`` for offline/seeded runs, and a ``DriftDetector``
for baseline-vs-current regression. This is the convergence point for the
evalforge <-> rag-evaluation-lab evaluation overlap.
"""

import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, TypeVar

from pydantic import BaseModel, Field

from app.internal.vendor_core.embeddings import (
    cosine_similarity,
    jaccard_similarity,
    tfidf_cosine,
)

_REFUSAL_MARKERS = (
    "i cannot",
    "i can't",
    "cannot help",
    "not able to",
    "i'm unable",
    "i am unable",
    "insufficient information",
    "no relevant",
    "cannot answer",
    "don't have enough",
)
_CITATION_RE = re.compile(r"\[\d+\]")


class JudgeResult(BaseModel):
    """Uniform result of evaluating one actual output."""

    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    judge: str
    reason: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Judge(ABC):
    """Abstract evaluation strategy."""

    name: str = "judge"

    @abstractmethod
    async def evaluate(
        self,
        *,
        expected: Optional[str],
        actual: str,
        context: Optional[dict[str, Any]] = None,
    ) -> JudgeResult: ...


_REGISTRY: dict[str, type[Judge]] = {}
JudgeT = TypeVar("JudgeT", bound=Judge)


def register_judge(name: str) -> Callable[[type[JudgeT]], type[JudgeT]]:
    """Class decorator registering a judge under ``name``."""

    def decorator(cls: type[JudgeT]) -> type[JudgeT]:
        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_judge(name: str, **kwargs: Any) -> Judge:
    """Instantiate a registered judge by name."""
    if name not in _REGISTRY:
        raise KeyError(
            f"No judge registered under '{name}'. Known: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name](**kwargs)


def list_judges() -> list[str]:
    """Return the sorted list of registered judge names."""
    return sorted(_REGISTRY)


@register_judge("semantic_match")
class SemanticMatchJudge(Judge):
    """Pass when expected and actual are semantically similar enough."""

    name = "semantic_match"

    def __init__(self, threshold: float = 0.8, provider: Any = None) -> None:
        self.threshold = threshold
        self.provider = provider

    async def evaluate(self, *, expected, actual, context=None) -> JudgeResult:
        if expected is None:
            return JudgeResult(
                passed=False, score=0.0, judge=self.name, reason="no expected value"
            )
        if self.provider is not None:
            ev = await self.provider.embed(expected)
            av = await self.provider.embed(actual)
            score = cosine_similarity(ev.vector, av.vector)
        else:
            score = max(
                tfidf_cosine(expected, actual),
                jaccard_similarity(expected, actual),
            )
        score = max(0.0, min(1.0, score))
        return JudgeResult(passed=score >= self.threshold, score=score, judge=self.name)


@register_judge("citation")
class CitationJudge(Judge):
    """Pass when the output carries at least ``min_citations`` ``[n]`` markers."""

    name = "citation"

    def __init__(self, min_citations: int = 1) -> None:
        self.min_citations = min_citations

    async def evaluate(self, *, expected, actual, context=None) -> JudgeResult:
        count = len(set(_CITATION_RE.findall(actual)))
        passed = count >= self.min_citations
        return JudgeResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            judge=self.name,
            reason=f"{count} citation(s)",
        )


@register_judge("refusal")
class RefusalJudge(Judge):
    """Pass when the output is a refusal (used to verify grounded refusal behavior)."""

    name = "refusal"

    async def evaluate(self, *, expected, actual, context=None) -> JudgeResult:
        lowered = actual.lower()
        refused = any(marker in lowered for marker in _REFUSAL_MARKERS)
        return JudgeResult(
            passed=refused,
            score=1.0 if refused else 0.0,
            judge=self.name,
            reason="refusal detected" if refused else "no refusal",
        )


class SimulatedEvaluator:
    """Deterministic offline lexical scoring for reproducible offline/sim runs."""

    def score(
        self, expected: Optional[str], actual: str, *, seed: Optional[int] = None
    ) -> float:
        if expected is None:
            return 1.0 if actual.strip() else 0.0
        lexical = max(
            tfidf_cosine(expected, actual),
            jaccard_similarity(expected, actual),
        )
        return max(0.0, min(1.0, lexical))


class DriftReport(BaseModel):
    """Regression summary comparing a current run against a baseline."""

    pass_rate_delta: float
    avg_score_delta: float
    changed_tests: list[str] = Field(default_factory=list)
    is_regression: bool = False


class DriftDetector:
    """Compare baseline vs current judge results to flag regressions."""

    def __init__(self, regression_threshold: float = 0.05) -> None:
        self.regression_threshold = regression_threshold

    def compare(
        self, baseline: list[JudgeResult], current: list[JudgeResult]
    ) -> DriftReport:
        def pass_rate(results: list[JudgeResult]) -> float:
            return (
                sum(1 for r in results if r.passed) / len(results) if results else 0.0
            )

        def avg_score(results: list[JudgeResult]) -> float:
            return sum(r.score for r in results) / len(results) if results else 0.0

        pass_rate_delta = pass_rate(current) - pass_rate(baseline)
        avg_score_delta = avg_score(current) - avg_score(baseline)
        baseline_by_judge = {r.judge: r for r in baseline}
        changed = [
            r.judge
            for r in current
            if r.judge in baseline_by_judge
            and baseline_by_judge[r.judge].passed != r.passed
        ]
        is_regression = (
            pass_rate_delta < -self.regression_threshold
            or avg_score_delta < -self.regression_threshold
        )
        return DriftReport(
            pass_rate_delta=pass_rate_delta,
            avg_score_delta=avg_score_delta,
            changed_tests=changed,
            is_regression=is_regression,
        )
