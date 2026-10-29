"""Pure source-declared paragraph grammar, shared by producer and record replay.

Paragraph ordinals are source order, not inferred numbered instructions. This
module proposes structural obligations; it never assesses truth or authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

CONTRACT = "declared-paragraph-procedure-v1"
STRUCTURE = "declared_paragraphs"
PATTERN = "complete-declared-paragraph-procedure-v1"
_SMALL = (
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_ORDINAL = (
    "zeroth first second third fourth fifth sixth seventh eighth ninth tenth "
    "eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth "
    "eighteenth nineteenth"
).split()
_COUNTS = {word: i for i, word in enumerate(_SMALL)}
_ORDINALS: dict[int, str] = dict(enumerate(_ORDINAL))
for _ten, _word in ((20, "twenty"), (30, "thirty")):
    _COUNTS[_word] = _ten
    _ORDINALS[_ten] = _word[:-1] + "ieth"
    for _unit in range(1, min(9, 32 - _ten) + 1):
        _COUNTS[f"{_word}-{_SMALL[_unit]}"] = _ten + _unit
        _ORDINALS[_ten + _unit] = f"{_word}-{_ORDINAL[_unit]}"


class ParagraphRejected(ValueError):
    """Explicit declaration exists but cannot establish a unique complete block."""


_TITLE = re.compile(
    r"\A\s*(?P<scope>[^:\n.!?]+):[ \t]*(?:current[ \t]+)?"
    r"operation[ \t]+note\.?[ \t]*\Z",
    re.I,
)


def _external_procedure_dependency(text: str) -> bool:
    """No referenced procedure is resolved by a declaration of this block's end.

    This subtype has no subprocedure resolver. Refuse explicit required
    execution of a named appendix/annex/attachment procedure; a copied label
    or a prohibition on execution does not assert that dependency.
    """
    action = r"(?:perform|follow|complete|execute|carry\s+out|use|apply)"
    clauses = re.split(
        rf"(?<=[.!?;])\s+|\s+(?:and|but|then)\s+"
        rf"(?=(?:{action}|do\s+not|never)\b)",
        text,
        flags=re.I,
    )
    for sentence in clauses:
        if not re.search(
            r"\b(?:appendix|annex|attachment)\s+[\w-]+\b", sentence, re.I
        ) or not re.search(
            r"\b(?:procedure|subprocedure|method|instructions|steps|protocol)\b",
            sentence,
            re.I,
        ):
            continue
        main = re.sub(
            r"^(?:before|after|if|when|unless|provided)\b[^,]*,\s*",
            "",
            sentence,
            flags=re.I,
        )
        if re.match(
            rf"(?:(?:do|must|shall|should)\s+not|never)\s+{action}\b", main, re.I
        ):
            continue
        if (
            re.match(rf"{action}\b", main, re.I)
            or re.search(
                rf"\b(?:must|shall|should|needs?\s+to|is\s+required\s+to)\s+{action}\b",
                sentence,
                re.I,
            )
            or re.search(
                r"\b(?:(?:do|must|shall|should)\s+not|never)\s+(?:skip|omit)\b|"
                r"\b(?:procedure|subprocedure|method|instructions|steps|protocol)\b.*?"
                r"\b(?:is|are)\s+(?:mandatory|required|a\s+prerequisite)\b|"
                r"\bmust\s+be\s+(?:performed|followed|completed|executed|used|applied)\b",
                sentence,
                re.I,
            )
        ):
            return True
    return False


def _range(start: int, end: int) -> dict[str, int]:
    return {"start": start, "end": end}


def _paragraphs(body: str) -> list[tuple[int, int]]:
    result = []
    cursor = 0
    for boundary in [*re.finditer(r"\n[^\S\n]*\n+", body), None]:
        right = boundary.start() if boundary else len(body)
        left = cursor
        while left < right and body[left].isspace():
            left += 1
        while right > left and body[right - 1].isspace():
            right -= 1
        if left < right:
            result.append((left, right))
        cursor = boundary.end() if boundary else len(body)
    return result


def _count(text: str) -> int | None:
    return (
        int(text) if text.isascii() and text.isdigit() else _COUNTS.get(text.casefold())
    )


def _ordinal(number: int, text: str) -> bool:
    suffix = (
        "th"
        if 10 <= number % 100 <= 20
        else {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    )
    return text.casefold() in {_ORDINALS.get(number), f"{number}{suffix}"}


def _outside_governing(text: str) -> bool:
    """Unknown or governing outside prose cannot disappear behind a delimiter.

    Only declarative context is outside this bounded source grammar. This is a
    rejection filter; it never establishes an action or a permission.
    """
    for sentence in re.findall(r"\S.*?(?:[.!?](?=\s|$)|$)", text, re.S):
        if re.search(r"\b(?:must|shall|required|prerequisites?)\b", sentence, re.I):
            return True
        main = sentence.strip()
        if re.match(r"(?:before|after|if|when|unless|provided)\b", main, re.I):
            if "," not in main:
                return True
            main = main.split(",", 1)[1].strip()
        if re.match(
            r"(?!(?:the|a|an|this|that|it|they|he|she)\b)[\w-]+\s+(?:the|a|an|both|one|\d+)\b",
            main,
            re.I,
        ):
            return True
        if not re.search(
            r"\b(?:is|are|was|were|has|have|can|does|makes|lasts|begins|contains|belongs|belong|remains|applies|apply|identifies|supply|uses|concerns|describes|grant)\b",
            main,
            re.I,
        ):
            return True
    return False


@dataclass(frozen=True)
class DeclaredParagraphs:
    body: str
    scope: str
    mode: str
    conditions: str
    title: tuple[int, int]
    heading: tuple[int, int]
    declaration: tuple[int, int]
    paragraphs: tuple[tuple[int, int], ...]
    end_marker: tuple[int, int]
    governance: tuple[int, int]

    @property
    def start(self) -> int:
        return self.paragraphs[0][0]

    @property
    def end(self) -> int:
        return self.paragraphs[-1][1]

    def record(self, topic: str, original: str) -> dict[str, Any]:
        return {
            "contract": CONTRACT,
            "source_body": self.body,
            "request_topic": topic,
            "request_original": original,
            "scope": self.scope,
            "mode": self.mode,
            "conditions": self.conditions,
            "declared_count": len(self.paragraphs),
            "title_range": _range(*self.title),
            "heading_range": _range(*self.heading),
            "declaration_range": _range(*self.declaration),
            "paragraph_ranges": [_range(*pair) for pair in self.paragraphs],
            "end_marker_range": _range(*self.end_marker),
            "governance_range": _range(*self.governance),
        }


def parse(body: str) -> DeclaredParagraphs | None:  # noqa: C901 - finite source declaration grammar
    parts = _paragraphs(body)
    headings = [
        (
            i,
            re.fullmatch(
                r"Complete (ordinary|standard|normal) procedure", body[a:b], re.I
            ),
        )
        for i, (a, b) in enumerate(parts)
    ]
    headings = [(i, m) for i, m in headings if m]
    if not headings:
        return None
    if len(headings) != 1:
        raise ParagraphRejected("procedure_paragraph_declaration_ambiguous")
    index, heading = headings[0]
    mode = heading.group(1).casefold()
    # Full consumption is deliberate: a namespace prefix never classifies a
    # same-line suffix or another line within the first source paragraph.
    title = _TITLE.fullmatch(body[: parts[0][1]])
    if title is None or index < 1 or index + 1 >= len(parts):
        raise ParagraphRejected("procedure_paragraph_namespace_missing")
    declaration_range = parts[index + 1]
    declaration = body[slice(*declaration_range)]
    match = re.fullmatch(
        rf"The next (?P<count>[\w-]+) instruction paragraphs are the entire {mode} "
        r"procedure, in the stated order\. Its prerequisites, inspection, "
        r"prohibited actions, and final reconciliation are part of completion\. "
        rf"The procedure ends at the explicit End of {mode} procedure marker "
        r"immediately after the (?P<ordinal>[\w-]+) instruction paragraph\. "
        r"It applies to (?P<conditions>[^.!?]+)\.",
        declaration,
        re.I,
    )
    if match is None:
        raise ParagraphRejected("procedure_paragraph_declaration_unverified")
    count = _count(match.group("count"))
    if (
        count is None
        or not 1 <= count <= 32
        or not _ordinal(count, match.group("ordinal"))
    ):
        raise ParagraphRejected("procedure_paragraph_count_unverified")
    start = index + 2
    marker_index = start + count
    marker = f"End of {mode} procedure"
    markers = [
        i for i, (a, b) in enumerate(parts) if body[a:b].casefold() == marker.casefold()
    ]
    if markers != [marker_index] or marker_index + 2 >= len(parts):
        raise ParagraphRejected("procedure_paragraph_closure_unverified")
    if (
        body[slice(*parts[marker_index + 1])].casefold()
        != "record governance commentary"
    ):
        raise ParagraphRejected("procedure_paragraph_tail_unverified")
    governance_start, governance_end = parts[marker_index + 2]
    governance = re.fullmatch(
        rf"The {mode} run is complete once the (?P<count>[\w-]+) preceding "
        r"instruction paragraphs have been satisfied\. The following commentary "
        r"describes separate post-completion record governance, not an additional "
        r"ordinary-run instruction or completion condition\.",
        body[governance_start:governance_end],
        re.I,
    )
    if governance is None or _count(governance.group("count")) != count:
        raise ParagraphRejected("procedure_paragraph_governance_unverified")
    conditions = match.group("conditions")
    if not re.match(rf"(?:an?|the)\s+{mode}\b", conditions, re.I) or re.search(
        r"\b(?:unless|except|provided)\b|\bonly\s+if\b", conditions, re.I
    ):
        raise ParagraphRejected("procedure_paragraph_applicability_unverified")
    if any(_outside_governing(body[a:b]) for a, b in parts[1:index]) or any(
        _outside_governing(body[a:b]) for a, b in parts[marker_index + 3 :]
    ):
        raise ParagraphRejected("procedure_paragraph_outside_governing_material")
    if any(
        _external_procedure_dependency(body[a:b]) for a, b in parts[start:marker_index]
    ):
        raise ParagraphRejected("procedure_paragraph_external_dependency_unresolved")
    return DeclaredParagraphs(
        body,
        title.group("scope").strip(),
        mode,
        conditions,
        (title.start(), title.end()),
        parts[index],
        declaration_range,
        tuple(parts[start:marker_index]),
        parts[marker_index],
        (parts[marker_index + 1][0], len(body)),
    )


def scope_matches(parsed: DeclaredParagraphs, topic: str) -> bool:
    def normal(value):
        return re.sub(r"^(?:the|an?)\s+", "", " ".join(value.casefold().split()))

    expected = normal(parsed.scope)
    requested = normal(topic)
    if requested == expected:
        return True
    if requested.startswith(parsed.mode + " "):
        requested = requested[len(parsed.mode) + 1 :]
    if requested.endswith(" run") and re.search(r"\brun\b", parsed.conditions, re.I):
        requested = requested[:-4]
    return requested == expected and bool(
        re.search(rf"\b{parsed.mode}\b", parsed.conditions, re.I)
    )


def unit_specs(
    parsed: DeclaredParagraphs, topic: str, original: str
) -> tuple[list[dict], list[dict]]:
    """All planned obligations, derived from the exact source before inference."""
    units = []

    def add(name, kind, interval, hypothesis, premise=None):
        units.append(
            {
                "name": name,
                "kind": kind,
                "source_range": _range(*interval),
                "premise_range": _range(*(premise or interval)),
                "hypothesis": hypothesis,
                "step": None,
            }
        )

    add(
        "paragraph_namespace",
        "namespace",
        parsed.title,
        f"This document concerns {parsed.scope}.",
    )
    add(
        "paragraph_declaration",
        "applicability",
        parsed.declaration,
        f"The complete {parsed.mode} procedure applies to {parsed.conditions} "
        f"and requires all {len(parsed.paragraphs)} instruction paragraphs "
        "in their stated order.",
    )
    add(
        "paragraph_requested_scope",
        "request_scope",
        (parsed.title[0], parsed.declaration[1]),
        f"The complete procedure is for {topic}.",
    )
    add(
        "whole_method",
        "whole_method",
        (parsed.start, parsed.end),
        f"Every one of the {len(parsed.paragraphs)} instruction paragraphs is "
        "required, in the stated order, for completion of the "
        f"{parsed.mode} procedure.",
        (parsed.declaration[0], parsed.end),
    )
    add(
        "paragraph_request_constraints",
        "bound_condition",
        (parsed.declaration[0], parsed.end),
        "These complete ordered instructions satisfy the entire procedure request, "
        f"including its material conditions: {original}",
    )
    for i, interval in enumerate(parsed.paragraphs, 1):
        text = parsed.body[slice(*interval)]
        kind = (
            "prohibition"
            if re.match(r"(?:do\s+not|never)\b", text, re.I)
            else "instruction"
        )
        add(
            f"paragraph_{i}",
            kind,
            interval,
            f"The instructions require the following entire instruction: {text}",
        )
    add(
        "paragraph_closure",
        "closure",
        (parsed.end_marker[0], parsed.governance[1]),
        f"The {parsed.mode} procedure ends after exactly {len(parsed.paragraphs)} "
        "instruction paragraphs. The following record governance commentary adds "
        "no ordinary-run instruction or completion condition.",
    )
    edges = [
        {
            "name": "paragraph_governance",
            "source": "paragraph_declaration",
            "target": unit["name"],
        }
        for unit in units
        if unit["name"] != "paragraph_declaration"
    ]
    return units, edges


def seed_matches(
    parsed: DeclaredParagraphs, raw_text: str, raw_range: tuple[int, int]
) -> bool:
    """Require the original full first paragraph, with optional terminal punctuation."""
    left, right = raw_range
    if not isinstance(raw_text, str) or parsed.body[left:right] != raw_text:
        return False
    core = raw_text.strip()
    start = left + len(raw_text) - len(raw_text.lstrip())
    end = right - (len(raw_text) - len(raw_text.rstrip()))
    first, last = parsed.paragraphs[0]
    text = parsed.body[first:last]
    return (start, end, core) == (first, last, text) or (
        text[-1:] in {".", "!", "?"}
        and (start, end, core) == (first, last - 1, text[:-1])
    )
