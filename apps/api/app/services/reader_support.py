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


def asks_elapsed(question: str) -> bool:
    return bool(
        re.search(
            r"\b(?:how\s+long|duration|elapsed\s+time|how\s+many\s+"
            r"(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?))\b",
            question,
            re.I,
        )
    )


def temporal_question(question: str) -> bool:
    return asks_elapsed(question) or bool(
        re.search(
            r"^\s*(?:(?:regarding|for|at|in|on)\s+[^,]+,\s*)?when\b"
            r"|\b(?:what|which)\s+(?:(?:is|are)\s+(?:the\s+)?)?"
            r"(?:time|date|day|schedule|calendar)\b"
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
    span. Named topics must occur in its own lead or, only when that
    lead is empty, in the immediately preceding topic sentence.
    Unknown offsets or unmarked procedures retain the ordinary margin ranking.
    """
    head = re.sub(
        r"^\s*(?:regarding|for|at|in|on)\s+[^,]+,\s*", "", question, flags=re.I
    )
    requested = bool(
        re.match(
            r"\s*(?:(?:what|which)\s+(?:(?:are|is)\s+)?(?:the\s+)?"
            r"(?:ordered\s+)?(?:steps?|sequence)\b"
            r"|how\s+(?:do|can|should|would)\s+(?:I|we)\b)",
            head,
            re.I,
        )
    )
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
            if first <= start < end <= right and all(a in lead_words for a in anchors):
                selected = True
                break
    return {
        "contract": "source-sequence-format-v3",
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


def binding_rejection(
    question: str, context: str, start: int, end: int, *, exact_temporal: bool
) -> str | None:
    if exact_temporal and not temporal_question(question):
        return "clock_does_not_establish_requested_attribute"
    left, right = clause_bounds(context, start)
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
