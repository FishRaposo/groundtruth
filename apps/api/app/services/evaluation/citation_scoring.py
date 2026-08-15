"""Citation grounding evaluation via the internal vendor citation judge.

Grades whether a generated answer is properly grounded with inline ``[n]``
citation markers, and whether those markers resolve to retrieved sources. The
core pass/fail signal comes from the local :class:`CitationJudge`, while
this wrapper adds GroundTruth-specific context (resolved vs. dangling markers).

Deterministic and offline: the judge is pure-Python regex matching with no
model calls.
"""

from __future__ import annotations

import re
from typing import Any

from app.internal.vendor_core.evaljudge import CitationJudge, JudgeResult
from app.models.query import SourceCitation

_MARKER_RE = re.compile(r"\[(\d+)\]")


class CitationEvaluator:
    """Evaluate citation grounding of generated answers.

    Args:
        min_citations: Minimum distinct ``[n]`` markers required to pass.
    """

    def __init__(self, min_citations: int = 1) -> None:
        self.min_citations = min_citations
        self._judge = CitationJudge(min_citations=min_citations)

    async def evaluate(
        self,
        answer: str,
        citations: list[SourceCitation] | None = None,
    ) -> JudgeResult:
        """Grade ``answer`` for citation grounding.

        Runs the internal vendor :class:`CitationJudge` and augments its result
        metadata with how many of the answer's markers actually resolve to a
        provided source citation (``dangling`` markers are those that do not).

        Args:
            answer: The generated answer text.
            citations: Optional source citations assembled for the answer.

        Returns:
            A ``JudgeResult`` with extended metadata.
        """
        result = await self._judge.evaluate(expected=None, actual=answer)

        markers = {int(m) for m in _MARKER_RE.findall(answer)}
        available = {c.citation_index for c in (citations or [])}
        dangling = sorted(markers - available) if available else sorted(markers)
        resolved = sorted(markers & available)

        result.metadata.update(
            {
                "markers": sorted(markers),
                "resolved_markers": resolved,
                "dangling_markers": dangling,
                "all_resolved": not dangling,
            }
        )
        return result

    async def score(
        self,
        answer: str,
        citations: list[SourceCitation] | None = None,
    ) -> float:
        """Return just the numeric citation score for ``answer`` in [0, 1]."""
        result = await self.evaluate(answer, citations)
        return result.score

    def to_dict(self, result: JudgeResult) -> dict[str, Any]:
        """Serialize a :class:`JudgeResult` to a plain dict for API responses."""
        return {
            "passed": result.passed,
            "score": result.score,
            "judge": result.judge,
            "reason": result.reason,
            "metadata": result.metadata,
        }


citation_evaluator = CitationEvaluator()
