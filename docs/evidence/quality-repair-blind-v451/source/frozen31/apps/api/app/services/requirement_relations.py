"""Literal relation propositions for a subsequent entailment check.

Recognized English forms are WH subjects with have/has, scalar copular
properties, explicit ``corresponds to`` mappings, and modal passive requests
bound to adjacent imperative instructions. This is deliberately not an English
parser or a support classifier. Every successful result still needs the
caller's entailment check. Unknown syntax keeps no proposition.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.services.answer_requirements import Requirement


class RelationBinding(Protocol):
    @property
    def req(self) -> Requirement: ...

    @property
    def context(self) -> str: ...

    @property
    def value(self) -> str: ...

    @property
    def premise(self) -> str: ...

    @property
    def topic(self) -> str: ...

    @property
    def start(self) -> int: ...

    @property
    def end(self) -> int: ...

    @property
    def clause_start(self) -> int: ...


_HAVE = r"(?:(?:do|does)\s+not\s+have|have|has)"
_ARGUMENT = r"\s+(?:for|on|in|under|at|with)\s+"
_NEGATIVE = re.compile(
    r"\b(?:not|never|neither|nor|cannot|formerly|previously)\b", re.I
)
_NESTED = re.compile(
    r"\b(?:of|for|by|with|whose|which|that|where|when|and|or|but)\b|['’]s\b", re.I
)


@dataclass(frozen=True)
class _Request:
    form: str
    subject: str
    predicate: str


@dataclass(frozen=True)
class _OrderedRequest:
    modal: str
    participle: str
    order: str
    condition_verb: str
    condition_object: str


@dataclass(frozen=True)
class _Imperative:
    verb: str
    object: str
    object_start: int
    object_end: int


@dataclass(frozen=True)
class _Proof:
    hypothesis: str
    left: int
    right: int
    answer_start: int
    answer_end: int


_SCOPE = re.compile(r"^\s*(?:for|in|at|on|regarding)\s+([^,;?!]+),\s*", re.I)
_SCALAR_CONTINUATION = re.compile(
    r",\s+(?:and|but)\s+(?:it|they|this|that)\s+"
    r"(?:do|does|is|are|was|were|has|have|may|must|can|should)\b",
    re.I,
)


def _scoped(text: str) -> tuple[str, str, int]:
    match = _SCOPE.match(text)
    return (
        (match.group(1), text[match.end() :], match.end()) if match else ("", text, 0)
    )


def _phrase_matches(source: str, requested: str) -> bool:
    source = _canonical(re.sub(r"['’]s\s+", " ", source), article=True)
    requested = _canonical(re.sub(r"['’]s\s+", " ", requested), article=True)
    if source == requested:
        return True
    if not source.endswith(" " + requested):
        return False
    prefix = source[: -len(requested)].strip()
    return (
        not _NESTED.search(prefix)
        and not _NEGATIVE.search(prefix)
        and not re.search(
            r"\b(?:former|previous|old|historical|retired)\b", prefix, re.I
        )
    )


def _source_sentence(context: str, start: int) -> tuple[str, int, int] | None:
    if type(start) is not int or not 0 <= start < len(context):
        return None
    boundaries = list(re.finditer(r"[.!?\n]", context[:start]))
    left = boundaries[-1].end() if boundaries else 0
    end = re.search(r"[.!?\n]", context[start:])
    right = start + end.end() if end else len(context)
    text = context[left:right]
    leading = len(text) - len(text.lstrip())
    if not _safe(text) or text.rstrip().endswith("?"):
        return None
    return text.strip(), left + leading, right


def _selected_interval(
    context: str, start: int, end: int, first: int, last: int, *, prefix: str = ""
) -> bool:
    if end != last:
        return False
    if first <= start < last:
        return _canonical(context[first:last], article=True) == _canonical(
            context[start:end], article=True
        )
    return bool(prefix and context[start:first].casefold() == prefix.casefold())


def _literal_proof(
    req: Requirement, context: str, start: int, end: int
) -> _Proof | None:
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(context)
    ):
        return None
    question_scope, question, _ = _scoped(req.original_text.strip().rstrip("?.!"))
    representation = re.fullmatch(
        r"how\s+(?:does|do)\s+(.+?)\s+represent\s+(.+)", question, re.I
    )
    identifying = re.fullmatch(
        r"(?:what|which)\s+([\w -]+?)\s+identifies\s+(.+)", question, re.I
    )
    sentence = _source_sentence(context, start)
    if sentence is None:
        return None
    text, left, right = sentence
    # These two relation forms have one source clause; a following semicolon
    # clause is not an extra argument of the selected representation/identifier.
    clause = re.split(r";", text, maxsplit=1)[0].rstrip(".!?")
    scope, body, shift = _scoped(clause)
    if question_scope and _canonical(scope) != _canonical(question_scope):
        return None
    prefix = f"For {scope}, " if scope else ""
    if representation:
        source = re.fullmatch(
            r"(.+?)\s+(?:represents|writes|encodes|records)\s+(.+?)\s+(as)\s+(.+)",
            body,
            re.I,
        )
        if source is None or (
            _canonical(source.group(1), article=True)
            != _canonical(representation.group(1), article=True)
            or _canonical(source.group(2), article=True)
            != _canonical(representation.group(2), article=True)
            or _NEGATIVE.search(source.group(1) + " " + source.group(2))
        ):
            return None
        first, last = left + shift + source.start(4), left + shift + source.end(4)
        if not _selected_interval(context, start, end, first, last, prefix="as "):
            return None
        return _Proof(
            f"{prefix}{representation.group(1)} represents "
            f"{representation.group(2)} as {source.group(4)}",
            left,
            left + len(clause),
            first,
            last,
        )
    if identifying:
        source = re.fullmatch(
            rf"(.+?)\s+(?:has|have)\s+(?:the\s+)?"
            rf"({re.escape(identifying.group(1))})\s+(.+)",
            body,
            re.I,
        )
        if source is None or (
            not _phrase_matches(source.group(1), identifying.group(2))
            or _canonical(source.group(2)) != _canonical(identifying.group(1))
            or _NEGATIVE.search(source.group(1) + " " + source.group(3))
        ):
            return None
        first, last = left + shift + source.start(3), left + shift + source.end(3)
        typed_first = left + shift + source.start(2)
        if not (
            _selected_interval(context, start, end, first, last)
            or (start == typed_first and end == last)
        ):
            return None
        return _Proof(
            f"{prefix}{source.group(3)} is the {identifying.group(1)} "
            f"that identifies {identifying.group(2)}",
            left,
            left + len(clause),
            first,
            last,
        )
    return None


def _covers_scalar(context: str, start: int, end: int, first: int, last: int) -> bool:
    return bool(
        end >= last
        and first <= start < last
        and _canonical(context[first:last], article=True)
        == _canonical(context[start:last], article=True)
        and (
            end == last
            or re.match(r"[.!?;]|,\s+(?:and|but)\b", context[last:end], re.I)
        )
    )


def _scalar_proof(
    req: Requirement, context: str, start: int, end: int
) -> _Proof | None:
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(context)
    ):
        return None
    scope, question, _ = _scoped(req.original_text.strip().rstrip("?.!"))
    requested = _request(question)
    if requested is None or requested.form != "property":
        return None
    signature = _property(requested.subject)
    sentence = _source_sentence(context, start)
    if signature is None or sentence is None:
        return None
    text, left, right = sentence
    body = text.rstrip(".!?")
    source_scope, body, shift = _scoped(body)
    if scope and _canonical(scope) != _canonical(source_scope):
        return None
    source = re.fullmatch(
        r"(?P<owner>.+?)\s+is\s+[^:;]+:\s*(?:its|their)\s+"
        r"(?P<field>.+?)\s+(?P<copula>is|are)\s+(?P<value>.+)",
        body,
        re.I,
    )
    if source:
        if _canonical(source.group("owner"), article=True) != signature[1]:
            return None
        property_text = source.group("owner") + "'s " + source.group("field")
    else:
        # Ordinary explicit properties keep their existing local-clause path.
        # This helper expands only a single colon-bound possessive antecedent.
        return None
    if _property(property_text) != signature or _canonical(
        source.group("copula")
    ) != _canonical(requested.predicate):
        return None
    value = source.group("value")
    continuation = _SCALAR_CONTINUATION.search(value)
    value = value[: continuation.start()] if continuation else value
    if not value or _NEGATIVE.search(value):
        return None
    first = left + shift + source.start("value")
    last = first + len(value)
    # A typed scalar may normalize only a nonnull span beginning exactly at the
    # full argument boundary (or after its article), never an arbitrary substring.
    if not _covers_scalar(context, start, end, first, last):
        return None
    prefix = f"For {source_scope}, " if source_scope else ""
    return _Proof(
        f"{prefix}{requested.subject} {requested.predicate} {context[start:last]}",
        left,
        right,
        start,
        last,
    )


def _mapping_question(req: Requirement) -> tuple[str, str, str] | None:
    scope, body, _ = _scoped(
        req.question if req.relation == "mapping" else req.original_text
    )
    atom = re.fullmatch(
        r"\s*(?:what|which)\s+([\w -]+?)\s+corresponds?\s+to\s+(.+?)[?.!]*\s*",
        body,
        re.I,
    )
    if atom is None:
        return None
    output, target = atom.groups()
    if req.relation == "mapping":
        original_scope, original, _ = _scoped(req.original_text)
        compound = re.fullmatch(
            r"\s*(?:what|which)\s+([\w -]+?)\s+corresponds?\s+to\s+"
            r"(?:the\s+)?(?:(?:two|both|2)\s+)?([\w-]+s)\s+([\w-]+)\s+and\s+([\w-]+)[?.!]*\s*",
            original,
            re.I,
        )
        if compound is None or (
            _canonical(scope) != _canonical(original_scope)
            or _canonical(output) != _canonical(compound.group(1))
            or _canonical(target)
            not in {
                _canonical(compound.group(2)[:-1] + " " + compound.group(3)),
                _canonical(compound.group(2)[:-1] + " " + compound.group(4)),
            }
        ):
            return None
    elif re.search(r"\b(?:and|or|but)\b", target, re.I):
        return None
    return scope, output, target


def _production_proof(
    req: Requirement, context: str, start: int, end: int
) -> _Proof | None:
    requested = _mapping_question(req)
    sentence = _source_sentence(context, start)
    if (
        requested is None
        or sentence is None
        or type(end) is not int
        or not start < end <= len(context)
    ):
        return None
    request_scope, output, target = requested
    text, left, right = sentence
    body = text.rstrip(".!?")
    source_scope, body, shift = _scoped(body)
    if request_scope and _canonical(source_scope) != _canonical(request_scope):
        return None
    output_words = output.split()
    head = output_words[-1]
    if head.endswith("s") and not head.endswith(("ss", "us", "is", "ies", "ves")):
        head = head[:-1]
    # A source namespace may discharge only identical leading output modifiers.
    modifiers = " ".join(output_words[:-1])
    if source_scope and _canonical(modifiers) == _canonical(source_scope):
        modifiers = ""
    source_type = " ".join(filter(None, (modifiers, head)))
    chunks = list(re.finditer(r"[^;]+", body))
    chosen = None
    for chunk in chunks:
        clause = chunk.group().strip()
        source = re.fullmatch(
            rf"(?P<input>.+?)\s+produces\s+(?P<type>{re.escape(source_type)})\s+(?P<value>.+)",
            clause,
            re.I,
        )
        if (
            source is None
            or _NEGATIVE.search(clause)
            or _UNRESOLVED_CONDITION.search(clause)
        ):
            return None
        offset = (
            left
            + shift
            + chunk.start()
            + len(chunk.group())
            - len(chunk.group().lstrip())
        )
        first, last = offset + source.start("value"), offset + source.end("value")
        if _canonical(source.group("input"), article=True) == _canonical(
            target, article=True
        ) and (
            _selected_interval(context, start, end, first, last)
            or (start == offset + source.start("type") and end == last)
        ):
            chosen = source.group("type"), source.group("value"), first, last
    if chosen is None:
        return None
    prefix = f"For {source_scope}, " if source_scope else ""
    return _Proof(
        f"{prefix}{chosen[0]} {chosen[1]} corresponds to {target}",
        left,
        right,
        chosen[2],
        chosen[3],
    )


_UNRESOLVED_CONDITION = re.compile(
    r"\b(?:before|after|until|if|unless|when|while|although|instead|except)\b", re.I
)


def _ordered_request(question: str) -> _OrderedRequest | None:
    if not _safe(question):
        return None
    match = re.fullmatch(
        r"\s*what\s+(must|should)\s+be\s+([\w-]+)\s+(before|after)\s+"
        r"([\w-]+ing)\s+(.+?)[?.!]*\s*",
        question,
        re.I,
    )
    if match is None:
        return None
    modal, participle, order, condition_verb, condition_object = match.groups()
    if (
        _NEGATIVE.search(condition_object)
        or _UNRESOLVED_CONDITION.search(condition_object)
        or re.search(r"[.!?;\n]|\b(?:and|or|but)\b", condition_object, re.I)
    ):
        return None
    return _OrderedRequest(
        modal, participle, order.casefold(), condition_verb, condition_object
    )


def _regular_forms(verb: str) -> tuple[str, str]:
    """Bounded regular morphology; no lexical/domain aliases or irregulars."""
    verb = verb.casefold()
    if verb.endswith("e"):
        return verb + "d", verb[:-1] + "ing"
    if len(verb) > 1 and verb.endswith("y") and verb[-2] not in "aeiou":
        return verb[:-1] + "ied", verb + "ing"
    vowels = re.findall(r"[aeiou]+", verb)
    if (
        len(verb) >= 3
        and len(vowels) == 1
        and verb[-1] not in "aeiouwxy"
        and verb[-2] in "aeiou"
        and verb[-3] not in "aeiou"
    ):
        verb += verb[-1]
    return verb + "ed", verb + "ing"


def _imperative(text: str, first: int) -> _Imperative | None:
    if text.rstrip().endswith("?"):
        return None
    body = text.rstrip(".!?; ")
    if not _safe(body) or _NEGATIVE.search(body) or _UNRESOLVED_CONDITION.search(body):
        return None
    match = re.fullmatch(r"([^\W\d_][\w-]*)\s+(.+)", body)
    if match is None:
        return None
    verb, object_text = match.groups()
    # An optional second positive instruction remains in the premise. Do not
    # mistake a coordinated noun phrase or a negative clause for that form.
    continuation = re.search(r"\s+and\s+([^\W\d_][\w-]*)\s+(.+)$", object_text)
    if continuation:
        if continuation.group(1).casefold() in {
            "the",
            "a",
            "an",
            "this",
            "that",
            "these",
            "those",
            "it",
            "they",
            "we",
            "you",
            "he",
            "she",
            "i",
            "do",
            "not",
            "never",
        }:
            return None
        object_text = object_text[: continuation.start()]
    if re.search(
        r"[,;:]|\b(?:is|are|was|were|must|should|can|may|and|or|but)\b",
        object_text,
        re.I,
    ):
        return None
    return _Imperative(
        verb,
        object_text,
        first + match.start(2),
        first + match.start(2) + len(object_text),
    )


def _instruction_pair(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int, _Imperative] | None:
    requested = _ordered_request(req.original_text)
    if (
        requested is None
        or type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(context)
        or re.search(r"[.!?;\n]", context[start:end])
    ):
        return None
    sentences = []
    for match in re.finditer(r"[^.!?;\n]+[.!?;]?", context):
        first = match.start() + len(match.group()) - len(match.group().lstrip())
        last = match.end()
        sentences.append((first, last))
    for index, (first, last) in enumerate(sentences):
        if not first <= start < end <= last:
            continue
        other_index = index + (1 if requested.order == "before" else -1)
        if not 0 <= other_index < len(sentences):
            return None
        other_first, other_last = sentences[other_index]
        left, right = min(first, other_first), max(last, other_last)
        gap = context[min(last, other_last) : max(first, other_first)]
        if gap.strip() or re.search(r"\n\s*\n", gap):
            return None
        action = _imperative(context[first:last], first)
        condition = _imperative(context[other_first:other_last], other_first)
        if (
            action is None
            or condition is None
            or not action.object_start <= start < end <= action.object_end
            or _canonical(action.object, article=True)
            != _canonical(context[start:end], article=True)
            or _regular_forms(action.verb)[0] != requested.participle.casefold()
            or _regular_forms(condition.verb)[1] != requested.condition_verb.casefold()
            or _canonical(condition.object, article=True)
            != _canonical(requested.condition_object, article=True)
        ):
            return None
        return left, right, action
    return None


def _safe(text: str) -> bool:
    return not any(
        unicodedata.category(char).startswith("C") and char not in "\t\r\n"
        for char in text
    )


def _canonical(text: str, *, article: bool = False) -> str:
    if article:
        text = re.sub(r"^(?:the|a|an)\s+", "", text.strip(), flags=re.I)
    return " ".join(text.casefold().split())


def _request(question: str) -> _Request | None:
    if not _safe(question):
        return None
    body = question.strip().rstrip("?.!").strip()
    # Match the complete question: no unparsed condition or conjunct is dropped.
    subject = re.fullmatch(
        rf"(?:which|what)\s+([\w\s-]+?)\s+({_HAVE}\s+.+)", body, re.I
    )
    if subject:
        return _Request("subject", subject.group(1), subject.group(2))
    mapping = re.fullmatch(
        r"(?:which|what)\s+([\w\s-]+?)\s+(corresponds?\s+to\s+.+)", body, re.I
    )
    if mapping:
        return _Request("mapping", mapping.group(1), mapping.group(2))
    scalar = re.fullmatch(r"(?:what|which)\s+(is|are)\s+(.+)", body, re.I)
    if scalar and _property(scalar.group(2)):
        return _Request("property", scalar.group(2), scalar.group(1))
    return None


def _property(text: str) -> tuple[str, str, str] | None:
    """Compare complete field/owner/argument slots, not bags of named words."""
    text = text.strip()
    # Identity forms already belong to the existing identity dispatcher.
    if re.match(r"(?:the\s+)?name\s+of\b", text, re.I):
        return None
    possessive = re.fullmatch(r"(.+?)['’]s\s+(.+)", text, re.I)
    if possessive:
        owner, field = possessive.groups()
        attribute = re.split(
            r"\s+(?:of|for|on|in|under|at|with)\s+", field, maxsplit=1, flags=re.I
        )[0]
        argument = field[len(attribute) :].strip()
    else:
        stem = re.split(_ARGUMENT, text, maxsplit=1, flags=re.I)[0]
        argument = text[len(stem) :].strip()
        of_form = re.fullmatch(r"(.+?)\s+of\s+(.+)", stem, re.I)
        if of_form is None:
            return None
        attribute, owner = of_form.groups()
    # Nested ownership is outside this grammar; never flatten it into an owner.
    if _NESTED.search(owner) or re.search(r"['’]s\b|\bof\b", attribute, re.I):
        return None
    if _NEGATIVE.search(owner + " " + attribute):
        return None
    return (
        _canonical(attribute, article=True),
        _canonical(owner, article=True),
        _canonical(argument),
    )


def question_topic(question: str) -> str | None:
    """Expose literal request scope without importing the requirement planner."""
    if not _safe(question):
        return None
    _, question, _ = _scoped(question)
    ordered = _ordered_request(question)
    if ordered:
        return ordered.condition_object
    representation = re.fullmatch(
        r"\s*how\s+(?:does|do)\s+(.+?)\s+represent\s+.+", question, re.I
    )
    identifying = re.fullmatch(
        r"\s*(?:what|which)\s+[\w -]+?\s+identifies\s+(.+?)[?.!]*\s*", question, re.I
    )
    if representation:
        return representation.group(1)
    if identifying:
        return identifying.group(1)
    request = _request(question)
    if request is None:
        return None
    if request.form == "mapping":
        return re.sub(r"^corresponds?\s+to\s+", "", request.predicate, flags=re.I)
    return request.subject


def relation_source_range(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int] | None:
    """Return an exact local instruction range when a recognized condition binds."""
    pair = _instruction_pair(req, context, start, end)
    if pair:
        return pair[0], pair[1]
    proof = (
        _literal_proof(req, context, start, end)
        or _scalar_proof(req, context, start, end)
        or _production_proof(req, context, start, end)
    )
    return (proof.left, proof.right) if proof else None


def relation_answer_range(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int] | None:
    """Return only an unambiguous full scalar at the raw candidate's boundary."""
    proof = _scalar_proof(req, context, start, end)
    if proof and proof.answer_end < end:
        return proof.answer_start, proof.answer_end
    return None


def _local_clause(binding: RelationBinding) -> tuple[str, int] | None:
    if (
        type(binding.start) is not int
        or type(binding.end) is not int
        or type(binding.clause_start) is not int
        or not 0
        <= binding.clause_start
        <= binding.start
        < binding.end
        <= len(binding.context)
        or binding.context[binding.start : binding.end] != binding.value
        or re.search(r"[.!?;\n]", binding.value)
    ):
        return None
    # Read original code-point coordinates, never offsets in a normalized premise.
    prefix = binding.context[binding.clause_start : binding.start]
    boundaries = list(re.finditer(r"[.!?;\n]", prefix))
    first = binding.clause_start + (boundaries[-1].end() if boundaries else 0)
    boundary = re.search(r"[.!?;\n]", binding.context[binding.end :])
    last = binding.end + boundary.start() if boundary else len(binding.context)
    clause = binding.context[first:last]
    leading = len(clause) - len(clause.lstrip())
    clause = clause.strip()
    if not _safe(clause):
        return None
    return clause, first + leading


def _selected(
    binding: RelationBinding, clause_start: int, source: re.Match[str], group: str
) -> bool:
    first, last = source.span(group)
    return (
        clause_start + first <= binding.start < binding.end <= clause_start + last
        and _canonical(source.group(group), article=True)
        == _canonical(binding.value, article=True)
    )


def _subject_hypothesis(
    binding: RelationBinding, request: _Request, clause: str, first: int
) -> tuple[str | None, str | None]:
    source = re.fullmatch(
        rf"(?P<value>.+?)\s+(?P<predicate>{_HAVE}\s+.+)", clause, re.I
    )
    if source is None or not _selected(binding, first, source, "value"):
        return None, "selected_subject_is_not_complete_argument"
    subject = _canonical(source.group("value"), article=True)
    noun_class = _canonical(request.subject, article=True)
    if (
        not (subject == noun_class or subject.endswith(" " + noun_class))
        or _NESTED.search(subject)
        or _NEGATIVE.search(subject)
        or _canonical(source.group("predicate")) != _canonical(request.predicate)
    ):
        return None, "requested_subject_relation_missing"
    return f"{binding.value} {request.predicate}", None


def _property_hypothesis(
    binding: RelationBinding, request: _Request, clause: str, first: int
) -> tuple[str | None, str | None]:
    source = re.fullmatch(
        r"(?P<property>.+?)\s+(?P<copula>is|are)\s+(?P<value>.+)", clause, re.I
    )
    if source is None:
        return None, "requested_property_relation_missing"
    # Quotes can wrap an exact scalar; they cannot conceal a larger noun phrase.
    start, end = source.span("value")
    scalar = source.group("value")
    if len(scalar) > 1 and (scalar[0], scalar[-1]) in {
        ("'", "'"),
        ('"', '"'),
        ("‘", "’"),
        ("“", "”"),
    }:
        start, end = start + 1, end - 1
    if (
        binding.start != first + start
        or binding.end != first + end
        or _NEGATIVE.search(scalar)
        or _property(source.group("property")) != _property(request.subject)
        or _canonical(source.group("copula")) != _canonical(request.predicate)
    ):
        return None, "requested_property_not_selected_argument"
    return f"{request.subject} {request.predicate} {binding.value}", None


def _mapping_hypothesis(
    binding: RelationBinding, request: _Request, clause: str, first: int
) -> tuple[str | None, str | None]:
    source = re.fullmatch(
        r"(?P<subject>.+?)\s+(?P<predicate>corresponds?\s+to\s+.+)", clause, re.I
    )
    if source is None or _canonical(source.group("predicate")) != _canonical(
        request.predicate
    ):
        return None, "requested_mapping_direction_missing"
    subject = source.group("subject")
    typed = re.fullmatch(
        rf"(?:the\s+)?{re.escape(request.subject)}\s+(?P<value>.+)", subject, re.I
    )
    if typed is None or _NEGATIVE.search(subject):
        return None, "requested_mapping_type_missing"
    if not (
        _selected(binding, first, source, "subject")
        or _selected(binding, first, typed, "value")
    ):
        return None, "selected_mapping_is_not_complete_argument"
    return f"{subject} {request.predicate}", None


def _ordered_hypothesis(
    binding: RelationBinding, ordered: _OrderedRequest
) -> tuple[str | None, str | None]:
    pair = _instruction_pair(binding.req, binding.context, binding.start, binding.end)
    if (
        pair is None
        or type(binding.clause_start) is not int
        or not 0 <= binding.clause_start <= pair[0]
        or binding.context[binding.start : binding.end] != binding.value
        or binding.context[pair[0] : pair[1]] not in binding.premise
    ):
        return None, "ordered_imperative_condition_missing"
    return (
        f"{pair[2].object} {ordered.modal} be {ordered.participle} "
        f"{ordered.order} {ordered.condition_verb} {ordered.condition_object}",
        None,
    )


def relation_hypothesis(binding: RelationBinding) -> tuple[str | None, str | None]:
    """Bind one selected local source argument; never accept factual support."""
    ordered = _ordered_request(binding.req.original_text)
    if ordered:
        return _ordered_hypothesis(binding, ordered)
    proof = (
        _literal_proof(binding.req, binding.context, binding.start, binding.end)
        or _scalar_proof(binding.req, binding.context, binding.start, binding.end)
        or _production_proof(binding.req, binding.context, binding.start, binding.end)
    )
    if proof:
        if (
            type(binding.clause_start) is not int
            or not 0 <= binding.clause_start <= proof.left
            or binding.context[binding.start : binding.end] != binding.value
            or binding.context[proof.left : proof.right] not in binding.premise
            or binding.end != proof.answer_end
        ):
            return None, "literal_relation_proof_missing"
        return proof.hypothesis, None
    request_scope, body, _ = _scoped(binding.req.original_text)
    request = _request(body)
    if request is None:
        return None, "unsupported_question_transformation"
    local = _local_clause(binding)
    if local is None:
        return None, "invalid_relation_source_coordinates"
    clause, first = local
    source_scope, clause, shift = _scoped(clause)
    first += shift
    if request_scope and _canonical(source_scope) != _canonical(request_scope):
        return None, "requested_relation_scope_missing"
    if request.form == "subject":
        result = _subject_hypothesis(binding, request, clause, first)
    elif request.form == "property":
        result = _property_hypothesis(binding, request, clause, first)
    else:
        result = _mapping_hypothesis(binding, request, clause, first)
    if result[0] and source_scope:
        return f"For {source_scope}, {result[0]}", None
    return result
