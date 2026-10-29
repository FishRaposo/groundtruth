"""Parser-bound required copies; literal preservation grants no model truth/ACL.

Only staged_source_proof's independently bound v3 ingress calls prepare. The
original ordinary/v2 guard is unchanged. Unknown source grammar remains refusal.
"""

import json
from copy import deepcopy
from dataclasses import asdict

from app.evidence_policy import reading_version
from app.services import contextual_source_proof as body
from app.services import required_reference_closure as graph
from app.services.linguistic_source_scope import _DOC

CONTRACT = "parser-bound-required-copy-v1"
METHOD = "required_copy_v1"
SEPARATOR = "\n\n"


def _require(condition, message):
    if not condition:
        raise body.SourceGuardRefusal(message)


def _nominal(g, head):
    indices = g.nominal(head)
    _require(
        g.nominal_closed(head)
        and all(
            g.tokens[i]["pos"] in {"NOUN", "PROPN", "ADJ", "DET", "NUM", "PUNCT"}
            for i in indices
        ),
        "Required-copy target has unresolved nominal ownership",
    )
    return indices


def _named(g, clause):
    root = body._one_root(g)
    if g.lemma(root) not in {"name", "call"}:
        return None
    subjects = g.children(root, {"nsubjpass"})
    values = g.children(root, {"oprd", "attr", "dobj"})
    _require(
        len(subjects) == len(values) == 1, "Required-copy name declaration is ambiguous"
    )
    _require(
        g.lemma(subjects[0]) in _DOC | body._CONTAINERS,
        "Required-copy declaration must name document material",
    )
    subject, value = _nominal(g, subjects[0]), _nominal(g, values[0])
    allowed = subject | value | {root} | set(g.children(root, {"auxpass"}))
    _require(
        g.tokens[root]["pos"] == "VERB"
        and not any(
            g.tokens[i]["dep"] == "neg" or g.tokens[i]["tag"] == "MD" for i in g.indices
        )
        and all(i in allowed or g.tokens[i]["pos"] == "PUNCT" for i in g.indices),
        "Required-copy name declaration has unresolved conditions or arguments",
    )
    return {
        "kind": "appendix",
        "raw": clause,
        "label_range": g.span(value),
        "label": g.span(value)["text"],
        "predicate": g.span({root}),
        "token_indices": sorted(g.indices),
    }


def _reference(g, clause):
    root = body._one_root(g)
    if g.lemma(root) not in body._NORMATIVE:
        return None
    _require(
        g.tokens[root]["pos"] == "VERB",
        "Required-copy instruction predicate is unresolved",
    )
    objects = g.children(root, {"dobj", "obj"})
    _require(len(objects) == 1, "Required-copy instruction needs one complete operand")
    operand = objects[0]
    target = operand
    # A complete nominal is a direct target. A nominal operand plus one actual
    # owned PP retains both the full operand and its distinct target designator.
    if not g.nominal_closed(operand):
        pps = [
            (p, o)
            for p in g.children(operand, {"prep"})
            for o in g.children(p, {"pobj"})
        ]
        _require(len(pps) == 1, "Required-copy operand has ambiguous target ownership")
        prep, target = pps[0]
        used = g.nominal(operand) | {prep} | _nominal(g, target)
        _require(
            g.subtree(operand) <= used,
            "Required-copy operand contains unresolved material",
        )
    target_ids = _nominal(g, target)
    allowed = {root} | g.subtree(operand)
    _require(
        all(i in allowed or g.tokens[i]["pos"] == "PUNCT" for i in g.indices),
        "Required-copy instruction conditions/modality/coordination remain unresolved",
    )
    return {
        "raw": clause,
        "target_literal": g.span(target_ids),
        "operand": g.span(g.subtree(operand)),
        "predicate": g.span({root}),
        "token_indices": sorted(g.indices),
        "ast": body._copy_ast_clause(g, root),
    }


def _fragments(snapshot):
    cursor, fragments, seen = 0, [], set()
    for chunk in snapshot["chunks"]:
        text = chunk["content"]
        start = snapshot["body"].find(text)
        _require(
            start >= 0 and snapshot["body"].find(text, start + 1) < 0,
            "Required-copy chunk mapping is ambiguous",
        )
        end = start + len(text)
        _require(
            chunk["id"] not in seen and start <= cursor < end,
            "Required-copy chunks have gaps/order/duplicate identities",
        )
        fragments.append(
            {
                **body._snapshot_identity(snapshot),
                "chunk_id": chunk["id"],
                "chunk_start": cursor - start,
                "chunk_end": end - start,
                "document_start": cursor,
                "document_end": end,
            }
        )
        seen.add(chunk["id"])
        cursor = end
    _require(
        cursor == len(snapshot["body"]),
        "Required-copy immutable body has an uncovered tail",
    )
    return fragments


def _analyse(snapshot, windows, requirement):
    text = snapshot["body"]
    identity = body._snapshot_identity(snapshot)
    cover = body.source_scope(text, identity, windows, asked_topic=requirement["topic"])
    validated = body._windows(text, windows)
    declaration = body._envelope_declaration(text)
    relation = body._declared_relation(
        text, declaration, windows, requirement["topic"], requirement
    )
    names, references, ast, obligations, dispositions = [], [], [], [], []
    for unit in cover["units"]:
        if unit["kind"] == "separator":
            continue
        _require(
            unit["kind"] != "nonoperative_region"
            and "capture_boundary" not in unit["unresolved"],
            "Required-copy source unit has unresolved capture/quotation",
        )
        if declaration.start() <= unit["start"] < unit["end"] <= declaration.end():
            dispositions.append(
                {
                    "unit_id": unit["id"],
                    "raw": body._literal(text, unit["start"], unit["end"]),
                    "retained_unknowns": unit["unresolved"],
                    "method": "independently_bound_whole_governing_declaration",
                }
            )
            continue
        g = body._unit_graph(text, validated, unit["start"], unit["end"])
        clause = body._literal(text, unit["start"], unit["end"])
        named = _named(g, clause)
        if named is not None:
            names.append(named)
            dispositions.append(
                {
                    "unit_id": unit["id"],
                    "raw": clause,
                    "retained_unknowns": unit["unresolved"],
                    "method": "complete_actual_name_declaration_ast",
                    "evidence": named,
                }
            )
            continue
        reference = _reference(g, clause)
        if reference is not None:
            references.append(reference)
            dispositions.append(
                {
                    "unit_id": unit["id"],
                    "raw": clause,
                    "retained_unknowns": unit["unresolved"],
                    "method": "complete_actual_required_reference_ast",
                    "evidence": reference,
                }
            )
            continue
        parsed = body._copy_clause(g, clause)
        inspected = body._ordinary_reference_inspections(
            g, parsed, identity, clause, unit["id"]
        )
        ast.append({"ast": parsed, "lexical_reference_inspections": inspected})
        dispositions.append(
            {
                "unit_id": unit["id"],
                "raw": clause,
                "retained_unknowns": unit["unresolved"],
                "method": "existing_complete_ordinary_directive_ast",
                "evidence": parsed,
            }
        )
        # Keep the existing exact operand semantics and its mandatory model
        # obligations; an ordinary copy does not turn an operand into a fact.
        from app.evidence_policy import source_copy_version

        copy_version = source_copy_version(reading_profile="contextual_source_v3")
        if copy_version.operand_semantics != "none":
            _, rows = body._semantic_operand_rows(
                g, parsed, unit["id"], identity, copy_version
            )
            obligations.extend(rows)
    return {
        "identity": identity,
        "body": text,
        "source_windows": deepcopy(windows),
        "source_scope": cover,
        "declared_relation": relation,
        "name_declarations": names,
        "references": references,
        "directive_ast": ast,
        "unit_dispositions": dispositions,
        "operand_obligations": obligations,
        "fragments": _fragments(snapshot),
    }


def _typed_source(snapshot):
    identity = graph.SourceIdentity(**body._snapshot_identity(snapshot))
    chunks = tuple(
        graph.SourceChunk(
            c["id"],
            c["index"],
            graph.RawRange(
                snapshot["body"].find(c["content"]),
                snapshot["body"].find(c["content"]) + len(c["content"]),
                c["content"],
            ),
            body._json(c["metadata"]),
        )
        for c in snapshot["chunks"]
    )
    return graph.SourceSnapshot(
        identity,
        snapshot["title"],
        snapshot["body"],
        body._json(snapshot["metadata"]),
        chunks,
    )


def _observations(
    root_identity, *, plan, requirement, use, planning_inputs, authoritative_snapshots
):
    """Reconstruct actual source observations before any NLI result exists."""
    windows = {}
    for source in planning_inputs["source_captures"]:
        identity = source["identity"]
        sid = identity["document_id"]
        body._same(identity, body._snapshot_identity(authoritative_snapshots[sid]))
        windows[sid] = [
            {
                "start": w["start"],
                "end": w["end"],
                "capture": json.loads(w["capture_json"]),
            }
            for w in source["windows"]
        ]
    _require(
        set(windows) == set(authoritative_snapshots),
        "Required-copy full source capture universe differs",
    )
    snapshots = tuple(_typed_source(s) for s in authoritative_snapshots.values())
    sources = {s.identity.document_id: s for s in snapshots}
    observed, analyses = {}, []
    for sid, snapshot in authoritative_snapshots.items():
        try:
            parsed = _analyse(snapshot, windows[sid], requirement)
            observed[sid] = parsed
            failures = ()
        except (body.SourceGuardError, ValueError) as exc:
            parsed = None
            failures = (str(exc),)
        source = sources[sid]
        declarations = []
        refs = []
        if parsed:
            relation = parsed["declared_relation"]
            declarations.append(
                graph.Declaration(
                    source.identity,
                    "procedure",
                    relation["declared_name"]["text"],
                    graph.RawRange(**relation["proposition"]),
                    graph.RawRange(**relation["declared_name"]),
                )
            )
            declarations.extend(
                graph.Declaration(
                    source.identity,
                    "appendix",
                    n["label"],
                    graph.RawRange(**n["raw"]),
                    graph.RawRange(**n["label_range"]),
                )
                for n in parsed["name_declarations"]
            )
            refs.extend(
                graph.RequiredReference(
                    source.identity,
                    r["target_literal"]["text"],
                    graph.RawRange(**r["raw"]),
                    graph.RawRange(**r["target_literal"]),
                )
                for r in parsed["references"]
            )
        else:
            # Nonrequired sources need not themselves be routines. Retain all
            # actual source windows/failures, and independently scan actual
            # complete body-name declarations as target/ambiguity proposals.
            declarations.extend(
                _candidate_names(
                    snapshot, windows[sid], source.identity, requirement["topic"]
                )
            )
        analyses.append(
            graph.SourceAnalysis(
                source.identity,
                CONTRACT,
                body._json(
                    parsed or {"unresolved": failures, "source_windows": windows[sid]}
                ),
                (graph.RawRange(0, len(source.body), source.body),),
                tuple(declarations),
                tuple(refs),
                failures,
            )
        )
    root = root_identity["document_id"]
    _require(
        root in observed and observed[root]["references"],
        "No independently bound required-copy instruction",
    )
    from app.services.staged_plan_replay import _arguments
    from app.services.staged_production_obligations import declared_copy_ownership
    from app.services.staged_request import compile_request

    actual_args = _arguments(planning_inputs, authoritative_snapshots)
    ownership = declared_copy_ownership(
        compile_request(actual_args["question"], actual_args["capture"]),
        actual_args["manifest"],
        actual_args["snapshots"],
        actual_args["source_captures"],
    )
    dispositions = _nonrequired_dispositions(plan, analyses, snapshots, ownership)
    return observed, tuple(analyses), snapshots, windows, dispositions


def _nonrequired_dispositions(plan, analyses, snapshots, ownership):
    """Retain unknown/global material; defer only independently closed scopes."""
    excluded = set(json.loads(plan["scope_bridge_json"])["excluded"])
    result = []
    for analysis, snapshot in zip(analyses, snapshots, strict=True):
        sid = snapshot.identity.document_id
        if not analysis.unresolved:
            continue
        status = "UNRESOLVED_POTENTIALLY_GOVERNING"
        source_ownership = next(
            row for row in ownership["sources"] if row["identity"]["document_id"] == sid
        )
        metadata = json.loads(snapshot.metadata_json)
        if metadata.get("condition") or metadata.get("conflict_group"):
            status = "UNRESOLVED_POTENTIALLY_GOVERNING"
        elif source_ownership["copy_ownership_complete"] is True:
            status = "RETAINED_CLOSED_NONPROCEDURAL_COPY_OWNERSHIP"
        elif sid in excluded:
            status = "RETAINED_CLOSED_OTHER_NAMESPACE_BRIDGE"
        result.append(
            {
                "source_identity": asdict(snapshot.identity),
                "status": status,
                "retained_analysis_failures": list(analysis.unresolved),
                "copy_production_ownership": source_ownership,
                "ownership_read_set": ownership["read_set"],
            }
        )
    return result


def _candidate_names(snapshot, windows, identity, asked_topic):
    text = snapshot["body"]
    validated = body._windows(text, windows)
    cover = body.source_scope(
        text, body._snapshot_identity(snapshot), windows, asked_topic=asked_topic
    )
    names = []
    for unit in cover["units"]:
        if unit["kind"] in {"separator", "nonoperative_region"}:
            continue
        try:
            g = body._unit_graph(text, validated, unit["start"], unit["end"])
            named = _named(g, body._literal(text, unit["start"], unit["end"]))
        except (ValueError, body.SourceGuardError):
            continue
        if named:
            names.append(
                graph.Declaration(
                    identity,
                    "appendix",
                    named["label"],
                    graph.RawRange(**named["raw"]),
                    graph.RawRange(**named["label_range"]),
                )
            )
    return names


def _bindings(root, analyses, windows):
    bindings = []
    by_id = {a.source.document_id: a for a in analyses}
    todo, seen = [root], set()
    while todo:
        sid = todo.pop(0)
        if sid in seen:
            continue
        seen.add(sid)
        analysis = by_id[sid]
        for ref in analysis.references:
            candidates = [
                d
                for a in analyses
                for d in a.declarations
                if d.kind == "appendix" and d.label == ref.target_literal
            ]
            _require(
                len(candidates) == 1,
                "Required-copy target declaration absent or ambiguous",
            )
            target = candidates[0]
            todo.append(target.source.document_id)
            bindings.append(
                graph.BindingEvidence(
                    ref,
                    target.source,
                    target,
                    ref.raw,
                    body._json(
                        {
                            "method": "complete_actual_nominal_and_unique_body_name",
                            "source_capture": windows[ref.source.document_id],
                            "target_capture": windows[target.source.document_id],
                        }
                    ),
                )
            )
    return bindings


def prepare(
    root_identity, *, plan, requirement, use, planning_inputs, authoritative_snapshots
):
    """Reconstruct actual source observations before NLI, then bounded closure."""
    observed, analyses, snapshots, windows, dispositions = _observations(
        root_identity,
        plan=plan,
        requirement=requirement,
        use=use,
        planning_inputs=planning_inputs,
        authoritative_snapshots=authoritative_snapshots,
    )
    root = root_identity["document_id"]
    bindings = _bindings(root, analyses, windows)
    universe = graph.AuthorizedUniverse(
        body._json(planning_inputs["manifest"]), tuple(s.identity for s in snapshots)
    )
    try:
        closure = graph.reconstruct_closure(
            root,
            snapshots=snapshots,
            analyses=tuple(analyses),
            binding_evidence=tuple(bindings),
            universe=universe,
        )
    except graph.ClosureRefusal as exc:
        raise body.SourceGuardRefusal(str(exc)) from exc
    pending = [
        d for d in dispositions if d["status"] == "UNRESOLVED_POTENTIALLY_GOVERNING"
    ]
    if pending:
        raise body.SourceReferenceUnresolved(
            "Unresolved nonrequired source remains a mandatory governing obligation",
            {
                "contract": CONTRACT + ":unresolved_sources",
                "source_dispositions": dispositions,
            },
        )
    documents, obligations, edges = _obligations(
        closure, observed, bindings, requirement
    )
    full = {"start": 0, "end": len(observed[root]["body"])}
    return {
        "contract": CONTRACT,
        "method": METHOD,
        "root_identity": deepcopy(root_identity),
        "documents": documents,
        "edges": edges,
        "ordered_document_ids": closure["ordered_document_ids"],
        "structural_closure": closure,
        "rendered_text": closure["rendered_text"],
        "separator": SEPARATOR,
        "nli_obligations": obligations,
        "structural_obligations": [
            {
                "kind": "reference_binding",
                "verification_method": "exact_source_structure",
                "evidence": edge,
            }
            for edge in edges
        ]
        + [
            {
                "kind": "ordered_immutable_boundaries",
                "verification_method": "exact_source_structure",
                "order": closure["ordered_document_ids"],
                "inclusions": closure["inclusions"],
            }
        ],
        "copy_obligations": [
            {
                "source_identity": doc["identity"],
                "verification_method": "exact_source_copy",
                "source_range": {"start": 0, "end": len(doc["body"])},
                "fragments": doc["fragments"],
            }
            for doc in documents
        ],
        "responsibilities": {
            "NLI": "Qualified namespace/applicability; no action execution claim.",
            "exact_source_structure": "Identity, names, scope, order, boundaries.",
            "exact_source_copy": "Every original instruction and condition.",
            "exact_output_cover": "Independent renderer and history replay.",
            "independent_factual_claims": "Separate factual and role consumers.",
        },
        "request_obligation_inventory": body._bound_request_obligations(
            plan, requirement, use, full, reading_profile="contextual_source_v3"
        ),
        "full_planning_read_set_sha256": body._digest(
            planning_inputs["sql_read_set_json"]
        ),
        "permissions_currentness": "REQUIRED_SEPARATELY",
        "action_truth": "NOT_ASSERTED",
        "nonrequired_source_dispositions": dispositions,
    }


def _obligations(closure, observed, bindings, requirement):
    documents = [observed[sid] for sid in closure["ordered_document_ids"]]
    obligations, edges = [], []
    for doc in documents:
        sid = doc["identity"]["document_id"]
        for kind in ("namespace", "applicability"):
            obligations.append(
                {
                    "name": kind + ":" + sid,
                    "verification_method": "nli_entailment",
                    "premise": doc["body"],
                    "hypothesis": doc["declared_relation"]["proposition"]["text"],
                    "source_identity": doc["identity"],
                    "source_range": {"start": 0, "end": len(doc["body"])},
                }
            )
        obligations.extend(doc["operand_obligations"])
    for binding in bindings:
        source, target = (
            observed[binding.reference.source.document_id],
            observed[binding.target.document_id],
        )
        if source not in documents:
            continue
        literal = asdict(binding.reference.literal_range)
        relation = asdict(binding.reference.raw)
        declaration = asdict(binding.target_declaration.raw)
        edge = {
            "source_identity": source["identity"],
            "target_identity": target["identity"],
            "target_literal": literal,
            "source_relation": relation,
            "target_declaration": declaration,
        }
        edges.append(edge)
        premise = source["body"] + SEPARATOR + target["body"]
        obligations.append(
            {
                "name": "incorporation:" + str(len(edges)),
                "kind": "scoped_required_body_applicability",
                "verification_method": "nli_entailment",
                "premise": premise,
                "hypothesis": (
                    "Under the source-declared scope "
                    f"«{source['declared_relation']['proposition']['text']}», "
                    "the instruction body declared as "
                    f"«{literal['text']}» by «{declaration['text']}» "
                    f"applies as incorporated by «{relation['text']}»."
                ),
                "source_relation": relation,
                "target_declaration": declaration,
                "source_identity": source["identity"],
                "target_identity": target["identity"],
                "meaning": (
                    "Scoped applicability; identity and edges are structural; "
                    "executed actions are not asserted."
                ),
            }
        )
    return documents, obligations, edges


def envelope(required, *, plan, requirement, use):
    root = required["documents"][0]
    return {
        "contract": reading_version("contextual_source_v3").procedure,
        "reading_profile": "contextual_source_v3",
        "method": METHOD,
        "source_identity": root["identity"],
        "source_body": root["body"],
        "requested_subject": requirement["topic"],
        "requirement": requirement,
        "request_use": use,
        "request_plan_sha256": body._digest(plan),
        "required_copy": required,
        "nli_obligations": required["nli_obligations"],
        "literal_scope": {
            "source_subject": requirement["topic"],
            "requested_subject": requirement["topic"],
            "disclosure": f"Source-declared scope: {requirement['topic']}.",
            "claim": "Full ordered required source copies; action truth not asserted.",
        },
        "request_obligation_inventory": required["request_obligation_inventory"],
    }


def proof_from_envelope(requirement, source, proposal, inventory):
    """Unassessed producer descriptor, independently recomputed by output."""
    required = inventory["required_copy"]
    body._same(required["contract"], CONTRACT)
    body._same(source.body, required["documents"][0]["body"])
    return proof_record(proposal, inventory)


def proof_record(proposal, inventory):
    required = inventory["required_copy"]
    text = inventory["source_body"]
    body._same(proposal["document_id"], inventory["source_identity"]["document_id"])
    raw = proposal["document_range"]
    body._same(proposal["text"], text[raw["start"] : raw["end"]])
    return {
        "contract": inventory["contract"],
        **inventory["source_identity"],
        "method": METHOD,
        "source_body": text,
        "body_length": len(text),
        "extent": {"start": 0, "end": len(text)},
        "closure": {"kind": "required_copy_graph", "contract": CONTRACT},
        "inventory": deepcopy(inventory),
        "proof_units": [],
        "raw_seed": {
            k: deepcopy(proposal[k])
            for k in (
                "proposal_id",
                "origin",
                "chunk_id",
                "text",
                "chunk_range",
                "document_range",
            )
        },
        "fragments": [
            deepcopy(f) for doc in required["documents"] for f in doc["fragments"]
        ],
        "required_copy": deepcopy(required),
    }
