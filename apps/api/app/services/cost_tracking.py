"""Per-workspace LLM cost and latency tracking.

Thin wrapper over the internal vendor ``LLMMetrics`` that keeps a separate telemetry
accumulator per workspace so the platform can attribute token spend,
latency percentiles, and error rate to the workspace that incurred them.

Offline-first: the internal vendor metrics module is pure-Python and defaults cost to
the internal vendor pricing registry when an explicit ``cost_usd`` is not
provided, so this works without any network access.
"""

from __future__ import annotations

from typing import Any

from app.internal.vendor_core.llmmetrics import LLMCall, LLMMetrics

DEFAULT_WORKSPACE = "default"


class CostTracker:
    """Accumulates per-workspace LLM telemetry and exposes aggregates.

    Each workspace gets its own :class:`~app.internal.vendor_core.llmmetrics.LLMMetrics`
    instance. Recording a call routes to the workspace's accumulator; summaries
    can be requested per workspace or rolled up across all of them.
    """

    def __init__(self) -> None:
        self._by_workspace: dict[str, LLMMetrics] = {}

    def _metrics_for(self, workspace: str) -> LLMMetrics:
        if workspace not in self._by_workspace:
            self._by_workspace[workspace] = LLMMetrics()
        return self._by_workspace[workspace]

    def record(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: float,
        workspace: str | None = None,
        workspace_id: str | None = None,
        prompt_version: str | None = None,
        error: str | None = None,
        cost_usd: float | None = None,
    ) -> LLMCall:
        """Record one LLM call against a workspace.

        Args:
            model: Model identifier (used for pricing lookup).
            prompt_tokens: Prompt/input token count.
            completion_tokens: Completion/output token count.
            latency_ms: Wall-clock latency for the call in milliseconds.
            workspace: Workspace key; falls back to ``DEFAULT_WORKSPACE``.
            prompt_version: Optional prompt version label for attribution.
            error: Optional error marker; non-empty counts toward error rate.
            cost_usd: Optional explicit cost; computed from pricing if omitted.

        Returns:
            The recorded :class:`~app.internal.vendor_core.llmmetrics.LLMCall`.
        """
        ws = workspace_id or workspace or DEFAULT_WORKSPACE
        return self._metrics_for(ws).record(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            prompt_version=prompt_version,
            error=error,
            cost_usd=cost_usd,
        )

    def record_usage(
        self,
        *,
        model: str,
        token_usage: dict[str, int],
        latency_ms: float = 0.0,
        workspace: str | None = None,
        workspace_id: str | None = None,
        prompt_version: str | None = None,
        error: str | None = None,
    ) -> LLMCall:
        """Record a call from a token-usage dict (as returned by generation).

        Accepts the ``{"prompt_tokens", "completion_tokens", "total_tokens"}``
        shape produced by :class:`app.services.generation.GenerationService`.
        """
        return self.record(
            model=model,
            prompt_tokens=int(token_usage.get("prompt_tokens", 0)),
            completion_tokens=int(token_usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
            workspace=workspace,
            workspace_id=workspace_id,
            prompt_version=prompt_version,
            error=error,
        )

    def summary(
        self, workspace: str | None = None, workspace_id: str | None = None
    ) -> dict[str, Any]:
        """Return the cost/latency/error summary for one workspace.

        An unknown workspace yields an empty (all-zero) summary rather than
        raising, so callers can query freely.
        """
        ws = workspace_id or workspace or DEFAULT_WORKSPACE
        return self._metrics_for(ws).summary()

    def summary_all(self) -> dict[str, Any]:
        """Return per-workspace summaries plus a rolled-up total.

        Returns:
            A dict with ``workspaces`` (per-workspace summaries) and ``total``
            (aggregate over every recorded call across all workspaces).
        """
        rollup = LLMMetrics()
        for metrics in self._by_workspace.values():
            for call in metrics.calls:
                rollup.record(
                    model=call.model,
                    prompt_tokens=call.prompt_tokens,
                    completion_tokens=call.completion_tokens,
                    latency_ms=call.latency_ms,
                    prompt_version=call.prompt_version,
                    error=call.error,
                    cost_usd=call.cost_usd,
                )
        return {
            "workspaces": {
                ws: metrics.summary() for ws, metrics in self._by_workspace.items()
            },
            "total": rollup.summary(),
        }

    def workspaces(self) -> list[str]:
        """Return the sorted list of workspaces that have recorded calls."""
        return sorted(self._by_workspace)

    def reset(self) -> None:
        """Drop all accumulated telemetry (primarily for tests)."""
        self._by_workspace.clear()


cost_tracker = CostTracker()
