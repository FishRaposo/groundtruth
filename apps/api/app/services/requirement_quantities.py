"""Bounded literal count propositions for a later entailment check.

These checks never establish factual support. They bind a selected count to a
local subject, counted noun and relation; unfamiliar grammar yields no claim.
The module deliberately does not import the binding dispatcher.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.services.answer_requirements import Requirement


class QuantityBinding(Protocol):
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


_CARDINAL = (
    r"(?:\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)"
)
_LIMIT = r"(?:maximum|limit|up\s+to|at\s+most|no\s+more\s+than)"
_NEGATIVE = r"\b(?:not|never|neither|nor|cannot|no\s+longer|formerly|previously)\b"


def _canonical(text: str) -> str:
    text = re.sub(r"^(?:the|a|an|each)\s+", "", text.strip(), flags=re.I)
    return " ".join(text.casefold().split())


def _noun_pattern(noun: str) -> str:
    words = noun.split()
    if not words:
        return r"(?!)"
    last = words[-1]
    stem = last[:-1] if last.endswith("s") and not last.endswith("ss") else last
    return r"\s+".join(map(re.escape, words[:-1] + [stem])) + r"s?"


def _local_clause(binding: QuantityBinding) -> tuple[str, str] | None:
    if (
        type(binding.start) is not int
        or type(binding.end) is not int
        or not 0
        <= binding.clause_start
        <= binding.start
        < binding.end
        <= len(binding.context)
        or binding.context[binding.start : binding.end] != binding.value
    ):
        return None
    prefix = binding.context[binding.clause_start : binding.start]
    # A supplied premise may include an antecedent, but local offsets remain
    # offsets into the original context, never into reconstructed prose.
    boundaries = list(
        re.finditer(r"[.!?;\n]|\b(?:and|but|whereas|while)\b", prefix, re.I)
    )
    if boundaries:
        prefix = prefix[boundaries[-1].end() :]
    suffix = re.split(
        r"[.!?;\n]|\b(?:and|but|whereas|while)\b",
        binding.context[binding.start :],
        maxsplit=1,
        flags=re.I,
    )[0]
    return prefix.strip(), suffix.strip()


def _active_request(question: str) -> re.Match[str] | None:
    return re.search(
        r"\bhow\s+many\s+.+?\s+(?:does|do|did)\s+(.+?)\s+([\w-]+)\s*[?.!]*$",
        question,
        re.I,
    )


def _passive_request(question: str) -> re.Match[str] | None:
    return re.search(
        r"\bhow\s+many\s+.+?\s+(?P<relation>(?:are|is)\s+"
        r"(?P<verb>[\w-]+)\s+(?:to|for|by))\s+(?P<subject>.+?)[?.!]*$",
        question,
        re.I,
    )


def _remaining_request(question: str) -> re.Match[str] | None:
    return re.search(
        r"\bhow\s+many\s+(?P<noun>[\w -]+?)\s+remain(?:s)?"
        r"(?:\s+[^?!.]+)?\s*[?.!]*$",
        question,
        re.I,
    )


def _acceptance_request(question: str) -> re.Match[str] | None:
    return re.search(
        r"\bhow\s+many\s+(?P<noun>[\w -]+?)\s+(?:may|can)\s+"
        r"(?P<subject>.+?)\s+accept\s*[?.!]*$",
        question,
        re.I,
    )


def question_relation(question: str) -> str | None:
    """Expose a literal requested count verb without importing the planner."""
    if _remaining_request(question):
        return "quantity:remain"
    if _acceptance_request(question):
        return "maximum_count:accept"
    active = _active_request(question)
    if active:
        return f"quantity:{active.group(2).casefold()}"
    passive = _passive_request(question)
    return f"quantity:{passive.group('verb').casefold()}" if passive else None


def _request_verb(req: Requirement) -> tuple[str, str] | None:
    request = _active_request(req.original_text)
    if request:
        return request.group(1), request.group(2).casefold()
    return None


def _verb_forms(verb: str) -> set[str]:
    if verb == "have":
        return {"have", "has"}
    if verb.endswith("y") and len(verb) > 1 and verb[-2] not in "aeiou":
        return {verb, verb[:-1] + "ies"}
    return {
        verb,
        verb + ("es" if verb.endswith(("s", "sh", "ch", "x", "z", "o")) else "s"),
    }


def _subject_matches(subject: str, topic: str) -> bool:
    return _canonical(subject) == _canonical(topic)


# Current containment/cardinality readings can be proposed to NLI together;
# ownership, receipt/transfer and permission are deliberately separate relations.
_CONTAINER_FORMS = frozenset(
    {
        "has",
        "have",
        "holds",
        "hold",
        "contains",
        "contain",
        "carries",
        "carry",
        "includes",
        "include",
        "consists of",
        "consist of",
    }
)
_CONTAINER_REQUESTS = frozenset({"have", "hold", "contain", "carry", "include", "use"})
_SUBJECT_RELATIONAL = frozenset(
    "of for by with under whose which that and but while is are was were has have "
    "can does deputy owner coordinator backup former previous retired exception "
    "alternative other standard ordinary normal current historical".split()
)


def _count_subject_matches(subject: str, topic: str) -> bool:
    """Allow descriptive modifiers before the same named subject's final head.

    This proposes an entity reading to NLI, never certifies coreference. Ordered
    request words, exact head, condition and proper-name tokens remain required.
    Relational/possessive or differently named subjects cannot become aliases.
    """
    if _subject_matches(subject, topic):
        return True
    source = re.sub(r"^(?:the|a|an|each)\s+", "", subject.strip(), flags=re.I)
    expected = _canonical(topic).split()
    observed = source.split()
    if len(expected) < 2 or not observed or observed[-1].casefold() != expected[-1]:
        return False
    index = 0
    for word in observed:
        if index < len(expected) and word.casefold() == expected[index]:
            index += 1
            continue
        if (
            index != len(expected) - 1
            or not re.fullmatch(r"[a-z][a-z-]*", word)
            or word.casefold() in _SUBJECT_RELATIONAL
        ):
            return False
    return index == len(expected)


def quantity_hypothesis(binding: QuantityBinding) -> tuple[str | None, str | None]:
    """Return a relation-preserving proposition, requiring separate NLI support."""
    req = binding.req
    if req.kind == "quantity" and req.relation == "allocation":
        frame = _allocation_frame(req, binding.context, binding.start, binding.end)
        if frame is None or binding.value != frame[0].group("amount"):
            return None, "allocation_subject_unit_or_relation_missing"
        source = frame[0]
        return f"The allocation for {source.group('subject')} is {binding.value}", None
    known_relation = req.relation in {
        "quantity",
        "maximum_count",
        "operand_count",
        "capacity_count",
    }
    explicit_relation = req.relation == question_relation(req.original_text)
    if req.kind != "quantity" or not (known_relation or explicit_relation):
        return None, "unsupported_quantity_relation"
    local = _local_clause(binding)
    if local is None:
        return None, "invalid_quantity_offsets"
    prefix, suffix = local
    if req.relation == "quantity:remain":
        return _remaining_hypothesis(binding, prefix, suffix)
    if re.search(_NEGATIVE, prefix + " " + suffix, re.I):
        return None, "selected_quantity_is_negated_or_historical"
    if req.relation in {"capacity_count", "maximum_count", "maximum_count:accept"}:
        capacity = _capacity_hypothesis(binding, prefix, suffix)
        if capacity is not None:
            return capacity
    return _ordinary_count_hypothesis(binding, prefix, suffix)


def _allocation_unit_consumed(unit: str) -> bool:
    """A bounded compound closes at its first literal plural count noun.

    Arbitrary prose after that head is never another unit modifier. Unfamiliar
    singular units and complex noun phrases remain unresolved; no unit is guessed
    or substituted. Symbols are recognized only when explicitly source-stated.
    """
    words = unit.split()
    symbols = {"g", "kg", "mg", "m", "cm", "mm", "l", "ml"}
    if len(words) == 1 and words[0].casefold() in symbols:
        return True
    for index, word in enumerate(words):
        if word.casefold().endswith("s") and not word.casefold().endswith("ss"):
            return index == len(words) - 1
        if not re.fullmatch(r"[a-z]+(?:-[a-z]+)*", word, re.I):
            return False
    return False


def _allocation_frame(req: Requirement, context: str, start: int, end: int):
    if req.kind != "quantity" or req.relation != "allocation":
        return None
    left = max((m.end() for m in re.finditer(r"[.!?;\n]", context[:start])), default=0)
    ending = re.search(r"[.!?;\n]", context[end:])
    right = end + ending.start() if ending else len(context)
    text = context[left:right]
    leading = len(text) - len(text.lstrip())
    frame = re.fullmatch(
        rf"(?:the\s+)?allocation\s+for\s+(?P<subject>.+?)\s+is\s+"
        rf"(?P<amount>{_CARDINAL}\s+(?P<unit>[a-z][a-z-]*(?:\s+[a-z][a-z-]*){{0,3}}))\s*",
        text.strip(),
        re.I,
    )
    if frame is None or not _allocation_unit_consumed(frame.group("unit")):
        return None

    def canonical(value: str) -> str:
        return _canonical(re.sub(r"^(?:one|single)\s+", "", value.strip(), flags=re.I))

    if canonical(frame.group("subject")) != canonical(req.topic):
        return None
    if any(
        word.casefold()
        in _SUBJECT_RELATIONAL
        | _COUNT_MODIFIER_BAD
        | {
            "if",
            "when",
            "unless",
            "except",
            "only",
            "provided",
            "after",
            "before",
            "until",
            "during",
            "must",
            "may",
            "shall",
            "would",
            "should",
        }
        for word in frame.group("unit").split()
    ):
        return None
    first, last = frame.span("amount")
    first += left + leading
    last += left + leading
    return (frame, first, last) if first <= start < end <= last else None


def allocation_answer_range(
    req: Requirement, context: str, start: int, end: int
) -> tuple[int, int] | None:
    """Copy the declared amount and unit only from one exact allocation frame."""
    frame = _allocation_frame(req, context, start, end)
    return (frame[1], frame[2]) if frame else None


def _ordinary_count_hypothesis(
    binding: QuantityBinding, prefix: str, suffix: str
) -> tuple[str | None, str | None]:
    req = binding.req
    noun = req.attribute.strip()
    if noun.casefold() in {"", "count", "quantity"}:
        return None, "quantity_attribute_missing"
    noun_pattern = _noun_pattern(noun)
    selected = re.fullmatch(
        rf"(?P<number>{_CARDINAL})(?:\s+{noun_pattern})?", binding.value, re.I
    )
    if selected is None:
        return None, "quantity_unit_mismatch"
    number = selected.group("number")
    counted = re.match(
        rf"{re.escape(number)}\s+(?P<noun>{noun_pattern})\b", suffix, re.I
    )
    counted_text = counted.group(0) if counted else None
    trailing = (
        suffix[counted.end() :].strip() if counted else suffix[len(number) :].strip()
    )
    passive = _passive_request(req.original_text)
    if trailing and passive is None:
        return None, "quantity_has_unbound_unit_or_qualifier"
    maximum = req.relation == "maximum_count"
    observed_limit = bool(re.search(rf"\b{_LIMIT}\b", prefix, re.I))
    if maximum != observed_limit:
        return None, "quantity_limit_relation_mismatch"

    return _relation_hypothesis(binding, prefix, number, counted_text, passive)


_ACCEPTANCE_BOUND = r"(?:at\s+most|up\s+to|no\s+more\s+than|a\s+maximum\s+of)"


def _capacity_subject_matches(subject: str, topic: str) -> bool:
    if _count_subject_matches(subject, topic):
        return True
    # A literal session head can specialize the requested activity only when
    # every requested entity/profile word matches. Keep that head in the claim.
    session = re.fullmatch(r"(.+?)\s+session", subject, re.I)
    return bool(session and _count_subject_matches(session.group(1), topic))


def _capacity_request_rejection(binding: QuantityBinding) -> str | None:
    req = binding.req
    if req.relation == "capacity_count" and not re.search(
        r"\bcapacity\b", req.original_text, re.I
    ):
        return "capacity_request_missing"
    if req.relation == "maximum_count" and _request_verb(req):
        return "requested_actual_count_is_not_capacity"
    modal = _acceptance_request(req.original_text)
    if req.relation == "maximum_count:accept" and (
        modal is None
        or not _subject_matches(
            re.sub(r"^one\s+", "", modal.group("subject"), flags=re.I), binding.topic
        )
        or _canonical(modal.group("noun")) != _canonical(req.attribute)
    ):
        return "requested_acceptance_subject_or_unit_mismatch"
    return None


def _capacity_unit_rejection(req: Requirement, source_noun: str) -> str | None:
    noun = req.attribute.strip()
    if noun:
        if not re.fullmatch(_noun_pattern(noun), source_noun, re.I):
            return "capacity_unit_mismatch"
    elif req.relation != "capacity_count":
        return "quantity_attribute_missing"
    if any(
        word.casefold() in _COUNT_MODIFIER_BAD
        or word.casefold()
        in {"for", "from", "by", "under", "with", "per", "in", "at", "or", "plus"}
        or re.fullmatch(_CARDINAL, word, re.I)
        for word in source_noun.split()
    ):
        return "capacity_unbound_unit_or_qualifier"
    return None


def _capacity_hypothesis(
    binding: QuantityBinding,
    prefix: str,
    suffix: str,
) -> tuple[str | None, str | None] | None:
    req = binding.req
    request_error = _capacity_request_rejection(binding)
    if request_error:
        return None, request_error
    modal = _acceptance_request(req.original_text)
    local = (prefix + " " if prefix else "") + suffix
    match = re.fullmatch(
        rf"(?P<subject>.+?)\s+(?P<predicate>"
        rf"(?:(?:may|can)\s+accept|accepts?)\s+(?P<bound>{_ACCEPTANCE_BOUND})|"
        r"has\s+(?:a\s+)?(?:maximum\s+)?capacity\s+of)\s+"
        rf"(?P<number>{_CARDINAL})\s+(?P<noun>[\w-]+(?:\s+[\w-]+){{0,3}})",
        local,
        re.I,
    )
    if match is None:
        # Existing explicit maximum-count grammars keep their old contract.
        if req.relation == "maximum_count":
            return None
        return None, "capacity_selected_argument_missing"
    if not _capacity_subject_matches(match.group("subject"), binding.topic):
        return None, "capacity_subject_mismatch"
    if modal and not re.search(r"\baccepts?\b", match.group("predicate"), re.I):
        return None, "requested_acceptance_relation_missing"
    unit_error = _capacity_unit_rejection(req, match.group("noun"))
    if unit_error:
        return None, unit_error
    # A raw answer may cover the complete numeral or the complete governed
    # argument, optionally with its literal upper-bound marker. No partial
    # numeral or detached noun supplies a count.
    selected_start = len(prefix) + 1 if prefix else 0
    selected_range = (selected_start, selected_start + len(binding.value))
    allowed = {
        (match.start("number"), match.end("number")),
        (match.start("number"), match.end("noun")),
    }
    if match.group("bound"):
        allowed |= {
            (match.start("bound"), match.end("number")),
            (match.start("bound"), match.end("noun")),
        }
    if selected_range not in allowed:
        return None, "capacity_incomplete_literal_argument"
    continuation = binding.context[binding.start + len(suffix) :]
    if re.match(
        rf"\s*(?:,\s*)?(?:and|but|plus)\s+(?:{_CARDINAL}\b|another\b|more\b|an?\b)",
        continuation,
        re.I,
    ):
        return None, "capacity_additional_count_unbound"
    return local, None


def _relation_hypothesis(
    binding: QuantityBinding,
    prefix: str,
    number: str,
    counted_text: str | None,
    passive: re.Match[str] | None,
) -> tuple[str | None, str | None]:
    req = binding.req
    noun = req.attribute.strip()
    noun_pattern = _noun_pattern(noun)
    if req.relation == "operand_count":
        copula = re.fullmatch(r"(?P<subject>.+?)\s+(?:is|are)", prefix, re.I)
        if (
            not copula
            or not counted_text
            or not _subject_matches(copula.group("subject"), binding.topic)
        ):
            return None, "requested_operand_not_selected_subject"
        return f"{binding.topic} has {counted_text}", None

    if passive:
        # Count-at-head passive clauses retain the entire requested recipient.
        expected = f"{passive.group('relation')} {passive.group('subject').strip()}"
        raw = binding.context[binding.start :]
        match = re.match(
            rf"{re.escape(number)}\s+(?P<noun>{noun_pattern})\s+(?P<tail>[^.!?;\n]+)",
            raw,
            re.I,
        )
        if (
            prefix
            or not match
            or not _subject_matches(passive.group("subject"), binding.topic)
            or _canonical(match.group("tail")) != _canonical(expected)
        ):
            return None, "requested_passive_count_relation_missing"
        return match.group(0), None

    prefix = _implicit_count_prefix(binding, prefix, noun_pattern)
    nominal = re.fullmatch(
        rf"(?P<subject>.+?)\s+(?:has\s+(?:a\s+)?(?:maximum\s+)?{noun_pattern}\s+count\s+of|(?:{_LIMIT}\s+)?(?:number|count)\s+of\s+{noun_pattern}\s+(?:is|:))",
        prefix,
        re.I,
    )
    if nominal:
        if _request_verb(req) or not _count_subject_matches(
            nominal.group("subject"), binding.topic
        ):
            return None, "requested_quantity_subject_or_verb_mismatch"
        counted_text = counted_text or _nominal_count_phrase(number, noun)
        return _natural_count_hypothesis(binding, "has", counted_text)

    return _direct_count(binding, prefix, counted_text)


def _direct_count(
    binding: QuantityBinding,
    prefix: str,
    counted_text: str | None,
) -> tuple[str | None, str | None]:
    direct = re.fullmatch(
        rf"(?P<subject>.+?)\s+(?P<verb>[\w-]+|consists\s+of)(?:\s+(?:{_LIMIT}|exactly))?",
        prefix,
        re.I,
    )
    if (
        not direct
        or not counted_text
        or not _count_subject_matches(direct.group("subject"), binding.topic)
    ):
        return None, "requested_quantity_not_selected_argument"
    return _count_predicate_hypothesis(binding, direct.group("verb"), counted_text)


def _count_predicate_hypothesis(
    binding: QuantityBinding,
    verb: str,
    counted_text: str,
) -> tuple[str | None, str | None]:
    req = binding.req
    maximum = req.relation == "maximum_count"
    requested = _request_verb(req)
    if requested:
        subject, base = requested
        compatible = (
            _CONTAINER_FORMS if base in _CONTAINER_REQUESTS else _verb_forms(base)
        )
        if (
            not _subject_matches(subject, binding.topic)
            or verb.casefold() not in compatible
        ):
            return None, "requested_quantity_subject_or_verb_mismatch"
        predicate = verb
        if verb.casefold() not in _verb_forms(base):
            plural = re.search(r"\bhow\s+many\s+.+?\s+do\s+", req.original_text, re.I)
            predicate = base if plural else sorted(_verb_forms(base) - {base})[0]
        return _natural_count_hypothesis(binding, predicate, counted_text)
    if verb.casefold() not in _CONTAINER_FORMS and not (
        maximum and verb.casefold() == "allows"
    ):
        return None, "quantity_relation_missing"
    return _natural_count_hypothesis(binding, verb, counted_text)


def _nominal_count_phrase(number: str, noun: str) -> str:
    """Inflect only the counted noun explicitly bound in a nominal count fact."""
    words = noun.split()
    head = words[-1]
    singular = number.casefold() in {"1", "one"}
    if (
        singular
        and head.endswith("s")
        and not head.endswith(("ss", "us", "species", "series"))
    ):
        head = head[:-3] + "y" if head.endswith("ies") else head[:-1]
    elif not singular and not head.endswith("s"):
        if head.endswith("y") and len(head) > 1 and head[-2] not in "aeiou":
            head = head[:-1] + "ies"
        else:
            head += "es" if head.endswith(("x", "z", "ch", "sh")) else "s"
    return f"{number} {' '.join([*words[:-1], head])}"


def _natural_count_hypothesis(
    binding: QuantityBinding,
    predicate: str,
    counted_text: str,
) -> tuple[str | None, str | None]:
    """Keep one literal number/unit and the requested subject and conditions."""
    if binding.req.relation == "maximum_count":
        return f"{binding.topic} has a maximum of {counted_text}", None
    implicit_passive = re.search(
        r"\bhow\s+many\s+.+?\s+(?P<aux>are|is)\s+(?P<verb>[\w-]+)\s*[?.!]*$",
        binding.req.original_text,
        re.I,
    )
    if implicit_passive:
        if implicit_passive.group("verb").casefold() != "provided":
            return None, "requested_implicit_quantity_relation_missing"
        return (
            f"{counted_text} {implicit_passive.group('aux')} provided for "
            f"{binding.topic}",
            None,
        )
    return f"{binding.topic} {predicate} {counted_text}", None


def _implicit_count_prefix(
    binding: QuantityBinding,
    prefix: str,
    noun_pattern: str,
) -> str:
    """Carry one literal shared subject across an immediately preceding 'and'."""
    if not re.fullmatch(
        rf"(?:a\s+)?(?:maximum\s+)?{noun_pattern}\s+count\s+of", prefix, re.I
    ):
        return prefix
    before = binding.context[: binding.start]
    sentence = re.split(r"[.!?;\n]", before)[-1]
    conjunction = re.fullmatch(
        r"(?P<subject>.+?)\s+has\s+(?:(?!\b(?:and|but|whereas|while)\b)[^,;])+?\s+and\s+"
        + re.escape(prefix)
        + r"\s*",
        sentence.strip(),
        re.I,
    )
    if (
        conjunction
        and _subject_matches(conjunction.group("subject"), binding.topic)
        and not re.search(_NEGATIVE, sentence, re.I)
    ):
        return f"{conjunction.group('subject')} has {prefix}"
    return prefix


_COUNT_MODIFIER_BAD = frozenset(
    "of the a an additional extra more further new aggregate overall total "
    "profile label version first second third not no other deputy owner".split()
)


def _remaining_argument(
    binding: QuantityBinding,
    suffix: str,
) -> tuple[str, str, str] | None:
    noun = binding.req.attribute.strip()
    if not noun or noun in {"count", "quantity"}:
        return None
    match = re.fullmatch(
        rf"(?P<argument>(?P<number>{_CARDINAL})\s+"
        rf"(?P<modifiers>(?:[a-z][a-z-]*\s+){{0,3}}){_noun_pattern(noun)})"
        r"(?P<tail>.*)",
        suffix,
        re.I,
    )
    if not match or binding.value not in {
        match.group("number"),
        match.group("argument"),
    }:
        return None
    number_end = binding.start + len(match.group("number"))
    before = binding.context[binding.start - 1 : binding.start] if binding.start else ""
    after = binding.context[number_end:]
    if (before and re.match(r"[\w-]", before)) or re.match(r"[\w-]|\.\d", after):
        return None
    argument_end = binding.start + len(match.group("argument"))
    continuation = binding.context[argument_end:]
    if re.match(
        rf"\s*(?:remains?\s*)?(?:,\s*)?(?:and|but|plus)\s+"
        rf"(?:{_CARDINAL}\b|another\b|an?\b|more\b)",
        continuation,
        re.I,
    ):
        return None
    modifiers = match.group("modifiers").casefold().split()
    if any(
        word in _COUNT_MODIFIER_BAD or re.fullmatch(_CARDINAL, word, re.I)
        for word in modifiers
    ):
        return None
    return match.group("argument"), match.group("number"), match.group("tail").strip()


def _condition_subject(topic: str) -> tuple[str, str] | None:
    match = re.fullmatch(
        r"(?P<condition>.+?)\s+in\s+(?P<scope>[\w-]+(?:\s+[\w-]+)*)", topic, re.I
    )
    return (match.group("condition"), match.group("scope")) if match else None


def _relative_gerund(match: re.Match[str]) -> str:
    verb = match.group(1)
    if verb.endswith(("ches", "shes", "sses", "xes", "zzes")):
        verb = verb[:-2]
    elif verb.endswith("ies"):
        verb = verb[:-3] + "y"
    elif verb.endswith("s"):
        verb = verb[:-1]
    if verb.endswith("e") and not verb.endswith(("ee", "ye")):
        verb = verb[:-1]
    return verb + "ing"


def _condition_form(text: str) -> str:
    text = _canonical(text)
    text = re.sub(r"\bthat\s+([\w-]+)\b", _relative_gerund, text)
    return re.sub(r"(\bwithout\s+[\w-]+)\s+it$", r"\1", text)


def _remaining_source_matches(
    binding: QuantityBinding,
    prefix: str,
    tail: str,
) -> bool:
    requested = _condition_subject(binding.topic)
    if requested is None:
        return False
    condition, scope = requested
    treated = re.fullmatch(
        r"(?P<scope>.+?)\s+treats?\s+(?P<condition>.+?)\s+as", prefix, re.I
    )
    if treated and not tail:
        return _canonical(treated.group("scope")) == _canonical(
            scope
        ) and _condition_form(treated.group("condition")) == _condition_form(condition)
    if not re.fullmatch(r"remains?", tail, re.I):
        return False
    conditional = re.fullmatch(r"(?:for|when|if)\s+(.+?)\s*,?", prefix, re.I)
    if conditional:
        source = _condition_subject(conditional.group(1))
        return bool(
            source
            and _canonical(source[1]) == _canonical(scope)
            and _condition_form(source[0]) == _condition_form(condition)
        )
    return False


def _remaining_hypothesis(
    binding: QuantityBinding,
    prefix: str,
    suffix: str,
) -> tuple[str | None, str | None]:
    requested = _remaining_request(binding.req.original_text)
    if not requested or _canonical(requested.group("noun")) != _canonical(
        binding.req.attribute
    ):
        return None, "remaining_count_requested_unit_missing"
    argument = _remaining_argument(binding, suffix)
    if argument is None:
        return None, "remaining_count_literal_argument_missing"
    counted, number, tail = argument
    if not _remaining_source_matches(binding, prefix, tail):
        return None, "remaining_count_condition_or_operation_missing"
    verb = "remains" if number.casefold() in {"1", "one"} else "remain"
    return f"For {binding.topic}, {counted} {verb}", None
