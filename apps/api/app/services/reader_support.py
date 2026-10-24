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
            r"(?:time|date|day|schedule)\s*[?.]*$",
            question,
            re.I,
        )
    )


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
