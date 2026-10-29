"""Pure capture-preserving source production inventory; no factual acceptance."""

import json
from dataclasses import asdict

from app.evidence_policy import recorded_evidence_policy
from app.services import contextual_procedures as procedures
from app.services import contextual_source_proof as copy
from app.services import declared_source_scope as finite
from app.services import planning_declarations as source
from app.services import request_grammar as grammar
from app.services.captured_production_policy import SOURCE_CONTRACT, selected_version
from app.services.captured_request_productions import reconstruct_request_productions
from app.services.request_parser import validate_capture


def _require(value, message):
    if not value:
        raise ValueError(message)


def _literal(graph, indices):
    value = graph.literal(indices)
    if value is None:
        raise ValueError("The complete captured argument is not one literal interval")
    return asdict(value)


def _windows(snapshot, captures):
    return [
        (
            window.start,
            window.end,
            validate_capture(
                snapshot.body[window.start : window.end],
                json.loads(window.capture_json),
            ),
        )
        for window in captures.windows
    ]


def _instruction_definition(snapshot):
    cover = finite.source_cover(snapshot.body, asdict(snapshot.identity))
    try:
        declaration = procedures._envelope_declaration(snapshot.body)
    except procedures.RoutineRejected:
        headings = [
            unit
            for unit in cover["units"]
            if unit["kind"] == "heading" and unit["disposition"] == "local"
        ]
        _require(
            len(headings) == 1 and headings[0]["start"] == 0,
            "One actual declared instruction heading required",
        )
        _require(
            all(
                unit["kind"] == "separator" or unit["disposition"] == "local"
                for unit in cover["units"]
            ),
            "Unclassified material outside a declared instruction block",
        )
        return {
            key: headings[0][key] for key in ("start", "end", "text")
        }, "declared_source_scope.source_cover"
    identity = {
        key: value
        for key, value in asdict(snapshot.identity).items()
        if key != "snapshot_id"
    }
    if procedures._ENVELOPE_GOVERNING_DECLARATION.fullmatch(declaration.group()):
        # The actual first declaration owns an opaque complete-source payload.
        # Reference roles are checked below against its captured AST, rather
        # than treating an ordinary data noun such as "attachment" as a link.
        procedures._source_identity(snapshot.body, identity)
        procedures._envelope_named_subject(declaration["subject"])
        return {
            "start": declaration.start(),
            "end": declaration.end(),
            "text": declaration.group(),
        }, "contextual_procedures._envelope_declaration"
    procedures.declared_envelope_inventory(
        snapshot.body, identity, requested_subject=declaration["subject"]
    )
    return {
        "start": declaration.start(),
        "end": declaration.end(),
        "text": snapshot.body[declaration.start() : declaration.end()],
    }, "contextual_procedures.declared_envelope_inventory"


def _definition_relation(
    snapshot, windows, header, captures=None, *, literal_declared_target=False
):
    declaration = procedures._ENVELOPE_GOVERNING_DECLARATION.fullmatch(header["text"])
    if declaration is not None:
        # Reuse the existing qualified declared-target bridge. This is a source
        # ownership proposal; the requested name/applicability NI is still due.
        actual = procedures._envelope_declaration(snapshot.body)
        if captures is None:
            raise ValueError("Original source captures required")
        left, right = procedures._envelope_named_subject(actual["subject"])
        relation = copy._declared_relation(
            snapshot.body,
            actual,
            [
                {
                    "start": window.start,
                    "end": window.end,
                    "capture": json.loads(window.capture_json),
                }
                for window in captures.windows
            ],
            actual["subject"][left:right],
            {"relation": "routine"},
            **({"literal_declared_target": True} if literal_declared_target else {}),
        )
        return {
            "predicate": relation["predicate"],
            "subject": relation["subject"],
            "literal_scope": relation["target"],
            "scope_name_kind": "NOT_ASSERTED",
            "namespace_disjointness": "NOT_ASSERTED",
        }
    graph = copy._unit_graph(snapshot.body, windows, header["start"], header["end"])
    root = copy._one_root(graph)
    subjects = graph.children(root, {"nsubj", "nsubjpass"})
    targets = [obj for _, obj in graph.pp(root, {"to", "for"})]
    _require(
        len(subjects) == len(targets) == 1
        and graph.lemma(root) in {"apply", "govern", "be"},
        "A positive captured instruction definition is required",
    )
    _require(
        not any(
            graph.tokens[i]["dep"] in {"neg", "advcl", "relcl", "acl", "ccomp", "xcomp"}
            or graph.tokens[i]["tag"] == "MD"
            for i in graph.indices
        ),
        "Qualified or reference-bearing definition remains mandatory",
    )
    target = graph.nominal(targets[0])
    _require(
        all(
            graph.tokens[i]["pos"] in {"NOUN", "PROPN"}
            and graph.tokens[i]["dep"] in {"compound", "pobj"}
            for i in target
        ),
        "Qualified definition target remains unresolved",
    )
    return {
        "predicate": graph.span({root}),
        "subject": graph.span(graph.nominal(subjects[0])),
        "literal_scope": graph.span(target),
        "scope_name_kind": "NOT_ASSERTED",
        "namespace_disjointness": "NOT_ASSERTED",
    }


def _copy_unit(snapshot, windows, unit, header):
    record = {"unit_id": unit.id, "raw": asdict(unit.raw)}
    if not unit.raw.text.strip():
        return {**record, "owner": "syntax_separator"}
    if header["start"] <= unit.raw.start < unit.raw.end <= header["end"]:
        return {**record, "owner": "local_declared_instruction_definition"}
    features = json.loads(unit.features_json)
    _require(
        not set(unit.unknowns) - {"unknown_source_grammar"},
        "Unclassified directive qualification remains mandatory",
    )
    _require(
        not any(
            features.get(key)
            for key in (
                "conditions",
                "modality",
                "negation",
                "references",
                "unbound_condition_markers",
            )
        ),
        "Directive qualifiers and references remain mandatory",
    )
    graph = copy._unit_graph(snapshot.body, windows, unit.raw.start, unit.raw.end)
    parsed = copy._copy_clause(graph, asdict(unit.raw))
    _require(
        parsed["kind"] == "root_directive",
        "Possible factual assertion remains mandatory",
    )
    _require(
        not any(graph.lemma(i) == "role" for i in graph.indices),
        "Possible role reference remains mandatory",
    )
    return {**record, "owner": "captured_root_directive", "directive_ast": parsed}


def _declared_payload_governance(graph, predicates, declared_name, attachments):
    """Check authority edges, without interpreting copied conditions as facts."""
    words = {graph.lemma(i) for i in graph.indices}
    lemmas = {graph.lemma(i) for i in predicates}
    _require(
        not copy._external_direction(graph, lemmas, words)
        and not words
        & {
            "global",
            "globally",
            "universal",
            "universally",
            "regardless",
            "elsewhere",
            "external",
            "outside",
            "above",
            "below",
            "omitted",
        },
        "External or global source governance requires actual closure",
    )
    material = copy._CONTAINERS | {
        "step",
        "procedure",
        "routine",
        "method",
        "rule",
        "guidance",
    }
    for predicate in predicates:
        if graph.lemma(predicate) in copy._NORMATIVE:
            _require(
                graph.tokens[predicate]["tag"] != "VB"
                and bool(graph.children(predicate, {"nsubj", "nsubjpass"}))
                and not words & material,
                "Instruction-authority edge requires actual closure",
            )
    for token in graph.indices:
        if graph.lemma(token) not in material:
            continue
        parent = graph.tokens[token]["head"]
        ordinary_attachment = (
            graph.lemma(token) == "attachment"
            and graph.tokens[token]["dep"] in {"dobj", "obj", "nsubj", "nsubjpass"}
            and parent in predicates
            and (
                graph.lemma(parent) == "record"
                or graph.lemma(parent) == "leave"
                and any(
                    graph.lemma(i) == "unresolved" and graph.tokens[i]["pos"] == "ADJ"
                    for i in graph.children(parent, {"oprd"})
                )
            )
            and len(attachments) == 1
            and not (words - {"attachment"}) & material
        )
        if ordinary_attachment:
            continue
        nominal = graph.nominal(token)
        if graph.tokens[token]["dep"] == "oprd" and parent in predicates:
            for obj in graph.children(parent, {"dobj", "obj"}):
                nominal |= graph.nominal(obj)
        literal = graph.span(nominal)
        local = False
        if graph.lemma(token) in {"routine", "procedure"}:
            try:
                left, right = procedures._envelope_named_subject(literal["text"])
                local = (
                    literal["text"][left:right].casefold() == declared_name.casefold()
                )
            except procedures.RoutineRejected:
                pass
        _require(local, "Instruction-material target requires actual closure")
    _require(
        not any(
            graph.tokens[i]["dep"] in {"dep", "meta", "intj", "parataxis"}
            for i in graph.indices
        ),
        "Unresolved source attachment remains mandatory",
    )


def _selected_payload_governance(graph, predicates, declared_name, attachments):
    """Own literal COPY ranges; do not infer action truth or reference absence."""
    try:
        _declared_payload_governance(graph, predicates, declared_name, attachments)
        return
    except ValueError:
        pass
    words = {graph.lemma(i) for i in graph.indices}
    _require(
        not copy._external_direction(
            graph, {graph.lemma(i) for i in predicates} - {"refer"}, words
        ),
        "External instruction relationship requires actual closure",
    )
    material = copy._CONTAINERS | {
        "step",
        "procedure",
        "routine",
        "method",
        "rule",
        "guidance",
    }
    _require(
        not words
        & {
            "global",
            "globally",
            "universal",
            "universally",
            "regardless",
            "elsewhere",
            "external",
            "above",
            "below",
            "omitted",
        },
        "External or global source governance requires actual closure",
    )
    roots = [i for i in graph.indices if graph.tokens[i]["dep"] == "ROOT"]
    root = roots[0]
    semicolons = [i for i in graph.indices if graph.tokens[i]["text"] == ";"]
    boundary = max(semicolons) if semicolons else None
    negative_declaration = (
        boundary is not None
        and graph.lemma(root) in {"govern", "supply"}
        and bool(graph.children(root, {"neg"}))
        and bool(graph.children(root, {"nsubj", "nsubjpass"}))
        and bool(graph.children(root, {"dobj", "obj"}))
        and any(
            i < boundary
            and graph.lemma(i) == "separate"
            and graph.tokens[i]["dep"] == "amod"
            for i in graph.indices
        )
    )
    sequenced_data_proposals = {
        i
        for i in graph.indices
        if graph.tokens[i]["dep"] == "dep"
        and graph.tokens[i]["pos"] == "VERB"
        and graph.lemma(i) == "record"
        and graph.tokens[i]["head"] == root
        and i - 1 in graph.indices
        and i - 2 in graph.indices
        and graph.lemma(i - 1) == "then"
        and graph.tokens[i - 1]["dep"] == "advmod"
        and graph.tokens[i - 1]["head"] in {root, i}
        and graph.tokens[i - 2]["text"] == ","
        and len(graph.children(i, {"dobj", "obj"})) == 1
        and all(
            graph.tokens[obj]["pos"] in {"NOUN", "PROPN"}
            and not any(graph.lemma(at) in material for at in graph.subtree(obj))
            for obj in graph.children(i, {"dobj", "obj"})
        )
    }
    _require(
        not any(
            graph.tokens[i]["dep"] in {"dep", "meta", "intj", "parataxis"}
            and not (negative_declaration and i < boundary)
            and i not in sequenced_data_proposals
            for i in graph.indices
        ),
        "Unresolved source attachment remains mandatory",
    )
    data_recipients = {
        destination
        for predicate in predicates
        if graph.lemma(predicate) == "return"
        and len(graph.children(predicate, {"dobj", "obj"})) == 1
        and all(
            graph.tokens[obj]["pos"] in {"NOUN", "PROPN"}
            and not any(graph.lemma(at) in material for at in graph.subtree(obj))
            for obj in graph.children(predicate, {"dobj", "obj"})
        )
        for _, destination in graph.pp(predicate, {"to"})
        if graph.lemma(destination) == "guide"
    }
    _require(
        all(
            i in data_recipients or negative_declaration and i > boundary
            for i in graph.indices
            if graph.lemma(i) in material
        ),
        "Instruction-material target requires actual closure",
    )
    for predicate in predicates:
        lemma = graph.lemma(predicate)
        if lemma == "refer":
            # An actual conditional data subject supplies the pronoun's raw
            # antecedent proposal. No instruction meaning is assigned to it.
            objects = graph.children(predicate, {"dobj", "obj"})
            destinations = graph.pp(predicate, {"to"})
            antecedents = [
                subject
                for clause in graph.indices
                if graph.tokens[clause]["dep"] == "advcl"
                and any(
                    graph.lemma(i) == "if" for i in graph.children(clause, {"mark"})
                )
                for subject in graph.children(clause, {"nsubj", "nsubjpass"})
                if graph.tokens[subject]["pos"] in {"NOUN", "PROPN"}
            ]
            _require(
                len(objects) == len(destinations) == len(antecedents) == 1
                and graph.tokens[objects[0]]["pos"] in {"PRON", "NOUN", "PROPN"}
                and graph.tokens[destinations[0][1]]["pos"] in {"NOUN", "PROPN"},
                "Referral has unresolved instruction authority",
            )
        else:
            _require(
                lemma not in copy._NORMATIVE | {"read", "apply"}
                or lemma == "follow"
                and bool(graph.children(predicate, {"neg"}))
                and len(graph.children(predicate, {"dobj", "obj"})) == 1
                and all(
                    graph.tokens[obj]["pos"] in {"NOUN", "PROPN"}
                    and not any(
                        graph.lemma(at) in material for at in graph.subtree(obj)
                    )
                    for obj in graph.children(predicate, {"dobj", "obj"})
                ),
                "Instruction-authority edge requires actual closure",
            )
    for token in graph.indices:
        if graph.lemma(token) != "outside":
            continue
        predicate = graph.tokens[token]["head"]
        objects = graph.children(predicate, {"dobj", "obj"})
        locations = graph.children(token, {"pobj"})
        _require(
            graph.tokens[token]["dep"] == "prep"
            and predicate in predicates
            and len(objects) == len(locations) == 1
            and graph.tokens[objects[0]]["pos"] in {"NOUN", "PROPN"}
            and graph.tokens[locations[0]]["pos"] in {"NOUN", "PROPN"},
            "External location has unresolved instruction authority",
        )


def _declared_payload_unit(
    snapshot, windows, unit, header, declared_name, attachments, *, selected_copy=False
):
    """Retain the entire captured payload as COPY-only, never factual authority."""
    record = {"unit_id": unit.id, "raw": asdict(unit.raw)}
    if selected_copy:
        record.update(
            original_features_json=unit.features_json,
            original_unknowns=list(unit.unknowns),
        )
    if not unit.raw.text.strip():
        return {**record, "owner": "syntax_separator"}
    if header["start"] <= unit.raw.start < unit.raw.end <= header["end"]:
        return {**record, "owner": "local_declared_instruction_definition"}
    whole = copy._unit_graph(snapshot.body, windows, unit.raw.start, unit.raw.end)
    roots = [i for i in whole.indices if whole.tokens[i]["dep"] == "ROOT"]
    _require(roots, "A captured payload predicate is required")
    covered, clauses = set(), []
    for root in sorted(roots):
        subtree = whole.subtree(root)
        _require(not covered & subtree, "Overlapping captured payload predicates")
        interval = whole.span(subtree)
        graph = copy._unit_graph(
            snapshot.body, windows, interval["start"], interval["end"]
        )
        _require(graph.indices == subtree, "Noncontiguous captured payload predicate")
        copy._one_root(graph)
        # A complete literal copy does not require correcting nominal roots or
        # auxiliary/complement POS proposals into an invented action parse.
        predicates = {root} | {
            i
            for i in graph.indices
            if graph.tokens[i]["pos"] in {"VERB", "AUX"}
            and graph.tokens[i]["dep"] not in {"aux", "auxpass", "amod"}
        }
        if selected_copy:
            _selected_payload_governance(graph, predicates, declared_name, attachments)
        else:
            _declared_payload_governance(graph, predicates, declared_name, attachments)
        clauses.append(
            {
                "clause": interval,
                "clauses": [
                    copy._copy_ast_clause(graph, i) for i in sorted(predicates)
                ],
                "tokens": [
                    {
                        **graph.tokens[i],
                        "source_start": graph.offset + graph.tokens[i]["start"],
                        "source_end": graph.offset + graph.tokens[i]["end"],
                    }
                    for i in sorted(graph.indices)
                ],
                "action_parse": "NOT_ASSERTED_actual_captured_proposals_retained",
                "argument_meaning": "UNASSESSED_requires_requested_NI",
            }
        )
        covered.update(subtree)
    _require(covered == whole.indices, "Unowned captured payload token")
    return {
        **record,
        "owner": "captured_declared_source_payload",
        "captured_clauses": clauses,
        "original_features_json": unit.features_json,
        "original_unknowns": list(unit.unknowns),
        "factual_authority": "NOT_ASSESSED",
        "required_reference_closure": "pending_consumer_replay",
    }


def _instruction_domain(snapshot, captures, units, *, evidence_profile=None):
    selected_copy = False
    if evidence_profile is not None:
        policy = recorded_evidence_policy(evidence_profile)
        _require(
            policy.record() == evidence_profile, "Canonical evidence profile required"
        )
        _require(
            policy.source_governance_profile == "requirement_bound_v1",
            "Selected COPY requires canonical source-bound evidence profile",
        )
        selected_copy = True
    windows = _windows(snapshot, captures)
    if selected_copy:
        _require(
            captures.identity == snapshot.identity, "Selected capture identity differs"
        )
        expected, cursor = [], 0
        for window, (_, _, annotation) in zip(captures.windows, windows, strict=True):
            _require(window.start == cursor, "Complete selected capture cover required")
            captured = json.loads(window.capture_json)
            rows, _, _ = source._window_inventory(
                snapshot, snapshot.identity, window, captured, annotation
            )
            expected.extend(rows)
            cursor = window.end
        _require(
            cursor == len(snapshot.body), "Complete selected capture cover required"
        )
        _require(
            source.canonical([asdict(unit) for unit in units])
            == source.canonical([asdict(unit) for unit in expected]),
            "Complete independently rebuilt selected source units required",
        )
    result = {
        "status": "mandatory_unresolved",
        "unit_ids": [unit.id for unit in units],
        "source_identity": asdict(snapshot.identity),
        "curated_opposition_inspection": "REQUIRED",
        "factual_authority": "NOT_ASSESSED",
        "source_relevance_exclusion": False,
        "namespace_disjointness": "NOT_ASSERTED",
    }
    if selected_copy:
        result.update(
            source_governance_profile="requirement_bound_v1",
            ownership_scope="complete_literal_selected_source_not_action_truth",
        )
    metadata = source._json_object(snapshot.metadata_json)
    try:
        _require(
            metadata.get("condition") is None
            and metadata.get("conflict_group") is None,
            "Curated or conditioned source requires independent all-member inspection",
        )
        header, parser = _instruction_definition(snapshot)
        relation = _definition_relation(
            snapshot,
            windows,
            header,
            captures,
            literal_declared_target=selected_copy,
        )
        if parser == "contextual_procedures._envelope_declaration":
            declaration = procedures._envelope_declaration(snapshot.body)
            left, right = procedures._envelope_named_subject(declaration["subject"])
            attachments = [
                {"start": first + token["start"], "end": first + token["end"]}
                for first, _, annotation in windows
                for token in annotation["tokens"]
                if token["lemma"].casefold() == "attachment"
                and token["dep"] in {"dobj", "obj"}
                and annotation["tokens"][token["head"]]["lemma"].casefold() == "record"
                and any(
                    annotation["tokens"][i]["dep"] == "compound"
                    for i in token["children"]
                )
            ]
            receipts = [
                _declared_payload_unit(
                    snapshot,
                    windows,
                    unit,
                    header,
                    declaration["subject"][left:right],
                    attachments,
                    selected_copy=selected_copy,
                )
                for unit in units
            ]
        else:
            receipts = [_copy_unit(snapshot, windows, unit, header) for unit in units]
        if selected_copy:
            for receipt, unit in zip(receipts, units, strict=True):
                receipt.update(
                    original_features_json=unit.features_json,
                    original_unknowns=list(unit.unknowns),
                )
        _require(
            any(
                row["owner"]
                in {"captured_root_directive", "captured_declared_source_payload"}
                for row in receipts
            ),
            "Actual instruction payload required",
        )
        result.update(
            status="copy_domain_structurally_owned",
            definition=header,
            definition_parser=parser,
            definition_relation=relation,
            units=receipts,
            ordinary_operand_meaning="UNASSESSED_requires_requested_NI",
            requested_complete_copy="NOT_ASSERTED",
            remaining_gates=[
                "actual_root_and_required_reference_binding",
                "global_overlap_curated_opposition_and_governance",
                "requested_operand_subject_applicability_NI",
                "source_authority_and_currentness",
            ],
        )
    except (ValueError, StopIteration) as exc:
        result["reason"] = str(exc)
    return result


def _role_relation_candidates(snapshot, captures, declarations):
    result = []
    catalogues = [
        row
        for row in declarations
        if row.kind == "role_catalogue" and row.source == snapshot.identity
    ]
    for first, last, annotation in _windows(snapshot, captures):
        graph = grammar.Graph(snapshot.body[first:last], annotation)
        original = source._Graph(snapshot.body, first, annotation)
        for root in sorted(graph.predicates):
            if graph.lemma(root) != "be":
                continue
            subjects = [
                i
                for i in graph.children[root]
                if graph.ts[i]["dep"] == "nsubj" and graph.lemma(i) == "role"
            ]
            values = [
                i
                for i in graph.children[root]
                if graph.ts[i]["dep"] in {"attr", "acomp"}
            ]
            if len(subjects) != 1 or len(values) != 1:
                continue
            subject, value = subjects[0], values[0]
            labels = [
                i for i in graph.children[subject] if graph.ts[i]["dep"] == "compound"
            ]
            if len(labels) != 1:
                continue
            scopes = [
                _literal(original, ids) for ids, _ in graph.direct_scopes(subject)
            ]
            label = _literal(original, graph.nominal(labels[0]))
            members = [
                {"catalogue_id": row.id, "literal": asdict(member)}
                for row in catalogues
                for member in row.members
                if member.text == label["text"]
                and len(scopes) == len(row.scope) == 1
                and scopes[0]["text"] == row.scope[0].text
            ]
            candidate = {
                "contract": "captured-role-relation-candidate-v1",
                "source": asdict(snapshot.identity),
                "raw": _literal(original, graph.subtree(root)),
                "subject": _literal(original, graph.nominal(subject)),
                "role_label": label,
                "predicate": _literal(original, {root}),
                "literal_value_candidate": _literal(original, graph.subtree(value)),
                "original_value_token": graph.ts[value],
                "scope_candidates": scopes,
                "catalogue_member_candidates": members,
                "original_subject_argument": asdict(
                    original.argument(subject, "role_subject_candidate")
                ),
                "original_value_argument": asdict(
                    original.argument(value, "role_value_candidate")
                ),
                "original_features": source._features(original, graph.subtree(root)),
                "actor_value": "UNBOUND",
                "accepted": False,
                "remaining_gates": [
                    "actual_request_member_scope_and_value_slot_lineage",
                    "actual_role_relation_subject_attribute_NI",
                    "captured_governing_context_NI",
                    "complete_condition_reference_curated_opposition_replay",
                    "source_authority_and_currentness",
                ],
            }
            candidate["id"] = "crr-" + source.digest(candidate)
            result.append(candidate)
    return result


def _field_candidates(declarations):
    return [
        {
            "contract": "captured-dependent-argument-candidate-v1",
            "declaration_id": row.id,
            "original_declaration": asdict(row),
            "actor_value": "UNBOUND",
            "accepted": False,
            "argument_meaning": "NOT_ASSERTED_FROM_POS_OR_CAPITALIZATION",
            "remaining_gates": [
                "prior_independently_supported_role_value_witness",
                "exact_member_scope_value_slot_ancestry",
                "complete_literal_argument_and_qualifier_replay",
                "requested_subject_attribute_units_negation_conditions_NI",
                "captured_governing_context_NI",
                "source_authority_and_currentness",
            ],
        }
        for row in declarations
        if row.kind == "literal_field"
    ]


def _source_record(snapshot, captures, inventory, enabled):
    units = tuple(unit for unit in inventory.units if unit.source == snapshot.identity)
    declarations = tuple(
        row for row in inventory.declarations if row.source == snapshot.identity
    )
    return {
        "identity": asdict(snapshot.identity),
        "unit_ids": [unit.id for unit in units],
        "declaration_ids": [row.id for row in declarations],
        "instruction_domain": _instruction_domain(snapshot, captures, units)
        if enabled
        else {"status": "legacy_source_inventory_only"},
        "relation_candidates": _role_relation_candidates(
            snapshot, captures, inventory.declarations
        )
        if enabled
        else [],
        "dependent_argument_candidates": _field_candidates(declarations)
        if enabled
        else [],
        "curated_opposition_inspection": "REQUIRED",
        "fact_or_actor_values": "UNBOUND",
    }


def reconstruct_source_productions(
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    *,
    sql_read_set_json,
    reading_profile=None,
):
    version = selected_version(reading_profile)
    inventory = source.declaration_inventory(manifest, snapshots, source_captures)
    source._json_object(sql_read_set_json)
    request = reconstruct_request_productions(
        question, capture, reading_profile=reading_profile
    )
    return json.loads(
        source.canonical(
            {
                "contract": SOURCE_CONTRACT,
                "reading_profile": reading_profile,
                "policy_enabled": version is not None,
                "request_productions": request,
                "original_inputs": {
                    "question": question,
                    "capture": capture,
                    "manifest": asdict(manifest),
                    "snapshots": [asdict(row) for row in snapshots],
                    "source_captures": [asdict(row) for row in source_captures],
                },
                "source_inventory": inventory.record(),
                "read_set": inventory.read_set.record(),
                "sql_read_set_json": sql_read_set_json,
                "sources": [
                    _source_record(
                        row,
                        next(
                            item
                            for item in source_captures
                            if item.identity == row.identity
                        ),
                        inventory,
                        version is not None,
                    )
                    for row in snapshots
                ],
                "excluded_sources": [],
                "full_plan_accepted": False,
                "source_NI_authority_currentness": "NOT_ASSESSED",
                "remaining_gates": [
                    "actual_requested_relation_and_dependency_NI",
                    "complete_governing_reference_curated_opposition_replay",
                    "actual_request_root_and_required_target_binding",
                    "complete_source_universe_and_current_SQL_recheck",
                    "source_authority_and_currentness",
                ],
            }
        )
    )


def validate_source_productions(record, *args, **kwargs):
    try:
        source._native(record)
        return source.canonical(record) == source.canonical(
            reconstruct_source_productions(*args, **kwargs)
        )
    except (ValueError, KeyError, TypeError, IndexError, RecursionError):
        return False


def reconstruct_root_composition(*args, selected_root_identity, **kwargs):
    """Index root-operation candidates; request/reference binding stays pending."""
    ledger = reconstruct_source_productions(*args, **kwargs)
    identity = (
        asdict(selected_root_identity)
        if type(selected_root_identity) is source.SourceIdentity
        else selected_root_identity
    )
    source._native(identity)
    roots = [
        row
        for row in ledger["sources"]
        if source.canonical(row["identity"]) == source.canonical(identity)
    ]
    _require(len(roots) == 1, "One exact original source identity is required")
    root = roots[0]
    if ledger["policy_enabled"]:
        _require(
            root["instruction_domain"]["status"] == "copy_domain_structurally_owned",
            "An actual declared instruction root is required",
        )
    rows = []
    for row in ledger["sources"]:
        if not ledger["policy_enabled"]:
            disposition = "LEGACY_SOURCE_INVENTORY_ONLY"
        elif row is root:
            disposition = "SELECTED_DECLARED_ROOT_CANDIDATE"
        elif row["instruction_domain"]["status"] == "copy_domain_structurally_owned":
            disposition = "UNREACHED_DECLARED_BLOCK_CANDIDATE_PENDING_RELATION_REPLAY"
        elif row["declaration_ids"] or row["relation_candidates"]:
            disposition = "SEPARATE_FACTUAL_PRODUCTION_WITH_ALL_REQUESTED_NI_GATES"
        else:
            disposition = "UNCLASSIFIED_SOURCE_REMAINS_MANDATORY"
        rows.append(
            {
                "source": row["identity"],
                "unit_ids": row["unit_ids"],
                "candidate_operation": disposition,
                "cannot_apply": "NOT_ASSERTED",
                "namespace_disjointness": "NOT_ASSERTED",
                "remaining_gates": [
                    "actual_root_required_target_and_curated_relation_replay",
                    "global_overlap_shared_qualifier_and_unknown_governance",
                    "requested_factual_NI_and_dependency_support",
                ],
            }
        )
    return {
        "contract": "captured-root-composition-v1",
        "reading_profile": ledger["reading_profile"],
        "policy_enabled": ledger["policy_enabled"],
        "source_production_sha256": source.digest(ledger),
        "selected_root_identity": identity,
        "sources": rows,
        "read_set": ledger["read_set"],
        "copy_scope": "COMPLETE_SELECTED_DECLARED_ROOT_PLUS_REQUIRED_REFERENCE_CLOSURE",
        "actual_captured_copy_request_binding": "NOT_ASSESSED",
        "required_reference_closure": "NOT_ASSESSED",
        "all_world_procedure_completeness": "NOT_ASSERTED",
        "excluded_sources": [],
        "remaining_gates": [
            "actual_request_root_and_reference_binding",
            "requested_subject_applicability_operand_NI",
            "complete_governing_and_curated_opposition_replay",
            "source_authority_and_currentness",
        ],
        "accepted": False,
    }


def validate_root_composition(record, *args, **kwargs):
    try:
        source._native(record)
        return source.canonical(record) == source.canonical(
            reconstruct_root_composition(*args, **kwargs)
        )
    except (ValueError, KeyError, TypeError, IndexError, RecursionError):
        return False
