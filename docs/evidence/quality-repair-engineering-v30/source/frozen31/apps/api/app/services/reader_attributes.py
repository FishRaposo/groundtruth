"""Literal attribute relevance among accepted QA witnesses, never entailment."""

import re
from typing import Any

from app.services.reader_support import request_head

_MODIFIERS = frozenset(
    "the a an its their our responsible explicit stated normal standard regular "
    "current actual".split()
)
ATTRIBUTE_CONTRACT = "explicit-selected-clause-attribute-v2"


def selected_attribute_clause(context: str, start: int, end: int) -> str | None:
    """Bounded punctuation/conjunction segments, not a general syntax parser."""
    left = 0
    for boundary in re.finditer(
        r"[.!?;:\n]|,\s*(?:and|but|or|yet|whereas|while|although|because)\b"
        r"|\b(?:but|whereas|although|while|because)\b",
        context,
        re.I,
    ):
        if left <= start < end <= boundary.start():
            return context[left : boundary.start()]
        left = boundary.end()
    return context[left:] if left <= start < end <= len(context) else None


def attribute_features(question: str, context: str, raw: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "contract": ATTRIBUTE_CONTRACT,
        "requested": False,
        "selected_clause_matches": False,
        "semantics": "literal ranking prior only; not support or entailment",
    }
    match = re.fullmatch(
        r"\s*(?:what|which)\s+(?:is|are)\s+(?P<modifier>[\w\s-]+?)\s+"
        r"(?P<kind>role|restriction|prohibition|workload)"
        r"(?:\s+(?P<relation>for|of)\s+[^?.,;]+)?"
        r"(?:,?\s+including\s+[^?]+)?[?.]*\s*",
        request_head(question),
        re.I,
    )
    if match is None:
        return result
    words = set(re.findall(r"\w[\w-]*", match.group("modifier").casefold()))
    if {"no", "not", "never", "without"} & words:
        return result
    if match.group("kind").casefold() == "role" and (
        "responsible" not in words or (match.group("relation") or "").casefold() == "of"
    ):
        return result
    terms = words - _MODIFIERS
    if not terms:
        return result
    result.update(
        requested=True, kind=match.group("kind").casefold(), terms=sorted(terms)
    )
    if not isinstance(raw, dict):
        return result
    start, end = raw.get("start"), raw.get("end")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or not 0 <= start < end <= len(context)
    ):
        return result
    clause = selected_attribute_clause(context, start, end)
    if clause is None:
        return result
    present = set(re.findall(r"\w[\w-]*", clause.casefold()))
    result["selected_clause_matches"] = terms.issubset(present)
    return result
