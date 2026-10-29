"""Public-replay parity after keyword policy and helper-class replacement."""

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


def test_keyword_only_policy_replacement_invalidates_cached_success(monkeypatch):
    _, body, raw = window_data()

    def validate(raw, tokens, *, allowed=True):
        if not allowed:
            raise ValueError("UNITONLY stricter keyword-only replay policy")

    monkeypatch.setattr(validate, "__module__", parser.__name__)
    monkeypatch.setattr(parser, "_validate_tokens", validate)
    memo.validate_serialized_capture(body, raw)
    monkeypatch.setattr(validate, "__kwdefaults__", {"allowed": False})
    with pytest.raises(parser.InvalidCapture):
        parser.validate_capture(body, json.loads(raw))
    with pytest.raises(parser.InvalidCapture):
        memo.validate_serialized_capture(body, raw)


def test_callable_helper_classes_bypass_replay_cache(monkeypatch):
    _, body, raw = window_data()

    class Accept:
        def __new__(cls, *args):
            return None

    class Reject:
        def __new__(cls, *args):
            raise ValueError("UNITONLY stricter callable helper class")

    monkeypatch.setattr(parser, "_validate_tokens", Accept)
    memo.validate_serialized_capture(body, raw)
    monkeypatch.setattr(parser, "_validate_tokens", Reject)
    with pytest.raises(parser.InvalidCapture):
        parser.validate_capture(body, json.loads(raw))
    with pytest.raises(parser.InvalidCapture):
        memo.validate_serialized_capture(body, raw)
    assert memo._cached.cache_info().currsize == 0
