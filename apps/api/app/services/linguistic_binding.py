"""Bounded literal availability inventory for the versioned linguistic reader.

Only complete temporal-list predicates for the requested actor are consumed.
Every assertion in the supplied context must match; unknown grammar refuses.
The synchronous binder cannot inventory omitted chunks of a larger source.
"""

import re
from dataclasses import dataclass

from app.services.answer_requirements import _clean
from app.services.contextual_binding import contextual_support_claim
from app.services.requirement_binding import (
    SupportCheck,
    SupportClaim,
    _canonical_argument,
)

_MAX_CONTEXT_CHARS = 8192
_MAX_ASSERTIONS = 8
_CLOCK = r"(?:[01]?\d|2[0-3]):[0-5]\d"
_DAY = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?"
_TEMPORAL = (
    rf"(?:from\s+{_CLOCK}\s+to\s+{_CLOCK}|(?:on\s+)?{_DAY}|"
    r"for\s+\d+(?:\.\d+)?\s+(?:seconds?|minutes?|hours?))"
)
_WINDOWS = rf"{_TEMPORAL}(?:\s+and\s+{_TEMPORAL})*"


class _InventoryRejected(ValueError):
    """The complete supplied availability context cannot be consumed."""


@dataclass(frozen=True)
class _Assertion:
    start: int
    end: int
    value_start: int
    value_end: int
    argument_end: int
    hypothesis: str


def _literal_pattern(text):
    return r"\s+".join(re.escape(word) for word in text.split())


def _request(requirement):
    question = _clean(requirement.question)
    matched = re.fullmatch(
        r"(?:what\s+is|give|state)\s+(.+?)['’]s\s+availability(?P<tail>.*)",
        question,
        re.I,
    ) or re.fullmatch(
        r"(?:when|during\s+which\s+hours)\s+is\s+(.+?)\s+available(?P<tail>.*)",
        question,
        re.I,
    )
    if matched is None:
        raise _InventoryRejected("availability_request_unconsumed")
    subject, tail = matched.group(1), matched["tail"].strip(" ,")
    if tail and not re.fullmatch(
        r"(?:if|unless|when|during|before|after|for)\s+\S(?:.*\S)?", tail, re.I
    ):
        raise _InventoryRejected("availability_request_tail_unconsumed")
    namespace = getattr(requirement, "dependency_scope", "")
    scope = re.fullmatch(r"(?:for|during)\s+(.+)", tail, re.I)
    if scope and (
        not namespace
        or _canonical_argument(scope.group(1)) != _canonical_argument(namespace)
    ):
        raise _InventoryRejected("availability_requested_namespace_unresolved")
    return subject, tail, namespace


def _sentences(context):
    cursor = 0
    ranges = []
    for boundary in re.finditer(r"[.!?](?=\s|$)", context):
        ranges.append((cursor, boundary.end()))
        cursor = boundary.end()
    if context[cursor:].strip():
        ranges.append((cursor, len(context)))
    if not ranges or len(ranges) > _MAX_ASSERTIONS:
        raise _InventoryRejected("availability_inventory_budget_or_empty")
    return ranges


def _assertion(context, bounds, subject, tail, namespace):
    left, right = bounds
    while left < right and context[left].isspace():
        left += 1
    while right > left and context[right - 1].isspace():
        right -= 1
    sentence = context[left:right]
    source = re.fullmatch(
        r"(?P<actor>.+?)\s+(?:is|are)\s+(?:also\s+)?available\s+"
        r"(?P<value>.+?)[.!?]?",
        sentence,
        re.I,
    )
    if source is None or _canonical_argument(source["actor"]) != _canonical_argument(
        subject
    ):
        raise _InventoryRejected(
            "availability_inventory_subject_or_predicate_unresolved"
        )
    value = source["value"]
    temporal = value
    if tail:
        condition = re.search(r"\s+" + _literal_pattern(tail) + r"$", temporal, re.I)
        if condition is None:
            raise _InventoryRejected("availability_requested_tail_not_literal")
        temporal = temporal[: condition.start()]
    scope = (
        rf"(?:\s+(?:for|during|in)\s+{_literal_pattern(namespace)})?"
        if namespace
        else ""
    )
    consumed = re.fullmatch(rf"(?P<windows>{_WINDOWS}){scope}", temporal, re.I)
    if consumed is None:
        raise _InventoryRejected("availability_value_or_scope_unconsumed")
    value_start = left + source.start("value")
    return _Assertion(
        left,
        right,
        value_start,
        left + source.end("value"),
        value_start + consumed.end("windows"),
        f"{subject} is available {value}",
    )


def support_linguistic_claim(requirement, context, start, end):
    if requirement.kind != "availability":
        return contextual_support_claim(requirement, context, start, end)
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(context)
    ):
        return SupportClaim(None, "", "", start, end, "invalid_candidate_offsets")
    try:
        if len(context) > _MAX_CONTEXT_CHARS:
            raise _InventoryRejected("availability_context_budget_exceeded")
        subject, tail, namespace = _request(requirement)
        assertions = [
            _assertion(context, bounds, subject, tail, namespace)
            for bounds in _sentences(context)
        ]
        if not any(a.value_start <= start < end <= a.argument_end for a in assertions):
            raise _InventoryRejected("availability_raw_span_not_requested_actor_value")
    except _InventoryRejected as exc:
        return SupportClaim(None, "", "", start, end, str(exc))
    first, last = assertions[0], assertions[-1]
    left, right = first.start, last.end
    # A multi-assertion answer is one contiguous literal copy, including actors
    # and separators. Each property assertion is independently assessed by NLI;
    # exact copy itself never grants a model-support decision.
    multi = len(assertions) > 1
    value_start = left if multi else first.value_start
    value_end = right if multi else first.value_end
    checks = (
        tuple(
            SupportCheck(
                f"availability_assertion_{n}",
                context[a.start : a.end],
                a.hypothesis,
                a.start,
                a.end,
            )
            for n, a in enumerate(assertions, 1)
        )
        if multi
        else ()
    )
    return SupportClaim(
        " and ".join(a.hypothesis for a in assertions),
        context[left:right],
        context[value_start:value_end],
        value_start,
        value_end,
        None,
        support_start=left,
        support_end=right,
        checks=checks,
        premise_start=left,
        premise_end=right,
    )
