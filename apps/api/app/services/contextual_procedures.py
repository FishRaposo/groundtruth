"""Finite source-declared routine inventory, without a support/publication verdict.

Every source character is covered. Context statements remain unknown, qualified
actions remain qualified, and required external instructions refuse. Consumers
must assess source scope/NLI and bind actual requests, output and authorization;
this module never marks an obligation supported. Replay reconstructs from the
actual immutable source and independently supplied subject, not producer flags.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.evidence_policy import reading_version

_FLAGS = re.IGNORECASE | re.ASCII
_SENTENCE = re.compile(r"\S[\s\S]*?[.!?](?=\s|$)")
_DECLARATION = re.compile(
    r"(?:The following|This) (?:complete (?:ordered )?)?"
    r"(?:routine|procedure|method) applies to (?P<subject>[^.!?,;:\n]+)\.",
    _FLAGS,
)
_QUALIFIED = re.compile(
    r"(?P<condition>(?:If|When|Unless|For|On|During|Before|After|Until|"
    r"Provided that|Only if)\s+[^,;.!?]+),\s+(?P<action>.+)",
    _FLAGS,
)
_TEMPORAL = re.compile(
    r"\s+(?P<condition>(?:before|after|during|when|while|until|only for)\s+)",
    _FLAGS,
)
# A declaration must itself name a namespace: no antecedent is guessed. This is
# deliberately a small positive nominal grammar, not a pronoun synonym screen.
_NAME = r"[A-Z][A-Za-z0-9_-]{0,63}(?:[^\x00-\x7f\s.!?,;:]+)?"
_SUBJECT = re.compile(
    rf"(?P<context>(?i:ordinary|special|regular)) (?P<namespace>{_NAME}) "
    r"(?P<head>(?i:sessions|runs|trials|cycles))"
)
_CONTEXT = re.compile(
    rf"The {_NAME}(?: [^\x00-\x7f\s]+)? station (?:has|uses) "
    r"(?:two|three|four) pads[.!?]"
)
# Every admitted action consumes its WHOLE complement. There is no fallback
# from an unrecognized clause to first-verb recognition or an arbitrary noun.
_PHYSICAL = (
    r"(?:the|a|an|each) (?:(?:inner|outer|upper|lower|short|long|folded|teaching|"
    r"signed|reference) ){0,2}(?:token|block|pad|timer|lamp|pointer|stripe|mark|"
    r"boundary|outline|path|turn|model|run|sheet|checklist|table|desk|tray|box)"
)
_READOUT = r"(?:the|a|an) (?:value|result|tie|mark|number|display|count|reading)"
_LOCATION = rf"(?:on|onto|in|into|from|beside|under) {_PHYSICAL}"
_PHYSICAL_CONDITION = re.compile(_PHYSICAL, _FLAGS)
_ACTION_PRODUCTIONS = tuple(
    (name, re.compile(pattern, _FLAGS))
    for name, pattern in (
        (
            "physical_handling",
            rf"(?:attach|carry|clip|collect|copy|file|hold|initial|inspect|keep|"
            rf"label|lay|leave|lift|lock|mark|move|obtain|omit|open|close|"
            rf"photograph|place|position|press|put|release|remove|retain|return|"
            rf"rotate|save|scan|select|send|set|show|sign|skip|slide|start|stop|"
            rf"reset|submit|take|trace|turn|use) {_PHYSICAL}(?: {_LOCATION})?",
        ),
        (
            "readout_action",
            rf"(?:record|write|log|enter|read|review|count|compare|verify|confirm) "
            rf"{_READOUT}(?: instead of choosing (?:the|a) mark)?",
        ),
        ("physical_path", r"follow the (?:bends of each boundary|outline|path|stripe)"),
        ("preceding_instruction", r"repeat the preceding instruction"),
    )
)
_ACTION_JOIN = re.compile(r"\s*;\s*|\s+(?:and then|and|then)\s+", _FLAGS)
_CONDITION_JOIN = re.compile(r"\s+(?:and|or)\s+", _FLAGS)
_CONDITION_MARKER = re.compile(
    r"(?:provided that|only if|only for|if|when|unless|for|on|during|before|after|"
    r"until|while)\s+",
    _FLAGS,
)
_CONDITION_PREDICATE = re.compile(
    rf"(?:{_PHYSICAL} (?:is (?:dark|lit|green|red|bent|visible|between marks)|"
    rf"rests between marks|(?:crosses|reaches) {_PHYSICAL})|"
    rf"beginning {_PHYSICAL})",
    _FLAGS,
)
_PRECEDING = re.compile(r"\bthe preceding instruction\b", _FLAGS)
_NORMATIVE_REFERENCE = re.compile(
    r"\b(?:appendix|annex|attachment|supplement|manual|protocol|policy|"
    r"instructions?|directions?|guide|handbook|procedure|method|routine|"
    r"rules?|requirements?|sequence|section\s+\w+|steps?|paragraph\s+\d+)\b|"
    r"\b(?:consult|refer\s+to|according\s+to|specified\s+in|as\s+directed|"
    r"as\s+prescribed|as\s+specified)\b",
    _FLAGS,
)
_MATERIAL = re.compile(
    r"\b(?:reference (?:sheet|block)|(?:signed )?checklist)\b", _FLAGS
)


class RoutineRejected(ValueError):
    """No complete finite inventory; offsets, if present, refer to actual source."""

    def __init__(self, code: str, source_range: dict[str, int] | None = None):
        super().__init__(code)
        self.code = code
        self.source_range = source_range


def _range(start: int, end: int) -> dict[str, int]:
    return {"start": start, "end": end}


def _literal(body: str, start: int, end: int) -> dict[str, Any]:
    return {**_range(start, end), "text": body[start:end]}


def _source_identity(body: str, identity: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(body, str) or not body.strip():
        raise RoutineRejected("routine_source_missing")
    try:
        encoded = body.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise RoutineRejected("routine_source_unicode_invalid") from exc
    if len(encoded) > 128 * 1024:
        raise RoutineRejected("routine_source_budget_exceeded")
    required = {"document_id", "document_version", "content_hash"}
    if (
        type(identity) is not dict
        or not required <= identity.keys()
        or (identity.keys() - required - {"workspace_id"})
    ):
        raise RoutineRejected("routine_source_identity_invalid")
    if (
        not isinstance(identity["document_id"], str)
        or not identity["document_id"].strip()
        or type(identity["document_version"]) is not int
        or identity["document_version"] < 1
        or identity["content_hash"] != hashlib.sha256(encoded).hexdigest()
        or (
            "workspace_id" in identity
            and identity["workspace_id"] is not None
            and (
                not isinstance(identity["workspace_id"], str)
                or not identity["workspace_id"].strip()
            )
        )
    ):
        raise RoutineRejected("routine_source_identity_invalid")
    return dict(identity)


def _sentences(body: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cover, sentences = [], []
    cursor = 0
    while cursor < len(body):
        start = cursor
        while cursor < len(body) and body[cursor].isspace():
            cursor += 1
        if cursor > start:
            cover.append({"kind": "separator", **_literal(body, start, cursor)})
        if cursor == len(body):
            break
        match = _SENTENCE.match(body, cursor)
        if match is None:
            raise RoutineRejected(
                "routine_unclassified_tail", _range(cursor, len(body))
            )
        unit = {"id": f"u{len(sentences) + 1}", **_literal(body, cursor, match.end())}
        sentences.append(unit)
        cover.append(
            {
                "kind": "sentence",
                "unit_id": unit["id"],
                **_literal(body, cursor, match.end()),
            }
        )
        cursor = match.end()
        if len(sentences) > 96:
            raise RoutineRejected("routine_unit_budget_exceeded")
    return cover, sentences


def _action_clause(text: str, source_range: dict[str, int]) -> tuple[str, str]:
    negative = re.match(r"(?:do\s+not|never|must\s+not)\s+", text, _FLAGS)
    action = text[negative.end() :] if negative else text
    if action.endswith((".", "!", "?")):
        action = action[:-1]
    for production, pattern in _ACTION_PRODUCTIONS:
        if pattern.fullmatch(action):
            return ("negative" if negative else "positive"), production
    raise RoutineRejected("routine_action_complement_unknown", source_range)


def _actions(body: str, start: int, end: int) -> dict[str, Any]:
    """Consume every action and joiner; an unknown suffix cannot disappear."""
    clauses, cover = [], []
    cursor = start
    joins = list(_ACTION_JOIN.finditer(body, start, end))
    for join in [*joins, None]:
        stop = join.start() if join else end
        if stop <= cursor:
            raise RoutineRejected("routine_action_clause_missing", _range(cursor, stop))
        literal = _literal(body, cursor, stop)
        polarity, production = _action_clause(literal["text"], _range(cursor, stop))
        clauses.append({**literal, "polarity": polarity, "production": production})
        cover.append({"kind": "action_clause", "index": len(clauses) - 1, **literal})
        if join:
            cover.append(
                {"kind": "separator", **_literal(body, join.start(), join.end())}
            )
            cursor = join.end()
    if len(clauses) > 16:
        raise RoutineRejected(
            "routine_action_clause_budget_exceeded", _range(start, end)
        )
    polarities = {c["polarity"] for c in clauses}
    if len(polarities) != 1:
        raise RoutineRejected(
            "routine_polarity_attachment_ambiguous", _range(start, end)
        )
    return {
        "action_clauses": clauses,
        "action_cover": cover,
        "polarity": next(iter(polarities)),
    }


def _condition(text: str, source_range: dict[str, int]) -> None:
    """A finite source predicate/scope, not arbitrary text after 'when'."""
    text = text.removesuffix(".").removesuffix("!").removesuffix("?")
    pieces = _CONDITION_JOIN.split(text)
    for index, piece in enumerate(pieces):
        marker = _CONDITION_MARKER.match(piece)
        if index == 0 and marker is None:
            raise RoutineRejected("routine_condition_grammar_unknown", source_range)
        atom = piece[marker.end() :] if marker else piece
        marker_text = marker.group().strip().casefold() if marker else None
        if not (
            _CONDITION_PREDICATE.fullmatch(atom)
            or (
                marker_text in {"for", "on", "during"}
                and _PHYSICAL_CONDITION.fullmatch(atom)
            )
            or (marker_text in {"for", "only for"} and _SUBJECT.fullmatch(atom))
        ):
            raise RoutineRejected("routine_condition_grammar_unknown", source_range)


def _unit_references(unit, instructions, *, in_prefix):
    first, text = unit["start"], unit["text"]
    # The one resolvable instruction referent is masked without changing offsets.
    # Every other instruction-authority mention refuses, regardless of its verb.
    reference_text = _PRECEDING.sub(lambda m: " " * len(m.group()), text)
    unresolved = _NORMATIVE_REFERENCE.search(reference_text)
    if unresolved:
        raise RoutineRejected(
            "routine_required_reference_unresolved",
            _range(first + unresolved.start(), first + unresolved.end()),
        )
    references = []
    preceding = _PRECEDING.search(text)
    if preceding:
        if in_prefix or not instructions:
            raise RoutineRejected(
                "routine_instruction_reference_unresolved", unit["source_range"]
            )
        references.append(
            {
                "kind": "instruction_reference",
                "text": preceding.group(),
                "source_range": _range(
                    first + preceding.start(), first + preceding.end()
                ),
                "target_range": dict(instructions[-1]),
            }
        )
    for material in _MATERIAL.finditer(text):
        references.append(
            {
                "kind": "material_reference",
                "text": material.group(),
                "source_range": _range(
                    first + material.start(), first + material.end()
                ),
            }
        )
    return references


def _classify_unit(body, unit, *, in_prefix):
    first, last, text = unit["start"], unit["end"], unit["text"]
    source_range = unit["source_range"]
    conditional = _QUALIFIED.fullmatch(text)
    if conditional:
        condition_range = _range(
            first + conditional.start("condition"), first + conditional.end("condition")
        )
        _condition(conditional.group("condition"), condition_range)
        actions = _actions(body, first + conditional.start("action"), last)
        unit.update(
            kind="conditional_instruction",
            condition=_literal(
                body,
                first + conditional.start("condition"),
                first + conditional.end("condition"),
            ),
            action=_literal(body, first + conditional.start("action"), last),
            **actions,
        )
    elif in_prefix and _CONTEXT.fullmatch(text):
        unit.update(kind="context_statement", scope="unknown")
    else:
        temporal = _TEMPORAL.search(text)
        action_end = first + temporal.start() if temporal else last
        actions = _actions(body, first, action_end)
        unit.update(
            kind="prohibition" if actions["polarity"] == "negative" else "instruction",
            **actions,
        )
        if temporal:
            if len(actions["action_clauses"]) != 1:
                raise RoutineRejected(
                    "routine_condition_attachment_ambiguous", source_range
                )
            _condition(
                text[temporal.start("condition") :],
                _range(first + temporal.start("condition"), last),
            )
            unit.update(
                kind="conditional_instruction",
                action=_literal(body, first, first + temporal.start()),
                condition=_literal(body, first + temporal.start("condition"), last),
            )
    if unit["kind"] != "context_statement":
        unit["scope"] = "assessment_required"


def routine_inventory(
    body: str,
    identity: dict[str, Any],
    *,
    requested_subject: str,
) -> dict[str, Any]:
    """Propose an exhaustive source inventory; no classifier is called or mocked.

    Unknown context statements require source-scope assessment by the consumer.
    Missing required external references fail closed, rather than manufacturing
    their contents. Source material names do not establish external authority.
    """
    source_identity = _source_identity(body, identity)
    if (
        not isinstance(requested_subject, str)
        or not requested_subject.strip()
        or (
            requested_subject != requested_subject.strip()
            or len(requested_subject) > 512
            or any(character in requested_subject for character in "\r\n")
        )
    ):
        raise RoutineRejected("routine_request_subject_invalid")
    cover, units = _sentences(body)
    declarations = [(i, _DECLARATION.fullmatch(u["text"])) for i, u in enumerate(units)]
    declarations = [(i, match) for i, match in declarations if match]
    if len(declarations) != 1:
        raise RoutineRejected("routine_declaration_missing_or_ambiguous")
    declaration_index, declaration = declarations[0]
    assert declaration is not None
    subject = _SUBJECT.fullmatch(declaration.group("subject"))
    if subject is None:
        raise RoutineRejected("routine_subject_referent_unresolved")
    if declaration_index == len(units) - 1:
        raise RoutineRejected("routine_instructions_missing")
    references, instructions = [], []
    for index, unit in enumerate(units):
        first, last = unit["start"], unit["end"]
        source_range = _range(first, last)
        unit["source_range"] = source_range
        if index == declaration_index:
            unit.update(kind="declaration", scope="source_declared")
            continue
        references.extend(
            _unit_references(unit, instructions, in_prefix=index < declaration_index)
        )
        _classify_unit(body, unit, in_prefix=index < declaration_index)
        if _PRECEDING.search(unit["text"]) and (
            len(unit.get("action_clauses", [])) != 1
            or (instructions and len(units[index - 1].get("action_clauses", [])) != 1)
        ):
            raise RoutineRejected(
                "routine_instruction_reference_ambiguous", source_range
            )
        if index > declaration_index:
            instructions.append(source_range)
    if len(instructions) > 32:
        raise RoutineRejected("routine_instruction_budget_exceeded")
    declaration_unit = units[declaration_index]
    declaration_range = declaration_unit["source_range"]
    subject_range = _range(
        declaration_unit["start"] + declaration.start("subject"),
        declaration_unit["start"] + declaration.end("subject"),
    )
    version = reading_version("contextual_source_v1")
    return {
        "contract": version.procedure,
        "reading_profile": version.profile,
        "structure": "source_declared_routine",
        "source_identity": source_identity,
        "source_body": body,
        "body_length": len(body),
        "requested_subject": requested_subject,
        "source_subject": declaration.group("subject"),
        "subject_range": subject_range,
        "declaration_range": declaration_range,
        "closure": {"kind": "immutable_eof", "offset": len(body)},
        "cover": cover,
        "units": units,
        "governing_prefix_ranges": [
            u["source_range"] for u in units[:declaration_index]
        ],
        "instruction_ranges": instructions,
        "references": references,
        "nli_obligations": [
            {
                "kind": kind,
                "verification_method": "nli_entailment",
                "source_range": declaration_range,
                "premise": declaration_unit["text"],
                "hypothesis": hypothesis,
            }
            for kind, hypothesis in (
                ("namespace", f"This routine is for {requested_subject}."),
                ("applicability", f"This routine applies to {requested_subject}."),
            )
        ],
    }


def validate_routine_inventory(
    record: dict[str, Any],
    body: str,
    identity: dict[str, Any],
    *,
    requested_subject: str,
) -> dict[str, Any]:
    """Reconstruct every field under its recorded version from actual inputs."""
    expected = routine_inventory(body, identity, requested_subject=requested_subject)
    try:
        _require_json_types(record)
        # JSON preserves bool/float distinctions which Python's equality erases.
        recorded = json.dumps(
            record, sort_keys=True, allow_nan=False, separators=(",", ":")
        )
        canonical = json.dumps(
            expected, sort_keys=True, allow_nan=False, separators=(",", ":")
        )
    except (TypeError, ValueError) as exc:
        raise RoutineRejected("routine_inventory_invalid") from exc
    if recorded != canonical:
        raise RoutineRejected("routine_inventory_reconstruction_mismatch")
    return expected


def _require_json_types(value: Any, depth: int = 0) -> None:
    """Require decoded-JSON containers; never normalize Python tuples/subclasses."""
    if depth > 32:
        raise TypeError("JSON nesting budget exceeded")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise TypeError("JSON object keys must be strings")
            _require_json_types(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _require_json_types(child, depth + 1)
    elif value is not None and type(value) not in (str, int, float, bool):
        raise TypeError("Non-JSON value")


# This separate representation does not broaden routine_inventory's finite
# semantics. Its positive declaration must be the first substantive statement.
_ENVELOPE_GOVERNING_DECLARATION = re.compile(
    r"The following instructions govern the "
    r"(?P<subject>(?:standard|ordinary|normal|regular|special) "
    r"[^.!?,;:\r\n]+? routine) only, "
    r"including references that omit the activity name\.",
    _FLAGS,
)
_ENVELOPE_WORD = re.compile(r"[\w]+(?:[-—'’][\w]+)*(?:[^\x00-\x7f\s.!?,;:\"“”]+)?")
# Logical/anaphoric links do not form a positively named scope. This is not an
# action-verb catalogue and never assigns semantics to the opaque payload.
_ENVELOPE_SCOPE_LINKS = frozenset(
    "and or but if unless when before after until during only except provided "
    "it its their them this that these those above below former latter same "
    "who what which where why whose".split()
)
_ENVELOPE_REFERENCE_CANDIDATE = re.compile(
    r"\b(?:appendi(?:x|ces)|annex(?:es)?|supplements?|attachments?|manuals?|handbooks?)\b|"
    r"\b(?:external|separate|omitted|required)\s+"
    r"(?:guides?|polic(?:y|ies)|protocols?|instructions?|directions?)\b",
    _FLAGS,
)


def _envelope_named_subject(text):
    if (
        type(text) is not str
        or not text
        or text != text.strip()
        or len(text) > 512
        or any(c in text for c in "\r\n")
    ):
        raise RoutineRejected("envelope_named_subject_invalid")
    qualifier = re.match(
        r"(?:(?:the|a|an)\s+)?(?:(?:ordinary|standard|normal|regular|special|demonstration)\s+)?"
        r"(?:sessions?\s+of\s+)?",
        text,
        _FLAGS,
    )
    if qualifier is None:
        raise RoutineRejected("envelope_named_subject_invalid")
    first = qualifier.end()
    suffix = re.search(
        r"\s+(?:routines?|procedures?|sessions?|runs?|trials?|cycles?)$", text, _FLAGS
    )
    last = suffix.start() if suffix else len(text)
    name = text[first:last]
    words = name.split()
    if (
        not words
        or len(words) > 32
        or name != name.strip()
        or not words[0][0].isupper()
        or any(not _ENVELOPE_WORD.fullmatch(w) for w in words)
        or any(w.casefold() in _ENVELOPE_SCOPE_LINKS for w in words)
    ):
        raise RoutineRejected("envelope_named_subject_unresolved")
    return first, last


def _envelope_declaration(body):
    first = len(body) - len(body.lstrip())
    declarations = {
        (m.start(), m.end()): m
        for pattern in (_ENVELOPE_GOVERNING_DECLARATION, _DECLARATION)
        for m in pattern.finditer(body)
    }
    if len(declarations) != 1:
        raise RoutineRejected("envelope_declaration_missing_or_ambiguous")
    declaration = next(iter(declarations.values()))
    if declaration.start() != first:
        raise RoutineRejected("envelope_authority_prefix_unresolved")
    if not body[declaration.end() :].strip():
        raise RoutineRejected("envelope_payload_missing")
    return declaration


def declared_envelope_inventory(body, identity, *, requested_subject):
    """Propose one complete literal declared-source copy, never publication.

    The first substantive statement must positively declare a named governing
    scope. All post-declaration governors, alternatives and tails remain opaque
    source text. Required reference, whole-source governing scope and complete
    actual request consumption still require independent consumer discharge.
    No unknown action is classified irrelevant, self-contained or supported.
    """
    source_identity = _source_identity(body, identity)
    _envelope_named_subject(requested_subject)
    declaration = _envelope_declaration(body)
    left, right = _envelope_named_subject(declaration["subject"])
    reference = _ENVELOPE_REFERENCE_CANDIDATE.search(body)
    if reference:
        raise RoutineRejected(
            "envelope_reference_requires_resolution",
            _range(reference.start(), reference.end()),
        )
    first, last = declaration.span()
    full_range = _range(0, len(body))
    declaration_range = _range(first, last)
    ranges = []
    if first:
        ranges.append({"kind": "literal_prefix", **_literal(body, 0, first)})
    ranges.extend(
        [
            {"kind": "governing_declaration", **_literal(body, first, last)},
            {"kind": "opaque_payload", **_literal(body, last, len(body))},
        ]
    )
    version = reading_version("contextual_source_v1")
    return {
        "contract": version.procedure,
        "reading_profile": version.profile,
        "envelope_kind": "opaque_declared_source",
        "claim_semantics": "complete_literal_copy_of_declared_source_body",
        "source_identity": source_identity,
        "source_body": body,
        "body_length": len(body),
        "requested_subject": requested_subject,
        "source_subject": declaration["subject"],
        "namespace": _literal(
            body,
            declaration.start("subject") + left,
            declaration.start("subject") + right,
        ),
        "declaration_range": declaration_range,
        "envelope_range": full_range,
        "closure": {"kind": "immutable_eof", "offset": len(body)},
        "ordered_ranges": ranges,
        "opaque_payload": _literal(body, last, len(body)),
        "guard_obligations": [
            {
                "kind": kind,
                "status": "pending_independent_discharge",
                "source_range": dict(full_range),
                "requested_subject": requested_subject,
            }
            for kind in (
                "actual_request_consumption",
                "whole_source_governing_scope",
                "required_reference_closure",
            )
        ],
        "nli_obligations": [
            {
                "kind": kind,
                "verification_method": "nli_entailment",
                "source_range": dict(declaration_range),
                "premise": declaration.group(),
                "hypothesis": hypothesis,
            }
            for kind, hypothesis in (
                ("namespace", f"This routine is for {requested_subject}."),
                ("applicability", f"This routine applies to {requested_subject}."),
            )
        ],
    }


def validate_declared_envelope_inventory(record, body, identity, *, requested_subject):
    """Rebuild from authoritative inputs; never accept submitted guard outcomes."""
    expected = declared_envelope_inventory(
        body, identity, requested_subject=requested_subject
    )
    try:
        _require_json_types(record)
        actual_json = json.dumps(
            record, sort_keys=True, allow_nan=False, separators=(",", ":")
        )
        expected_json = json.dumps(
            expected, sort_keys=True, allow_nan=False, separators=(",", ":")
        )
    except (TypeError, ValueError) as exc:
        raise RoutineRejected("envelope_inventory_invalid") from exc
    if actual_json != expected_json:
        raise RoutineRejected("envelope_inventory_reconstruction_mismatch")
    return expected
