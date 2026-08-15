# Vendored from FishRaposo/operator-shared-core v1.3.0.
# Source commit: dbf276a7708da65b55e1f10b35af634b300d1f07.
"""LLM-specific telemetry: token/cost/latency aggregation with percentiles.

Records per-call telemetry and computes aggregates (totals, per-model, per-prompt-
version, latency p50/p95/p99, error rate). Pure-Python and offline-friendly; cost
defaults to the internal pricing registry. Used by the cost/latency monitor,
agent framework, and issue/PR agent.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Callable, Optional

from app.internal.vendor_core.pricing import calculate_cost


@dataclass
class LLMCall:
    """A single recorded LLM invocation."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    cost_usd: float
    prompt_version: Optional[str] = None
    error: Optional[str] = None


def _percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    low = int(k)
    high = min(low + 1, len(sorted_vals) - 1)
    if low == high:
        return round(sorted_vals[low], 2)
    interpolated = sorted_vals[low] + (sorted_vals[high] - sorted_vals[low]) * (k - low)
    return round(interpolated, 2)


def _group_sum(
    calls: list[LLMCall],
    key_fn: Callable[[LLMCall], str],
    val_fn: Callable[[LLMCall], float],
) -> dict[str, float]:
    out: dict[str, float] = {}
    for call in calls:
        key = key_fn(call)
        out[key] = round(out.get(key, 0.0) + val_fn(call), 6)
    return out


class LLMMetrics:
    """Accumulates LLM-call telemetry and computes summary aggregates."""

    def __init__(self) -> None:
        self._calls: list[LLMCall] = []

    def record(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        prompt_version: Optional[str] = None,
        error: Optional[str] = None,
        cost_usd: Optional[float] = None,
    ) -> LLMCall:
        """Record one call; use the internal pricing registry when cost is omitted."""
        cost = (
            cost_usd
            if cost_usd is not None
            else calculate_cost(model, prompt_tokens, completion_tokens)
        )
        call = LLMCall(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_usd=cost,
            prompt_version=prompt_version,
            error=error,
        )
        self._calls.append(call)
        return call

    @property
    def calls(self) -> list[LLMCall]:
        return list(self._calls)

    def summary(self) -> dict[str, Any]:
        """Return the standard cost/latency/error metrics over all recorded calls."""
        calls = self._calls
        n = len(calls)
        latencies = sorted(c.latency_ms for c in calls)
        errors = sum(1 for c in calls if c.error)
        return {
            "total_requests": n,
            "total_tokens": sum(c.prompt_tokens + c.completion_tokens for c in calls),
            "input_tokens": sum(c.prompt_tokens for c in calls),
            "output_tokens": sum(c.completion_tokens for c in calls),
            "estimated_cost": round(sum(c.cost_usd for c in calls), 6),
            "average_latency_ms": (
                round(statistics.mean(latencies), 2) if latencies else 0.0
            ),
            "p50_latency_ms": _percentile(latencies, 50),
            "p95_latency_ms": _percentile(latencies, 95),
            "p99_latency_ms": _percentile(latencies, 99),
            "error_rate": round(errors / n, 4) if n else 0.0,
            "cost_by_model": _group_sum(calls, lambda c: c.model, lambda c: c.cost_usd),
            "cost_by_prompt_version": _group_sum(
                calls,
                lambda c: c.prompt_version or "unversioned",
                lambda c: c.cost_usd,
            ),
        }
