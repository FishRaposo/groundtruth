"""Closed captured literal slots for model context, never factual acceptance.

Parallel literal slots remain UNASSESSED_NI. Their represented syntax is not
a namespace disjointness, relevance or opposite-fact judgment.
"""

import json

from app.services.captured_governing_context import reconstruct_governing_context
from app.services.captured_plan_inputs import DecodedCapturedInputs
from app.services.planning_declarations import canonical, digest

CONTRACT = "captured-fact-context-cover-v1"
_QUALIFIED = (
    "conditions",
    "modality",
    "negation",
    "references",
    "governors",
    "unbound_condition_markers",
    "quantifiers",
    "typed_quantifiers",
)


def _fold(value):
    return " ".join(value.casefold().split())


def _closed_features(value, *, definition=False):
    keys = tuple(key for key in _QUALIFIED if not (definition and key == "governors"))
    closure = value.get("coordination_closure", {})
    return not any(value.get(key) for key in keys) and not (
        closure.get("unresolved_head_indices")
        or closure.get("unresolved_marker_indices")
    )


def _closed_arguments(arguments):
    return bool(arguments) and all(
        not set(row["unknowns"]) - {"argument_qualifier_meaning_unassessed"}
        and not row["quantifiers"]
        and all(
            q["kind"] in {"governing_scope", "nominal_modifier"}
            and row["literal"]["start"]
            <= q["raw"]["start"]
            < q["raw"]["end"]
            <= row["literal"]["end"]
            for q in row["qualifiers"]
        )
        for row in arguments
    )


def _closed_relation(row):
    subject, value = row["original_subject_argument"], row["original_value_argument"]
    if len(row["scope_candidates"]) != 1 or not _closed_arguments([value]):
        return False
    if subject["quantifiers"] or set(subject["unknowns"]) - {
        "argument_qualifier_meaning_unassessed"
    }:
        return False
    scope = row["scope_candidates"][0]
    return all(
        qualifier["kind"] in {"governing_scope", "prepositional_qualifier"}
        and qualifier["raw"]["start"] <= scope["start"]
        and qualifier["raw"]["end"] == scope["end"]
        for qualifier in subject["qualifiers"]
    )


def _slot(unit, ledger):
    candidates = [
        row
        for source in ledger["sources"]
        for row in source["relation_candidates"]
        if row["source"] == unit["source"] and row["raw"] == unit["raw"]
    ]
    if len(candidates) == 1:
        row = candidates[0]
        if not _closed_relation(row):
            return None
        return (
            "role_assignment",
            tuple(_fold(x["text"]) for x in row["scope_candidates"]),
            _fold(row["role_label"]["text"]),
        )
    declarations = [
        row
        for row in ledger["source_inventory"]["declarations"]
        if row["unit_id"] == unit["id"]
        and row["kind"]
        in {"role_catalogue", "role_assignment", "literal_field", "literal_name"}
    ]
    if len(declarations) != 1 or not _closed_arguments(declarations[0]["arguments"]):
        return None
    row = declarations[0]
    if row["kind"] != "literal_name" and len(row["scope"]) != 1:
        return None
    return (
        row["kind"],
        tuple(_fold(x["text"]) for x in row["scope"]),
        "declared_name"
        if row["kind"] == "literal_name"
        else _fold(row["literal"]["text"]),
    )


def _copy_owner(unit, ledger):
    row = next(row for row in ledger["sources"] if row["identity"] == unit["source"])
    domain = row["instruction_domain"]
    if domain.get("status") != "copy_domain_structurally_owned":
        return None
    owners = [row["owner"] for row in domain["units"] if row["unit_id"] == unit["id"]]
    if len(owners) != 1 or owners[0] not in {
        "local_declared_instruction_definition",
        "captured_root_directive",
        "syntax_separator",
    }:
        return None
    if owners[0] == "local_declared_instruction_definition" and (
        unit["raw"] != domain["definition"]
        or not all(
            unit["raw"]["start"]
            <= domain["definition_relation"][key]["start"]
            < domain["definition_relation"][key]["end"]
            <= unit["raw"]["end"]
            for key in ("subject", "predicate", "literal_scope")
        )
    ):
        return None
    return owners[0]


def _account(unit, ledger):
    if not unit["raw"]["text"].strip():
        return "captured_separator", None, None
    features = json.loads(unit["features_json"])
    owner = _copy_owner(unit, ledger)
    if owner == "local_declared_instruction_definition" or (
        owner is not None
        and _closed_features(
            features, definition=owner == "local_declared_instruction_definition"
        )
    ):
        return "strict_931_instruction_syntax_owned", None, None
    if not _closed_features(features):
        return (
            "governing_reference_or_qualification_pending",
            None,
            "unresolved_captured_governor_reference_or_condition",
        )
    slot = _slot(unit, ledger)
    if slot is None or set(unit["unknowns"]) - {
        "unknown_source_grammar",
        "argument_qualifier_meaning_unassessed",
    }:
        return "unaccounted_source_material", None, "unaccounted_captured_source_unit"
    return "parallel_closed_literal_assertion_UNASSESSED_NI", slot, None


def reconstruct_fact_context(decoded, *, source_identity, selected_clause):
    if type(decoded) is not DecodedCapturedInputs:
        raise ValueError("Independently decoded input2 required")
    arguments = decoded.arguments
    context = reconstruct_governing_context(
        **{
            k: arguments[k]
            for k in (
                "question",
                "capture",
                "manifest",
                "snapshots",
                "source_captures",
                "sql_read_set_json",
            )
        },
        source_identity=source_identity,
        selected_clause=selected_clause,
        reading_profile="contextual_source_v4",
    )
    ledger = decoded.source_productions
    if context["source_production_sha256"] != digest(ledger):
        raise ValueError("Fixed context and complete source ledger differ")
    pending, receipts, slots = [], [], {}
    if context["context"] is None:
        pending.append("selected_captured_governing_context_unresolved")
    pending.extend(_curated_pending(arguments["snapshots"]))
    selected_ids = []
    for unit in ledger["source_inventory"]["units"]:
        disposition, slot, blocker = _account(unit, ledger)
        selected = (
            unit["source"] == context["source_identity"]
            and unit["raw"] == context["selected_clause"]
        )
        if selected:
            selected_ids.append(unit["id"])
        if blocker is not None:
            pending.append(blocker)
        if slot is not None:
            key = canonical(slot)
            if key in slots:
                pending.append(
                    "same_literal_slot_requires_independent_opposition_replay"
                )
            slots[key] = unit["id"]
        receipts.append(
            {
                "unit_id": unit["id"],
                "source": unit["source"],
                "raw": unit["raw"],
                "selected": selected,
                "disposition": disposition,
                "literal_slot": slot,
                "semantic_status": "UNASSESSED_NI",
            }
        )
    if len(selected_ids) != 1:
        raise ValueError("One exact original selected source unit required")
    return json.loads(
        canonical(
            {
                "contract": CONTRACT,
                "reading_profile": "contextual_source_v4",
                "governing_context": context,
                "full_source_ledger": ledger,
                "unit_accounting": receipts,
                "necessary_contiguous_unit_ids": selected_ids,
                "context": None if pending else context["context"],
                "pending": list(dict.fromkeys(pending)),
                "ready_for_assessment": not pending,
                "model_support": "UNASSESSED_NI",
                "namespace_disjointness": "NOT_ASSERTED",
                "parallel_assertion_policy": "closed_captured_literal_slots_v1",
                "publication_ready": False,
            }
        )
    )


def _curated_pending(snapshots):
    pending = []
    for snapshot in snapshots:
        metadata = json.loads(snapshot.metadata_json)
        if (
            metadata.get("condition") is not None
            or metadata.get("conflict_group") is not None
        ):
            pending.append("curated_condition_or_opposition_pending")
    return pending
