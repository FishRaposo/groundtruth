"""Finite, lossless source scope for candidate selection, never factual support.

Only the opt-in contextual reading contract consumes this cover. Every source
character remains in an ordered unit. Unknown text and references are mandatory
candidates, including when an otherwise local note precedes them. Before trusting
a serialized index, callers must validate it against the authoritative immutable
body and identity; internal reconstruction alone cannot establish publication or
authorization. QA, NLI, roles, instructions and conditions remain separate checks.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.evidence_policy import reading_version

_IDENTITY_KEYS = frozenset(
    {"document_id", "document_version", "content_hash", "workspace_id", "snapshot_id"}
)
_WORD = r"[^\W_]+(?:[-'’—][^\W_]+)*"
_REFERENCE = re.compile(
    r"\b(?:appendi(?:x|ces)|annex(?:es)?|attachments?|handbooks?|schedules?|"
    r"nominations?|appointments?|rosters?)\b",
    re.I,
)
_CONDITION = re.compile(
    r"\b(?:if|unless|except|provided|whether|subject\s+to|pending)\b", re.I
)
_GLOBAL = re.compile(
    r"\b(?:all|each|every|any)\s+(?:ordinary\s+)?"
    r"(?:sessions?|activities|operations?|documents?)\b|"
    r"\bregardless\s+of\s+(?:the\s+)?(?:activity|session)\b",
    re.I,
)
_GLOBAL_MODIFIER = re.compile(
    r"\b(?:global(?:ly)?|(?:system|company|enterprise|organisation|organization|"
    r"corporation|universe)[ -]?wide|universally)\b",
    re.I,
)
# Closed physical types, not a blacklist of known reference nouns. A manual,
# statute or an unfamiliar operand cannot inherit physical status merely from
# an article/nominal shape. Informational commands need a reference resolver.
_PHYSICAL_HEADS = frozenset(
    "board box card chain container counter cube disc disk envelope frame grid "
    "map mat panel record ribbon ring sheet strip table tile trail tray wheel".split()
)
_LOCAL_HEADS = _PHYSICAL_HEADS | frozenset(
    "activity operation procedure review routine session sessions".split()
)
_PHYSICAL_MODIFIERS = frozenset(
    "blank closed discrepancy folded labeled labelled marked numbered open "
    "printed retained session signed".split()
)
_COUNT_UNITS = _PHYSICAL_HEADS | frozenset({"participant"})
_TIME_UNITS = frozenset({"second", "minute", "hour"})
_INSTRUCTION = re.compile(
    r"(?:(?:do\s+not|never)\s+)?(?:attach|arrange|close|count|inspect|label|leave|"
    r"lock|mark|move|obtain|open|place|print|put|record|remove|retain|return|save|"
    r"scan|set|take|turn|unlock|wait|write|discard)\s+"
    r"(?P<argument>[^.!?;,:\n]+)",
    re.I,
)
_SUBJECT_BLOCKERS = frozenset(
    "the a an all any each every its their his her our your this that these those "
    "it they and or but if unless except provided whether who which "
    "is are was were be been has have must may can should will "
    "requires require leads led deputy lead".split()
)
_ACTOR_BLOCKERS = _SUBJECT_BLOCKERS | frozenset(
    "before after during until only not never replaces replace".split()
)
_INSTRUCTION_BLOCKERS = (
    _SUBJECT_BLOCKERS - {"the", "a", "an", "this", "that", "it", "them"}
) | frozenset(
    "then because since governs govern appoint nominates nominate replaces "
    "replace declares states says".split()
)
_METADATA = re.compile(
    r"this\s+is\s+an?\s+(?:invented|synthetic)\s+"
    r"(?:[\w-]+\s+){0,3}(?:fixture|example),\s+not\s+real\s+"
    r"(?:professional\s+)?guidance|"
    r"this\s+is\s+an?\s+(?:(?:separate|tentative|draft|proposed)\s+){1,3}"
    r"(?:planning\s+item|plan|example),\s+not\s+an?\s+"
    r"(?:(?:ordinary-session|current|approved)\s+)?(?:limit|rule|policy|fact)",
    re.I,
)


def _identity(body: str, identity: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(body, str) or not isinstance(identity, Mapping):
        raise ValueError("A raw body and document identity are required")
    if set(identity) - _IDENTITY_KEYS:
        raise ValueError("Unsupported source identity fields")
    document_id = identity.get("document_id")
    version = identity.get("document_version")
    if (
        not isinstance(document_id, str)
        or not document_id.strip()
        or document_id != document_id.strip()
        or type(version) is not int
        or version < 1
    ):
        raise ValueError("A document ID and positive integer version are required")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if "content_hash" in identity and identity["content_hash"] != digest:
        raise ValueError("Source identity does not match the raw body")
    result = dict(identity)
    for key in ("workspace_id", "snapshot_id"):
        if key in result and (
            not isinstance(result[key], str) or not result[key].strip()
        ):
            raise ValueError("Invalid source identity field")
    result["content_hash"] = digest
    return result


def _nominal(text: str, blockers: frozenset[str]) -> bool:
    words = re.sub(r"^(?:the|a|an)\s+", "", text.strip(), flags=re.I).split()
    return (
        1 <= len(words) <= 12
        and all(re.fullmatch(_WORD, word) for word in words)
        and not any(word.casefold() in blockers for word in words)
        and any(char.isalpha() for char in text)
    )


def _evidence(body: str, start: int, end: int) -> dict[str, Any]:
    return {"start": start, "end": end, "text": body[start:end]}


def _scope_from_match(body, offset, match, group="subject"):
    first, last = match.span(group)
    subject = match[group].strip()
    first += len(match[group]) - len(match[group].lstrip())
    last = first + len(subject)
    article = re.match(r"(?:the|a|an)\s+", subject, re.I)
    if article:
        first += article.end()
        subject = subject[article.end() :]
    return subject, _evidence(body, offset + first, offset + last)


def _heading(text: str):
    return (
        re.fullmatch(r"#{1,6}\s+(?P<subject>[^#]+)", text)
        or re.fullmatch(
            r"(?P<subject>[^:]+):\s*(?:current\s+)?"
            r"(?:operation|activity|coordination|procedure|session)\s+"
            r"(?:note|guide|instructions|routine)",
            text,
            re.I,
        )
        or re.fullmatch(
            r"(?:this\s+(?:note|document|guide|procedure|routine)\s+"
            r"(?:applies\s+to|is\s+for|concerns)|"
            r"the\s+following\s+(?:routine|instructions|procedure|rules)\s+"
            r"(?:applies|apply)\s+to)\s+(?P<subject>.+)",
            text,
            re.I,
        )
    )


def _role(text: str):
    actor = rf"(?P<actor>{_WORD}(?:\s+{_WORD})*)"
    subject = r"(?P<subject>.+?)"
    patterns = (
        rf"{actor}\s+(?P<relation>leads|is\s+(?:the\s+)?deputy\s+for)\s+{subject}",
        rf"{subject}\s+(?P<relation>is\s+led\s+by)\s+{actor}",
        rf"{subject}\s+(?P<relation>(?:activity\s+)?(?:lead|deputy)\s+is)\s+{actor}",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, re.I)
        if match and _nominal(match["actor"], _ACTOR_BLOCKERS):
            return match
    return None


def _local_predicate(text: str) -> str | None:
    if _role(text):
        return "role"
    if _contextual_role(text):
        return "role"
    if _instruction(text):
        return "instruction"
    return None


def _instruction(text: str) -> bool:
    clauses = re.split(r"\s+and\s+", text, flags=re.I)
    nominal = (
        r"(?:(?:the|a|an|this|that|one|two|three)\s+"
        r"(?:[a-z]+\s+){0,2}"
        r"[a-z]+)"
    )
    for clause in clauses:
        match = _INSTRUCTION.fullmatch(clause)
        if not match:
            return False
        argument = re.sub(
            r"\s+(?:immediately|open|closed|intact|unchanged)$",
            "",
            match["argument"],
            flags=re.I,
        )
        parts = re.split(
            r"\s+(?:in|on|at|with|to|inside|against|beside)\s+", argument, flags=re.I
        )
        if not all(re.fullmatch(nominal, part, re.I) for part in parts):
            return False
        if not all(_physical_head(part.split()[-1]) for part in parts):
            return False
        if not all(
            all(word.casefold() in _PHYSICAL_MODIFIERS for word in part.split()[1:-1])
            for part in parts
        ):
            return False
        if any(word.casefold() in _INSTRUCTION_BLOCKERS for word in argument.split()):
            return False
    return bool(clauses)


def _physical_head(word: str) -> bool:
    return word.casefold().removesuffix("s") in _PHYSICAL_HEADS


def _named_local_subject(subject: str) -> bool:
    words = re.sub(r"^(?:the|a|an)\s+", "", subject, flags=re.I).split()
    while words and words[-1].casefold() in {
        "current",
        "draft",
        "next-season",
        "proposed",
        "tentative",
    }:
        words.pop()
    return (
        len(words) >= 2
        and any(word[0].isupper() for word in words[:-1])
        and words[-1].casefold().removesuffix("s") in _LOCAL_HEADS
        and _nominal(subject, _SUBJECT_BLOCKERS)
    )


def _contextual_role(text: str):
    actor = rf"(?P<actor>{_WORD}(?:\s+{_WORD})*)"
    patterns = (
        rf"(?:its|the)\s+(?P<relation>(?:lead|deputy)\s+is)\s+{actor}",
        rf"{actor}\s+(?P<relation>leads)",
        rf"{actor}\s+(?P<relation>replaces)\s+(?P<previous>{_WORD}(?:\s+{_WORD})*)\s+as\s+(?P<role>lead|deputy)",
    )
    for pattern in patterns:
        match = re.fullmatch(pattern, text, re.I)
        if (
            match
            and _nominal(match["actor"], _ACTOR_BLOCKERS)
            and (
                "previous" not in match.groupdict()
                or _nominal(match["previous"], _ACTOR_BLOCKERS)
            )
        ):
            return match
    return None


def _role_declaration(body, offset, match, target):
    actor_start, actor_end = match.span("actor")
    rel_start, rel_end = match.span("relation")
    kind = "deputy" if re.search(r"\bdeputy\b", match.group(), re.I) else "owner"
    return {
        "kind": kind,
        "actor": _evidence(body, offset + actor_start, offset + actor_end),
        "target": deepcopy(target),
        "relation": _evidence(body, offset + rel_start, offset + rel_end),
    }


def _scalar_fact(text: str):
    # A numerical copula is not a local scope declaration. Require a named,
    # typed local entity/property and matching physical/count or temporal units.
    # Unknown governing thresholds/requirements do not enter this grammar.
    match = re.fullmatch(
        r"(?P<subject>.+?)\s+(?P<property>capacity(?:\s+cap)?|count|duration|interval)"
        r"\s+(?:is|are)\s+[0-9]+(?:\.[0-9]+)?\s+(?P<unit>[a-z]+)",
        text,
        re.I,
    )
    if match:
        allowed = (
            _TIME_UNITS
            if match["property"].casefold() in {"duration", "interval"}
            else _COUNT_UNITS
        )
        return (
            match
            if (
                _named_local_subject(match["subject"])
                and match["unit"].casefold().removesuffix("s") in allowed
            )
            else None
        )
    match = re.fullmatch(
        r"(?P<subject>.+?)\s+(?:contains?|has|holds?|accepts?)\s+"
        r"[0-9]+(?:\.[0-9]+)?\s+(?P<unit>[a-z]+)",
        text,
        re.I,
    )
    return (
        match
        if (
            match
            and _named_local_subject(match["subject"])
            and _physical_head(match["subject"].split()[-1])
            and match["unit"].casefold().removesuffix("s") in _COUNT_UNITS
        )
        else None
    )


def _classify(body, start, end, active, declared):  # noqa: C901 - finite source frames
    raw = body[start:end]
    text = raw.strip().rstrip(".!?;")
    offset = start + len(raw) - len(raw.lstrip())
    unit = {
        **_evidence(body, start, end),
        "kind": "unknown",
        "disposition": "unknown",
        "subjects": [],
        "scope_evidence": [],
        "role_declarations": [],
    }
    if re.search(r"\n[ \t\r]*\n", raw):
        active = declared
    if not text:
        unit.update(kind="separator", disposition="separator")
        return unit, active, declared
    if _GLOBAL.search(text):
        unit.update(kind="governance", disposition="global")
        return unit, active, declared
    if _GLOBAL_MODIFIER.search(text):
        unit["kind"] = "governance"
        return unit, declared, declared
    # References are not silently resolved, even within a declared local note.
    if _REFERENCE.search(text) or _CONDITION.search(text):
        unit["kind"] = "reference" if _REFERENCE.search(text) else "governance"
        return unit, declared, declared
    if _METADATA.fullmatch(text):
        unit.update(kind="metadata", disposition="non_governing")
        return unit, active, declared
    heading = _heading(text)
    if heading and _nominal(heading["subject"], _SUBJECT_BLOCKERS):
        active = _scope_from_match(body, offset, heading)
        unit.update(
            kind="heading",
            disposition="local",
            subjects=[active[0]],
            scope_evidence=[active[1]],
        )
        return unit, active, active
    fronted = re.fullmatch(r"for\s+(?P<subject>[^,]+),\s*(?P<predicate>.+)", text, re.I)
    if fronted and _nominal(fronted["subject"], _SUBJECT_BLOCKERS):
        kind = _local_predicate(fronted["predicate"])
        if kind:
            current = _scope_from_match(body, offset, fronted)
            unit.update(
                kind=kind,
                disposition="local",
                subjects=[current[0]],
                scope_evidence=[current[1]],
            )
            role_match = _contextual_role(fronted["predicate"])
            if role_match:
                unit["role_declarations"] = [
                    _role_declaration(
                        body,
                        offset + fronted.start("predicate"),
                        role_match,
                        current[1],
                    )
                ]
            nested = _role(fronted["predicate"]) if role_match is None else None
            if nested:
                if not _nominal(nested["subject"], _SUBJECT_BLOCKERS):
                    return (
                        {
                            **unit,
                            "kind": "unknown",
                            "disposition": "unknown",
                            "role_declarations": [],
                        },
                        declared,
                        declared,
                    )
                nested_scope = _scope_from_match(
                    body, offset + fronted.start("predicate"), nested
                )
                unit["subjects"].append(nested_scope[0])
                unit["scope_evidence"].append(nested_scope[1])
                unit["role_declarations"] = [
                    _role_declaration(
                        body,
                        offset + fronted.start("predicate"),
                        nested,
                        nested_scope[1],
                    )
                ]
            return unit, current, declared
    match = _role(text)
    if match and _nominal(match["subject"], _SUBJECT_BLOCKERS):
        current = _scope_from_match(body, offset, match)
        unit.update(
            kind="role",
            disposition="local",
            subjects=[current[0]],
            scope_evidence=[current[1]],
        )
        unit["role_declarations"] = [_role_declaration(body, offset, match, current[1])]
        return unit, current, declared
    inherited = _contextual_role(text)
    if active and inherited:
        unit.update(
            kind="role",
            disposition="local",
            subjects=[active[0]],
            scope_evidence=[active[1]],
        )
        unit["role_declarations"] = [
            _role_declaration(body, offset, inherited, active[1])
        ]
        return unit, active, declared
    fact = _scalar_fact(text)
    if fact:
        current = _scope_from_match(body, offset, fact)
        unit.update(
            kind="fact",
            disposition="local",
            subjects=[current[0]],
            scope_evidence=[current[1]],
        )
        return unit, current, declared
    if active and _instruction(text):
        unit.update(
            kind="instruction",
            disposition="local",
            subjects=[active[0]],
            scope_evidence=[active[1]],
        )
        return unit, active, declared
    return unit, declared, declared


def source_cover(body: str, identity: Mapping[str, Any]) -> dict[str, Any]:
    """Cover the exact raw body; unparsed units never become negative evidence."""
    bound = _identity(body, identity)
    units = []
    cursor = 0
    active = declared = None
    boundaries = [
        match.end() for match in re.finditer(r"[.!?;](?=\s|$)|\n(?:[ \t\r]*\n)*", body)
    ]
    if not boundaries or boundaries[-1] != len(body):
        boundaries.append(len(body))
    for end in boundaries:
        if end == cursor:
            continue
        unit, active, declared = _classify(body, cursor, end, active, declared)
        units.append(unit)
        cursor = end
    return {
        "contract": reading_version("contextual_source_v1").scope_cover,
        "identity": bound,
        "body_sha256": bound["content_hash"],
        "body_length": len(body),
        "units": units,
    }


def _reconstructed(cover: Any) -> str:
    if not isinstance(cover, dict) or not isinstance(cover.get("units"), list):
        raise ValueError("Missing whole-source cover")
    cursor = 0
    parts = []
    for unit in cover["units"]:
        if (
            not isinstance(unit, dict)
            or type(unit.get("start")) is not int
            or type(unit.get("end")) is not int
            or unit["start"] != cursor
            or unit["end"] <= cursor
            or not isinstance(unit.get("text"), str)
            or len(unit["text"]) != unit["end"] - cursor
        ):
            raise ValueError("Invalid source-cover ranges")
        parts.append(unit["text"])
        cursor = unit["end"]
    body = "".join(parts)
    identity = cover.get("identity")
    if not isinstance(identity, Mapping):
        raise ValueError("Missing source identity")
    if _json(source_cover(body, identity)) != _json(cover):
        raise ValueError("Source-cover reconstruction differs")
    return body


def validate_source_cover(cover: Any, body: str, identity: Mapping[str, Any]) -> bool:
    """Re-derive from caller-supplied authoritative snapshot, not producer flags."""
    try:
        return _reconstructed(cover) == body and source_cover(body, identity) == cover
    except (ValueError, TypeError, AttributeError, KeyError):
        return False


def serialize_source_cover(cover: dict[str, Any]) -> str:
    """Stable JSON serialization of a reconstructed cover."""
    _reconstructed(cover)
    return _json(cover)


def _json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _canonical(text: str) -> str:
    value = re.sub(r"^(?:the|a|an)\s+", "", " ".join(text.split()), flags=re.I)
    return re.sub(r"\bsessions$", "session", value.casefold())


def _same_namespace(subject: str, requested: str) -> bool:
    left, right = _canonical(subject), _canonical(requested)
    # Broad retention only: a qualified session containing the exact activity is
    # still a candidate. This does not choose a branch or certify applicability.
    return left == right or f" {left} " in f" {right} " or f" {right} " in f" {left} "


def scope_relevance(
    cover: Any, requested_subject: str, *, activity: str | None = None
) -> dict[str, Any]:
    """Classify candidate relevance only; unknown/global governance is retained."""
    result: dict[str, Any] = {
        "status": "unknown",
        "reason": "invalid_cover",
        "evidence": [],
    }
    try:
        body = _reconstructed(cover)
    except (ValueError, TypeError, AttributeError, KeyError):
        return result
    if (
        not isinstance(requested_subject, str)
        or not requested_subject.strip()
        or (
            activity is not None
            and (not isinstance(activity, str) or not activity.strip())
        )
    ):
        result["reason"] = "unresolved_request_scope"
        return result
    units = [unit for unit in cover["units"] if unit["disposition"] != "separator"]
    result["evidence"] = deepcopy(units)
    if not body.strip() or not units:
        result["reason"] = "empty_source"
        return result
    queries = [requested_subject, *([activity] if activity is not None else [])]
    matched = any(
        _same_namespace(subject, query)
        for unit in units
        for subject in unit["subjects"]
        for query in queries
    )
    if matched or any(unit["disposition"] == "global" for unit in units):
        result.update(status="relevant", reason="declared_or_global_scope")
    elif any(unit["disposition"] == "unknown" for unit in units):
        result["reason"] = "unclassified_source_region"
    else:
        result.update(status="irrelevant", reason="all_regions_declared_elsewhere")
    return result
