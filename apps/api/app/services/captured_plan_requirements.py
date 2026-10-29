"""Typed new-plan transports and literal catalogue expansion, without facts."""

import json
from dataclasses import asdict, dataclass

from app.services.answer_requirements import Requirement, _requirement_anchors
from app.services.dependency_frames import resolve_frames
from app.services.effective_request import Edge, MemberBinding, SourceUse, ValueSlot
from app.services.linguistic_requirements import LiteralRange, RequirementUse
from app.services.planning_declarations import (
    RawRange,
    SourceIdentity,
    canonical,
    digest,
)
from app.services.request_parser import validate_capture


@dataclass(frozen=True)
class CapturedRequirementUse(RequirementUse):
    node_id: str = ""
    parent_id: str | None = None
    operation: str = ""
    features_json: str = "{}"
    source_uses_json: str = "[]"
    member_binding_id: str | None = None
    value_slot_id: str | None = None
    execution_dependencies: tuple[str, ...] = ()
    resolution: str = "CAPTURED_STRUCTURE_EXTERNAL_GATES_PENDING"
    quantifiers: tuple[LiteralRange, ...] = ()
    negation: tuple[LiteralRange, ...] = ()


def closed_original_frames(question, capture, historical):
    """Match actual atomic frames, without adopting a legacy resolved plan."""
    frames, syntax = resolve_frames(question, validate_capture(question, capture))
    if historical["unknowns"] or any(frame.errors for frame in frames):
        return {}, ()
    matched = {}
    for index, frame in enumerate(frames):
        nodes = [
            node
            for node in historical["nodes"]
            if node["kind"] == frame.kind
            and node["grammar"] == frame.grammar
            and tuple(node["token_indices"]) == frame.tokens
            and tuple(node["head_indices"]) == frame.heads
            and node["scopes"] == [asdict(LiteralRange(*s)) for s in frame.scopes]
        ]
        if len(nodes) != 1 or nodes[0]["id"] in matched:
            return {}, ()
        matched[nodes[0]["id"]] = (index, frame)
    if len(matched) != len(historical["nodes"]):
        return {}, ()
    return matched, syntax


def closed_catalogue(row):
    features = json.loads(row["features_json"])
    return (
        bool(row["members"])
        and len(row["scope"]) == 1
        and not any(
            features.get(k)
            for k in (
                "conditions",
                "modality",
                "negation",
                "references",
                "governors",
                "quantifiers",
                "typed_quantifiers",
                "unbound_condition_markers",
            )
        )
        and not features.get("coordination_closure", {}).get("unresolved_head_indices")
        and not features.get("coordination_closure", {}).get(
            "unresolved_marker_indices"
        )
        and all(
            not a["unknowns"]
            and not a["quantifiers"]
            and all(q["kind"] == "governing_scope" for q in a["qualifiers"])
            for a in row["arguments"]
        )
        and len({m["text"] for m in row["members"]}) == len(row["members"])
    )


def source_use(row):
    return SourceUse(
        row["id"],
        SourceIdentity(**row["source"]),
        row["unit_id"],
        row["kind"],
        RawRange(**row["raw"]),
    )


def _rows(
    question,
    node,
    identifier,
    kind,
    *,
    parent=None,
    member=None,
    slot=None,
    sources=(),
    depends=(),
    frame=None,
    order_after=(),
):
    start = min(e["start"] for e in node["evidence"])
    end = max(e["end"] for e in node["evidence"])
    features = json.loads(node["feature_json"])
    literal_scope = node["scopes"][0]["text"] if len(node["scopes"]) == 1 else ""
    topic = frame.topic if frame else literal_scope
    label = member.literal.text if member else ""
    features.update(role_label=label, source_scope=literal_scope)
    requirement = Requirement(
        identifier,
        question[start:end],
        start,
        end,
        node["proposed_question"] or question[start:end],
        kind,
        topic,
        _requirement_anchors(topic),
        tuple(depends),
        features.get("relation", ""),
        features.get("attribute", ""),
        features.get("source_workspace"),
    )

    def spans(key):
        if frame is not None and hasattr(frame, key):
            return tuple(LiteralRange(*r) for r in getattr(frame, key))
        return tuple(LiteralRange(**r) for r in features.get(key, ()))

    use = CapturedRequirementUse(
        requirement_id=identifier,
        original=LiteralRange(start, end, question[start:end]),
        scopes=tuple(LiteralRange(**r) for r in node["scopes"]),
        conditions=spans("conditions"),
        modality=spans("modality"),
        units=spans("units"),
        governors=spans("governors"),
        references=spans("references"),
        condition_ast=frame.condition_ast if frame else (),
        order_after=tuple(order_after),
        order_evidence=spans("order"),
        scope_kind="captured_literal_scope",
        grammar=node["grammar"],
        head_token_indices=tuple(node["head_indices"]),
        consumed_token_indices=tuple(node["token_indices"]),
        extent=features.get("extent", "unspecified"),
        node_id=node["id"],
        parent_id=parent,
        operation=node["operation"],
        features_json=canonical(features),
        source_uses_json=canonical([asdict(s) for s in sources]),
        member_binding_id=member.id if member else None,
        value_slot_id=slot,
        execution_dependencies=tuple(depends),
        quantifiers=spans("quantifiers"),
        negation=spans("negation"),
    )
    return requirement, use


def derive_requirements(structure, ledger):
    requirements, uses, members, values, edges, unresolved = [], [], [], [], [], []
    roots, catalogue_members, actor_rows = {}, {}, {}
    declarations = ledger["source_inventory"]["declarations"]
    frames, _ = closed_original_frames(
        structure["question"],
        structure["original_capture"],
        structure["historical_partial"],
    )
    roots.update(
        {
            node["id"]: "r-" + digest({"node": node, "question": structure["question"]})
            for node in structure["nodes"]
        }
    )
    frame_roots = {index: roots[node_id] for node_id, (index, _) in frames.items()}
    for node in structure["nodes"]:
        identifier = roots[node["id"]]
        original = frames.get(node["id"])
        frame = original[1] if original else None
        depends = tuple(frame_roots[i] for i in frame.dependencies) if frame else ()
        order_after = (
            (frame_roots[original[0] - 1],)
            if original and original[1].order and original[0]
            else ()
        )
        sources = []
        catalogue = None
        catalogue, sources = _select_catalogue(node, declarations, unresolved)
        requirement, use = _rows(
            structure["question"],
            node,
            identifier,
            node["kind"],
            sources=sources,
            frame=frame,
            depends=depends,
            order_after=order_after,
        )
        requirements.append(requirement)
        uses.append(use)
        if catalogue:
            child_rows, child_uses, bound, slots, child_edges, actors = (
                _expand_catalogue(
                    structure, node, identifier, catalogue, ledger, sources
                )
            )
            requirements.extend(child_rows)
            uses.extend(child_uses)
            members.extend(bound)
            values.extend(slots)
            edges.extend(child_edges)
            actor_rows.update(actors)
            catalogue_members[node["id"]] = bound
    for edge in structure["edges"]:
        if edge["source_id"] not in roots or edge["target_id"] not in roots:
            raise ValueError("Captured request edge endpoint missing")
        if edge["kind"] != "catalogue_member_value":
            edges.append(
                Edge(
                    edge["kind"],
                    roots[edge["source_id"]],
                    roots[edge["target_id"]],
                    canonical(edge["evidence"]),
                )
            )
            continue
        parent, target = roots[edge["source_id"]], roots[edge["target_id"]]
        edges.append(Edge("set_reference", parent, target, canonical(edge["evidence"])))
        node = next(n for n in structure["nodes"] if n["id"] == edge["target_id"])
        bound = catalogue_members.get(edge["source_id"], [])
        if not bound:
            unresolved.append(
                {"owner_id": node["id"], "reason": "unresolved_set_antecedent"}
            )
        for member in bound:
            if member.id not in actor_rows:
                raise ValueError(
                    "Dependent member lacks actual actor value-slot lineage"
                )
            actor_id, slot = actor_rows[member.id]
            child_id = "r-" + digest(
                {"parent": target, "member": member.id, "slot": slot}
            )
            child, use = _rows(
                structure["question"],
                node,
                child_id,
                node["kind"],
                parent=target,
                member=member,
                slot=slot,
                depends=(actor_id,),
            )
            requirements.append(child)
            uses.append(use)
            edges.append(
                Edge(
                    "actor_value_dependency",
                    actor_id,
                    child_id,
                    canonical(edge["evidence"]),
                    member.id,
                    slot,
                )
            )
    if len(requirements) > 64:
        raise ValueError("Requirement expansion exceeds64; no truncation")
    return requirements, uses, members, values, edges, unresolved


def operation_ledger(ledger):
    """Account each full-source unit, never declare a source inapplicable."""
    dispositions, unresolved = [], []
    declarations = ledger["source_inventory"]["declarations"]
    snapshots = ledger["original_inputs"]["snapshots"]
    for unit in ledger["source_inventory"]["units"]:
        source_row = next(
            r for r in ledger["sources"] if r["identity"] == unit["source"]
        )
        snapshot = next(r for r in snapshots if r["identity"] == unit["source"])
        metadata = json.loads(snapshot["metadata_json"])
        features = json.loads(unit["features_json"])
        domain = source_row["instruction_domain"]
        rows = [r for r in declarations if r["unit_id"] == unit["id"]]
        relation = [
            r for r in source_row["relation_candidates"] if r["raw"] == unit["raw"]
        ]
        state = "UNRESOLVED_POSSIBLE_GOVERNANCE"
        gates = ["complete_governing_reference_curated_opposition_replay"]
        if not unit["raw"]["text"].strip():
            state, gates = "SYNTAX_SEPARATOR", []
        elif (
            metadata.get("condition") is not None
            or metadata.get("conflict_group") is not None
        ):
            gates += ["curated_source_all_member_inspection"]
        elif domain["status"] == "copy_domain_structurally_owned":
            state = "COPY_DOMAIN_ONLY_NOT_FACTUAL_AUTHORITY"
            gates += domain["remaining_gates"]
        elif not any(
            features.get(k)
            for k in (
                "conditions",
                "modality",
                "negation",
                "references",
                "governors",
                "quantifiers",
                "typed_quantifiers",
                "unbound_condition_markers",
            )
        ):
            if rows and all(
                r["kind"]
                in {
                    "literal_name",
                    "role_catalogue",
                    "role_assignment",
                    "literal_field",
                }
                and _declared_scope(r, declarations)
                for r in rows
            ):
                # Literal field value/subject meanings remain prior-witness+NI gates.
                field_rows = [r for r in rows if r["kind"] == "literal_field"]
                arguments = [a for r in rows for a in r["arguments"]]
                known_arguments = all(
                    not a["quantifiers"]
                    and not a["unknowns"]
                    and all(q["kind"] == "governing_scope" for q in a["qualifiers"])
                    for a in arguments
                )
                if known_arguments or (
                    len(field_rows) == len(rows)
                    and all(_dependent_literal_candidate(r, ledger) for r in field_rows)
                ):
                    state = "FACTUAL_DECLARATION_PER_FACT_GATES_PENDING"
                    gates += [
                        "exact_subject_attribute_and_literal_argument_NI",
                        "prior_actor_witness_for_dependent_fields",
                    ]
            elif relation and all(_relation_scope(r, declarations) for r in relation):
                state = "ROLE_RELATION_CANDIDATE_PER_FACT_GATES_PENDING"
                gates += [
                    "actual_role_relation_subject_attribute_NI",
                    "actual_request_member_and_value_slot_lineage",
                ]
        if state == "UNRESOLVED_POSSIBLE_GOVERNANCE":
            unresolved.append(
                {
                    "owner_id": unit["id"],
                    "reason": "source_governance_or_production_unresolved",
                    "original_unit": unit,
                    "source_metadata": metadata,
                }
            )
        dispositions.append(
            {
                "unit_id": unit["id"],
                "source": unit["source"],
                "raw": unit["raw"],
                "original_features_json": unit["features_json"],
                "original_unknowns": unit["unknowns"],
                "disposition": state,
                "remaining_gates": gates,
                "cannot_apply": "NOT_ASSERTED",
                "namespace_disjointness": "NOT_ASSERTED",
                "accepted_fact": False,
            }
        )
    return dispositions, unresolved


def _declared_scope(row, declarations):
    if row["kind"] == "literal_name":
        return True
    return len(row["scope"]) == 1 and any(
        d["kind"] == "literal_name" and d["literal"]["text"] == row["scope"][0]["text"]
        for d in declarations
    )


def _relation_scope(row, declarations):
    return len(row["scope_candidates"]) == 1 and any(
        d["kind"] == "literal_name"
        and d["literal"]["text"] == row["scope_candidates"][0]["text"]
        for d in declarations
    )


def _dependent_literal_candidate(row, ledger):
    """Only propose the exact captured prior-value literal; never bind its truth."""
    # Source offsets differ across documents; bind whole literal scope text.
    candidates = [
        r
        for s in ledger["sources"]
        for r in s["relation_candidates"]
        if [v["text"] for v in r["scope_candidates"]]
        == [v["text"] for v in row["scope"]]
    ]
    for argument in row["arguments"]:
        if argument["quantifiers"]:
            return False
        extra = [q for q in argument["qualifiers"] if q["kind"] != "governing_scope"]
        if not extra:
            if argument["unknowns"]:
                return False
            continue
        if argument["kind"] != "declaration_subject" or len(extra) != 1:
            return False
        qualifier = extra[0]
        if (
            qualifier["kind"] != "nominal_modifier"
            or argument["unknowns"] != ["argument_qualifier_meaning_unassessed"]
            or len(qualifier["token_indices"]) != 1
        ):
            return False
        matches = [
            r
            for r in candidates
            if r["literal_value_candidate"]["text"] == qualifier["raw"]["text"]
            and not r["original_value_token"]["children"]
        ]
        if len(matches) != 1:
            return False
    return True


def _expand_catalogue(structure, node, identifier, catalogue, ledger, sources):
    requirements, uses, members, values, edges = [], [], [], [], []
    actor_rows = {}
    bound = []
    for literal in catalogue["members"]:
        member = MemberBinding(
            "mb-"
            + digest(
                {
                    "parent": identifier,
                    "declaration": catalogue["id"],
                    "literal": literal,
                }
            ),
            identifier,
            catalogue["id"],
            RawRange(**literal),
            canonical(catalogue["scope"]),
        )
        members.append(member)
        bound.append(member)
        child_id = "r-" + digest({"parent": identifier, "member": member.id})
        kind = "role_label" if node["operation"] == "labels_only" else "role_assignment"
        slot = None
        if kind == "role_assignment":
            slot = "vs-" + digest({"requirement": child_id, "member": member.id})
            candidates = [
                r
                for s in ledger["sources"]
                for r in s["relation_candidates"]
                if r["role_label"]["text"] == literal["text"]
                and [v["text"] for v in r["scope_candidates"]]
                == [v["text"] for v in catalogue["scope"]]
            ]
            values.append(
                ValueSlot(slot, child_id, member.id, (), canonical(candidates))
            )
            actor_rows[member.id] = (child_id, slot)
        child, child_use = _rows(
            structure["question"],
            node,
            child_id,
            kind,
            parent=identifier,
            member=member,
            slot=slot,
            sources=sources,
        )
        requirements.append(child)
        uses.append(child_use)
        edges.append(
            Edge(
                "catalogue_member",
                identifier,
                child_id,
                canonical(node["evidence"]),
                member.id,
                slot,
            )
        )
    return requirements, uses, members, values, edges, actor_rows


def _select_catalogue(node, declarations, unresolved):
    catalogue, sources = None, []
    if node["kind"] == "role_catalogue":
        matches = [
            r
            for r in declarations
            if r["kind"] == "role_catalogue"
            and len(r["scope"]) == len(node["scopes"]) == 1
            and r["scope"][0]["text"] == node["scopes"][0]["text"]
        ]
        if len(matches) == 1 and closed_catalogue(matches[0]):
            catalogue = matches[0]
            sources = [source_use(catalogue)]
        else:
            unresolved.append(
                {
                    "owner_id": node["id"],
                    "reason": "missing_ambiguous_or_qualified_catalogue",
                    "candidate_ids": [r["id"] for r in matches],
                }
            )
    return catalogue, sources
