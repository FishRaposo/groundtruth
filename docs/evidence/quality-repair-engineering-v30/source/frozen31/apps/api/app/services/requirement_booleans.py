"""Bound complete, nonnull negative proposals to propositions for later NLI.

Factual nonoccurrence, permission, capability, obligation and advice remain
distinct. This helper never certifies support, revives QA nulls, aliases verbs,
or imports the binding dispatcher. Unknown grammar has no proposition.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.answer_requirements import Requirement


@dataclass(frozen=True)
class BooleanClaim:
    hypothesis: str | None
    start: int | None
    end: int | None
    support_start: int | None
    support_end: int | None
    rejection: str | None
    relation_kind: str | None
    raw_start: int | None
    raw_end: int | None


@dataclass(frozen=True)
class _Request:
    auxiliary: str
    subject: str
    verb: str
    obj: str
    scope: str
    kind: str


@dataclass(frozen=True)
class _Action:
    actor: str
    auxiliary: str
    verb: str
    obj: str
    predicate: str
    kind: str
    starts: tuple[int, ...]
    predicate_start: int
    object_start: int
    end: int


_SCOPE = re.compile(r"^\s*((?:for|in|at|on|regarding)\s+[^,;?!]+,)\s*", re.I)
_BOUNDARY = re.compile(r";\s*|,\s*(?:and|but|whereas|while)\s+", re.I)
_NEGATIVE = re.compile(r"\b(?:not|never|cannot|neither|nor)\b", re.I)
_KINDS = {
    "do": "factual",
    "does": "factual",
    "may": "permission",
    "can": "capability",
    "must": "obligation",
    "should": "advice",
}
# One declared edge: a negative obligation prohibits permission. It establishes
# neither inability nor factual nonoccurrence; keep the source "must not" in H.
_NEGATIVE_MODAL_ENTAILMENTS = frozenset({("obligation", "permission")})


def _safe(text: str) -> bool:
    return not any(
        unicodedata.category(char).startswith("C") and char not in "\t\r\n"
        for char in text
    )


def _canonical(text: str, *, subject: bool = False) -> str:
    text = " ".join(text.casefold().split())
    return text.removeprefix("the ") if subject else text


def _scope(text: str) -> tuple[str, str, int]:
    match = _SCOPE.match(text)
    return (
        (match.group(1), text[match.end() :], match.end()) if match else ("", text, 0)
    )


def _request(req: Requirement) -> _Request | None:
    if req.kind != "boolean" or not req.topic or not _safe(req.question + req.topic):
        return None
    scope, body, _ = _scope(req.question.strip().rstrip("?.!"))
    match = re.fullmatch(
        rf"(does|do|may|can|must|should)\s+(?:the\s+)?{re.escape(req.topic)}\s+"
        r"([\w-]+)\s+(.+)",
        body,
        re.I,
    )
    if match is None or _canonical(req.topic) in {
        "it",
        "they",
        "this",
        "that",
        "these",
        "those",
    }:
        return None
    auxiliary, verb, obj = match.groups()
    if verb.casefold() in {"not", "never", "cannot"}:
        return None
    return _Request(
        auxiliary.casefold(), req.topic, verb, obj, scope, _KINDS[auxiliary.casefold()]
    )


def _action(body: str, offset: int) -> _Action | None:
    match = re.fullmatch(
        r"(?P<actor>.+?)\s+(?P<aux>does|do|may|must|should|can)\s+"
        r"(?P<neg>not)\s+(?P<verb>[\w-]+)\s+(?P<obj>.+)",
        body,
        re.I,
    )
    kind = ""
    if match:
        kind = _KINDS[match.group("aux").casefold()]
    else:
        match = re.fullmatch(
            r"(?P<actor>.+?)\s+(?P<aux>cannot)\s+(?P<verb>[\w-]+)\s+(?P<obj>.+)",
            body,
            re.I,
        )
        kind = "capability"
    if match is None:
        match = re.fullmatch(
            r"(?P<actor>.+?)\s+(?P<aux>is|are)\s+(?P<neg>not)\s+"
            r"(?:permitted|allowed)\s+to\s+(?P<verb>[\w-]+)\s+(?P<obj>.+)",
            body,
            re.I,
        )
        kind = "permission"
    if match is None or _NEGATIVE.search(match.group("actor")):
        return None
    starts = [offset + match.start("actor"), offset + match.start("aux")]
    if "neg" in match.re.groupindex:
        starts.append(offset + match.start("neg"))
    return _Action(
        match.group("actor"),
        match.group("aux").casefold(),
        match.group("verb"),
        match.group("obj"),
        body[match.start("aux") :],
        kind,
        tuple(starts),
        offset + match.start("aux"),
        offset + match.start("obj"),
        offset + match.end("obj"),
    )


def _sentence(context: str, start: int) -> tuple[str, int, int] | None:
    previous = list(re.finditer(r"[.!?\n]", context[:start]))
    left = previous[-1].end() if previous else 0
    following = re.search(r"[.!?\n]", context[start:])
    right = start + following.end() if following else len(context)
    text = context[left:right]
    if not _safe(text) or text.rstrip().endswith("?"):
        return None
    leading = len(text) - len(text.lstrip())
    return text.strip(), left + leading, right


def _antecedent(subject: str, prefix: str) -> bool:
    if _NEGATIVE.search(prefix):
        return False
    classifier = re.fullmatch(
        r"(.+?)\s+(?:is|are)\s+(?:an?|the)\s+([\w -]+?)(?:\s+only)?"
        r"(?:\s*:\s*its\s+[^:;]+?\s+(?:is|are)\s+[^:;]+)?",
        prefix,
        re.I,
    )
    if classifier:
        owner, noun_class = classifier.groups()
        if re.search(
            r"\b(?:if|unless|when|while|before|after|under)\b", noun_class, re.I
        ):
            return False
        return _canonical(subject, subject=True) in {
            _canonical(owner, subject=True),
            _canonical(owner + " " + noun_class, subject=True),
        }
    representation = re.fullmatch(
        r"(.+?)\s+(?:writes?|represents?|encodes?|records?)\s+.+", prefix, re.I
    )
    return bool(
        representation
        and _canonical(representation.group(1), subject=True)
        == _canonical(subject, subject=True)
    )


def _actor_matches(request: _Request, action: _Action, prefix: str) -> bool:
    actor = _canonical(action.actor, subject=True)
    if actor == _canonical(request.subject, subject=True):
        return True
    return (
        actor in {"it", "they"}
        and bool(prefix)
        and _antecedent(request.subject, prefix)
    )


def _previous_antecedent(
    context: str, current_left: int, pronoun: str
) -> tuple[str, str, int] | None:
    """Read exactly one adjacent source sentence, never search older mentions."""
    preceding = context[:current_left].rstrip()
    if not preceding or preceding[-1] not in ".!":
        return None
    right = len(preceding)
    gap = context[right:current_left]
    if re.search(r"\n\s*\n", gap):
        return None
    boundaries = list(re.finditer(r"[.!?\n]", context[: right - 1]))
    left = boundaries[-1].end() if boundaries else 0
    text = context[left:right]
    leading = len(text) - len(text.lstrip())
    body = text.strip()[:-1]
    if (
        not _safe(text + gap)
        or _BOUNDARY.search(body)
        or re.search(r"\b(?:and|but|or|whereas|while)\b", body, re.I)
    ):
        return None
    scope, body, _ = _scope(body)
    if ":" in body or re.search(
        r"\b(?:if|unless|when|while|before|after|under)\b", body, re.I
    ):
        return None
    finite = re.search(
        r"\s+(is|are|writes?|represents?|encodes?|records?)\s+", body, re.I
    )
    if finite:
        verb = finite.group(1).casefold()
        expected = "they" if verb == "are" or not verb.endswith("s") else "it"
        if pronoun != expected:
            return None
    return scope, body, left + leading


def _candidate_complete(context: str, start: int, end: int, action: _Action) -> bool:
    if start == action.object_start and end == action.end:
        return True
    if start not in action.starts or end < action.end:
        return False
    excess = context[action.end : end]
    return not excess or bool(
        re.match(r"[.!?;]|,\s+(?:and|but|whereas|while)\b", excess, re.I)
    )


def _rejected(start: int | None, end: int | None, reason: str) -> BooleanClaim:
    return BooleanClaim(None, start, end, None, None, reason, None, start, end)


def _bound_claim(
    request: _Request,
    action: _Action,
    scope: str,
    context: str,
    start: int,
    end: int,
    left: int,
    right: int,
) -> BooleanClaim:
    if not _candidate_complete(context, start, end, action):
        return _rejected(start, end, "negative_action_or_polarity_incomplete")
    if action.kind == "factual" and request.kind == "permission":
        return _rejected(start, end, "factual_negative_does_not_establish_permission")
    if (
        action.kind != request.kind
        and (action.kind, request.kind) not in _NEGATIVE_MODAL_ENTAILMENTS
    ):
        return _rejected(start, end, "boolean_relation_kind_mismatch")
    if request.kind == "factual" and action.auxiliary != request.auxiliary:
        return _rejected(start, end, "boolean_auxiliary_mismatch")
    if _canonical(action.verb) != _canonical(request.verb) or _canonical(
        action.obj
    ) != _canonical(request.obj):
        return _rejected(start, end, "boolean_action_or_object_mismatch")
    prefix = scope + " " if scope else ""
    normalized_start = (
        action.predicate_start
        if (start, end) == (action.object_start, action.end)
        else start
    )
    return BooleanClaim(
        f"{prefix}{request.subject} {action.predicate}",
        normalized_start,
        action.end,
        left,
        right,
        None,
        action.kind,
        start,
        end,
    )


def _action_claim(
    requested: _Request,
    action: _Action,
    scope: str,
    antecedent: str,
    inherited_scope: str,
    preceding_clauses: int,
    context: str,
    start: int,
    end: int,
    left: int,
    right: int,
) -> BooleanClaim:
    pronoun = action.actor.casefold() in {"it", "they"}
    prefix = antecedent if preceding_clauses == 1 else ""
    inherited = inherited_scope if preceding_clauses == 1 else ""
    if pronoun and preceding_clauses == 0:
        previous = _previous_antecedent(context, left, action.actor.casefold())
        if previous is None:
            return _rejected(start, end, "boolean_subject_mismatch")
        inherited, prefix, left = previous
    if pronoun and scope and inherited and _canonical(scope) != _canonical(inherited):
        return _rejected(start, end, "boolean_scope_mismatch")
    actual_scope = scope or (inherited if pronoun else "")
    if requested.scope and _canonical(requested.scope) != _canonical(actual_scope):
        return _rejected(start, end, "boolean_scope_mismatch")
    if not _actor_matches(requested, action, prefix):
        return _rejected(start, end, "boolean_subject_mismatch")
    return _bound_claim(
        requested, action, actual_scope, context, start, end, left, right
    )


def negative_boolean_claim(
    req: Requirement, context: str, start: int | None, end: int | None
) -> BooleanClaim:
    """Bind a complete source-negative proposal; never infer factual support.

    A source interval is usable only with the usual authority, typed-request,
    null/model-error, NLI and complete-cover gates retained by the caller.
    """
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(context)
    ):
        return _rejected(start, end, "invalid_boolean_candidate_offsets")
    requested = _request(req)
    sentence = _sentence(context, start)
    if requested is None or sentence is None:
        return _rejected(start, end, "unsupported_negative_boolean")
    text, left, right = sentence
    body = text.rstrip(".!?")
    bounds = list(_BOUNDARY.finditer(body))
    first = 0
    antecedent = ""
    inherited_scope = ""
    preceding_clauses = 0
    for last in [m.start() for m in bounds] + [len(body)]:
        clause = body[first:last]
        leading = len(clause) - len(clause.lstrip())
        scope, local, shift = _scope(clause.strip())
        offset = left + first + leading + shift
        action = _action(local, offset)
        if action and offset <= start < action.end:
            return _action_claim(
                requested,
                action,
                scope,
                antecedent,
                inherited_scope,
                preceding_clauses,
                context,
                start,
                end,
                left,
                right,
            )
        if not antecedent:
            inherited_scope, antecedent = scope, local
        preceding_clauses += 1
        following = next((m for m in bounds if m.start() == last), None)
        first = following.end() if following else last
    return _rejected(start, end, "negative_boolean_relation_missing")
