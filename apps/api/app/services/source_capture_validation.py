"""Bounded pure validation memo for immutable serialized source captures.

Only syntax replay is memoized. Source identities, SQL membership, authorization,
applicability, model execution, factual support and publication still have their
own independent checks. Cached values are JSON strings; callers never share a
mutable annotation. Public mutable-dictionary validation remains uncached.
"""

import json
from functools import lru_cache
from types import FunctionType

from app.request_parser_catalog import MAX_QUESTION_CHARS
from app.services import request_parser
from app.services.planning_declarations import canonical

MAX_ENTRIES = 128
MAX_CAPTURE_BYTES = 128 * 1024
MAX_RESULT_BYTES = 256 * 1024


def _validated_json(question, capture_json):
    capture = json.loads(capture_json)
    if canonical(capture) != capture_json:
        raise request_parser.InvalidCapture("Canonical source capture JSON required")
    annotation = request_parser.validate_capture(question, capture)
    return canonical(annotation)


def _known_replay_callables():
    # Only callables used by strict replay matter. Runtime pipeline loaders use
    # their own caches, locks and readiness checks and are never invoked here.
    pending = [request_parser.validate_capture]
    visited = set()
    while pending:
        function = pending.pop()
        if not isinstance(function, FunctionType):
            return False
        if function in visited:
            continue
        visited.add(function)
        for name in function.__code__.co_names:
            dependency = vars(request_parser).get(name)
            if isinstance(dependency, FunctionType):
                pending.append(dependency)
            elif callable(dependency) and not (
                isinstance(dependency, type) and issubclass(dependency, BaseException)
            ):
                # Unknown replay callables may carry mutable hidden state.
                return False
    return True


def _function_policy(value):
    owned = value.__module__ == request_parser.__name__
    try:
        keyword_defaults = canonical(value.__kwdefaults__) if owned else None
    except (TypeError, ValueError, RecursionError):
        return None
    return (
        value,
        value.__code__,
        value.__defaults__ if owned else None,
        keyword_defaults,
    )


def _validation_policy():
    """Invalidate when parser helpers or immutable declared policies change.

    This covers module function/code replacement and immutable policy values,
    including transitive replay helpers. It is not a sandbox against arbitrary
    mutation of imported libraries or hidden state inside a replacement closure.
    """
    if not _known_replay_callables():
        return None
    values = []
    for name, value in sorted(vars(request_parser).items()):
        if name.startswith("__"):
            continue
        if isinstance(value, FunctionType):
            # Imported library defaults may contain private mutable sentinels.
            # Their internals are outside the parser-policy replacement contract.
            policy = _function_policy(value)
            if policy is None:
                return None
            values.append((name, policy))
        elif type(value) in (str, int, float, bool, tuple, frozenset, type(None)):
            values.append((name, value))
    result = tuple(values)
    try:
        hash(result)
    except TypeError:
        return None
    return result


@lru_cache(maxsize=MAX_ENTRIES)
def _cached(question, capture_json, parser_policy, validation_policy):
    # The final arguments are policy-identity keys, never producer callbacks.
    # Actual validation always uses the current module's strict implementation.
    if parser_policy != canonical(request_parser.parser_identity()):
        raise request_parser.InvalidCapture("Source capture parser policy changed")
    value = _validated_json(question, capture_json)
    return value if len(value.encode("utf-8")) <= MAX_RESULT_BYTES else None


def validate_serialized_capture(question, capture_json):
    """Validate exact input bytes or return a fresh copy of that validated graph.

    Both complete input text and complete canonical capture JSON form the key,
    together with current parser/validator identity. No producer hash or success
    flag substitutes for validation. Oversize entries bypass the memo through the
    same strict validator; invalid inputs and errors are never memoized.
    """
    try:
        if type(question) is not str or type(capture_json) is not str:
            raise request_parser.InvalidCapture("Text and serialized capture required")
        if (
            len(question) > MAX_QUESTION_CHARS
            or len(capture_json.encode("utf-8")) > MAX_CAPTURE_BYTES
        ):
            return json.loads(_validated_json(question, capture_json))
        policy = _validation_policy()
        if policy is None:
            return json.loads(_validated_json(question, capture_json))
        value = _cached(
            question,
            capture_json,
            canonical(request_parser.parser_identity()),
            policy,
        )
        if value is None or len(value.encode("utf-8")) > MAX_RESULT_BYTES:
            value = _validated_json(question, capture_json)
        return json.loads(value)
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise request_parser.InvalidCapture(
            "Serialized source capture does not reconstruct"
        ) from exc
