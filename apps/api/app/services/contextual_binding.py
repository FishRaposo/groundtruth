"""Source-context binding before mandatory NLI; never a support decision.

Only finite relation-preserving transformations produce hypotheses. All premise
and answer text remains an exact source slice; no context is inserted into a
model premise. The default clause-bound profile is deliberately unchanged.
"""

from __future__ import annotations

import re

from app.services.answer_requirements import Requirement
from app.services.requirement_binding import SupportClaim, support_claim

_TIME = r"(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?)"
_SENTENCE = re.compile(r"(?:[^.!?\n]|\.(?<=\d\.)(?=\d))+(?:[.!?](?!\d)|$)")
_SCOPE = re.compile(r"^\s*(?:for|in|at|regarding)\s+([^,]+),\s*", re.I)


def _text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,;?.!")


def _source_window(req, context, start, end):
    sentences = []
    for match in _SENTENCE.finditer(context):
        left = match.start() + len(match.group()) - len(match.group().lstrip())
        if left < match.end():
            sentences.append((left, match.end()))
    containing = [i for i, (a, b) in enumerate(sentences) if a <= start < end <= b]
    if len(containing) != 1:
        return None
    index = containing[0]
    left, right = sentences[index]
    # Named source scope must occur in the same short contiguous context, not
    # in an unrelated later paragraph. Unsupported long-range anaphora refuses.
    first = max(0, index - 2)
    window_left = sentences[first][0]
    premise = context[window_left:right]
    anchors = {a.casefold() for a in req.anchors}
    present = set(re.findall(r"[\w-]+", premise.casefold()))
    if anchors and anchors.isdisjoint(present):
        return None
    if len(premise) > 900:
        return None
    return window_left, right, left, right


def _request(req):
    question = _text(req.question)
    scope = _SCOPE.match(question)
    return question[scope.end() :] if scope else question


def _duration(req, question, value, clause):
    if not re.fullmatch(rf"\d+(?:\.\d+)?\s+{_TIME}", value, re.I):
        return None
    if not re.search(
        r"\b(?:lasts?|takes?|duration|interval|minutes?|hours?|seconds?)\b",
        clause,
        re.I,
    ):
        return None
    for pattern in (
        r"how\s+long\s+is\s+(.+)",
        r"how\s+long\s+(?:does|will)\s+(.+?)\s+(?:last|take)",
        r"what\s+is\s+the\s+(?:length|duration)\s+of\s+(.+)",
    ):
        match = re.fullmatch(pattern, question, re.I)
        if match:
            return f"{match.group(1)} lasts {value}"
    match = re.fullmatch(
        r"what\s+(\w+\s+interval)\s+does\s+(.+?)\s+specify", question, re.I
    )
    return (
        f"{match.group(2)} specifies a {match.group(1)} of {value}" if match else None
    )


def _quantity(question, value, clause):
    if not re.fullmatch(r"\d+(?:\.\d+)?(?:\s+[\w-]+){0,3}", value):
        return None
    match = re.fullmatch(r"how\s+many\s+(.+?)\s+(are\s+.+|belong\s+.+)", question, re.I)
    if match:
        noun, predicate = match.groups()
        if re.search(
            r"\b(?:minutes?|hours?|seconds?)\b", value, re.I
        ) and not re.search(r"\b(?:minutes?|hours?|seconds?)\b", noun, re.I):
            return None
        return f"{value} {noun} {predicate}"
    match = re.fullmatch(
        r"(?:tell\s+me\s+|what\s+is\s+)?(?:the\s+)?(.+?)\s+count\s+for\s+(.+)",
        question,
        re.I,
    )
    return (
        f"The {match.group(1)} count for {match.group(2)} is {value}" if match else None
    )


def _boolean(question, clause):
    negative = bool(
        re.search(r"\b(?:not|never|cannot|forbidden|prohibited)\b", clause, re.I)
    )
    match = re.fullmatch(r"(may|can|must|should)\s+(.+?)\s+be\s+(.+)", question, re.I)
    if match:
        modal, subject, predicate = match.groups()
        # A selected prohibition must refer to the requested action. Merely
        # sharing an object does not prove a permission or its opposite.
        verb = predicate.split()[0].casefold()
        stem = verb[:-1] if verb.endswith("d") else verb
        if not any(w.startswith(stem) for w in re.findall(r"\w+", clause.casefold())):
            return None
        relation = "must not" if negative else modal.casefold()
        return f"{subject} {relation} be {predicate}"
    match = re.fullmatch(r"(may|can|must|should)\s+(?:I|we)\s+(.+)", question, re.I)
    if match:
        modal, action = match.groups()
        verb = action.split()[0]
        if re.search(rf"\b{re.escape(verb)}\b", clause, re.I):
            relation = {
                "may": "permitted",
                "can": "permitted",
                "must": "required",
                "should": "recommended",
            }[modal.casefold()]
            return f"It is {'not ' if negative else ''}{relation} to {action}"
    return None


def _passive_choice(question, value, clause, local_start):
    match = re.fullmatch(
        r"(?:which|what)\s+([\w -]+?)\s+(is|are)\s+"
        r"(used|chosen|selected|needed|required)\s+(.+)",
        question,
        re.I,
    )
    if not match:
        return None
    excluded = re.search(r"\b(?:instead\s+of|rather\s+than|not)\b", clause, re.I)
    if excluded and local_start >= excluded.end():
        return None
    return f"{value} {match.group(2)} {match.group(3)} {match.group(4)}"


def _hypothesis(req, question, value, clause, local_start):
    if req.kind == "duration":
        return _duration(req, question, value, clause)
    if req.kind == "quantity":
        return _quantity(question, value, clause)
    if req.kind == "boolean":
        return _boolean(question, clause)
    if req.kind in {"owner", "deputy"}:
        match = re.fullmatch(
            r"who\s+is\s+the\s+(lead|deputy)\s+for\s+(.+)", question, re.I
        )
        if match:
            return f"{value} is the {match.group(1)} for {match.group(2)}"
    return _passive_choice(question, value, clause, local_start)


def contextual_support_claim(
    req: Requirement, context: str, start: int, end: int
) -> SupportClaim:
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(context)
    ):
        return SupportClaim(None, "", "", start, end, "invalid_candidate_offsets")
    legacy = support_claim(req, context, start, end)
    if legacy.rejection is None:
        return legacy
    window = _source_window(req, context, start, end)
    value = context[start:end]
    if window is None:
        return SupportClaim(
            None, value, value, start, end, "contextual_subject_unresolved"
        )
    left, right, clause_start, clause_end = window
    clause = context[clause_start:clause_end]
    question = _request(req)
    hypothesis = _hypothesis(req, question, value, clause, start - clause_start)
    if not hypothesis:
        return SupportClaim(
            None, clause, value, start, end, "contextual_relation_unresolved"
        )
    return SupportClaim(
        hypothesis,
        context[left:right],
        value,
        start,
        end,
        None,
        clause_start,
        clause_end,
        premise_start=left,
        premise_end=right,
    )
