"""Immutable request facts, independent from reader scores and answer prose."""

import re
from dataclasses import dataclass, replace

from app.services.reader_questions import named_anchors as _legacy_named_anchors
from app.services.requirement_quantities import question_relation


@dataclass(frozen=True)
class Requirement:
    id: str
    original_text: str
    input_start: int
    input_end: int
    question: str
    kind: str
    topic: str
    anchors: tuple[str, ...]
    depends_on: tuple[str, ...] = ()
    relation: str = ""
    attribute: str = ""
    source_workspace: str | None = None


@dataclass(frozen=True)
class ProhibitionRequest:
    """Lossless material argument of one bounded, topic-scoped request."""

    mode: str
    argument: str = ""


def _prohibition_request_body(text: str, topic: str) -> str | None:
    text = _clean(text)
    subject = re.escape(re.sub(r"^(?:the|an?)\s+", "", topic.strip(), flags=re.I))
    regarding = re.match(rf"regarding\s+(?:the\s+|an?\s+)?{subject},\s*", text, re.I)
    if regarding:
        text = text[regarding.end() :]
    # Retain the existing fully consumed method-reference activity/session form.
    activity = re.escape(re.sub(r"\s+session$", "", topic.strip(), flags=re.I))
    if re.fullmatch(
        rf"for\s+{activity},\s*what\s+action\s+is\s+prohibited\s+in\s+the\s+method",
        text,
        re.I,
    ):
        return "what action is prohibited in the method"
    if re.fullmatch(
        rf"what\s+action\s+is\s+prohibited\s+in\s+(?:the\s+|an?\s+)?{subject}",
        text,
        re.I,
    ):
        return "what is the prohibition"
    preface = re.match(rf"(?:for|in|at)\s+(?:the\s+|an?\s+)?{subject},\s*", text, re.I)
    if preface:
        text = text[preface.end() :]
    separators = list(re.finditer(r"\s+for\s+", text, re.I))
    if separators:
        terminal = separators[-1]
        scope = re.sub(r"^(?:the|an?)\s+", "", text[terminal.end() :], flags=re.I)
        expected = re.sub(r"^(?:the|an?)\s+", "", topic.strip(), flags=re.I)
        if scope.casefold() != expected.casefold():
            return None
        text = text[: terminal.start()]
    return re.sub(r"^(?:give|state|include)\s+", "", text, count=1, flags=re.I)


def prohibition_request(text: str, topic: str) -> ProhibitionRequest | None:
    """Interpret a whole atomic fragment using its explicit or inherited topic.

    No trailing words are discarded. Captured material arguments remain whole
    for source-predicate binding; unsupported request grammar stays unresolved.
    """
    if not topic.strip():
        return None
    body = _prohibition_request_body(text, topic)
    if body is None:
        return None
    generic = (
        r"(?:what\s+is\s+the\s+prohibition|what\s+action\s+is\s+prohibited\s+in\s+the\s+method|"
        r"(?:the\s+)?(?:(?:method|procedure)['’]s\s+(?:explicit\s+)?prohibition|"
        r"(?:explicit\s+)?(?:method|procedure)\s+prohibition|prohibition))"
    )
    if re.fullmatch(generic, body, re.I):
        return ProhibitionRequest("generic")
    for mode, pattern in (
        ("action", r"(?:the\s+)?rule\s+against\s+(.+)"),
        ("object", r"(?:the\s+)?prohibition\s+on\s+(.+)"),
        ("substitution", r"what\s+substitution\s+must\s+not\s+be\s+made\s+to\s+(.+)"),
        (
            "substitution",
            r"what\s+replacement\s+of\s+(.+)\s+is\s+(?:forbidden|prohibited)",
        ),
        ("object", r"which\s+(.+)\s+manipulation\s+is\s+prohibited"),
        ("assignment", r"what\s+must\s+not\s+be\s+assigned\s+to\s+(.+)"),
        ("inference", r"what\s+must\s+not\s+be\s+inferred\s+from\s+(.+)"),
        ("classification", r"what\s+must\s+not\s+count\s+as\s+(.+)"),
    ):
        match = re.fullmatch(pattern, body, re.I)
        if match:
            return ProhibitionRequest(mode, _clean(match.group(1)))
    return None


_KINDS = (
    ("deputy", r"\b(?:deputy|deputies|deputizing|deputises|deputizes|deputize)\b"),
    (
        "owner",
        r"\b(?:(?:who|which\s+role)\s+(?:leads|runs|manages|owns|oversees)|owner(?!-)|lead\s+role|responsible\s+(?:party|role|for))\b|"
        r"^\s*(?:(?:identify|give|name|need)\s+)?(?:(?:the|its|their)\s+)?lead\b",
    ),
    (
        "duration",
        r"\b(?:how\s+long|duration|elapsed\s+time|running\s+time|session\s+length)\b",
    ),
    (
        "start_time",
        r"\b(?:start\s+time|(?:what|which)\s+time|when\s+does|when(?=,\s*including))\b",
    ),
    (
        "weekday",
        r"\b(?:(?:what|which)\s+day|day\s+of\s+the\s+week|weekday|(?:weekly|scheduled|starting)\s+(?:starting\s+)?day)\b",
    ),
    (
        "availability",
        r"\b(?:availability|(?:what|which)\s+hours|during\s+which\s+hours)\b",
    ),
    (
        "quantity",
        r"\b(?:how\s+many|count|number\s+of|quantity|capacity|maximum\s+(?:participants?|attendees?))\b",
    ),
    (
        "prohibition",
        r"\b(?:prohibition|restriction|forbidden|prohibited|must\s+not|rule\s+against)\b",
    ),
)
_PREFACE = re.compile(r"^\s*(?:for|in|at|on|regarding)\s+([^,;?!]+)[,:]\s*", re.I)
_SPLIT = re.compile(
    r"(?:[,;]\s*(?:and\s+)?|\s+and\s+)(?=(?:who|what|which|where|when|how|why|"
    r"on\s+which|at\s+what|during\s+which|may|can|does|do|is|are|must|should|the\s+person-role|"
    r"(?:the\s+)?owner\s+of|the\s+(?:rule\s+against|prohibition\s+on))\b)"
    r"|(?<=[?!.])\s+(?:and\s+)?(?=(?:who|what|which|when|how|why|may|can|does|is)\b)",
    re.I,
)
_IMPERATIVE_SPLIT = re.compile(
    r"(?:[,;]\s*(?:(?:also|then)\s+)?|\s+(?:and|then)\s+)(?="
    r"(?:give|state|identify|say|include)\b|tell\s+me\s+when\b|the\s+day\s+and\s+time\b|exactly\s+when\b)"
    r"|(?<=[?.!])\s+(?:(?:also)\s+)?(?=(?:give|include|say|when)\b)",
    re.I,
)


def _requirement_anchors(text: str) -> tuple[str, ...]:
    result = list(_legacy_named_anchors(text))
    for word in re.findall(r"\b[\w-]+\b", text):
        if ord(word[0]) > 127 and word[0].isupper() and word.casefold() not in result:
            result.append(word.casefold())
    return tuple(result)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,;?.!")


def _literal_topic(text: str) -> str | None:
    from app.services.requirement_relations import question_topic

    if any(re.search(pattern, text, re.I) for _, pattern in _KINDS):
        return None
    literal = question_topic(text)
    scalar = re.fullmatch(r"(?:what|which)\s+(?:is|are)\s+(.+)", text, re.I)
    # Unsupported nested properties retain the complete object as scope.
    return literal or (scalar.group(1) if scalar else None)


def _input_subject(text: str) -> str | None:
    """Explicit grammatical input subjects, independent of extracted answers."""
    body = _without_preface(text).strip()
    active = re.fullmatch(
        r"how\s+(?:does|do)\s+(.+?)\s+"
        r"(?:represent|encode|format|store|record|process|render|handle)\s+.+",
        body,
        re.I,
    )
    possessive = re.match(
        r"(?:what|which)\s+(?:is|are)\s+([\w -]+?)['’]s\s+", body, re.I
    )
    match = active or possessive
    return _clean(match.group(1)) if match else None


def _generic_request(text: str) -> tuple[str, str, str] | None:
    body = _without_preface(text).strip().rstrip("?.!")
    representation = re.fullmatch(
        r"how\s+(?:does|do)\s+([\w -]+?)\s+represent\s+(.+)", body, re.I
    )
    if representation:
        return "represent", representation.group(1), representation.group(2)
    identifying = re.fullmatch(r"(?:what|which)\s+code\s+identifies\s+(.+)", body, re.I)
    return ("code_identity", identifying.group(1), "code") if identifying else None


def _direct_factual_subject(text: str) -> str | None:
    request = re.fullmatch(r"(?:does|do)\s+(.+)", text.strip(), re.I)
    if request is None:
        return None
    body = request.group(1)
    verbs = list(
        re.finditer(
            r"\b(?:describe|represent|encode|format|store|record|process|render|"
            r"handle|contain|include|hold|mean|allow|require|use|skip|follow|omit|have)\b",
            body,
            re.I,
        )
    )
    # An action word inside a compound name, or an additional nested predicate,
    # is ambiguous in this bounded grammar. Never choose a greedy noun boundary.
    verbs = [v for v in verbs if _scope_key(body[: v.start()])]
    if len(verbs) != 1:
        return ""
    verb = verbs[0]
    subject = re.sub(r"\s+(?:not|never)$", "", body[: verb.start()].strip(), flags=re.I)
    if (
        not body[verb.end() :].strip(" ?.!")
        or re.fullmatch(r"[\w-]+(?:\s+[\w-]+)*", subject) is None
        or re.search(
            r"\b(?:it|its|they|their|this|that|these|those|and|or|of|for|by|with|"
            r"from|in|under|at|whose|who|which|how|when|where|if|unless|not|never)\b",
            subject,
            re.I,
        )
    ):
        return ""
    return re.sub(r"^(?:the|a|an)\s+", "", subject, flags=re.I)


def _planning_body(text: str) -> str:
    context = _scheduling_context(text)
    if context:
        text = text[context.end() :]
    text = re.sub(r"[?.!]\s*What\s+are\s+they[?.!]*\s*$", "", text, flags=re.I)
    return _clean(re.sub(r"^\s*(?:also\s+)?", "", _without_preface(text), flags=re.I))


def _scheduling_context(text: str) -> re.Match[str] | None:
    return re.match(
        r"\s*I\s+am\s+scheduling\s+(?P<subject>[^.!?]+)\.\s*"
        r"(?=What\s+are\s+its\b)",
        text,
        re.I,
    )


def _consultation_requested(text: str) -> bool:
    body = re.sub(
        r"^(?:give|state|include|tell\s+me)\s+", "", _planning_body(text), flags=re.I
    )
    return bool(
        re.fullmatch(
            r"when\s+can\s+I\s+consult\s+(?:the|that)\s+owner|"
            r"(?:the|that)\s+owner(?:\s+role)?['’]s\s+(?:published\s+)?consultation\s+(?:window|availability)|"
            r"when\s+(?:the\s+)?owning\s+role\s+takes\s+consultations",
            body,
            re.I,
        )
    )


def _coverage_nominal_kind(text: str) -> str | None:
    body = re.sub(
        r"^(?:(?:give|state|report|include|identify)\s+|what\s+(?:is|are)\s+)",
        "",
        _planning_body(text),
        flags=re.I,
    )
    body = re.sub(r"^(?:the|its|their)\s+", "", body, flags=re.I)
    if re.fullmatch(r"(?:beginning\s+time|start(?:\s+time)?)", body, re.I):
        return "start_time"
    if re.fullmatch(r"(?:length|duration)", body, re.I):
        return "duration"
    if re.fullmatch(
        r"(?:full\s+)?(?:allocation|allocated\s+amount)"
        r"(?:\s+(?:with\s+units|in\s+(?:its|the)\s+stated\s+units))?"
        r"(?:\s+for\s+.+)?(?:,\s*keeping\s+(?:the\s+)?allocation\s+units)?",
        body,
        re.I,
    ):
        return "quantity"
    return None


def _allocation_requested(text: str) -> bool:
    return _coverage_nominal_kind(text) == "quantity" or bool(
        re.fullmatch(
            r"(?:what|which)\s+quantity(?:\s+in\s+the\s+stated\s+units)?\s+is\s+allocated\s+to\s+it",
            _planning_body(text),
            re.I,
        )
    )


def _coverage_topic(topic: str, original: str, inherited: str) -> str:
    """Consume explicit operation/session frames without comparing word overlap."""
    operation = re.fullmatch(
        r"(ordinary\s+operation)\s+at\s+(?:the\s+)?(.+)", topic, re.I
    )
    if operation:
        return f"{operation.group(2)} {operation.group(1)}"
    body = _planning_body(original)
    if inherited and re.fullmatch(r"ordinary\s+operation", topic, re.I):
        return f"{inherited} {topic}"
    if (
        inherited
        and topic == inherited
        and re.fullmatch(
            r"(?:name|give|identify)\s+(?:the\s+)?ordinary\s+operation\s+owner",
            body,
            re.I,
        )
    ):
        return f"{topic} ordinary operation"
    session = re.fullmatch(
        r"(?:(?:one|single)\s+)?(?P<class>ordinary|normal|standard)\s+session\s+at\s+(?:the\s+)?(?P<entity>.+)",
        topic,
        re.I,
    )
    if session:
        return f"{session.group('class')} {session.group('entity')} session"
    return (
        re.sub(
            r"^(?:one|single)\s+(?=(?:ordinary|normal|standard)\b)",
            "",
            topic,
            flags=re.I,
        )
        if re.search(r"\bsessions?$", topic, re.I)
        else topic
    )


def _activity_base(topic: str) -> str:
    base = re.split(
        r"\s+(?:worksheet|procedure|method|sessions?)\b", topic, maxsplit=1, flags=re.I
    )[0]
    base = re.split(r"\s+(?:with\s+no|bearing\s+no)\b", base, maxsplit=1, flags=re.I)[0]
    return re.sub(r"\s+no-[\w-]+\b", "", base, flags=re.I)


def _session_topic(subject: str, inherited: str) -> str:
    anonymous = re.fullmatch(
        r"(?:(?:an?|one|those)\s+)?(?:(ordinary|standard|normal)\s+)?(sessions?)",
        subject,
        re.I,
    )
    if anonymous is None or not inherited:
        return re.sub(r"^(?:an?|one|the)\s+", "", subject, flags=re.I)
    if re.search(r"\bsessions?\b", inherited, re.I) and not re.search(
        r"\b(?:worksheet|procedure|method)\b", inherited, re.I
    ):
        return (
            anonymous.group(1)
            + " "
            + re.sub(r"^(?:ordinary|normal|standard)\s+", "", inherited, flags=re.I)
            if anonymous.group(1)
            else inherited
        )
    base = _activity_base(inherited)
    if anonymous.group(1):
        base = re.sub(r"^(?:ordinary|standard|normal)\s+", "", base, flags=re.I)
        base = anonymous.group(1) + " " + base
    return base + " " + anonymous.group(2)


def _schedule_topic(body: str, inherited: str) -> str | None:
    if not re.search(
        r"\b(?:scheduled|start\s+day|day\s+and\s+time|those\s+sessions)\b", body, re.I
    ):
        return None
    explicit = re.search(
        r"\b(?:of|that)\s+(.+?)\s+(?:starts?|begins?)[?.!]*$|\bof\s+(.+)$", body, re.I
    )
    if explicit:
        subject = next(x for x in explicit.groups() if x)
        return _session_topic(subject, inherited)
    if re.search(r"\b(?:those\s+sessions|scheduled\s+session)\b", body, re.I):
        return _session_topic(
            "sessions" if "those sessions" in body.casefold() else "session", inherited
        )
    if re.search(r"\bsessions?\b", inherited, re.I):
        return _session_topic("session", inherited)
    return _activity_base(inherited) if inherited else None


def _composed_topic(text: str, inherited: str) -> str | None:
    body = _planning_body(text)
    schedule = _schedule_topic(body, inherited)
    if schedule is not None:
        return schedule
    modal = re.search(
        r"\bhow\s+many\s+.+?\s+(?:may|can)\s+(.+?)\s+accept\b", body, re.I
    )
    duration = re.search(
        r"\bhow\s+(?:many\s+\w+|long)\s+(?:does|do)\s+((?:an?|one)\s+(?:ordinary|normal|standard)\s+session)\s+(?:last|take)\b",
        body,
        re.I,
    )
    anonymous_session = modal if modal is not None else duration
    if anonymous_session is not None:
        return _session_topic(anonymous_session.group(1), inherited)
    scalar = re.fullmatch(
        r"(?:what\s+is|give|provide|identify)\s+(?:the\s+)?(.+?)\s+(duration|capacity|deputy)(?:\s+in\s+.+)?",
        body,
        re.I,
    )
    if scalar and scalar.group(1).casefold() in {"ordinary", "normal", "standard"}:
        return (
            scalar.group(1)
            + " "
            + re.sub(r"^(?:ordinary|normal|standard)\s+", "", inherited, flags=re.I)
            if inherited
            else ""
        )
    if scalar and scalar.group(1).casefold() not in {
        "ordinary",
        "normal",
        "standard",
        "its",
        "their",
        "both its",
        "both their",
        "the",
        "both the",
    }:
        return re.sub(r"^an?\s+", "", scalar.group(1), flags=re.I)
    if re.search(r"\bsession\s+length\b|^(?:identify\s+)?its\s+lead\b", body, re.I):
        return (
            (
                _session_topic("session", inherited)
                if "session length" in body.casefold()
                and not re.search(r"\bsession\b", inherited, re.I)
                else inherited
            )
            if inherited
            else None
        )
    if re.match(
        r"(?:give|provide|supply|state)\s+(?:the\s+)?(?:maximum\s+)?number\s+of\b",
        body,
        re.I,
    ) and not re.search(r"\b(?:in|for)\s+", body, re.I):
        return inherited or None
    if _procedure_requested(body):
        topic = _procedure_topic(body)
        if topic and inherited and not _requirement_anchors(topic):
            qualifier = re.match(r"(ordinary|normal|standard)\s+", topic, re.I)
            return (
                (qualifier.group(1) + " " + inherited + " " + topic[qualifier.end() :])
                if qualifier
                else inherited + " " + topic
            )
    return None


def _cover_events(body: str) -> list[tuple[int, str]] | None:
    window = re.search(
        r"\b(?:permitted\s+cover\s+window|condition\s+on\s+"
        r"(?:their|its)\s+availability|exactly\s+when|under\s+what\s+"
        r"day[- ]and[- ]time\s+restriction)\b",
        body,
        re.I,
    )
    if window is None:
        return None
    deputy = re.search(r"\bdeputy\b", body, re.I)
    return ([(deputy.start(), "deputy")] if deputy else []) + [
        (window.start(), "availability")
    ]


def _composed_quantity(text: str) -> str | None:
    body = _planning_body(text)
    modal = re.search(r"\bhow\s+many\s+(.+?)\s+(?:may|can)\b", body, re.I)
    if modal:
        return modal.group(1)
    if re.search(r"\bcapacity\b", body, re.I):
        units = re.search(r"\bcapacity\s+in\s+(.+)", body, re.I)
        return units.group(1) if units else ""
    return None


def _composed_relation(text: str, kind: str) -> str | None:
    body = _planning_body(text)
    if kind == "availability" and _cover_events(body):
        return "cover_window"
    if kind == "quantity" and re.search(r"\bcapacity\b", body, re.I):
        return "capacity_count"
    if kind == "quantity" and re.search(
        r"\bhow\s+many\s+.+?\s+(?:may|can)\s+.+?\s+accept\b", body, re.I
    ):
        return "maximum_count:accept"
    if (
        kind == "owner"
        and re.search(r"\blead\b", body, re.I)
        and not re.search(r"\b(?:owns|owner|responsible)\b", body, re.I)
    ):
        return "leads"
    return None


def _explicit_topic(text: str, inherited: str) -> str | None:
    if (
        inherited
        and _coverage_nominal_kind(text)
        and not re.search(r"\b(?:for|of)\b", _planning_body(text), re.I)
    ):
        return inherited
    composed = _composed_topic(text, inherited)
    if composed is not None:
        return composed
    direct = _direct_factual_subject(text)
    if direct is not None:
        return direct
    identity = _identity_request(text)
    if identity:
        return re.sub(r"^(?:the|a|an)\s+", "", identity[1], flags=re.I)
    if _procedure_requested(text):
        topic = _procedure_topic(text)
        if topic:
            return topic
    forbidden = re.fullmatch(
        r"(?:what|which)\s+.+?\s+of\s+(.+?)\s+is\s+(?:forbidden|prohibited)",
        text,
        re.I,
    )
    if forbidden:
        return inherited or _clean(forbidden.group(1))
    generic = _generic_request(text)
    if generic:
        return generic[1]
    # The full literal scalar scope is more precise than its possessive owner.
    return _literal_topic(text) or _input_subject(text)


def _same_indefinite_head(value: str, inherited: str) -> bool:
    noun = re.fullmatch(r"(?:a|an)\s+([\w-]+)", value, re.I)
    if noun is None or not inherited or re.search(r"\b(?:and|or)\b", inherited, re.I):
        return False
    # Keep postmodifiers/namespace in the inherited phrase, but compare its head
    # before a bounded prepositional postmodifier. Never strip a new modifier.
    stem = re.split(
        r"\s+(?:of|in|under|with|for|at)\s+", inherited, maxsplit=1, flags=re.I
    )[0]
    return stem.split()[-1].casefold() == noun.group(1).casefold()


def _topic(text: str, inherited: str) -> str:
    scheduling = _scheduling_context(text)
    if scheduling:
        return _topic(text[scheduling.end() :], _clean(scheduling.group("subject")))
    text = re.sub(r"[?.!]\s*What\s+are\s+they[?.!]*\s*$", "", text, flags=re.I)
    text = text.strip().rstrip("?.!")
    preface = _PREFACE.match(text)
    if preface:
        inherited = re.sub(r"^(?:the|a|an)\s+", "", preface.group(1), flags=re.I)
        text = text[preface.end() :]
    explicit = _explicit_topic(text, inherited)
    if explicit is not None:
        return explicit
    patterns = (
        r"\bnumber\s+of\s+.+?\s+in\s+(.+)",
        r"\bhow\s+many\s+.+?\s+(?:does|do|did)\s+(.+?)\s+[\w-]+$",
        r"\bhow\s+many\s+.+?\s+(?:are|is)\s+[\w-]+\s+(?:to|for|by)\s+(.+)$",
        r"\bhow\s+many\s+.+?\s+(?:go\s+into|are\s+in)\s+(.+)",
        r"\b(?:what|which)\s+hours\s+is\s+(.+?)\s+(?:available|present)\b",
        r"\bhow\s+many\s+.+?\s+(?:does|do)\s+(.+?)\s+(?:contain|include|have|comprise|consist|receive|hold|take)\b",
        r"\b(?:who|which\s+role)\s+(?:leads|runs|manages|owns|oversees)\s+(.+)",
        r"\bwho\s+(?!(?:is|are|was|were|does|do|did|can|may|must)\b)[\w-]+\s+(.+)",
        r"\bhow\s+long\s+(?:does|will|did)\s+(.+?)\s+(?:last|take)\b",
        r"\b(?:(?:what|which)\s+(?:time|day)|when(?:,\s*including\s+the\s+day\s+of\s+the\s+week,)?)\s+(?:does|will|did)\s+(.+?)\s+(?:start|begin|open)\b",
        r"\b(?:who\s+is\s+(?:the\s+)?deputy|owner|deputy|prohibition|restriction|count|duration|"
        r"start\s+time|weekday|availability)\s+(?:of|for|in)\s+(.+)",
        r"\b(?:for|of)\s+([^,;?]+)$",
        r"\bhow\s+(?:do|does|can|should)\s+(?:I|we|you)\s+(?:run|perform|conduct|complete)\s+(.+)",
        r"^\s*(?:may|can|must|should|does|is)\s+(.+?)\s+(?:skip|use|follow|omit|allow|permitted|allowed)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            value = _clean(match.group(1))
            if _same_indefinite_head(value, inherited):
                return inherited
            if re.match(r"(?:its|their)\s+", value, re.I) and inherited:
                return (
                    re.sub(r"^(?:its|their)\s+", "", value, flags=re.I)
                    + " of "
                    + inherited
                )
            if not re.match(
                r"(?:it|its|that\s+(?:role|owner)|the\s+owner)(?:\s+with\b|$)",
                value,
                re.I,
            ):
                return re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.I)
    return inherited


def _opening_relation(text: str, kind: str) -> str | None:
    if kind not in {"start_time", "weekday"}:
        return None
    opening = re.search(r"\b(?:does|will|did)\s+.+?\s+(open|begin|start)\b", text, re.I)
    return opening.group(1).casefold() + "s" if opening else None


def _coverage_relation(text: str, kind: str) -> str | None:
    if kind == "availability" and _consultation_requested(text):
        return "consultation_window"
    if (
        kind == "quantity"
        and _allocation_requested(text)
        and _quantity_attribute(text) == "count"
    ):
        return "allocation"
    return None


def _relation(text: str, kind: str) -> str:
    return _coverage_relation(text, kind) or _base_relation(text, kind)


def _base_relation(text: str, kind: str) -> str:
    opening = _composed_relation(text, kind) or _opening_relation(text, kind)
    if opening:
        return opening
    identity = _identity_request(text) or _generic_request(text)
    if kind == "generic" and identity:
        return identity[0]
    if kind == "boolean" and _count_as_parts(text):
        return "count_as"
    if kind == "deputy" and re.search(r"\bdeputi[sz](?:es|ing)\b", text, re.I):
        return "deputizes"
    if kind == "quantity":
        requested = question_relation(text)
        if requested:
            return requested
    if kind == "quantity" and re.search(r"\bmaximum\b", text, re.I):
        return "maximum_count"
    if kind == "owner":
        if re.search(r"\bresponsible\s+for\b", text, re.I):
            return "is responsible for"
        match = re.search(
            r"\b(?:who|which\s+role)\s+(leads|runs|manages|owns|oversees)\b", text, re.I
        )
        return match.group(1).casefold() if match else "owner"
    return {
        "deputy": "deputy",
        "duration": "lasts",
        "start_time": "starts",
        "weekday": "starts",
    }.get(kind, kind)


def _quantified_question(
    kind: str, topic: str, relation: str, attribute: str, original: str
) -> str | None:
    if kind == "quantity" and relation == "allocation":
        return f"What is the allocation for {topic} in its stated units?"
    if kind == "quantity" and relation in {"capacity_count", "maximum_count:accept"}:
        if relation == "capacity_count" and not attribute:
            return _capacity_count_question(topic, original)
        return (
            f"What is the capacity of {topic}?"
            if not attribute
            else f"What is the maximum number of {attribute} for {topic}?"
        )
    if kind == "duration" and attribute != "duration":
        return f"How many {attribute} does {topic} take?"
    return None


def _capacity_count_question(topic: str, original: str) -> str:
    """Prepare the accepted-count profile only for a fully consumed request.

    ``items`` is a generic QA placeholder, never an inferred answer unit. Unknown
    facets retain their original wording instead of being erased by a template.
    """
    if not re.fullmatch(r"[\w-]+(?:\s+[\w-]+)*", topic) or re.search(
        r"\b(?:under|in|at|on|for|of|to|before|after|during|from|until|since|"
        r"between|within|with|without|"
        r"if|when|while|unless|except|only|not|no|and|or|per|each|by|including|"
        r"excluding|rather|instead|using|minimum|maximum|remaining|available|"
        r"current|actual|nominal|expected|planned|free|spare|unused|estimated|"
        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"today|tomorrow|yesterday|morning|afternoon|evening|night|noon)\b",
        topic,
        re.I,
    ):
        return original
    subject = rf"(?:(?:the|an?)\s+)?{re.escape(topic)}"
    frame = (
        rf"(?:what\s+is|give|provide|identify)\s+{subject}\s+capacity"
        rf"|what\s+is\s+the\s+capacity\s+of\s+{subject}"
    )
    if re.fullmatch(frame, _clean(original), re.I) is None:
        return original
    return f"How many items may {topic} accept at most?"


def _prepared_prohibition(topic: str, original: str) -> str:
    contract = prohibition_request(original, topic)
    if contract is not None and contract.mode == "generic":
        return f"What is the prohibition for {topic}?"
    return f"Regarding {topic}, {original}"


def _temporal_subject_matches(subject: str, topic: str) -> bool:
    if re.fullmatch(r"it|its\s+session|those\s+sessions", subject, re.I):
        return bool(topic)

    return (
        _scope_key(subject) == _scope_key(topic)
        or _same_indefinite_head(subject, topic)
        or _scope_key(_session_topic(subject, topic)) == _scope_key(topic)
    )


def temporal_request_consumed(text: str, kind: str, topic: str) -> bool:
    """Certify the whole bounded temporal request before replacing its prose.

    Event discovery is deliberately permissive; it does not prove that a typed
    template accounts for every requested argument. Unknown residual material
    keeps its original wording and cannot be discharged by the scalar binder.
    """
    if kind not in {"duration", "start_time", "weekday"}:
        return True
    body = _planning_body(text)
    unit = r"(?:seconds?|minutes?|hours?|days?|weeks?)"
    head = (
        rf"(?:how\s+long|how\s+many\s+{unit}|(?:at\s+)?(?:what|which)\s+time|"
        r"(?:on\s+)?(?:what|which)\s+day|when(?:,\s*including\s+the\s+day\s+of\s+the\s+week,)?)"
    )
    verbal = re.fullmatch(
        rf"{head}\s+(?:does|do|will|did)\s+(?P<subject>.+?)\s+"
        r"(?:start|begin|open|last|take)(?:s)?"
        r"(?:\s+each\s+week|\s*\(day\s+and\s+time\))?",
        body,
        re.I,
    )
    if verbal:
        return _temporal_subject_matches(verbal.group("subject"), topic)
    body = re.sub(
        r"^(?:(?:give|name|list|state|report|include|identify|supply|provide|I\s+need)\s+|"
        r"what\s+(?:is|are)\s+)",
        "",
        body,
        flags=re.I,
    )
    body = re.sub(r"^(?:both\s+)?(?:the|its|their)\s+", "", body, flags=re.I)
    attribute = (
        rf"(?:duration|elapsed\s+time|running\s+time|(?:session\s+)?length(?:\s+in\s+{unit})?|"
        r"beginning\s+time|(?:(?:weekly|scheduled)\s+)?(?:session\s+)?"
        r"(?:starting\s+|start\s+)?(?:weekday|day(?:\s+and\s+time)?|time)|start)"
    )
    if re.fullmatch(attribute, body, re.I):
        return True
    scoped = re.fullmatch(
        rf"{attribute}\s+(?:of|for)\s+(?P<subject>.+)|"
        rf"{attribute}\s+that\s+(?P<relative>.+?)\s+(?:starts|begins)|"
        rf"(?P<adjectival>.+?)\s+{attribute}",
        body,
        re.I,
    )
    return bool(
        scoped
        and _temporal_subject_matches(
            next(value for value in scoped.groups() if value), topic
        )
    )


def _prepared(
    kind: str, topic: str, original: str, relation: str, attribute: str
) -> str:
    if (
        kind == "deputy"
        and topic
        and re.fullmatch(
            r"which\s+deputy\s+can\s+cover\s+it\s+under\s+what\s+"
            r"day[- ]and[- ]time\s+restriction|"
            r"(?:the\s+)?deputy(?:\s+role)?\s+with\s+its\s+permitted\s+cover\s+window",
            _planning_body(original),
            re.I,
        )
    ):
        return f"Who is the deputy for {topic}?"
    if (
        not topic
        or not temporal_request_consumed(original, kind, topic)
        or re.search(
            r"\b(?:if|unless|except|only|provided|under|whenever|approved|reserved|retired|overnight|owner-only)\b",
            original,
            re.I,
        )
    ):
        return original
    if kind == "procedure":
        subject = re.split(r"\s+with\s+(?!no\b)", topic, maxsplit=1, flags=re.I)[0]
        if _phrasal_action(subject):
            return f"What is the first step to {subject}?"
        return f"What is the first step for {subject}?"
    quantified = _quantified_question(kind, topic, relation, attribute, original)
    if quantified is not None:
        return quantified
    if kind == "prohibition":
        return _prepared_prohibition(topic, original)
    if kind in {"start_time", "weekday"} and re.search(
        r"\beach\s+week\b", original, re.I
    ):
        verb = relation.removesuffix("s")
        head = "At what time" if kind == "start_time" else "On which day"
        return f"{head} does {topic} {verb} each week?"
    if kind == "quantity" and re.search(
        r"\b(?:shown\s+by|and\s+by|per|each)\b", original, re.I
    ):
        return original
    count = "count" if attribute in {"quantity", "count"} else f"{attribute} count"
    if relation == "maximum_count":
        count = "maximum " + count
    templates = {
        "owner": f"Who {relation} {topic}?"
        if relation != "owner"
        else f"Who is the owner of {topic}?",
        "deputy": f"Who is the deputy for {topic}?",
        "duration": f"How long does {topic} last?",
        "start_time": f"What time does {topic} start?",
        "weekday": f"On which day does {topic} start?",
        "availability": f"During which hours is {topic} present?",
        "quantity": f"What is the {count} for {topic}?",
        "prohibition": f"What is the prohibition for {topic}?",
    }
    return templates.get(kind, original)


def _weekly_event(original: str, events: list[tuple[int, str]]) -> None:
    kinds = {kind for _, kind in events}
    weekly = re.search(r"\beach\s+week\b", original, re.I)
    if "start_time" in kinds and "weekday" not in kinds and weekly:
        events.append((weekly.start(), "weekday"))


def _request_head_events(original: str) -> list[tuple[int, str]] | None:
    body = _without_preface(original)
    cover = _cover_events(body)
    if cover is not None:
        return cover
    if re.search(
        r"\b(?:day|weekday|time)\s+or\s+"
        r"(?:(?:the|its|their|what|which|at|on|start|starting|scheduled)\s+)*"
        r"(?:day|weekday|time)\b",
        body,
        re.I,
    ):
        return [(0, "generic")]
    if re.search(r"\b(?:what|which)\s+must\s+not\b", body, re.I):
        return [(0, "prohibition")]
    if re.match(r"\s*(?:may|can|must|should|does|do|is|are)\b", body, re.I):
        return [(0, "boolean")]
    if re.search(
        r"\bhow\s+many\s+(?:seconds?|minutes?|hours?|days?|weeks?)\s+"
        r"(?:does|do)\s+.+?\s+(?:take|last)\b",
        original,
        re.I,
    ):
        return [(0, "duration")]
    return None


def _coverage_events(original: str, procedure: bool) -> list[tuple[int, str]] | None:
    if _consultation_requested(original):
        return [(0, "availability")]
    consultation_head = re.sub(
        r"^(?:give|state|include|tell\s+me)\s+",
        "",
        _planning_body(original),
        flags=re.I,
    )
    if re.match(
        r"(?:when\b|(?:the|that)\s+owner(?:\s+role)?['’]s\b)", consultation_head, re.I
    ) and re.search(r"\bconsult(?:ation|ations)?\b", consultation_head, re.I):
        return [(0, "generic")]
    nominal = _coverage_nominal_kind(original)
    if not procedure and nominal:
        return [(0, nominal)]
    return None


def _events(original: str, procedure: bool) -> list[tuple[int, str]]:
    return _coverage_events(original, procedure) or _base_events(original, procedure)


def _base_events(original: str, procedure: bool) -> list[tuple[int, str]]:
    events: list[tuple[int, str]] = []
    head = _request_head_events(original)
    if head:
        return head
    if procedure:
        events = [(0, "procedure")]
    else:
        for kind, pattern in _KINDS:
            match = re.search(pattern, _without_preface(original), re.I)
            if match:
                # "that owner" is an antecedent, not another owner request.
                if (
                    kind == "owner"
                    and re.search(r"\bthat\s+owner\b", original, re.I)
                    and not re.search(r"\bowner\s+of\b", original, re.I)
                ):
                    continue
                events.append((match.start(), kind))
        events.extend(_unknown_nominals(original))
        if re.search(r"\bday\s+and\s+time\b", original, re.I):
            events = [
                (p, k)
                for p, k in events
                if k not in {"weekday", "start_time", "generic"}
            ]
            events.extend([(0, "weekday"), (1, "start_time")])
        elif re.search(r"\bstart\s+day\b", original, re.I) and not any(
            k == "weekday" for _, k in events
        ):
            events = [(p, k) for p, k in events if k != "generic"] + [(0, "weekday")]
        _weekly_event(original, events)
        events.sort()
    if not events and re.match(
        r"\s*(?:(?:the|its|their)\s+)?(?:starting\s+)?time\b", original, re.I
    ):
        events = [(0, "start_time")]
    if not events:
        kind = (
            "boolean"
            if re.match(r"\s*(?:may|can|must|should|does|do|is|are)\b", original, re.I)
            else "generic"
        )
        events = [(0, kind)]
    return events


def _unknown_nominals(original: str) -> list[tuple[int, str]]:
    events: list[tuple[int, str]] = []
    if re.match(
        r"\s*(?:give|name|list|identify|supply|provide|what\s+(?:is|are))\b",
        original,
        re.I,
    ):
        first = re.split(r",\s*|\s+and\s+", original, maxsplit=1, flags=re.I)[0]
        if not any(re.search(pattern, first, re.I) for _, pattern in _KINDS):
            events.append((0, "generic"))
        for conjunction in re.finditer(r",\s*(?:and\s+)?|\s+and\s+", original, re.I):
            following = re.split(
                r",\s*|\s+and\s+",
                original[conjunction.end() :],
                maxsplit=1,
                flags=re.I,
            )[0]
            if not any(re.search(pattern, following, re.I) for _, pattern in _KINDS):
                events.append((conjunction.end(), "generic"))
    return events


def _procedure_requested(text: str) -> bool:
    return bool(
        re.match(
            r"\s*(?:provide|give|list|state)\s+all\s+instructions\s+for\b",
            _without_preface(text),
            re.I,
        )
    ) or bool(
        re.search(
            r"\b(?:how\s+(?:do|does|can|should)\s+(?:I|we|you)|procedure|steps?|walk\s+me\s+through|(?:complete|full|ordered)\s+(?:ordered\s+)?method)\b",
            text,
            re.I,
        )
    )


def _procedure_topic(text: str) -> str:
    carry = re.match(
        r"\s*How\s+do\s+I\s+carry\s+out\s+the\s+complete\s+ordinary\s+routine\s+at\s+(?:the\s+)?([^?;.]+)",
        text,
        re.I,
    )
    if carry:
        return _clean(carry.group(1))
    phrasal = re.search(
        r"\bhow\s+(?:do|does|can|should)\s+(?:I|we|you)\s+([\w-]+\s+(?:back|up|down|out|off|on|over|in|away|through)\s+[^?;.]+)",
        text,
        re.I,
    )
    if phrasal:
        return _clean(phrasal.group(1))
    direct = re.search(
        r"\bhow\s+(?:do|does|can|should)\s+(?:I|we|you)\s+(?:run|perform|conduct|complete)\s+([^?;.]+)",
        text,
        re.I,
    )
    scoped = re.search(
        r"\b(?:procedure|method|steps?|instructions)\b.{0,40}?\b(?:for|of)\s+([^,?;.]+)",
        text,
        re.I,
    )
    command = re.sub(
        r"^\s*(?:(?:give|provide|list|state|describe|I\s+need)\s+)?(?:(?:the|a|an|complete|full|all|ordered)\s+)*",
        "",
        text,
        flags=re.I,
    )
    adjectival = re.match(r"(.+?)\s+procedure\b", command, re.I)
    match = direct or scoped or adjectival
    if not match:
        return ""
    topic = re.split(
        r",\s*(?:including|covering)|\s+with\s+(?!no\b)",
        match.group(1),
        maxsplit=1,
        flags=re.I,
    )[0]
    topic = re.sub(r"\s+in\s+order$", "", topic, flags=re.I)
    return re.sub(r"^(?:the|a|an)\s+", "", _clean(topic), flags=re.I)


def _phrasal_action(text: str) -> tuple[str, str, str] | None:
    action = re.fullmatch(
        r"([\w-]+)\s+(back|up|down|out|off|on|over|in|away|through)\s+(.+)", text, re.I
    )
    return (action.group(1), action.group(2), action.group(3)) if action else None


def _identity_request(text: str) -> tuple[str, str] | None:
    patterns = (
        ("identity_name", r"\s*what\s+is\s+(?:the\s+)?name\s+of\s+(.+?)[?.]*\s*"),
        ("identity_called", r"\s*what\s+is\s+(.+?)\s+called[?.]*\s*"),
        ("identity_command", r"\s*name\s+(.+?)[?.]*\s*"),
    )
    for kind, pattern in patterns:
        match = re.fullmatch(pattern, text, re.I)
        if match:
            if kind == "identity_command" and any(
                re.search(attribute, match.group(1), re.I) for _, attribute in _KINDS
            ):
                continue
            return kind, _clean(match.group(1))
    return None


def _nominal_segments(
    question: str, start: int, end: int
) -> list[tuple[int, int, str]]:
    text = question[start:end]
    preface = _PREFACE.match(text)
    body_start = preface.end() if preface else 0
    body = text[body_start:]
    context = (
        re.sub(r"^(?:the|a|an)\s+", "", preface.group(1), flags=re.I) if preface else ""
    )
    if _procedure_requested(text) or not re.match(
        r"\s*(?:give|name|list|state|report|include|identify|supply|provide|I\s+need|what\s+(?:is|are))\b",
        body,
        re.I,
    ):
        return [(start, end, context)]
    parts = []
    left = start
    for boundary in re.finditer(
        r",\s*(?:and\s+)?|\s+(?:and|as\s+well\s+as)\s+", body, re.I
    ):
        if re.match(
            r"(?:excluding|rather\s+than|except|instead\s+of)\b",
            body[boundary.end() :],
            re.I,
        ):
            continue
        if re.fullmatch(
            r"keeping\s+(?:the\s+)?allocation\s+units[?.!]*",
            body[boundary.end() :],
            re.I,
        ):
            continue
        parts.append((left, start + body_start + boundary.start()))
        left = start + body_start + boundary.end()
    parts.append((left, end))
    preceding = " ".join(question[a:b] for a, b in parts[:-1])
    shared = context or (
        ""
        if re.search(r"\b(?:for|of)\b", preceding, re.I)
        else _topic(question[parts[-1][0] : end], "")
    )
    return [(a, b, shared) for a, b in parts]


def _request_segments(question: str) -> list[tuple[int, int, str]]:
    scheduling = _scheduling_context(question)
    if scheduling:
        offset = scheduling.end()
        subject = _clean(scheduling.group("subject"))
        return [
            (0 if index == 0 else first + offset, last + offset, subject)
            for index, (first, last, _) in enumerate(
                _request_segments(question[offset:])
            )
        ]
    result = []
    left = 0
    preface = _PREFACE.match(question)
    boundaries = sorted(
        list(_SPLIT.finditer(question)) + list(_IMPERATIVE_SPLIT.finditer(question)),
        key=lambda m: (m.start(), -m.end()),
    )
    for boundary in boundaries:
        if boundary.start() < left:
            continue
        if preface and boundary.start() < preface.end():
            continue
        if re.fullmatch(
            r"\s*(?:when(?!\s+(?:does|do|will|did)\b)|if)\s+[^,]+",
            question[left : boundary.start()],
            re.I,
        ):
            continue
        if re.fullmatch(
            r"\s*what\s+are\s+they[?.!]*\s*", question[boundary.end() :], re.I
        ):
            continue
        if re.fullmatch(
            r"\s*when,\s*including\s+the\s+day\s+of\s+the\s+week",
            question[left : boundary.start()],
            re.I,
        ):
            continue
        if _procedure_requested(question[left : boundary.start()]) and re.match(
            r"\s*where\s+to\b", question[boundary.end() :], re.I
        ):
            continue
        result.extend(_nominal_segments(question, left, boundary.start()))
        left = boundary.end()
    result.extend(_nominal_segments(question, left, len(question)))
    return result


def _quantity_attribute(original: str) -> str:
    composed = _composed_quantity(original)
    if composed is not None:
        return composed
    counted = re.search(
        r"\bhow\s+many\s+(.+?)\s+(?:does|do|are|is|go\s+into)\b", original, re.I
    )
    if counted:
        return counted.group(1).strip()
    full = re.search(
        r"\bnumber\s+of\s+(.+?)(?=\s+(?:in|for|of)\s+|[?.!]|$)", original, re.I
    )
    if full:
        return full.group(1).strip()
    noun = re.search(r"\b(?:([\w-]+)\s+count|number\s+of\s+([\w-]+))", original, re.I)
    return next((v for v in noun.groups() if v), "count") if noun else "count"


def _attribute(kind: str, original: str) -> str:
    if kind == "quantity":
        if _allocation_requested(original) and _quantity_attribute(original) == "count":
            return "source_units"
        return _quantity_attribute(original)
    if kind == "generic":
        generic = _generic_request(original)
        return generic[2] if generic else "generic"
    if kind == "duration":
        unit = re.search(
            r"\b(?:how\s+many|length\s+in)\s+(seconds?|minutes?|hours?|days?|weeks?)\b",
            original,
            re.I,
        )
        if unit:
            return unit.group(1)
    return kind


_CONDITION = re.compile(
    r"\b(?:if|unless|except|under|provided\s+that|only\s+when)\b.+", re.I
)


def _contextual_question(
    kind: str,
    topic: str,
    original: str,
    relation: str,
    attribute: str,
    previous_input: str,
    inherited_topic: str,
) -> str:
    repeated = re.search(
        r"\b(?:how\s+long|(?:what|which)\s+(?:time|day))\s+"
        r"(?:does|will|did)\s+((?:a|an)\s+[\w-]+)\s+"
        r"(?:last|take|start|begin|open)\b",
        original,
        re.I,
    )
    if repeated is None or not _same_indefinite_head(
        repeated.group(1), inherited_topic
    ):
        prepared = _prepared(kind, topic, original, relation, attribute)
        constraint = re.search(
            r"\b(?:excluding|rather\s+than|instead\s+of)\s+.+", original, re.I
        )
        return (
            prepared.rstrip("?.!") + ", " + constraint.group(0)
            if constraint and kind in {"weekday", "start_time"}
            else prepared
        )
    first, last = repeated.span(1)
    bound_input = original[:first] + topic + original[last:]
    prepared = _prepared(kind, topic, bound_input, relation, attribute)
    condition = _CONDITION.search(previous_input.strip().rstrip("?.!"))
    if condition and not _CONDITION.search(bound_input):
        return prepared.rstrip("?.!") + " " + condition.group(0) + "?"
    return prepared


def _coverage_inherited_scope(shared: str, active: str) -> str:
    return (
        active
        if shared and active == f"{shared} ordinary operation"
        else shared or active
    )


def _coverage_dependency(kind: str, original: str, owner: str | None):
    if kind == "availability" and _consultation_requested(original):
        return (kind, (owner,)) if owner else ("generic", ())
    return kind, ()


def plan_requirements(
    question: str, *, reading_profile: str = "clause_bound_v1"
) -> tuple[Requirement, ...]:
    """Plan supported atomic attributes without mutating any original input.

    This is a bounded English grammar. An unrecognized conjunct is retained as
    generic, so the caller can conservatively refuse instead of losing it.
    """
    if reading_profile == "contextual_source_v2":
        raise ValueError(
            "Linguistic request planning requires an actual parser capture"
        )
    if reading_profile != "clause_bound_v1":
        from app.evidence_policy import reading_version
        from app.services.contextual_requirements import plan_contextual_requirements

        reading_version(reading_profile)
        return plan_contextual_requirements(question)
    return _plan_clause_bound_requirements(question)


def _plan_clause_bound_requirements(question: str) -> tuple[Requirement, ...]:
    spans = _request_segments(question)
    result: list[Requirement] = []
    active_topic = ""
    previous_input = ""
    responsible_id: str | None = None
    deputy_id: str | None = None
    deputy_topic = ""
    for start, end, shared_topic in spans:
        original = question[start:end]
        procedure = _procedure_requested(original)
        workspace = re.search(
            r"\b(?:in|from)\s+(?:the\s+)?workspace\s+[\"']?([\w-]+)",
            original + " " + shared_topic,
            re.I,
        )
        inherited_topic = _coverage_inherited_scope(shared_topic, active_topic)
        topic = _coverage_topic(
            _topic(original, inherited_topic), original, inherited_topic
        )
        if topic:
            active_topic = topic
        events = _events(original, procedure)
        for _, kind in events:
            identifier = f"r{len(result) + 1}"
            kind, dependency = _coverage_dependency(kind, original, responsible_id)
            if kind == "availability" and _cover_events(_planning_body(original)):
                if deputy_id and _scope_key(topic) == _scope_key(deputy_topic):
                    dependency = (deputy_id,)
                else:
                    kind = "generic"
            if (
                kind in {"availability", "deputy"}
                and re.search(
                    r"\b(?:that\s+role|that\s+person|that\s+owner)\b", original, re.I
                )
                and responsible_id
            ):
                dependency = (responsible_id,)
            relation = _relation(original, kind)
            attribute = _attribute(kind, original)

            result.append(
                Requirement(
                    identifier,
                    original,
                    start,
                    end,
                    _contextual_question(
                        kind,
                        topic,
                        original,
                        relation,
                        attribute,
                        previous_input,
                        inherited_topic,
                    ),
                    kind,
                    topic,
                    _requirement_anchors(topic),
                    dependency,
                    relation,
                    attribute,
                    workspace.group(1) if workspace else None,
                )
            )
            if kind == "owner":
                responsible_id = identifier
            if kind == "deputy":
                deputy_id = identifier
                deputy_topic = topic
            if len(result) > 8:
                raise ValueError("requirement_limit")
        previous_input = original
    return _semantic_requirements(tuple(result))


def _without_preface(text: str) -> str:
    preface = _PREFACE.match(text)
    return text[preface.end() :] if preface else text


def _count_as_parts(text: str) -> tuple[str, str, str] | None:
    match = re.fullmatch(
        r"\s*(does|do)\s+(.+?)\s+count(?:\s+as\s+(.+?))?[?.]*\s*",
        _without_preface(text),
        re.I,
    )
    return (
        (match.group(1), _clean(match.group(2)), _clean(match.group(3) or ""))
        if match
        else None
    )


def _count_as_requirement(req: Requirement, previous: str) -> Requirement:
    parts = _count_as_parts(req.original_text)
    if parts is None:
        return req
    auxiliary, subject, target = parts
    target = target or previous
    if not target:
        return replace(req, kind="generic", question=req.original_text)
    scope = req.topic
    preface = _PREFACE.match(req.original_text)
    if preface:
        scope = preface.group(1)
    prefix = f"For {scope}, " if scope else ""
    topic = prefix + subject
    return replace(
        req,
        question=f"{prefix}{auxiliary} {subject} count as {target}?",
        topic=topic,
        anchors=_requirement_anchors(topic),
        attribute=target,
    )


def _operand_requirements(req: Requirement) -> list[Requirement]:
    body = _without_preface(req.original_text)
    match = re.fullmatch(r"\s*how\s+many\s+(.+?)\s+are\s+(.+?)[?.]*\s*", body, re.I)
    if match is None or not re.search(r"\s+and\s+", match.group(2), re.I):
        return [req]
    if re.match(r"\w+(?:ed|en|wn)\s+by\b", match.group(2), re.I):
        preface = _PREFACE.match(req.original_text)
        scope = preface.group(1) if preface else req.topic
        return [
            replace(
                req,
                kind="generic",
                question=req.original_text,
                relation="generic",
                topic=scope,
                anchors=_requirement_anchors(scope),
            )
        ]
    units = match.group(1)
    operands = re.split(r"\s+and\s+", match.group(2), flags=re.I)
    preface = _PREFACE.match(req.original_text)
    prefix = (
        req.original_text[: preface.end()].strip() + " "
        if preface
        else (f"For {req.topic}, " if req.topic else "")
    )
    return [
        replace(
            req,
            question=f"{prefix}how many {units} are {operand}?",
            topic=prefix + operand,
            anchors=_requirement_anchors(prefix + operand),
            attribute=units,
            relation="operand_count",
        )
        for operand in operands
    ]


def _semantic_requirements(
    requirements: tuple[Requirement, ...],
) -> tuple[Requirement, ...]:
    result = []
    mapping = {}
    previous_count_target = ""
    for req in requirements:
        mapping[req.id] = f"r{len(result) + 1}"
        req = replace(req, depends_on=tuple(mapping[x] for x in req.depends_on))
        if req.kind == "boolean" and req.relation == "count_as":
            req = _count_as_requirement(req, previous_count_target)
            previous_count_target = req.attribute
        req = _boolean_input_subject(req, result)
        req = _remaining_requirement(req, result) or req
        dependent = _dependent_count_requirements(req, result)
        mapping_items = _mapping_requirements(req)
        items = (
            dependent
            if dependent is not None
            else mapping_items
            if mapping_items is not None
            else (_operand_requirements(req) if req.kind == "quantity" else [req])
        )
        for item in items:
            result.append(replace(item, id=f"r{len(result) + 1}"))
            if len(result) > 8:
                raise ValueError("requirement_limit")
    return tuple(result)


def _mapping_requirements(req: Requirement) -> list[Requirement] | None:
    if req.kind != "generic":
        return None
    mapping = re.fullmatch(
        r"\s*(what|which)\s+([\w -]+?)\s+corresponds?\s+to\s+"
        r"(?:the\s+)?(?:(?:two|both|2)\s+)?([\w-]+s)\s+"
        r"([\w-]+)\s+and\s+([\w-]+)[?.!]*\s*",
        _without_preface(req.original_text),
        re.I,
    )
    if mapping is None:
        return None
    wh, output, units, first, second = mapping.groups()
    if re.search(
        r"\b(?:and|or|if|under|with|for|in|unless)\b|"
        r"(?:ss|us|is|ies|ves|oes|[sxz]es|ches|shes)$",
        units,
        re.I,
    ):
        return None
    preface = _PREFACE.match(req.original_text)
    prefix = req.original_text[: preface.end()] if preface else ""
    scope = f" in {preface.group(1)}" if preface else ""
    unit = units.removesuffix("s")
    return [
        replace(
            req,
            question=f"{prefix}{wh} {output} correspond to {unit} {operand}?",
            topic=f"{output} for {unit} {operand}{scope}",
            anchors=_requirement_anchors(prefix + output),
            relation="mapping",
            attribute=output,
        )
        for operand in (first, second)
    ]


def _boolean_input_subject(
    req: Requirement, preceding: list[Requirement]
) -> Requirement:
    if req.kind != "boolean" or not preceding:
        return req
    copular = _copular_input_subject(req, preceding[-1])
    if copular:
        return copular
    subject = _input_subject(preceding[-1].original_text)
    if not subject:
        return req
    body = _without_preface(req.original_text)
    pronoun = re.fullmatch(
        r"(may|can|must|should|does|do|is|are)\s+it\b(.+)", body, re.I
    )
    demonstrative = re.fullmatch(
        r"(may|can|must|should|does|do|is|are)\s+(?:this|that)\s+"
        r"([\w -]+?)\s+(describe|use|represent|encode|store|contain|hold|mean|"
        r"allow|require)\b(.+)",
        body,
        re.I,
    )
    if pronoun:
        # A property owner's namespace is not the referent of a bare "it".
        if not re.match(
            r"\s*how\s+(?:does|do)\b",
            _without_preface(preceding[-1].original_text),
            re.I,
        ):
            return req
        question = f"{pronoun.group(1)} {subject}{pronoun.group(2)}"
    elif demonstrative:
        subject += " " + demonstrative.group(2)
        question = (
            f"{demonstrative.group(1)} {subject} "
            f"{demonstrative.group(3)}{demonstrative.group(4)}"
        )
    else:
        return req
    preface = _PREFACE.match(req.original_text)
    prefix = req.original_text[: preface.end()] if preface else ""
    return replace(
        req,
        question=prefix + question,
        topic=subject,
        anchors=_requirement_anchors(prefix + subject),
    )


def _copular_input_subject(
    req: Requirement, previous: Requirement
) -> Requirement | None:
    previous_body = _without_preface(previous.original_text).strip().rstrip("?.!")
    if re.search(r"[?!.;]", previous_body):
        return None
    pronoun = re.fullmatch(
        r"(is|are)\s+it\b(.+)", _without_preface(req.original_text), re.I
    )
    antecedent = re.fullmatch(
        r"(?:is|are)\s+((?:a|an|the)\s+[\w-]+(?:\s+[\w-]+)*?)\s+"
        r"(?:a|an)\s+.+",
        previous_body,
        re.I,
    )
    if pronoun is None or antecedent is None:
        return None
    subject = antecedent.group(1)
    if re.search(r"\b(?:and|or)\b", subject, re.I):
        return None
    old_scope = _PREFACE.match(previous.original_text)
    new_scope = _PREFACE.match(req.original_text)
    if new_scope and (
        old_scope is None
        or new_scope.group(1).casefold() != old_scope.group(1).casefold()
    ):
        return None
    prefix = previous.original_text[: old_scope.end()] if old_scope else ""
    scope = f" in {old_scope.group(1)}" if old_scope else ""
    topic = subject + scope
    return replace(
        req,
        question=f"{prefix}{pronoun.group(1)} {subject}{pronoun.group(2)}",
        topic=topic,
        anchors=_requirement_anchors(topic),
    )


def _remaining_requirement(
    req: Requirement, preceding: list[Requirement]
) -> Requirement | None:
    remaining = re.fullmatch(
        r"\s*how\s+many\s+([\w -]+?)\s+remain[?.!]*\s*",
        _without_preface(req.original_text),
        re.I,
    )
    if remaining is None:
        return None
    counted = remaining.group(1)
    unresolved = replace(
        req,
        kind="generic",
        relation="unresolved:remain",
        attribute=counted,
        topic="",
        question=req.original_text,
        anchors=_requirement_anchors(req.original_text),
    )
    if not preceding:
        return unresolved
    previous = preceding[-1]
    condition = re.fullmatch(
        r"(?:is|are)\s+((?:a|an|the)\s+([\w-]+)\s+that\s+.+?)\s+"
        r"(?:not\s+)?(?:split|merged|retained|removed|closed|kept|discarded|"
        r"duplicated|preserved|unchanged|valid|allowed)[?.!]*\s*",
        _without_preface(previous.original_text),
        re.I,
    )
    if condition is None or counted.casefold() not in {
        condition.group(2).casefold(),
        condition.group(2).casefold() + "s",
    }:
        return unresolved
    old_scope = _PREFACE.match(previous.original_text)
    new_scope = _PREFACE.match(req.original_text)
    if new_scope and (
        old_scope is None
        or new_scope.group(1).casefold() != old_scope.group(1).casefold()
    ):
        return unresolved
    description = condition.group(1)
    prefix = previous.original_text[: old_scope.end()] if old_scope else ""
    scope = f" in {old_scope.group(1)}" if old_scope else ""
    topic = description + scope
    return replace(
        req,
        question=f"{prefix}for {description}, how many {counted} remain?",
        topic=topic,
        anchors=_requirement_anchors(topic),
        relation="quantity:remain",
        attribute=counted,
    )


def _dependent_count_requirements(
    req: Requirement, preceding: list[Requirement]
) -> list[Requirement] | None:
    """Bind only an explicit backward selection, never guess a missing noun.

    The selected class must occur in the immediately preceding literal have/has
    question. A missing counted object remains unresolved: an "extra day" in a
    selection predicate does not establish whether the ellipsis asks for extra
    days or total days. More complicated selection predicates remain unresolved.
    """
    body = _without_preface(req.original_text).strip()
    if not re.match(r"how\s+many\b", body, re.I):
        return None
    if not re.match(r"how\s+many\s+(?:do|does)\b", body, re.I) and not re.search(
        r"\bdo\s+(?:those|these)\b", body, re.I
    ):
        return None
    dependent = re.fullmatch(
        r"how\s+many(?:\s+([\w -]+?))?\s+do\s+(?:those|these)"
        r"(?:\s+and\s+the\s+other\s+([\w-]+))?\s+have[?.!]*",
        body,
        re.I,
    )
    previous = preceding[-1] if preceding else None
    selection = (
        re.fullmatch(
            r"\s*(?:which|what)\s+([\w-]+)\s+(?:have|has)\s+"
            r"(?:a|an)\s+([\w -]+?)[?.!]*\s*",
            _without_preface(previous.original_text),
            re.I,
        )
        if previous is not None and previous.kind == "generic"
        else None
    )
    if (
        dependent is None
        or selection is None
        or previous is None
        or (
            dependent.group(2)
            and dependent.group(2).casefold() != selection.group(1).casefold()
        )
    ):
        return [
            replace(req, kind="generic", relation="generic", question=req.original_text)
        ]
    # Do not re-interpret a conditioned or nested predicate as a simple noun.
    if re.search(
        r"\b(?:if|unless|with|and|or|that|which|for|in|under)\b",
        selection.group(2),
        re.I,
    ):
        return [
            replace(req, kind="generic", relation="generic", question=req.original_text)
        ]
    preface = _PREFACE.match(previous.original_text)
    scope = preface.group(1) if preface else ""
    topic = selection.group(1) + (f" in {scope}" if scope else "")
    base = replace(
        req,
        kind="quantity",
        topic=topic,
        attribute=_clean(dependent.group(1) or "count"),
        depends_on=(previous.id,),
        relation="selected_count",
        question=req.original_text,
        anchors=_requirement_anchors(topic),
    )
    return (
        [base, replace(base, relation="other_count")] if dependent.group(2) else [base]
    )


_OWNER_RELATIVE_EXCLUDED = re.compile(
    r"\b(?:personal|private|HR|human\s+resources|proxy|assistant|aide|alias|"
    r"separately|separate|independently|appointed|appointment)\b",
    re.I,
)


def _scope_key(text: str) -> str:
    return re.sub(r"^(?:the|a|an)\s+", "", _clean(text), flags=re.I).casefold()


def _paired_owner_scope(owner: Requirement) -> bool:
    body = _clean(_without_preface(owner.original_text))
    direct = re.fullmatch(
        r"(?:who|which\s+role)\s+owns\s+(.+)|"
        r"who\s+is\s+(?:the\s+)?owner\s+(?:of|for)\s+(.+)",
        body,
        re.I,
    )
    if direct:
        target = next(value for value in direct.groups() if value is not None)
        return target.casefold() == "it" or _scope_key(target) == _scope_key(
            owner.topic
        )
    nominal = re.fullmatch(
        r"(?:give|name|list|state|provide|supply)\s+(?:both\s+)?(?:the\s+)?"
        r"(?:([\w-]+)\s+)?owner(?:\s+(?:of|for)\s+(.+))?",
        body,
        re.I,
    )
    if nominal is None:
        return False
    label, target = nominal.groups()
    if target and _scope_key(target) != _scope_key(owner.topic):
        return False
    stem = re.split(
        r"\s+(?:of|in|under|with|for|at)\s+", owner.topic, maxsplit=1, flags=re.I
    )[0]
    return label is None or label.casefold() == stem.split()[-1].casefold()


def _paired_deputy_scope(deputy: Requirement) -> bool:
    body = _clean(_without_preface(deputy.original_text))
    match = re.fullmatch(
        r"(?:(?:who|which\s+role)\s+(?:is|acts?\s+as|serves?\s+as)\s+)?"
        r"(?:the\s+)?deputy(?:\s+role)?(?:\s+(?:of|for)\s+(.+))?",
        body,
        re.I,
    )
    return bool(
        match
        and (
            match.group(1) is None
            or _scope_key(match.group(1)) == _scope_key(deputy.topic)
        )
    )


def _owner_relative_pair(owner: Requirement, deputy: Requirement) -> bool:
    if not all(
        (
            owner.kind == "owner",
            owner.relation in {"owner", "owns"},
            deputy.kind == "deputy",
            deputy.relation == "deputy",
            not owner.depends_on,
            not deputy.depends_on,
            bool(owner.topic),
            _scope_key(owner.topic) == _scope_key(deputy.topic),
            owner.source_workspace == deputy.source_workspace,
            owner.anchors == deputy.anchors,
            owner.input_end <= deputy.input_start <= owner.input_end + 16,
            not owner.original_text.rstrip().endswith(("?", ".", "!", ";")),
        )
    ):
        return False
    if _OWNER_RELATIVE_EXCLUDED.search(
        owner.original_text + " " + deputy.original_text + " " + owner.topic
    ):
        return False
    return _paired_owner_scope(owner) and _paired_deputy_scope(deputy)


def owner_relative_alternatives(
    requirements: tuple[Requirement, ...],
) -> tuple[Requirement, ...]:
    """Expose a scoped interpretation without replacing direct requirements.

    This is not role transitivity or support. A caller must validate the owner
    witness, pin that exact value, preserve this scope, and prove the separate
    deputy-of-owner edge before recording the owner-relative interpretation.
    """
    if len({req.id for req in requirements}) != len(requirements):
        return ()
    alternatives = []
    for owner, deputy in zip(requirements, requirements[1:], strict=False):
        owners = [
            req
            for req in requirements
            if req.kind == "owner" and _scope_key(req.topic) == _scope_key(deputy.topic)
        ]
        if len(owners) != 1 or not _owner_relative_pair(owner, deputy):
            continue
        alternatives.append(
            replace(
                deputy,
                relation="owner_relative_deputy",
                depends_on=(owner.id,),
                question=f"Who is the deputy of the owner of {deputy.topic}?",
            )
        )
    return tuple(alternatives)


def _resolve_owner_relative(req: Requirement, value: str) -> Requirement:
    if _OWNER_RELATIVE_EXCLUDED.search(value):
        raise ValueError("unsupported_owner_relative_target")
    return replace(
        req,
        question=f"For {req.topic}, who is the deputy of {value}?",
        topic=value,
        anchors=tuple(dict.fromkeys(req.anchors + _requirement_anchors(value))),
    )


def _resolved_role_dependency(req: Requirement, value: str) -> Requirement | None:
    if req.kind == "availability" and req.relation == "consultation_window":
        return replace(
            req,
            question=f"When is {value} available for consultations?",
            topic=value,
            anchors=_requirement_anchors(value),
        )
    if req.kind == "availability" and req.relation == "cover_window":
        return replace(
            req,
            question=(
                f"For {req.topic}, under what day-and-time restriction "
                f"may {value} cover?"
            ),
            topic=value,
            anchors=tuple(dict.fromkeys(req.anchors + _requirement_anchors(value))),
        )
    if req.kind == "deputy" and req.relation == "owner_relative_deputy":
        return _resolve_owner_relative(req, value)
    return None


def resolve_requirement(req: Requirement, values: dict[str, str]) -> Requirement:
    if not req.depends_on:
        return req
    for identifier in req.depends_on:
        if identifier not in values or not values[identifier].strip():
            raise ValueError(f"missing_dependency:{identifier}")
    if len(req.depends_on) != 1:
        raise ValueError("unsupported_dependency")
    value = values[req.depends_on[0]].strip()
    resolved = _resolved_role_dependency(req, value)
    if resolved is not None:
        return resolved
    if req.kind == "quantity" and req.relation in {"selected_count", "other_count"}:
        if req.attribute == "count":
            raise ValueError("unsupported_dependency")
        noun_class, _, scope = req.topic.partition(" in ")
        subject = (
            value
            if req.relation == "selected_count"
            else f"{noun_class} other than {value}"
        )
        prefix = f"In {scope}, " if scope else ""
        return replace(
            req,
            question=f"{prefix}What is the {req.attribute} count for {subject}?",
            topic=subject + (f" in {scope}" if scope else ""),
            anchors=_requirement_anchors(subject + " " + scope),
        )
    if req.kind not in {"availability", "deputy"}:
        raise ValueError("unsupported_dependency")
    anchors = _requirement_anchors(value)
    if req.kind == "deputy":
        anchors = tuple(dict.fromkeys(req.anchors + anchors))
    return replace(
        req,
        question=f"Who deputizes for {value}?"
        if req.kind == "deputy"
        else f"During which hours is {value} present?",
        topic=value,
        anchors=anchors,
    )
