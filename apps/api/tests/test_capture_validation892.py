"""Pure UNITONLY capture replay; no model, API or authorization claims."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace

import pytest
from app.services import planning_declarations as source
from app.services import request_parser
from app.services import source_capture_validation as memo

from tests.staged_plan_unit837.test_binding import args


@pytest.fixture(autouse=True)
def clear_memo():
    memo._cached.cache_clear()
    yield
    memo._cached.cache_clear()


def window_data():
    actual = args()
    window = actual["source_captures"][0].windows[0]
    body = actual["snapshots"][0].body[window.start : window.end]
    memo._cached.cache_clear()
    return actual, body, window.capture_json


def test_repeated_immutable_source_windows_validate_once(monkeypatch):
    actual = args()
    calls = []
    original = request_parser._validate_annotation

    def observed(*arguments, **keywords):
        calls.append(arguments[0])
        return original(*arguments, **keywords)

    monkeypatch.setattr(request_parser, "_validate_annotation", observed)
    first = source._inputs(
        actual["manifest"], actual["snapshots"], actual["source_captures"]
    )
    second = source._inputs(
        actual["manifest"], actual["snapshots"], actual["source_captures"]
    )
    windows = sum(len(row.windows) for row in actual["source_captures"])
    assert len(calls) == windows
    assert first == second
    key = next(iter(first[1]))
    first[1][key][0][2]["tokens"][0]["text"] = "UNITONLY mutation"
    assert first[1][key][0][2] != second[1][key][0][2]
    assert first[1][key][0][1]["annotation"] != first[1][key][0][2]


def test_public_mutable_capture_validation_still_runs_each_time(monkeypatch):
    actual = args()
    window = actual["source_captures"][0].windows[0]
    body = actual["snapshots"][0].body[window.start : window.end]
    capture = json.loads(window.capture_json)
    calls = []
    original = request_parser._validate_annotation

    def observed(*arguments, **keywords):
        calls.append(arguments[0])
        return original(*arguments, **keywords)

    monkeypatch.setattr(request_parser, "_validate_annotation", observed)
    request_parser.validate_capture(body, capture)
    request_parser.validate_capture(body, capture)
    assert len(calls) == 2


def test_cached_outputs_are_detached_and_exact():
    _, body, capture_json = window_data()
    expected = request_parser.validate_capture(body, json.loads(capture_json))
    first = memo.validate_serialized_capture(body, capture_json)
    second = memo.validate_serialized_capture(body, capture_json)
    assert first == second == expected
    first["tokens"][0]["text"] = "UNITONLY mutation"
    assert second == expected
    assert memo.validate_serialized_capture(body, capture_json) == expected
    assert memo._cached.cache_info().hits >= 2


def test_cached_capture_cannot_validate_different_original_text():
    _, body, capture_json = window_data()
    memo.validate_serialized_capture(body, capture_json)
    with pytest.raises(request_parser.InvalidCapture):
        memo.validate_serialized_capture(body + " changed", capture_json)


def test_coherently_rehashed_invalid_graph_is_not_cache_hit():
    _, body, capture_json = window_data()
    memo.validate_serialized_capture(body, capture_json)
    changed = json.loads(capture_json)
    changed["annotation"]["tokens"][0]["head"] = 99999
    changed["annotation_sha256"] = request_parser._digest(changed["annotation"])
    changed["capture_sha256"] = request_parser._digest(
        {key: value for key, value in changed.items() if key != "capture_sha256"}
    )
    with pytest.raises(request_parser.InvalidCapture):
        memo.validate_serialized_capture(body, source.canonical(changed))
    assert memo._cached.cache_info().currsize == 1


def test_parser_identity_change_invalidates_cache(monkeypatch):
    _, body, capture_json = window_data()
    memo.validate_serialized_capture(body, capture_json)
    different = deepcopy(request_parser.parser_identity())
    different["UNITONLY-policy-change"] = True
    monkeypatch.setattr(request_parser, "parser_identity", lambda: different)
    with pytest.raises(request_parser.InvalidCapture):
        memo.validate_serialized_capture(body, capture_json)


def test_validator_policy_change_does_not_reuse_success(monkeypatch):
    _, body, capture_json = window_data()
    memo.validate_serialized_capture(body, capture_json)

    def reject(*arguments, **keywords):
        raise ValueError("UNITONLY stricter validation policy")

    monkeypatch.setattr(request_parser, "_validate_annotation", reject)
    with pytest.raises(request_parser.InvalidCapture):
        memo.validate_serialized_capture(body, capture_json)


def test_source_membership_is_rechecked_after_cache_hit():
    actual, _, _ = window_data()
    source._inputs(actual["manifest"], actual["snapshots"], actual["source_captures"])
    empty = replace(actual["manifest"], publications=())
    with pytest.raises(ValueError):
        source._inputs(empty, actual["snapshots"], actual["source_captures"])


def test_source_identity_types_are_rechecked_after_cache_hit():
    actual, _, _ = window_data()
    source._inputs(actual["manifest"], actual["snapshots"], actual["source_captures"])
    first = actual["snapshots"][0]
    changed = replace(first, identity=replace(first.identity, document_version=True))
    with pytest.raises(ValueError):
        source._inputs(
            actual["manifest"],
            (changed, *actual["snapshots"][1:]),
            actual["source_captures"],
        )


def test_oversize_input_bypasses_memo_through_same_validator(monkeypatch):
    _, body, capture_json = window_data()
    original = request_parser._validate_annotation
    calls = []

    def observed(*arguments, **keywords):
        calls.append(arguments[0])
        return original(*arguments, **keywords)

    monkeypatch.setattr(request_parser, "_validate_annotation", observed)
    monkeypatch.setattr(memo, "MAX_CAPTURE_BYTES", 1)
    first = memo.validate_serialized_capture(body, capture_json)
    assert memo.validate_serialized_capture(body, capture_json) == first
    assert len(calls) == 2
    assert memo._cached.cache_info().currsize == 0


def test_oversize_result_is_revalidated_not_an_acceptance_flag(monkeypatch):
    _, body, capture_json = window_data()
    monkeypatch.setattr(memo, "MAX_RESULT_BYTES", 1)
    expected = request_parser.validate_capture(body, json.loads(capture_json))
    assert memo.validate_serialized_capture(body, capture_json) == expected
    assert memo.validate_serialized_capture(body, capture_json) == expected


def test_memo_entry_count_is_bounded(monkeypatch):
    _, body, capture_json = window_data()
    original = request_parser._validate_annotation
    for _ in range(memo.MAX_ENTRIES + 3):

        def observed(*arguments, **keywords):
            return original(*arguments, **keywords)

        monkeypatch.setattr(request_parser, "_validate_annotation", observed)
        memo.validate_serialized_capture(body, capture_json)
    assert memo._cached.cache_info().currsize == memo.MAX_ENTRIES


def test_parallel_callers_receive_independent_graphs():
    _, body, capture_json = window_data()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: memo.validate_serialized_capture(body, capture_json), range(8)
            )
        )
    expected = deepcopy(results[0])
    results[0]["tokens"][0]["text"] = "UNITONLY thread mutation"
    assert all(value == expected for value in results[1:])
