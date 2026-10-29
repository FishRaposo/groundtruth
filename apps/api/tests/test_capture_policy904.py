"""Pure replay-policy invalidation regressions; no model or authority claims."""

import json

import pytest
from app.services import request_parser as parser
from app.services import source_capture_validation as memo

from tests.test_capture_validation892 import window_data


@pytest.fixture(autouse=True)
def clear_cache():
    memo._cached.cache_clear()
    yield
    memo._cached.cache_clear()


@pytest.mark.parametrize(
    "helper",
    ["_validate_tokens", "_validate_sentences", "_question", "_native", "_same"],
)
def test_stricter_replay_helper_invalidates_warm_success(monkeypatch, helper):
    _, body, raw = window_data()
    memo.validate_serialized_capture(body, raw)

    def reject(*args, **kwargs):
        raise ValueError("UNITONLY stricter replay policy")

    monkeypatch.setattr(parser, helper, reject)
    with pytest.raises(parser.InvalidCapture):
        parser.validate_capture(body, json.loads(raw))
    with pytest.raises(parser.InvalidCapture):
        memo.validate_serialized_capture(body, raw)


@pytest.mark.parametrize("policy", ["_POS", "_TAGS", "_DEPS"])
def test_stricter_label_inventory_invalidates_warm_success(monkeypatch, policy):
    _, body, raw = window_data()
    memo.validate_serialized_capture(body, raw)
    monkeypatch.setattr(parser, policy, frozenset())
    with pytest.raises(parser.InvalidCapture):
        parser.validate_capture(body, json.loads(raw))
    with pytest.raises(parser.InvalidCapture):
        memo.validate_serialized_capture(body, raw)


def test_helper_default_policy_invalidates_warm_success(monkeypatch):
    _, body, raw = window_data()
    memo.validate_serialized_capture(body, raw)
    monkeypatch.setattr(parser._question, "__defaults__", (0,))
    with pytest.raises(parser.InvalidCapture):
        parser.validate_capture(body, json.loads(raw))
    with pytest.raises(parser.InvalidCapture):
        memo.validate_serialized_capture(body, raw)


def test_replaced_helper_code_invalidates_warm_success(monkeypatch):
    _, body, raw = window_data()
    memo.validate_serialized_capture(body, raw)

    def reject(*args, **kwargs):
        raise ValueError("UNITONLY replacement helper code")

    # Same function identity, different actual replay implementation.
    monkeypatch.setattr(parser._same, "__code__", reject.__code__)
    with pytest.raises(parser.InvalidCapture):
        parser.validate_capture(body, json.loads(raw))
    with pytest.raises(parser.InvalidCapture):
        memo.validate_serialized_capture(body, raw)
