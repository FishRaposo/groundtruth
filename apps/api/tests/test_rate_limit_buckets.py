"""Deterministic workspace/API-key rate-limit bucket contracts."""

from app.middleware.rate_limit import RateLimitBuckets


def test_rate_limit_buckets_isolate_workspaces_and_api_keys() -> None:
    buckets = RateLimitBuckets(window_seconds=60)
    assert buckets.check("ws-a", "key-a", limit=1, now=0).allowed is True
    denied = buckets.check("ws-a", "key-a", limit=1, now=1)
    assert denied.allowed is False
    assert denied.retry_after == 59
    assert buckets.check("ws-b", "key-a", limit=1, now=1).allowed is True
    assert buckets.check("ws-a", "key-b", limit=1, now=1).allowed is True


def test_rate_limit_bucket_resets_at_fixed_window_boundary() -> None:
    buckets = RateLimitBuckets(window_seconds=60)
    buckets.check("ws", "key", limit=1, now=59.9)
    decision = buckets.check("ws", "key", limit=1, now=60.0)
    assert decision.allowed is True
    assert decision.remaining == 0
    assert decision.reset_after == 60
