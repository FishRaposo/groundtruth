"""Versioned policy-authorized discourse roles, never physical card identity.

This obligation is compiled from the whole canonical note before any inference.
It carries exact literals/typed links; no model result can supply or replace it.
"""

from __future__ import annotations

from copy import deepcopy

REFERENCE_CONTRACT = "context-reference-structure-v1"
PLAN_CONTRACT = "source-note-obligation-plan-v2"
EXACT_METHOD = "exact_context_reference_structure"
DISCLOSURE_TEMPLATE_V2 = (
    "Context reading: the note's card and cover references and its bare "
    "disposition and action references are read within its stated {condition} "
    "and marked audit card context. The opposing card dispositions remain unresolved."
)

# id, type, clause, selector (binding slot or an exact literal template).
ROLE_SPECS = (
    ("event", "audit_event_or_state_role", "scoped_directive", "binding:condition"),
    ("actor", "operator_role", "scoped_directive", "binding:actor"),
    ("card", "marked_audit_card_role", "scoped_directive", "binding:object"),
    ("mark", "mark_literal_slot", "scoped_directive", "binding:mark"),
    ("cover", "card_cover_role", "mark_identity", "its audit cover card"),
    ("decision", "disposition_decision_role", "exclusive_object", "The decision here"),
    (
        "instruction",
        "instruction_role",
        "state_scope",
        "This is a fictional current instruction",
    ),
    (
        "condition",
        "instruction_condition_role",
        "scoped_directive",
        "binding:condition",
    ),
    ("state", "audit_state_literal_slot", "state_definition", "A {state}"),
    (
        "guard",
        "identity_and_mark_guard_predicate",
        "classification_prerequisite",
        "the operator identifies the card as a {state} "
        "and confirms the {mark} on its cover",
    ),
    (
        "generic_cards",
        "generic_candidate_card_variable",
        "negative_membership",
        "Cards",
    ),
    (
        "card_predicate",
        "generic_card_condition_predicate",
        "negative_membership",
        "whole_clause",
    ),
    (
        "document",
        "scoped_document_authority_role",
        "authority_condition",
        "This document",
    ),
    (
        "group",
        "curated_opposition_group_role",
        "no_precedence",
        "same curated conflict group",
    ),
    ("title", "note_title_role", "title", "whole_clause"),
    (
        "opposition",
        "disposition_disagreement_role",
        "unresolved_opposition",
        "whole_clause",
    ),
)

# Every old complete-body reference plus the mark/actor/state/variable uses that
# require more precise targets than the old coarse clause edges provided.
REFERENCE_SPECS = (
    ("instruction_this", "state_scope", "This", "instruction"),
    ("cover_declaration", "mark_identity", "its audit cover card", "cover"),
    ("cover_mark", "mark_identity", "The {mark}", "mark"),
    ("state_definition", "state_definition", "A {state}", "state"),
    (
        "ordinary_procedure",
        "ordinary_noninterference",
        "its complete procedure",
        "selected_complete_procedure",
    ),
    ("instruction_changes", "unchanged_attributes", "this instruction", "instruction"),
    ("decision_here", "exclusive_object", "here", "instruction"),
    ("decision_object", "exclusive_object", "the marked audit card", "card"),
    ("decision_it", "excluded_treatment", "It", "decision"),
    ("classification_actor", "classification_prerequisite", "the operator", "actor"),
    ("classification_card", "classification_prerequisite", "the card", "card"),
    ("classification_state", "classification_prerequisite", "a {state}", "state"),
    ("classification_cover", "classification_prerequisite", "its cover", "cover"),
    (
        "classification_mark",
        "classification_prerequisite",
        "the {mark} on its cover",
        "mark",
    ),
    (
        "disposition_domain",
        "classification_prerequisite",
        "any disposition",
        "decision",
    ),
    ("guard_combination", "negative_membership", "that combination", "guard"),
    ("condition_instruction", "negative_membership", "this instruction", "instruction"),
    ("generic_cards", "negative_membership", "Cards", "generic_cards"),
    ("stated_condition", "authority_condition", "its stated condition", "condition"),
    ("document_it", "no_precedence", "It", "document"),
    ("opposition_group", "unresolved_opposition", "The grouping", "group"),
    ("opposition_disposition", "unresolved_opposition", "the disposition", "decision"),
    ("ranking_title", "reader_constraints", "the title", "title"),
    ("action_domain", "reader_constraints", "one action", "decision"),
    ("resolution", "missing_resolution", "Resolution", "opposition"),
)
GUARD_MEMBERS = (
    (
        "identity_classification",
        "the operator identifies the card as a {state}",
        ("actor", "card", "state"),
    ),
    (
        "mark_confirmation",
        "confirms the {mark} on its cover",
        ("actor", "cover", "mark"),
    ),
)

ROLE_PROPERTIES = {
    "cover": {"cover_of": "card"},
    "card": {"type_distinct_from": ["event"]},
}
BINDING_ROLES = (
    ("condition", "event"),
    ("actor", "actor"),
    ("object", "card"),
    ("mark", "mark"),
)
DOMAIN_SPECS = (
    (
        "classification_prerequisite",
        "quantifier_domain",
        "decision",
        "resolved_quantifier_domain",
    ),
    ("reader_constraints", "choice_domain", "decision", "resolved_choice_domain"),
)
GUARD_MEANING = "required classification and confirmation, not successful execution"
GENERIC_PREDICATE_CONSTANTS = {
    "id": "card_predicate",
    "variable_role": "generic_cards",
    "guard_target": "guard",
    "condition_target": "condition",
    "relation": "without_complete_guard_combination_implies_outside_condition",
    "interpretation": (
        "generic candidate-card predicate, not singular physical identity"
    ),
}
REFERENCE_REASON = "complete_unique_scoped_note_discourse_roles"
ASSERTION_KIND = "policy_authorized_discourse_roles_only"


def exact_structure_equal(actual, expected):
    """Exact schema equality, including bool/int/float and container distinctions."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            exact_structure_equal(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            exact_structure_equal(a, b) for a, b in zip(actual, expected, strict=True)
        )
    return actual == expected


def _literal_slot(clause, literal):
    """One exact occurrence, never the nearest matching phrase."""
    start = clause["literal"].find(literal)
    if start < 0 or clause["literal"].find(literal, start + 1) >= 0:
        raise ValueError("Missing or competing contextual reference occurrence")
    start += clause["source_range"]["start"]
    return {
        "literal": literal,
        "source_range": {"start": start, "end": start + len(literal)},
    }


def _slot(clause, selector, context):
    if selector == "whole_clause":
        return {
            "literal": clause["literal"],
            "source_range": deepcopy(clause["source_range"]),
        }
    if selector.startswith("binding:"):
        return deepcopy(clause["bindings"][selector.split(":", 1)[1]])
    return _literal_slot(clause, selector.format(**context))


def _reference_plan(reading):
    """Internal canonical-parser seam; caller cannot supply a trusted AST."""
    context = reading["adopted_context"]
    clauses = {row["kind"]: row for row in reading["clause_inventory"]}
    entities = [
        {
            "id": name,
            "type": kind,
            "declaration_clause": clause,
            **_slot(clauses[clause], selector, context),
        }
        for name, kind, clause, selector in ROLE_SPECS
    ]
    by_id = {row["id"]: row for row in entities}
    for name, properties in ROLE_PROPERTIES.items():
        by_id[name].update(deepcopy(properties))
    occurrences = []
    for name, clause_name, literal, target in REFERENCE_SPECS:
        source = _literal_slot(clauses[clause_name], literal.format(**context))
        row = {
            "id": name,
            "source_clause": clause_name,
            **source,
            "target_id": target,
            "cardinality": 1,
            "source_clause_range": deepcopy(clauses[clause_name]["source_range"]),
            "compatible_region": {"start": 0, "end": len(reading["source_body"])},
        }
        if target == "selected_complete_procedure":
            row.update(
                target_type="complete_ordinary_procedure_role", external_binding=target
            )
        else:
            row.update(
                target_type=by_id[target]["type"],
                target_range=deepcopy(by_id[target]["source_range"]),
            )
        occurrences.append(row)
    prerequisite = clauses["classification_prerequisite"]
    guard = {
        "id": "guard",
        "connective": "and",
        "source_range": deepcopy(by_id["guard"]["source_range"]),
        "members": [
            {
                "kind": kind,
                **_literal_slot(prerequisite, literal.format(**context)),
                "argument_roles": list(roles),
            }
            for kind, literal, roles in GUARD_MEMBERS
        ],
        "meaning": GUARD_MEANING,
    }
    generic = {
        **GENERIC_PREDICATE_CONSTANTS,
        "variable_literal": by_id["generic_cards"]["literal"],
        "variable_range": deepcopy(by_id["generic_cards"]["source_range"]),
        "source_range": deepcopy(clauses["negative_membership"]["source_range"]),
        "literal": clauses["negative_membership"]["literal"],
    }
    domains = []
    for clause_name, binding, target, adopted in DOMAIN_SPECS:
        domains.append(
            {
                "source_clause": clause_name,
                "raw": deepcopy(clauses[clause_name]["bindings"][binding]),
                "adopted_domain": context[adopted],
                "target_role": target,
            }
        )
    return {
        "contract": REFERENCE_CONTRACT,
        "policy": "scoped_note_context_v2",
        "context_contract": reading["contract"],
        "grammar": reading["grammar"],
        "source_body_hash": reading["source_body_hash"],
        "source_range": {"start": 0, "end": len(reading["source_body"])},
        "assertion_kind": ASSERTION_KIND,
        "entities": entities,
        "binding_slots": [
            {
                "binding": key,
                "target_role": role,
                **deepcopy(clauses["scoped_directive"]["bindings"][key]),
            }
            for key, role in BINDING_ROLES
        ],
        "required_reference_count": len(REFERENCE_SPECS),
        "reference_occurrences": occurrences,
        "guard": guard,
        "generic_card_predicate": generic,
        "domains": domains,
        "complete_body_edges": deepcopy(reading["reference_edges"]),
    }


def validate_reference_inventory(reading):
    """Called only after the whole-body parser, before accepting the production."""
    _reference_plan(reading)


def compile_reference_obligation(reading):
    from app.services.source_context_scope import parse_context_note

    context = reading["adopted_context"]
    canonical = parse_context_note(
        reading["source_body"],
        context["operation"],
        context["state"],
        policy="scoped_note_context_v2",
    )
    if canonical is None or not exact_structure_equal(reading, canonical):
        raise ValueError("Reference obligation requires the complete canonical note")
    return {
        "name": "card_reference_linkage",
        "contract": REFERENCE_CONTRACT,
        "verification_method": EXACT_METHOD,
        "reference_plan": _reference_plan(canonical),
        "result": "bound",
        "reason": REFERENCE_REASON,
    }


def obligation_plan(reading):
    from app.services.source_context_scope import semantic_checks

    if (
        reading["contract"] != "source-note-context-v2"
        or reading["grammar"] != "scoped-note-grammar-v2"
    ):
        raise ValueError("Unsupported reference obligation plan contract")
    return {
        "contract": PLAN_CONTRACT,
        "source_context_policy": "scoped_note_context_v2",
        "source_context_contract": "source-note-context-v2",
        "grammar": reading["grammar"],
        "mandatory_obligation_count": 23,
        "mandatory_nli_count": 22,
        "mandatory_exact_reference_count": 1,
        "obligations": [
            *[
                {"name": row["name"], "verification_method": "nli_entailment"}
                for row in semantic_checks(reading)
            ],
            {
                "name": "card_reference_linkage",
                "verification_method": EXACT_METHOD,
                "method_contract": REFERENCE_CONTRACT,
            },
        ],
    }


def reference_descriptor():
    """Projection from the same mandatory role/reference/method authority."""
    return {
        "disclosure_template": DISCLOSURE_TEMPLATE_V2,
        "reference_structure": {
            "contract": REFERENCE_CONTRACT,
            "plan_contract": PLAN_CONTRACT,
            "method": EXACT_METHOD,
            "name": "card_reference_linkage",
            "role_specs": [list(row) for row in ROLE_SPECS],
            "reference_specs": [list(row) for row in REFERENCE_SPECS],
            "guard_members": [
                [kind, literal, list(roles)] for kind, literal, roles in GUARD_MEMBERS
            ],
            "role_properties": deepcopy(ROLE_PROPERTIES),
            "binding_roles": [list(row) for row in BINDING_ROLES],
            "domain_specs": [list(row) for row in DOMAIN_SPECS],
            "guard_meaning": GUARD_MEANING,
            "generic_predicate_constants": deepcopy(GENERIC_PREDICATE_CONSTANTS),
            "reason": REFERENCE_REASON,
            "assertion_kind": ASSERTION_KIND,
            "mandatory_obligation_count": 23,
            "mandatory_nli_count": 22,
            "mandatory_exact_reference_count": 1,
        },
    }
