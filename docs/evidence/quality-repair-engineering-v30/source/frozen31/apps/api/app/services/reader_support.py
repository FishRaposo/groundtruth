"""Conservative span mismatch signals; these do not establish entailment.

No aliases, case IDs or answer labels are used. Whole authorized source contexts
still reach the model; these checks never manufacture a replacement prediction.
"""

import re

_GRAMMAR = frozenset(
    "a an the is are was were what which how when where why who to of for in on "
    "and or do does did should can could i we my our please about with from it "
    "its this that be by as into regarding me tell give".split()
)


def request_head(question: str) -> str:
    return re.sub(
        r"^\s*(?:(?:regarding|for|at|in|on)\s+[^,]+,\s*"
        r"|from\s+beginning\s+to\s+end,\s*)",
        "",
        question,
        flags=re.I,
    )


def requests_procedure(question: str) -> bool:
    """Inspect the requested head, never keywords inside the named object."""
    head = re.sub(r"^\s*please\s+", "", request_head(question), flags=re.I)
    return bool(
        re.match(
            r"\s*(?:(?:what|which)\s+(?:(?:are|is)\s+)?"
            r"|(?:give|copy|list|show|describe|explain)\s+(?:me\s+)?)"
            r"(?:(?:all|the|every|complete|ordered|practice|detailed|entire)\s+)*"
            r"(?:steps?|sequence|procedure)(?=\s*(?:[,?.!]|$|"
            r"\b(?:for|to|of|in|after|before|during|at|on)\b))"
            r"|\s*what\s+(?:steps?|sequence|procedure)\s+"
            r"(?:should|must|can|do)\s+(?:I|we)\s+follow\b"
            r"|\s*how\s+(?:do|can|should|would)\s+(?:I|we)\b"
            r"|\s*(?:give|tell)\s+(?:me\s+)?how\s+to\b",
            head,
            re.I,
        )
    )


def asks_elapsed(question: str) -> bool:
    return bool(
        re.search(
            r"\b(?:how\s+long|duration|elapsed\s+time|time\s+"
            r"(?:required|needed|taken)|how\s+many\s+"
            r"(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?))\b",
            request_head(question),
            re.I,
        )
    )


def nominal_session_start(question: str) -> bool:
    return bool(
        re.match(
            r"\s*(?:what|which)\s+(?:(?:is|are)\s+)?"
            r"(?:(?:the|its|their|our)\s+)?(?:session|appointment)\s+start(?:ing)?"
            r"(?:\s+time)?(?=\s*(?:[?.!,;]|$|"
            r"\b(?:for|of|at|in|on|after|before|during)\b))",
            request_head(question),
            re.I,
        )
    )


def session_start_duration_mismatch(
    question: str, context: str, start: int, end: int
) -> bool:
    return bool(
        nominal_session_start(question)
        and re.search(
            r"\b(?:seconds?|minutes?|hours?|days?|weeks?)\b", context[start:end], re.I
        )
        and re.search(
            r"\b(?:takes?|lasts?|duration\s+(?:is|of))\s+"
            r"(?:(?:for|about|approximately|around)\s+)?$",
            context[:start],
            re.I,
        )
    )


def temporal_question(question: str) -> bool:
    return (
        asks_elapsed(question)
        or nominal_session_start(question)
        or bool(
            re.search(
                r"^\s*(?:(?:regarding|for|at|in|on)\s+[^,]+,\s*)?when\b"
                r"|\b(?:what|which)\s+(?:(?:is|are)\s+(?:the\s+)?)?"
                r"(?:time|date|day|schedule|calendar)\b"
                r"|\b(?:what|which)\s+(?:is|are)\s+(?:(?:the|its|their|our)\s+)?"
                r"(?:(?:start|starting|opening|closing|session|scheduled)\s+){1,2}"
                r"(?:time|date|day)\b"
                r"|\b(?:what|which)\s+(?:is|are)\s+(?:the|its|their|our)\s+"
                r"[^?;,]+?\s+"
                r"(?:time|date|day|schedule)\s*[?.]*$"
                r"|\b(?:what|which)\s+(?:is|are)\s+(?:the|its|their|our)\s+"
                r"(?:(?!(?:for|in|of|on|within|during|per|at|from|to|by|before|"
                r"after|under|over|inside|outside|with|without)\b)[\w'-]+\s+){0,8}"
                r"(?:session|time)\s+window\s*[?.]*$",
                question,
                re.I,
            )
        )
    )


def deadline_duration_mismatch(
    question: str, context: str, start: int, end: int
) -> bool:
    if not asks_elapsed(question) or re.search(
        r"\b(?:before|after|until|advance|deadline|cutoff)\b", question, re.I
    ):
        return False
    left, right = clause_bounds(context, start)
    if end > right:
        return False
    return any(
        left + deadline.start(1) <= start < left + deadline.end(1)
        for deadline in re.finditer(
            r"\buntil\b(.+?)\b(?:before|after)\b", context[left:right], re.I
        )
    )


def temporal_relation_rejection(
    question: str, context: str, start: int, end: int
) -> str | None:
    if session_start_duration_mismatch(question, context, start, end):
        return "elapsed_duration_is_not_session_start"
    if deadline_duration_mismatch(question, context, start, end):
        return "relative_deadline_is_not_elapsed_duration"
    return None


def generic_heading_has_topic(
    context: str, lead_start: int, anchors: tuple[str, ...]
) -> bool:
    """Borrow a generic heading's nearest unambiguous named topic.

    A new capitalized subject stops inheritance. Unknown sentence-initial words
    therefore fail conservatively; this is a formatting prior, not coreference
    resolution or permission to accept an otherwise rejected prediction. Only
    paragraph breaks present in the canonical context can stop inheritance;
    ingestion can collapse original layout, which this prior cannot recover.
    """
    preceding = context[:lead_start]
    paragraph_left = max(
        (m.end() for m in re.finditer(r"\n\s*\n", preceding)), default=0
    )
    for sentence in reversed(re.split(r"[.!?;](?:\s+)|\n", preceding[paragraph_left:])):
        words = set(re.findall(r"\b[\w-]+\b", sentence.casefold()))
        named = {
            word.casefold() for word in re.findall(r"\b[A-Z][\w-]*\b", sentence)
        } - _GRAMMAR
        if named - set(anchors):
            return False
        if all(anchor in words for anchor in anchors):
            return True
        if named:
            return False
    return False


def procedure_features(
    question: str,
    context: str,
    *,
    start: int | None = None,
    end: int | None = None,
    anchors: tuple[str, ...] = (),
) -> dict[str, bool | int | str]:
    """Rank only selected sequence evidence, never certify factual support.

    Ingestion canonicalizes whitespace. Numbered items must therefore work
    inline too. A sequence elsewhere in a chunk cannot promote the selected
    span. Named topics occur in its own lead, the immediately preceding topic
    sentence for an empty lead, or a generic heading's nearest named subject.
    Generic heading inheritance stops at another named entity or a paragraph
    break present in canonical context; original layout may already be lost.
    Unknown offsets or unmarked procedures retain the ordinary margin ranking.
    """
    requested = requests_procedure(question)
    markers = list(
        re.finditer(
            r"(?:^|[.!?;:\n]\s*)\s*(first|next|then|finally|last|lastly|"
            r"begin\s+by|after\s+that|finish\s+by)\b[,:\s]+",
            context,
            re.I,
        )
    )
    numbered = list(re.finditer(r"(?<!\S)(\d{1,2})[.)]\s+\S", context))
    bullets = list(re.finditer(r"(?<!\S)([-*])\s+\S", context))
    groups: list[list[tuple[int, int, str]]] = []
    for matches in (markers, numbered, bullets):
        group: list[tuple[int, int, str]] = []
        for match in matches:
            token = " ".join(match.group(1).casefold().split())
            if group and token in {"first", "begin by", "1"}:
                groups.append(group)
                group = []
            group.append((match.start(1), match.end(), token))
        if group:
            groups.append(group)
    sequences = [
        group
        for group in groups
        if len(group) >= 2
        and (group[0][2] in {"-", "*"} or len({item[2] for item in group}) >= 2)
    ]
    selected = False
    valid_offsets = (
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and 0 <= start < end <= len(context)
    )
    if valid_offsets:
        assert start is not None and end is not None
        for group in sequences:
            first, last = group[0][0], group[-1][1]
            following = re.search(r"[.!?;](?=\s|$)", context[last:])
            right = last + following.end() if following else len(context)
            # The heading belongs to this sequence, rather than an earlier
            # booking sentence containing the same named entity.
            lead_start = max(
                (m.end() for m in re.finditer(r"[.!?;](?:\s+)|\n", context[:first])),
                default=0,
            )
            lead = context[lead_start:first].strip()
            if not lead:
                # "Topic sentence. First, ..." has no inline heading. Borrow
                # only that immediately preceding sentence; an explicit other
                # heading must never inherit an earlier topic's named scope.
                preceding = context[:lead_start].rstrip().rstrip(".!?;")
                previous_start = max(
                    (m.end() for m in re.finditer(r"[.!?;](?:\s+)|\n", preceding)),
                    default=0,
                )
                lead = preceding[previous_start:]
            lead_words = set(re.findall(r"\b[\w-]+\b", lead.casefold()))
            topic_bound = all(a in lead_words for a in anchors)
            if not topic_bound and re.fullmatch(
                r"(?:(?:complete|full|ordered|standard|normal|review)\s+)*"
                r"(?:procedure|steps|instructions)\s*:",
                lead,
                re.I,
            ):
                topic_bound = generic_heading_has_topic(context, lead_start, anchors)
            if first <= start < end <= right and topic_bound:
                selected = True
                break
    return {
        "contract": "source-sequence-format-v4",
        "requested": requested,
        "explicit_sequence": bool(sequences),
        "selected_sequence": selected,
        "distinct_sequence_markers": len({m.group(1).casefold() for m in markers}),
        "listed_items": len(numbered) + len(bullets),
    }


def clause_bounds(context: str, position: int) -> tuple[int, int]:
    for match in re.finditer(r"[^.!?;\n]+", context):
        if match.start() <= position < match.end():
            return match.start(), match.end()
    return 0, len(context)


def content_words(text: str) -> list[tuple[str, int, int]]:
    return [
        (match.group().casefold(), match.start(), match.end())
        for match in re.finditer(r"\b\w+\b", text)
        if match.group().casefold() not in _GRAMMAR
    ]


def adjacent_before_steps(question: str, preceding: str, following: str) -> bool:
    """Recognize only an explicit before qualifier and two matching commands.

    Mechanical suffix comparison avoids making a later instruction look like
    an unrelated topic. It is a rejection exemption, never proof of entailment.
    """
    requested = re.match(
        r"\s*(?:what|which)\s+(?:must|should)\s+be\s+([a-z]+)"
        r"\s+before\s+([a-z]+ing)\b",
        question,
        re.I,
    )
    first = re.match(r"\s*([a-z]+)\b", preceding, re.I)
    second = re.match(r"\s*([a-z]+)\b", following, re.I)
    if not requested or not first or not second:
        return False
    if re.search(
        r"\b(?:no|not|never|neither|nor)\b", preceding + " " + following, re.I
    ):
        return False

    def forms(word: str) -> set[str]:
        word = word.casefold()
        candidates = {word, word.removesuffix("e")}
        for suffix in ("ed", "ing"):
            if word.endswith(suffix):
                base = word[: -len(suffix)]
                candidates.add(base)
                if len(base) > 2 and base[-1] == base[-2]:
                    candidates.add(base[:-1])
        return candidates

    return bool(
        forms(requested.group(1))
        & {first.group(1).casefold(), first.group(1).casefold().removesuffix("e")}
        and forms(requested.group(2))
        & {second.group(1).casefold(), second.group(1).casefold().removesuffix("e")}
    )


def topic_introduced_later(question: str, context: str, clause_end: int) -> bool:
    """Reject earlier sibling evidence when an explicit target comes later.

    Matching phrases are a rejection signal only. No match is not a refusal and
    a match never certifies support. Backward-referencing qualifiers are kept.
    """
    query = [word for word, _, _ in content_words(question)]
    source = content_words(context)
    for width in range(min(4, len(query)), 1, -1):
        wanted = {tuple(query[i : i + width]) for i in range(len(query) - width + 1)}
        occurrences = [
            (source[i][1], source[i + width - 1][2])
            for i in range(len(source) - width + 1)
            if tuple(item[0] for item in source[i : i + width]) in wanted
        ]
        if not occurrences:
            continue
        if any(end <= clause_end for _, end in occurrences):
            return False
        for start, _ in occurrences:
            left, right = clause_bounds(context, start)
            selected_start, _ = clause_bounds(context, max(0, clause_end - 1))
            preceding = [
                word for word, _, _ in content_words(context[selected_start:clause_end])
            ]
            following = [word for word, _, _ in content_words(context[left:right])]
            if (
                left >= clause_end
                and re.fullmatch(r"[.!;\s]*", context[clause_end:left])
                and context[right : right + 1] != "?"
                and adjacent_before_steps(
                    question,
                    context[selected_start:clause_end],
                    context[left:right],
                )
            ):
                return False
            # Repetition can bind an instruction to its following explanation:
            # 'Press the green button. The green button resets X.' A phrase is
            # only a reason not to apply this rejection, never proof of support.
            if (preceding and following and preceding[-1] == following[0]) or any(
                preceding[i : i + 2] == following[j : j + 2]
                for i in range(len(preceding) - 1)
                for j in range(len(following) - 1)
            ):
                return False
            if re.search(
                r"\b(?:this|that|these|those|above|same|it|they)\b",
                context[left:right],
                re.I,
            ):
                return False
        return True
    return False


def linked_instruction(context: str, scope_start: int, left: int, right: int) -> bool:
    """Only an immediate, unnamed anaphoric instruction inherits this scope."""
    scope_end = clause_bounds(context, scope_start)[1]
    gap = context[scope_end:left]
    named = {
        word.casefold() for word in re.findall(r"\b[A-Z][\w-]+\b", context[left:right])
    } - {"this", "that"}
    single_letter_topic = re.search(
        r"\b(?:for|about|regarding|under)\s+(?:the\s+)?[A-Z]\b", context[left:right]
    )
    return bool(
        left >= scope_end
        and re.fullmatch(r"[.!;\s]*", gap)
        and not re.search(r"\n\s*\n", gap)
        and re.match(r"\s*(?:this|that)\s+instruction\b", context[left:right], re.I)
        and not named
        and single_letter_topic is None
    )


def plural_reference(noun: str) -> str:
    if re.search(r"[^aeiou]y$", noun):
        return noun[:-1] + "ies"
    if noun.endswith(("s", "x", "z", "ch", "sh")):
        return noun + "es"
    return noun + "s"


def binding_rejection(
    question: str, context: str, start: int, end: int, *, exact_temporal: bool
) -> str | None:
    if exact_temporal and not temporal_question(question):
        return "clock_does_not_establish_requested_attribute"
    left, right = clause_bounds(context, start)
    query_words = {word for word, _, _ in content_words(question)}
    # An adjacent explicit exclusion scopes its own antecedent only. It cannot
    # invalidate a different supported sentence elsewhere in the same chunk.
    for exclusion in re.finditer(
        r"\b(?:this|that|the)\s+([\w-]+)\s+is\s+outside\s+(?:the\s+)?"
        r"((?:(?:standard|normal|regular)\s+)?[^.!?;\n]+)",
        context,
        re.I,
    ):
        antecedent = exclusion.group(1).casefold()
        target = {word for word, _, _ in content_words(exclusion.group(2))}
        target -= {"standard", "normal", "regular"}
        default_scope = bool(
            re.match(r"(?:standard|normal|regular)\b", exclusion.group(2), re.I)
        )
        local_words = {word for word, _, _ in content_words(context[left:right])}
        adjacent = exclusion.start() >= right and re.fullmatch(
            r"[.!;\s]*", context[right : exclusion.start()]
        )
        within = left <= exclusion.start() < right
        continuation = linked_instruction(context, exclusion.start(), left, right)
        if (
            (antecedent in local_words or continuation)
            and not {antecedent, plural_reference(antecedent)} & query_words
            and "outside" not in query_words
            and re.search(
                r"\b(?:procedure|process|policy|workflow|protocol|scope)\s*$",
                exclusion.group(2),
                re.I,
            )
            and (target & query_words or default_scope)
            and (adjacent or within or continuation)
        ):
            return "selected_clause_explicitly_outside_requested_scope"
    if re.search(r"\bwho\b", question, re.I):
        prefix = context[left:start]
        location_object = re.match(
            r"(?:the\s+)?(?:shelf|basket|rack|drawer|cabinet|cupboard|box|trolley)\b",
            context[start:end],
            re.I,
        )
        spatial = location_object and re.search(
            r"\b(?:on|in|inside|under|beneath|beside|at)\s+(?:the\s+)?$", prefix, re.I
        )
        destination = location_object and re.search(
            r"\bto\s+(?:the\s+)?$", prefix, re.I
        )
        if spatial or destination:
            return "spatial_object_does_not_establish_responsible_party"
    if topic_introduced_later(question, context, right):
        return "requested_topic_is_introduced_after_selected_clause"
    return None
