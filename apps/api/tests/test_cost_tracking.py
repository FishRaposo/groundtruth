"""Tests for per-workspace LLM cost tracking through the vendored registry."""

from app.services.cost_tracking import DEFAULT_WORKSPACE, CostTracker


def test_record_returns_call_with_computed_cost() -> None:
    tracker = CostTracker()
    call = tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=120.0,
        workspace="ws1",
    )
    assert call.model == "gpt-4o-mini"
    assert call.prompt_tokens == 100
    assert call.completion_tokens == 50
    # Cost is computed via the vendored pricing registry for a known model.
    assert call.cost_usd > 0


def test_explicit_cost_overrides_pricing() -> None:
    tracker = CostTracker()
    call = tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=10.0,
        cost_usd=1.23,
    )
    assert call.cost_usd == 1.23


def test_summary_aggregates_per_workspace() -> None:
    tracker = CostTracker()
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=120.0,
        workspace="ws1",
    )
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=80.0,
        workspace="ws1",
    )
    summary = tracker.summary("ws1")
    assert summary["total_requests"] == 2
    assert summary["total_tokens"] == 165
    assert summary["input_tokens"] == 110
    assert summary["output_tokens"] == 55


def test_workspaces_are_isolated() -> None:
    tracker = CostTracker()
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=120.0,
        workspace="ws1",
    )
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=200,
        completion_tokens=80,
        latency_ms=200.0,
        workspace="ws2",
    )
    assert tracker.summary("ws1")["total_requests"] == 1
    assert tracker.summary("ws2")["total_requests"] == 1
    assert tracker.workspaces() == ["ws1", "ws2"]


def test_summary_all_rolls_up_total() -> None:
    tracker = CostTracker()
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=120.0,
        workspace="ws1",
    )
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=200,
        completion_tokens=80,
        latency_ms=200.0,
        workspace="ws2",
    )
    rollup = tracker.summary_all()
    assert set(rollup["workspaces"]) == {"ws1", "ws2"}
    assert rollup["total"]["total_requests"] == 2
    assert rollup["total"]["total_tokens"] == 430


def test_default_workspace_when_unspecified() -> None:
    tracker = CostTracker()
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=10.0,
    )
    assert tracker.workspaces() == [DEFAULT_WORKSPACE]


def test_workspace_id_alias_is_additive() -> None:
    tracker = CostTracker()
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=10.0,
        workspace_id="ws-alias",
    )
    assert tracker.summary(workspace_id="ws-alias")["total_requests"] == 1


def test_record_usage_from_token_dict() -> None:
    tracker = CostTracker()
    tracker.record_usage(
        model="gpt-4o-mini",
        token_usage={"prompt_tokens": 40, "completion_tokens": 20, "total_tokens": 60},
        latency_ms=50.0,
        workspace="ws1",
    )
    summary = tracker.summary("ws1")
    assert summary["input_tokens"] == 40
    assert summary["output_tokens"] == 20


def test_record_usage_handles_missing_keys() -> None:
    tracker = CostTracker()
    tracker.record_usage(model="gpt-4o-mini", token_usage={}, workspace="ws1")
    summary = tracker.summary("ws1")
    assert summary["total_tokens"] == 0
    assert summary["total_requests"] == 1


def test_error_is_recorded_in_error_rate() -> None:
    tracker = CostTracker()
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=0,
        latency_ms=10.0,
        workspace="ws1",
        error="timeout",
    )
    assert tracker.summary("ws1")["error_rate"] == 1.0


def test_unknown_workspace_returns_empty_summary() -> None:
    tracker = CostTracker()
    summary = tracker.summary("never-used")
    assert summary["total_requests"] == 0
    assert summary["estimated_cost"] == 0.0


def test_reset_clears_all_workspaces() -> None:
    tracker = CostTracker()
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=10.0,
        workspace="ws1",
    )
    tracker.reset()
    assert tracker.workspaces() == []


def test_cost_by_model_and_prompt_version() -> None:
    tracker = CostTracker()
    tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=10.0,
        workspace="ws1",
        prompt_version="v1",
    )
    summary = tracker.summary("ws1")
    assert "gpt-4o-mini" in summary["cost_by_model"]
    assert "v1" in summary["cost_by_prompt_version"]
