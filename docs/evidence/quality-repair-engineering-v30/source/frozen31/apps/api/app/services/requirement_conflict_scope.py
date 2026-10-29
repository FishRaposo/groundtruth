"""Body-only temporal relevance and procedure condition proposals, never support.

Unknown scope is not permission, entailment, an actor alias or group inheritance.
The controller separately owns applicability, model decisions and authorization.
"""

from __future__ import annotations

import re
from dataclasses import replace

from app.services import requirement_binding as binding
from app.services.answer_requirements import Requirement, _requirement_anchors
from app.services.requirement_contract import PROCEDURE_COPY_CONTRACT

_PREFIX = re.compile(r"^\s*for\s+([^,;:.!?]+)[,:]\s*", re.I)
_BREAK = re.compile(
    r"[.!?;\n]|\s+(?:and|but|whereas|while)\s+"
    r"(?!(?:may|is|are)\b)",
    re.I,
)
_COVER = r"may(?:\s+not)?\s+(?:substitute|cover)"
_PRESENCE = r"(?:is|are)\s+(?:not\s+)?(?:available|present)"
_AVAILABILITY = re.compile(
    rf"(?P<actor>.+?)\s+(?P<predicate>{_COVER}|{_PRESENCE})\b(?P<tail>.*)",
    re.I,
)
_COORDINATED_COVER = re.compile(
    rf"(?P<actor>.+?)\s+is\s+(?:the\s+)?deputy\s+for\s+"
    rf"(?P<activity>.+?)\s+and\s+(?P<predicate>{_COVER})\b(?P<tail>.*)",
    re.I,
)
_TARGET = re.compile(r"\s+(?:for|during|in)\s+(.+?)(?=\s+(?:only|on|from)\b|$)", re.I)
_START = re.compile(r"(?P<activity>.+?)\s+(?:starts?|begins?)\b(?P<tail>.*)", re.I)
_ARRIVAL = re.compile(
    r"^(?:(?:the|its)\s+)?(?:arrival|check[ -]in)\s+(?:time|window)\b", re.I
)
_UNRESOLVED_ACTOR = frozenset(
    {"it", "they", "this", "that", "the role", "role", "deputy", "owner", "person"}
)
_DAY = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)s?"
_CLOCK = r"\d{1,2}:\d{2}(?:\s*[ap]m)?"
_TEMPORAL_VALUE = re.compile(
    rf"\b(?:{_DAY}|{_CLOCK}|noon|midnight|morning|afternoon|evening|dawn|dusk)\b",
    re.I,
)
_TEMPORAL_TAIL = re.compile(
    rf"(?:\s|,|{_CLOCK}\b|{_DAY}\b|\d+\b|"
    r"\b(?:only|on|from|to|until|through|between|at|not|every|each|any|time|"
    r"noon|midnight|morning|afternoon|evening|dawn|dusk|am|pm|utc|"
    r"hours?|minutes?|seconds?)\b)*",
    re.I,
)
_FIELD_LABEL = re.compile(
    r"(?:these|those|this|that)\s+(?:is|are)\s+(?P<actor>.+?)['’]s\s+"
    r"(?P<field>cover\s+hours|duty\s+hours|availability|start\s+time|opening\s+time)",
    re.I,
)


def _canonical(text: str) -> str:
    return binding._canonical_argument(" ".join(text.split()))


def _nominal_subject(text: str) -> bool:
    # A typed subject cannot swallow an earlier unparsed statement or clock.
    return bool(re.fullmatch(r"[\w'’-]+(?:\s+[\w'’-]+)*", text.strip())) and not bool(
        re.search(
            r"\b(?:is|are|was|were|has|have|may|can|scheduled|assigned|"
            r"if|when|unless|except|not|no|only)\b",
            text,
            re.I,
        )
    )


def _complete_temporal_tail(tail: str) -> bool:
    target = _TARGET.search(tail)
    if target is not None:
        if not _nominal_subject(target.group(1)):
            return False
        tail = tail[: target.start()] + " " + tail[target.end() :]
    return _TEMPORAL_TAIL.fullmatch(tail) is not None


def _unparsed_statement_scope(req: Requirement, body: str) -> str | None:
    label = _FIELD_LABEL.fullmatch(body)
    if label is not None and _nominal_subject(label.group("actor")):
        cover = label.group("field").casefold() in {
            "cover hours",
            "duty hours",
            "availability",
        }
        if cover == (req.kind == "availability"):
            actor = (
                _actor_scope(label.group("actor"), req.topic)
                if req.kind == "availability"
                else _activity_scope(req, label.group("actor"), req.topic)
            )
            return "irrelevant" if actor == "irrelevant" else "unknown"
    fields = (
        r"\b(?:availability|available|present|hours?|cover|substitut\w*|duty|"
        r"schedule\w*|reliev\w*)\b"
        if req.kind == "availability"
        else r"\b(?:starts?|begins?|scheduled|opening|commences?|kickoff)\b"
    )
    incidental = re.fullmatch(
        r"(?P<subject>.+?)\s+(?:archives?|stores?)\s+(?P<object>.+)", body, re.I
    )
    # Discard only a completely parsed non-temporal incidental statement. Every
    # other unparsed statement remains possible field evidence, including novel
    # paraphrases without familiar keywords, clocks or an explicit actor.
    if (
        incidental is not None
        and _nominal_subject(incidental.group("subject"))
        and _nominal_subject(incidental.group("object"))
        and not _TEMPORAL_VALUE.search(body)
        and not re.search(fields, body, re.I)
    ):
        return None
    return "unknown"


def _scope_and_body(clause: str) -> tuple[str | None, str]:
    prefix = _PREFIX.match(clause)
    return (
        (prefix.group(1), clause[prefix.end() :].strip())
        if prefix
        else (None, clause.strip())
    )


def _activity_scope(req: Requirement, actual: str, expected: str) -> str:
    # Reuse the existing canonical activity/namespace authority. In particular,
    # an abbreviated session or missing condition remains unknown, not an alias.
    scoped = replace(req, topic=expected, anchors=_requirement_anchors(expected))
    return binding._scope_target(scoped, actual)


def _actor_scope(actor: str, expected: str) -> str:
    actual = _canonical(actor)
    if actual in _UNRESOLVED_ACTOR or _canonical(expected) in _UNRESOLVED_ACTOR:
        return "unknown"
    if actual == _canonical(expected):
        return "applies"
    if re.search(r"[,;:]|\b(?:and|but|if|when)\b", actor, re.I):
        return "unknown"
    return "irrelevant"


def _availability_scope(req: Requirement, scope: str | None, body: str) -> str | None:
    event = _COORDINATED_COVER.fullmatch(body)
    linked = event.group("activity") if event else None
    event = event or _AVAILABILITY.fullmatch(body)
    if event is None:
        return None
    if not _nominal_subject(event.group("actor")) or not _complete_temporal_tail(
        event.group("tail")
    ):
        return "unknown"
    actor = _actor_scope(event.group("actor"), req.topic)
    if actor != "applies":
        return actor
    cover = event.group("predicate").casefold().startswith("may")
    if cover != (req.relation == "cover_window"):
        return "irrelevant"  # Presence and cover permission are different fields.
    expected, _ = _scope_and_body(req.question)
    if expected is None:
        return "applies"
    target = _TARGET.search(event.group("tail"))
    scopes = [
        value for value in (scope, linked, target.group(1) if target else None) if value
    ]
    if not scopes:
        return "unknown"
    decisions = [_activity_scope(req, value, expected) for value in scopes]
    if "irrelevant" in decisions:
        return "irrelevant"
    return "applies" if all(value == "applies" for value in decisions) else "unknown"


def _start_scope(req: Requirement, scope: str | None, body: str) -> str | None:
    event = _START.fullmatch(body)
    if event is None:
        arrival = _ARRIVAL.match(body)
        tail = body[arrival.end() :] if arrival else ""
        tail = re.sub(r"^\s*(?:is|are)\b", "", tail, flags=re.I)
        return "irrelevant" if arrival and _complete_temporal_tail(tail) else None
    target = event.group("activity")
    if not _nominal_subject(target) or not _complete_temporal_tail(event.group("tail")):
        return "unknown"
    if scope and _activity_scope(req, scope, req.topic) == "irrelevant":
        return "irrelevant"
    if _canonical(target) == _canonical(req.topic):
        return "applies"
    if _ARRIVAL.match(target):
        return "irrelevant"
    if _canonical(target) in {"session", "it", "its session"}:
        return _activity_scope(req, scope, req.topic) if scope else "unknown"
    result = _activity_scope(req, target, req.topic)
    return result


def source_relation_scope(req: Requirement, content: str) -> str:
    """Classify body relation scope without proving facts or inheriting a role.

    Only availability and session start are added here. Existing typed kinds
    retain their binding authority; every other grammar remains unknown.
    """
    if req.kind in {"owner", "deputy", "procedure"}:
        return binding.source_relation_scope(req, content)
    if req.kind not in {"availability", "start_time"}:
        return "unknown"
    decisions = []
    for clause in _BREAK.split(content):
        scope, body = _scope_and_body(clause.strip())
        if not body:
            continue
        decision = (
            _availability_scope(req, scope, body)
            if req.kind == "availability"
            else _start_scope(req, scope, body)
        )
        if decision is None:
            decision = _unparsed_statement_scope(req, body)
        if decision is not None:
            decisions.append(decision)
    if "applies" in decisions:
        return "applies"
    return "unknown" if not decisions or "unknown" in decisions else "irrelevant"


def procedure_condition_exclusion(  # noqa: C901 - bounded source-class proposal only
    req: Requirement,
    body: str,
    metadata: dict,
    proofs,
    *,
    context_policy="explicit_target_v1",
) -> dict | None:
    """Propose a disjoint condition, never establish exclusive applicability.

    The accepted procedure's canonical declaration must explicitly exclude the
    opponent's entire source class. A title/leading condition alone cannot prove
    that every instruction in the opponent has that scope; the caller must assess
    exclusive applicability against its complete immutable body.
    """
    from app.services.procedure_paragraphs import (
        ParagraphRejected,
        _paragraphs,
        parse,
        scope_matches,
    )

    # Existing explicit metadata conditions retain their own authority. A body
    # proposal cannot silently narrow or override a differently stated scope.
    if metadata.get("condition") is not None:
        return None
    for proof in proofs:
        proof = proof or {}
        if proof.get("contract") != PROCEDURE_COPY_CONTRACT:
            continue
        try:
            parsed = parse(proof.get("source_body", ""))
        except ParagraphRejected:
            continue
        if parsed is None or not scope_matches(parsed, req.topic):
            continue
        conditions = re.fullmatch(
            r"(?P<included>(?:an?|the)\s+[^,;.!?]+),\s+not\s+"
            r"(?:an?|the)\s+(?P<excluded>[\w-]+(?:\s+[\w-]+){0,3})",
            parsed.conditions,
            re.I,
        )
        if conditions is None or not _nominal_subject(conditions.group("excluded")):
            continue
        # Reuse literal For-condition boundaries. Only an optional document title
        # may precede the governing header; no arbitrary prose is discarded.
        parts = _paragraphs(body)
        if not parts:
            continue
        first = 0
        title = re.fullmatch(r"([^:\n.!?]+):[^\n.!?]+", body[slice(*parts[0])])
        if title and _canonical(title.group(1)) == _canonical(parsed.scope):
            first = 1
        if first >= len(parts):
            continue
        header = _PREFIX.match(body[slice(*parts[first])])
        if header is None:
            continue
        condition = header.group(1)
        # The namespace and excluded class are literal, source-derived values.
        # An alternative class or unparsed governing qualifier remains unknown.
        expected = (
            rf"(?:the\s+)?{re.escape(parsed.scope)}\s+"
            rf"{re.escape(conditions.group('excluded'))}"
            r"(?:\s+marked\s+with\s+(?:an?|the)\s+[\w-]+)?"
        )
        if re.fullmatch(expected, condition, re.I) is None:
            continue
        start = parts[first][0] + header.start(1)
        candidate = {
            "contract": "procedure-condition-scope-v1",
            "condition": condition,
            "condition_range": {"start": start, "end": start + len(condition)},
            "excluded_class": conditions.group("excluded"),
            "procedure_source_identity": {
                key: proof.get(key)
                for key in ("document_id", "document_version", "content_hash")
            },
            "procedure_conditions": parsed.conditions,
            "hypothesis": f"The instructions apply only to {condition}.",
            "premise_range": {"start": 0, "end": len(body)},
        }
        if context_policy in ("scoped_note_context_v1", "scoped_note_context_v2"):
            from app.services.source_context_scope import (
                parse_context_note,
                semantic_checks,
            )

            reading = parse_context_note(
                body, parsed.scope, conditions.group("excluded"), policy=context_policy
            )
            if reading is None:
                return None
            candidate.pop("hypothesis")
            from app.evidence_policy import context_version

            candidate.update(
                contract=context_version(context_policy).scope,
                context_reading=reading,
                semantic_checks=semantic_checks(reading),
            )
            if context_policy == "scoped_note_context_v2":
                from app.services.source_context_references import (
                    compile_reference_obligation,
                    obligation_plan,
                )

                candidate.update(
                    obligation_plan=obligation_plan(reading),
                    reference_obligations=[compile_reference_obligation(reading)],
                )
        elif context_policy != "explicit_target_v1":
            return None
        return candidate
    return None
