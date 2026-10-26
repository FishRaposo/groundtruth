"""Closed, opt-in note-context reading; grammar is policy, never NLI absence.

The parser consumes the immutable body, not a caller's AST or source identity.
Unknown material, transitions and alternative antecedents fail closed. Literal
arguments parameterize productions; no corpus names or document IDs are used.
"""

from __future__ import annotations

import hashlib
import re

CONTEXT_CONTRACT = "source-note-context-v1"
CONTEXT_POLICY = "scoped_note_context_v1"
SCOPE_CONTRACT = "procedure-condition-scope-v2"
INVENTORY_CONTRACT = "procedure-condition-exclusion-inventory-v2"
OUTPUT_CONTRACT = "procedure-output-cover-v3"

LOCATION = (
    r"(?:station|archive|records|locked paper|secure paper|blue|red|sealed) "
    r"(?:folder|container|cabinet|box)"
)
NOMINAL = r"[\w-]+(?: [\w-]+){0,9}"
NOMINAL_REJECT = (
    r"\b(?:and|or|but|if|unless|when|must|may|should|not|only|every|all|any|"
    r"is|are|changes|requires|before|after|means|identifies|confirms|where|"
    r"who|whose|that|which)\b"
)
LIST_CATEGORIES = {
    "attributes": (
        r"(?:owner assignments|consultation windows|session start|"
        r"session duration|ordinary allocation)"
    ),
    "excluded_objects": (
        r"(?:samples|equipment|session cards|records belonging "
        r"to a completed ordinary run)"
    ),
}

SEMANTIC_TEMPLATES = (
    (
        "activity_subject",
        "scoped_directive",
        "scoped_directive",
        "The instruction concerns {operation} {state} marked with a {mark}.",
    ),
    (
        "actor_applicability",
        "scoped_directive",
        "scoped_directive",
        "For {condition}, the operator is instructed to {action_content}",
    ),
    (
        "classification_identity",
        "classification_prerequisite",
        "classification_prerequisite",
        "Before selecting any disposition, the operator identifies "
        "the card as a {state}.",
    ),
    (
        "classification_mark",
        "classification_prerequisite",
        "classification_prerequisite",
        "Before selecting any disposition, the operator confirms the {mark} "
        "on the card's cover.",
    ),
    (
        "negative_condition_tuple",
        "classification_prerequisite",
        "negative_membership",
        "Cards without the combination of {state} identification "
        "and {mark} confirmation "
        "do not fall within this instruction's condition.",
    ),
    (
        "card_reference_identity",
        "scoped_directive",
        "negative_membership",
        "The card identified as a {state} and checked for the {mark} "
        "is the marked audit card.",
    ),
    (
        "reader_ranking_prohibition",
        "reader_constraints",
        "reader_constraints",
        "A reader must not invent a recency ranking from the title.",
    ),
    (
        "reader_choice_prohibition",
        "reader_constraints",
        "reader_constraints",
        "A reader must not choose one action because it appears convenient.",
    ),
)
CONTEXT_CONSTANTS = {
    "quantifier_domain": "any disposition",
    "resolved_quantifier_domain": "disposition of the marked audit card",
    "choice_domain": "one action",
    "resolved_choice_domain": "the disputed marked audit card disposition",
    "authority": (
        "explicit opt-in document-context reading policy; not universal NLI exclusivity"
    ),
}
DISCLOSURE_TEMPLATE = (
    "Context reading: the note's bare disposition and action references are read "
    "within its stated {condition} and marked audit card context. "
    "The opposing card dispositions remain unresolved."
)


def parse_context_note(  # noqa: C901 - finite complete-body versioned parser
    body: str, operation: str, state: str, *, policy="scoped_note_context_v1"
) -> dict | None:
    """Reconstruct one complete finite discourse production, or reject it."""
    if policy not in ("scoped_note_context_v1", "scoped_note_context_v2"):
        return None
    if not all(_nominal(value) for value in (operation, state)):
        return None
    op, event = re.escape(operation), re.escape(state)
    title = re.match(
        rf"{op}: {event} disposition (?P<action>retain|discard)(?=\n)", body
    )
    if title is None:
        return None
    action = title.group("action")
    directive = _directive(op, event, action)
    cursor = title.end()
    whitespace = re.match(r"\s+", body[cursor:])
    if whitespace is None:
        return None
    header = directive.match(body, cursor + whitespace.end())
    if header is None or re.fullmatch(LOCATION, header.group("destination")) is None:
        return None
    mark = header.group("mark")
    if not _nominal(mark):
        return None
    patterns = _patterns(title.group(), directive.pattern, event, mark)
    clauses, gaps, cursor = [], [], 0
    for kind, pattern, references in patterns:
        gap = re.match(r"\s+", body[cursor:])
        if gap:
            end = cursor + gap.end()
            gaps.append(
                {
                    "literal": body[cursor:end],
                    "source_range": {"start": cursor, "end": end},
                }
            )
            cursor = end
        match = re.compile(pattern).match(body, cursor)
        if match is None:
            return None
        bindings = {
            key: {
                "literal": value,
                "source_range": {"start": match.start(key), "end": match.end(key)},
            }
            for key, value in match.groupdict().items()
        }
        for name in ("attributes", "excluded_objects"):
            if name in bindings:
                members = _noun_list(bindings[name]["literal"], name)
                if members is None:
                    return None
                bindings[name]["members"] = members
        clauses.append(
            {
                "kind": kind,
                "literal": match.group(),
                "source_range": {"start": cursor, "end": match.end()},
                "bindings": bindings,
                "references": references,
            }
        )
        cursor = match.end()
    if cursor < len(body):
        if not body[cursor:].isspace():
            return None
        gaps.append(
            {
                "literal": body[cursor:],
                "source_range": {"start": cursor, "end": len(body)},
            }
        )
    edges = []
    by_kind = {clause["kind"]: clause for clause in clauses}
    for clause in clauses:
        for literal, target in clause["references"].items():
            start = clause["source_range"]["start"] + clause["literal"].index(literal)
            edge = {
                "source_literal": literal,
                "source_range": {"start": start, "end": start + len(literal)},
                "target_kind": target,
            }
            if target in by_kind:
                edge["target_range"] = dict(by_kind[target]["source_range"])
            else:
                edge["external_binding"] = "selected_complete_procedure"
            edges.append(edge)
    reading = {
        "contract": CONTEXT_CONTRACT,
        "grammar": "scoped-note-grammar-v1",
        "source_body": body,
        "source_body_hash": hashlib.sha256(body.encode()).hexdigest(),
        "adopted_context": {
            "operation": operation,
            "condition": header.group("condition"),
            "state": state,
            "actor": header.group("actor"),
            "object": header.group("object"),
            "mark": mark,
            **CONTEXT_CONSTANTS,
        },
        "clause_inventory": clauses,
        "gaps": gaps,
        "reference_edges": edges,
        "disclosure": DISCLOSURE_TEMPLATE.format(condition=header.group("condition")),
    }
    if policy == "scoped_note_context_v2":
        from app.evidence_policy import context_version
        from app.services.source_context_references import (
            DISCLOSURE_TEMPLATE_V2,
            validate_reference_inventory,
        )

        version = context_version(policy)
        reading.update(
            contract=version.context,
            grammar=version.grammar,
            disclosure=DISCLOSURE_TEMPLATE_V2.format(
                condition=header.group("condition")
            ),
        )
        try:
            validate_reference_inventory(reading)
        except (KeyError, TypeError, ValueError):
            return None
    return reading


def _directive(op, event, action):
    return re.compile(
        rf"For (?P<condition>the {op} {event} marked with a (?P<mark>[\w-]+)), "
        rf"the (?P<actor>operator) must {action} (?P<object>the marked audit card) "
        r"in the (?P<destination>[\w-]+(?: [\w-]+){0,4})\."
    )


def _patterns(title, directive, event, mark):
    return [
        ("title", re.escape(title), {}),
        ("scoped_directive", directive, {}),
        (
            "state_scope",
            r"This is a fictional current instruction for a very narrow audit state\.",
            {"This": "scoped_directive"},
        ),
        (
            "state_definition",
            rf"A {event} means an audit whose appointment was canceled before "
            rf"inspection\.",
            {},
        ),
        (
            "mark_identity",
            rf"The {re.escape(mark)} is a mark on its audit cover card, not an "
            rf"ordinary batch identifier\.",
            {"its audit cover card": "scoped_directive"},
        ),
        (
            "ordinary_noninterference",
            r"An unflagged ordinary run remains governed by the operation note "
            r"and its complete procedure\.",
            {"its complete procedure": "operation note"},
        ),
        (
            "unchanged_attributes",
            r"Nothing in this instruction changes (?P<attributes>[\w ,'-]+)\.",
            {"this instruction": "scoped_directive"},
        ),
        (
            "exclusive_object",
            r"The decision here concerns the marked audit card only\.",
            {"here": "scoped_directive", "the marked audit card": "scoped_directive"},
        ),
        (
            "excluded_treatment",
            r"It does not describe treatment of (?P<excluded_objects>[\w ,'-]+)\.",
            {"It": "exclusive_object"},
        ),
        (
            "classification_prerequisite",
            rf"Before selecting (?P<quantifier_domain>any disposition), the "
            rf"operator identifies the card as a {event} and confirms the "
            rf"{re.escape(mark)} on its cover\.",
            {
                "the card": "scoped_directive",
                "its cover": "mark_identity",
                "any disposition": "exclusive_object",
            },
        ),
        (
            "negative_membership",
            r"Cards without that combination do not fall within this "
            r"instruction's condition\.",
            {
                "that combination": "classification_prerequisite",
                "this instruction": "scoped_directive",
            },
        ),
        (
            "authority_condition",
            r"This document is published as a current authority for its stated "
            r"condition\.",
            {"its stated condition": "scoped_directive"},
        ),
        (
            "no_precedence",
            r"It has no precedence over another current document in the same "
            r"curated conflict group\.",
            {"It": "authority_condition"},
        ),
        (
            "unresolved_opposition",
            r"The grouping deliberately preserves an unresolved policy "
            r"disagreement about the disposition\.",
            {"The grouping": "no_precedence", "the disposition": "exclusive_object"},
        ),
        (
            "reader_constraints",
            r"A reader must not invent a recency ranking from the title or "
            r"choose (?P<choice_domain>one action) because it appears convenient\.",
            {"the title": "title", "one action": "unresolved_opposition"},
        ),
        (
            "missing_resolution",
            r"Resolution requires a later authoritative revision that is not "
            r"present in this corpus\.",
            {"Resolution": "unresolved_opposition"},
        ),
    ]


def grammar_descriptor(*, policy="scoped_note_context_v1"):
    """JSON grammar projection from the exact canonical production builder.

    Sentinels are literal replacement slots, escaped before regex substitution.
    Consumers account for literal source/offsets; this exports no NLI authority.
    """
    directive = _directive(
        "CONTEXT_OPERATION", "CONTEXT_STATE", "CONTEXT_ACTION"
    ).pattern
    descriptor = {
        "contract": CONTEXT_CONTRACT,
        "grammar": "scoped-note-grammar-v1",
        "slots": [
            "CONTEXT_OPERATION",
            "CONTEXT_STATE",
            "CONTEXT_ACTION",
            "CONTEXT_MARK",
            "CONTEXT_TITLE",
        ],
        "title": (
            r"CONTEXT_OPERATION: CONTEXT_STATE disposition "
            r"(?P<action>retain|discard)(?=\n)"
        ),
        "directive": directive,
        "clauses": [
            {"kind": kind, "pattern": pattern, "references": references}
            for kind, pattern, references in _patterns(
                "CONTEXT_TITLE", directive, "CONTEXT_STATE", "CONTEXT_MARK"
            )
        ],
        "location": LOCATION,
        "nominal": NOMINAL,
        "nominal_reject": NOMINAL_REJECT,
        "list_categories": LIST_CATEGORIES,
        "whitespace": r"\s+",
        "offsets": "Unicode codepoints",
        "context_constants": dict(CONTEXT_CONSTANTS),
        "context_inputs": ["operation", "state"],
        "context_directive_bindings": ["condition", "actor", "object", "mark"],
        "disclosure_template": DISCLOSURE_TEMPLATE,
        "semantic_templates": [list(row) for row in SEMANTIC_TEMPLATES],
        "source_content_checks": "all non-title clauses in inventory order",
    }
    if policy == "scoped_note_context_v2":
        from app.evidence_policy import context_version
        from app.services.source_context_references import reference_descriptor

        version = context_version(policy)
        descriptor.update(
            contract=version.context,
            grammar=version.grammar,
            semantic_templates=[
                list(row)
                for row in SEMANTIC_TEMPLATES
                if row[0] != "card_reference_identity"
            ],
            **reference_descriptor(),
        )
    elif policy != "scoped_note_context_v1":
        raise ValueError("Unknown context grammar policy")
    return descriptor


def _nominal(value):
    return bool(re.fullmatch(NOMINAL, value)) and not re.search(
        NOMINAL_REJECT, value, re.I
    )


def _noun_list(value, name):
    # Closed nominal members: clauses/conditions/aliases cannot hide in a list.
    parts = re.split(r", (?:or )?| or ", value)
    category = re.compile(LIST_CATEGORIES[name])
    if len(parts) < 2 or any(not category.fullmatch(part) for part in parts):
        return None
    return parts


def semantic_checks(reading):
    """Literal propositions keep the bare domains; interpretation stays separate."""
    checks = [
        {
            "name": clause["kind"],
            "premise_range": clause["source_range"],
            "hypothesis": clause["literal"],
        }
        for clause in reading["clause_inventory"]
        if clause["kind"] != "title"
    ]
    clauses = {clause["kind"]: clause for clause in reading["clause_inventory"]}
    context = {
        **reading["adopted_context"],
        "action_content": clauses["scoped_directive"]["literal"].split("must ", 1)[1],
    }
    for name, first, last, template in SEMANTIC_TEMPLATES:
        checks.append(
            {
                "name": name,
                "premise_range": {
                    "start": clauses[first]["source_range"]["start"],
                    "end": clauses[last]["source_range"]["end"],
                },
                "hypothesis": template.format(**context),
            }
        )
    if reading["contract"] == "source-note-context-v2":
        return [check for check in checks if check["name"] != "card_reference_identity"]
    if reading["contract"] != CONTEXT_CONTRACT:
        raise ValueError("Unknown contextual reading contract")
    return checks


def replay_context_scope(candidate, recorded, source, requirement, settings):
    """Rebuild complete canonical grammar and checks from actual source, no model."""
    from copy import deepcopy

    from app.services.requirement_contract import valid_condition_assessment

    expected = deepcopy(candidate)
    checks = recorded.get("semantic_checks", [])
    if len(checks) != len(expected["semantic_checks"]):
        raise ValueError("Missing contextual semantic checks")
    for actual, check in zip(checks, expected["semantic_checks"], strict=True):
        span = check["premise_range"]
        assessment = actual["assessment"]
        if not valid_condition_assessment(assessment, settings):
            raise ValueError("Invalid contextual semantic assessment")
        check.update(
            pair={
                "premise": source.body[span["start"] : span["end"]],
                "hypothesis": check["hypothesis"],
                "requirement_id": requirement.id,
                "reference_id": (
                    f"{source.identity['document_id']}:context-scope:{check['name']}"
                ),
            },
            assessment=deepcopy(assessment),
            verification_method="nli_entailment",
        )
        if candidate["contract"] == "procedure-condition-scope-v3":
            from app.services.source_context_references import exact_structure_equal

            matches = exact_structure_equal(actual, check)
        else:
            matches = actual == check
        if not matches:
            raise ValueError("Contextual check differs from immutable clause")
    method = "contextual_source_reading_and_nli"
    if candidate["contract"] == "procedure-condition-scope-v3":
        from app.services.source_context_references import (
            compile_reference_obligation,
            exact_structure_equal,
            obligation_plan,
        )

        reading = candidate["context_reading"]
        expected["obligation_plan"] = obligation_plan(reading)
        expected["reference_obligations"] = [compile_reference_obligation(reading)]
        if not all(
            exact_structure_equal(recorded.get(key), expected[key])
            for key in ("context_reading", "obligation_plan", "reference_obligations")
        ):
            raise ValueError("Invalid typed contextual reference plan")
        method = "contextual_source_reading_nli_and_exact_reference"
    expected.update(
        model_settings=deepcopy(settings),
        verification_method=method,
        reason="verified_contextual_excluded_source_condition",
    )
    return expected


def contextual_disclosures(selection):
    return sorted(
        {
            scope["context_reading"]["disclosure"]
            for conflict in selection.get("conflicts", [])
            for check in conflict.get("source_extent_checks", [])
            if (scope := check.get("condition_scope", {})).get("contract")
            in (SCOPE_CONTRACT, "procedure-condition-scope-v3")
            and scope.get("reason") == "verified_contextual_excluded_source_condition"
        }
    )
