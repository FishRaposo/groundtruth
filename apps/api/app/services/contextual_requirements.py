"""Versioned, bounded request decomposition; unresolved text stays an obligation.

This planner establishes no source authority or model support. Its original ranges
are retained for independent history reconstruction, including unsupported clauses.
"""

from __future__ import annotations

import re
from dataclasses import replace

from app.services.answer_requirements import Requirement, _requirement_anchors

_HEAD = (
    r"(?:(?:the|its|their)\s+)?(?:activity\s+)?(?:lead\b|deputy\b|owner\b|"
    r"(?:entire|complete|full|every|all)\b|bench\b|desk\b|station\b|location\b|"
    r"duration\b|hours\b|start\s+time\b)|"
    r"who\b|what\b|which\b|where\b|when\b|how\b|why\b|whether\b|"
    r"may\b|can\b|must\b|should\b|does\b|do\b|is\b|are\b|at\s+which\b|"
    r"(?:name|give|list|state|identify|include|explain|describe|provide)\b"
)
_SEPARATOR = re.compile(
    rf"(?:,\s*(?:(?:and|plus)\s+)?|\s+(?:and|plus|then)\s+)(?=(?:{_HEAD}))"
    rf"|(?<=[?.!])\s+(?:and\s+)?(?=(?:{_HEAD}))",
    re.I,
)
_PREFIX = re.compile(r"\s*(?:for|in|at|regarding)\s+([^,;?!]+)[,:]\s*", re.I)
_ARTICLE = re.compile(r"^(?:the|an?)\s+", re.I)
_PROCEDURE = re.compile(
    r"\b(?:routine|procedure|instructions|steps|sequence|protocol)\b", re.I
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,;?.!")


def _explicit_role_scope(text: str) -> str | None:
    active = re.fullmatch(
        r"(?:who|which\s+role)\s+(?:leads|owns|runs|manages)\s+(.+)|"
        r"who\s+is\s+(?:in\s+charge\s+(?:of|during)|responsible\s+for)\s+(.+)",
        _clean(text),
        re.I,
    )
    if active:
        return _ARTICLE.sub("", next(g for g in active.groups() if g))
    nominal = re.search(
        r"\b(?:lead|owner|deputy|lead\s+role|responsible\s+role)\s+"
        r"(?:for|of|in|during)\s+(.+)",
        _clean(text),
        re.I,
    )
    return _ARTICLE.sub("", nominal.group(1)) if nominal else None


def _subject(text: str, inherited: str) -> str:
    prefix = _PREFIX.match(text)
    if prefix:
        return _ARTICLE.sub("", _clean(prefix.group(1)))
    explicit = _explicit_role_scope(text)
    if explicit:
        if (
            re.fullmatch(r"(?:ordinary|normal|standard)\s+sessions?", explicit, re.I)
            and inherited
        ):
            activity = re.sub(
                r"^(?:ordinary|normal|standard)\s+", "", inherited, flags=re.I
            )
            activity = re.sub(r"\s+sessions?$", "", activity, flags=re.I)
            return f"ordinary {activity} session"
        return explicit
    patterns = (
        r"\b(?:lead|deputy|owner|count|hours|availability)\s+for\s+(.+?)(?:,|[?.!]|$)",
        r"^how\s+long\s+(?:is|does|will)\s+(.+?)(?:\s+(?:last|take))?[?.!]*$",
        r"^(?:what|which)\s+is\s+the\s+(?:length|duration)\s+of\s+(.+?)[?.!]*$",
        r"^who\s+(?:leads|runs|manages|owns|is\s+in\s+charge\s+(?:of|during))\s+(.+?)[?.!]*$",
        r"^how\s+many\s+.+?\s+(?:on|in|for|to)\s+(.+?)[?.!]*$",
        r"\b(?:for|during)\s+(.+?)[?.!]*$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidate = _ARTICLE.sub("", _clean(match.group(1)))
            if inherited and not _requirement_anchors(candidate):
                return inherited
            return candidate
    # A named routine can introduce the scope before a later role conjunct.
    match = re.search(
        r"(?:full|complete|entire)\s+(.+?)\s+(?:routine|procedure|protocol)\b",
        text,
        re.I,
    )
    if match:
        candidate = _ARTICLE.sub("", _clean(match.group(1)))
        return (
            inherited
            if inherited and not _requirement_anchors(candidate)
            else candidate
        )
    return inherited


def _role_kind(text: str) -> str | None:
    """Consume a role request, rather than finding a role inside another fact."""
    text = _clean(text)
    active = re.fullmatch(
        r"(?:who|which\s+role)\s+(?:leads|owns|runs|manages)\s+.+|"
        r"who\s+is\s+(?:in\s+charge\s+(?:of|during)|responsible\s+for)\s+.+",
        text,
        re.I,
    )
    if active:
        return "owner"
    label = re.fullmatch(
        r"(?:(?:who\s+(?:is|are)|name|give|identify|state|list|need|tell\s+me)\s+)?"
        r"(?:(?:the|its|their|ordinary|normal|standard|activity)\s+)*"
        r"(?P<role>lead|owner|deputy|lead\s+role|responsible\s+role)"
        r"(?:\s+(?:for|of|in|when|if|unless|during|under|without|excluding|except|"
        r"before|after)\s+.+)?",
        text,
        re.I,
    )
    if label:
        return "deputy" if label.group("role").casefold() == "deputy" else "owner"
    return None


def _kind(text: str) -> str:
    # Per-fragment precedence is safe only after decomposition: a procedure in
    # one fragment cannot swallow a role in a different fragment.
    if re.search(r"\b(?:and|plus|also|then)\b", text, re.I):
        # The splitter did not understand this coordination. It cannot become
        # part of an invented role namespace or disappear into a procedure.
        return "generic"
    if _PROCEDURE.search(text) and re.search(
        r"\b(?:entire|all|every|complete|full|list|order|steps)\b", text, re.I
    ):
        return "procedure"
    role = _role_kind(text)
    if role:
        return role
    if re.search(r"\b(?:lead|deputy|owner)['’]s\b", text, re.I):
        return "generic"
    patterns = (
        ("availability", r"\b(?:hours|availability|available)\b"),
        ("location", r"\b(?:where|bench|desk|station|location|venue)\b"),
        ("duration", r"\b(?:how\s+long|length|duration|interval|elapsed)\b"),
        ("quantity", r"\b(?:how\s+many|count|number|capacity|quantity)\b"),
        ("start_time", r"\b(?:start\s+time|what\s+time|when\s+does|when\s+will)\b"),
        ("weekday", r"\b(?:which\s+day|what\s+day|weekday)\b"),
        ("boolean", r"^\s*(?:may|can|does|do|is|are|must|should)\b"),
        ("prohibition", r"\b(?:prohibition|forbidden|prohibited|rule\s+against)\b"),
    )
    for kind, pattern in patterns:
        if re.search(pattern, text, re.I):
            return kind
    return "generic"


def _question(kind: str, body: str, topic: str, inherited: bool) -> str:
    text = _clean(body)
    if kind in {"owner", "deputy"}:
        # Retain named/conditional scope; no silent activity-role fallback here.
        role = "lead" if kind == "owner" else "deputy"
        condition = re.search(
            r"\b(?:when|if|unless|only|under|without|excluding|except|before|after)\s+.+",
            text,
            re.I,
        )
        suffix = (
            f" {condition.group()}"
            if condition and condition.group().casefold() not in topic.casefold()
            else ""
        )
        return f"Who is the {role} for {topic}{suffix}?"
    if kind == "procedure":
        return f"For {topic}, {text}?"
    if inherited and topic:
        return f"For {topic}, {text}?"
    return text + "?"


def _request_intervals(question: str) -> list[tuple[int, int]]:
    prefix = _PREFIX.match(question)
    # A trailing explicit topic scopes a coordinated nominal list too ("lead
    # and deputy for X"). It is input evidence, never a source/title guess.
    cuts = [0]
    intervals = []
    for match in _SEPARATOR.finditer(question):
        if prefix and match.start() < prefix.end():
            continue
        intervals.append((cuts[-1], match.start()))
        cuts.append(match.end())
    intervals.append((cuts[-1], len(question)))
    trimmed = []
    for start, end in intervals:
        while start < end and question[start].isspace():
            start += 1
        while end > start and question[end - 1].isspace():
            end -= 1
        if start < end:
            trimmed.append((start, end))
    return trimmed


def _share_ordinary_role_scope(requirements):
    """A trailing ordinary-session modifier scopes a bare coordinated role list."""
    result = list(requirements)
    for index, req in enumerate(requirements):
        session = re.fullmatch(r"ordinary (.+) session", req.topic, re.I)
        if req.kind not in {"owner", "deputy"} or not session:
            continue
        for previous in range(index - 1, -1, -1):
            item = result[previous]
            if item.kind not in {"owner", "deputy"}:
                break
            body = item.original_text
            prefix = _PREFIX.match(body)
            body = body[prefix.end() :] if prefix else body
            if item.topic.casefold() != session.group(1).casefold() or not re.fullmatch(
                r"(?:(?:identify|name|give|state|list)\s+)?(?:the\s+)?(?:lead|deputy)",
                _clean(body),
                re.I,
            ):
                break
            result[previous] = replace(
                item,
                topic=req.topic,
                anchors=req.anchors,
                question=_question(item.kind, body, req.topic, True),
            )
    return tuple(result)


def plan_contextual_requirements(question: str) -> tuple[Requirement, ...]:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("empty_request")
    result = []
    active = _subject(question, "")
    role_ids = {}
    for start, end in _request_intervals(question):
        original = question[start:end]
        prefix = _PREFIX.match(original)
        body = original[prefix.end() :] if prefix else original
        topic = _subject(original, active)
        inherited = topic == active and not prefix
        active = topic or active
        kind = _kind(body)
        role_target = (
            _explicit_role_scope(body) if kind in {"owner", "deputy"} else None
        )
        if (
            prefix
            and role_target
            and _clean(role_target).casefold() != topic.casefold()
        ):
            # Two distinct explicit scopes cannot be collapsed into the fronted
            # one. Keep the entire request unresolved, rather than ask NLI to
            # certify only the easy role at the cost of the requested entity.
            kind = "generic"
        dependency = ()
        if re.search(r"\b(?:that\s+(?:role|person|owner)|their|its)\b", body, re.I):
            if kind == "availability" and role_ids.get("owner"):
                dependency = (role_ids["owner"],)
        identifier = f"r{len(result) + 1}"
        result.append(
            Requirement(
                identifier,
                original,
                start,
                end,
                _question(kind, body, topic, inherited),
                kind,
                topic,
                _requirement_anchors(topic),
                dependency,
                "leads" if kind == "owner" else kind,
                kind,
            )
        )
        if kind in {"owner", "deputy"}:
            role_ids[kind] = identifier
        if len(result) > 8:
            raise ValueError("requirement_limit")
    return _share_ordinary_role_scope(result)
