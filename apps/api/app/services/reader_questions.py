"""Bounded question preparation and obvious evidence mismatches, not entailment.

Only explicit repeated interrogatives are split. Procedure conjunctions remain
intact. Unrecognized grammar is passed to the QA model unchanged. No corpus
identifiers, expected answers or domain-specific synonym tables belong here.
"""

import re
from dataclasses import dataclass

from app.services.reader_support import (
    asks_elapsed,
    binding_rejection,
    requests_procedure,
    temporal_relation_rejection,
)


@dataclass(frozen=True)
class QuestionPart:
    question: str
    anchors: tuple[str, ...]


_OPENERS = frozenset(
    "who what which where when how why is are was were do does did can could "
    "would will should may must please give tell take walk for at in on i "
    "we it its the a an".split()
)
_INTERROGATIVE = r"(?:who|what|which|where|when|how|why|may|can|is|are|does|do)\b"


def named_anchors(question: str) -> tuple[str, ...]:
    # Discourse/command words at sentence starts are grammar. The same spelling
    # inside a proper name (e.g. 'the Copy queue') remains an entity constraint.
    question = re.sub(
        r"(?:^|(?<=[.!?])\s+)(?:please\s+)?"
        r"(?:limit\s+the\s+answer\s+to(?:\s+(?:the\s+)?document\s+titled)?"
        r"|as|from|using|regarding|also|copy|identify|combine)\b",
        " ",
        question,
        flags=re.I,
    )
    return tuple(
        dict.fromkeys(
            token.casefold()
            for token in re.findall(r"\b[A-Z][\w-]*\b", question)
            if token.casefold() not in _OPENERS
        )
    )


def nominal_parts(question: str) -> tuple[list[str], str] | None:
    """Recognize an explicit requested noun list and any shared topic."""
    postposed_topic = ""
    requested_list = re.match(
        r"^(\s*(?:(?:for|at|in|on|as|from|using)\b[^?!;]*?[,:]\s*)?"
        r"(?:please\s+)?)(?:\b(?:give|tell|identify|combine)\s+(?:me\s+)?"
        r"|\bI\s+need\s+(?!to\b))(.+)",
        question,
        re.I,
    )
    if requested_list and not requests_procedure(question):
        items = re.split(
            r"\s*(?:,\s*(?!including\b)(?:(?:and|then|plus|along with)\s+)?"
            r"|\s+and\s+|\s+plus\s+|\s+along with\s+)\s*",
            re.sub(r"^both\s+", "", requested_list.group(2), flags=re.I),
            flags=re.I,
        )
        if items:
            pieces = [
                item if re.match(_INTERROGATIVE, item, re.I) else f"What is {item}"
                for item in items
            ]
            prefix = re.sub(r"\bplease\s*$", "", requested_list.group(1), flags=re.I)
            pieces[0] = prefix + pieces[0]
            for qualifier in re.finditer(
                r"\b(?:for|at|in)\s+([^,;?.]+)", question, re.I
            ):
                if named_anchors(qualifier.group(1)) == named_anchors(question):
                    postposed_topic = qualifier.group(1).strip()
                    break
            return pieces, postposed_topic
    return None


def join_declarative_prefix(pieces: list[str]) -> list[str]:
    if (
        len(pieces) > 1
        and re.match(r"\s*(?:I\s+am|we\s+are)\b", pieces[0], re.I)
        and not re.search(_INTERROGATIVE, pieces[0], re.I)
    ):
        return [pieces[0] + " " + pieces[1], *pieces[2:]]
    return pieces


def question_parts(question: str) -> tuple[QuestionPart, ...]:
    """Split at explicit question boundaries; carry named topic into pronouns."""
    pieces = re.split(
        rf"(?:[,;]\s*(?:and\s+)?|\s+and\s+)(?={_INTERROGATIVE})"
        rf"|(?<=[?.!])\s+(?:also\s+)?(?={_INTERROGATIVE}|give\b|tell\b)",
        question.strip(),
        flags=re.I,
    )
    pieces = join_declarative_prefix(pieces)
    postposed_topic = ""
    expanded = []
    for piece in pieces:
        nominal = nominal_parts(piece)
        if nominal:
            requested, shared_topic = nominal
            expanded.extend(requested)
            postposed_topic = postposed_topic or shared_topic
        else:
            expanded.append(piece)
    pieces = expanded
    # Bound CPU work. Unsupported larger compounds keep the original request;
    # they must not be silently truncated into a successfully answered subset.
    if len(pieces) > 8:
        pieces = [question]
    if (
        len(pieces) > 1
        and re.match(r"\s*(?:for|at|in|on|as|from|using|regarding)\b", pieces[0], re.I)
        and not re.search(_INTERROGATIVE, pieces[0], re.I)
    ):
        pieces = [pieces[0] + ", " + pieces[1], *pieces[2:]]
    preface = re.match(r"\s*(?:for|at|in|on|regarding)\s+([^,:]+)[,:]", question, re.I)
    explicit_topic = preface.group(1) if preface else postposed_topic
    active_anchors = named_anchors(explicit_topic)
    topic = explicit_topic
    rewritten = len(pieces) != 1 or pieces[0] != question
    result = []
    for piece in pieces:
        piece = re.sub(r"^\s*(?:give|tell)\s+(?:me\s+)?", "What is ", piece, flags=re.I)
        own = named_anchors(piece)
        if own:
            active_anchors = own
            # Preserve the actual qualified subject, not just its proper name.
            # Future entities never flow backwards into a pronoun continuation.
            subject = re.search(
                r"\b(?:who|which\s+role|what\s+role)\s+"
                r"(?:is\s+responsible\s+for|\w+)\s+(.+)",
                piece,
                re.I,
            )
            if explicit_topic and set(own).issubset(named_anchors(explicit_topic)):
                topic = explicit_topic
            elif subject:
                topic = subject.group(1)
            else:
                topic = re.sub(
                    r"^\s*(?:what|which|when|where|how)\s+"
                    r"(?:(?:is|are|was|were)\s+)?",
                    "",
                    piece,
                    flags=re.I,
                )
            topic = topic.strip().rstrip("?.;")
        anchors = own or active_anchors
        prepared = piece.strip().rstrip("?.;") + "?"
        if len(pieces) > 1 and not own and topic:
            prepared = f"Regarding {topic}, {prepared}"
        result.append(QuestionPart(prepared if rewritten else question, anchors))
    return tuple(result)


def scope_matches(part: QuestionPart, context: str) -> bool:
    words = set(re.findall(r"\w[\w-]*", context.casefold()))
    return all(anchor in words for anchor in part.anchors)


def selected_clause(context: str, start: int, end: int) -> str:
    """Use the raw span's local clause, rather than a borrowed adjacent fact."""
    for clause in re.finditer(r"[^.!?;\n]+", context):
        if clause.start() <= start < end <= clause.end():
            return clause.group()
    return context[start:end]


def currency_evidence_missing(question: str, clause: str, raw: str) -> bool:
    payment = bool(
        re.search(
            r"\b(?:what\s+(?:exact\s+)?amount|how\s+much)\s+"
            r"(?:must|should|does|do|will|would|can)\b",
            question,
            re.I,
        )
        and re.search(r"\bpay\b", question, re.I)
    )
    if payment or (
        re.search(
            r"\bhow\s+much\b|\bwhat\s+(?:price|cost|fee)\b"
            r"|\bwhat\s+(?:is|are|was|were)\b.+?\b(?:cost|price|fee|insured value)\b"
            r"|\bwhat\s+(?:does|do|will|would)\b.+?\bcost\b",
            question,
            re.I,
        )
        and re.search(r"\b(?:cost|price|fee|insured value)\b", question, re.I)
    ):
        money = r"[$€£¥]|\b(?:dollars?|euros?|pounds?|cents?|free|no charge)\b"
        wrong_unit = r"\b(?:grams?|kilograms?|kg|copies|minutes?|hours?|cm|meters?)\b"
        if not re.search(money, clause, re.I) or (
            re.search(wrong_unit, raw, re.I) and not re.search(money, raw, re.I)
        ):
            return True
    return False


def mismatch_reason(question: str, context: str, start: int, end: int) -> str | None:
    """Reject bounded currency and explicit subject mismatches only.

    This does not certify arbitrary facts. Model null scores and the measured
    synthetic contract remain separate from these conservative surface checks.
    """
    clause = selected_clause(context, start, end)
    raw = context[start:end]
    clock = r"\b\d{1,2}:\d{2}\b"
    weekday = r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b"
    # Exact temporal expressions differ from roles or procedures which merely
    # contain a weekday or clock time.
    temporal = bool(
        re.fullmatch(
            rf"\s*(?:(?:on|at)\s+)?(?:{weekday}(?:\s+at\s+{clock})?|{clock})"
            r"(?:\s*[ap]m)?\s*",
            raw,
            re.I,
        )
    )
    temporal = temporal or bool(
        re.fullmatch(
            rf"\s*(?:(?:on\s+)?{weekday}\s+(?:from|at)\s+|from\s+)?"
            rf"{clock}(?:\s*[ap]m)?\s*(?:to|[-–—])\s*"
            rf"{clock}(?:\s*[ap]m)?\s*",
            raw,
            re.I,
        )
    )
    if re.search(r"\bwho\b", question, re.I) and temporal:
        return "schedule_is_not_a_responsible_party"
    if asks_elapsed(question) and temporal:
        if not re.search(
            rf"(?:duration|elapsed(?:\s+time)?|lasts?\s+for|takes)"
            rf"\s*(?:is|of|:)?\s*{clock}",
            clause,
            re.I,
        ):
            return "start_clock_is_not_elapsed_duration"
    if relation_rejection := temporal_relation_rejection(question, context, start, end):
        return relation_rejection
    if temporal and requests_procedure(question):
        return "appointment_is_not_a_procedure"
    if currency_evidence_missing(question, clause, raw):
        return "currency_evidence_missing"
    # In an explicit 'does X use Y' relationship, Y's rule cannot establish X's
    # participation merely because both entities occur somewhere in a paragraph.
    relation = re.match(
        r"\s*(?:does|do|is|are)\s+(?:the\s+)?(.+?)\s+"
        r"(?:use|uses|follow|follows|using|following)\b",
        question,
        re.I,
    )
    if relation:
        subject = set(re.findall(r"\w+", relation.group(1).casefold()))
        present = subject.issubset(set(re.findall(r"\w+", clause.casefold())))
        if not present and re.match(r"\s*(?:it|they)\s+", clause, re.I):
            preceding = context[:start].split(".")
            antecedent = preceding[-2].strip() if len(preceding) > 1 else ""
            present = bool(
                re.match(
                    r"(?:the\s+)?" + re.escape(relation.group(1)) + r"\b",
                    antecedent,
                    re.I,
                )
            )
        if not present:
            return "relationship_subject_missing_from_selected_clause"
    return binding_rejection(question, context, start, end, exact_temporal=temporal)
