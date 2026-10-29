"""Captured whole-clause availability classification, never factual support.

The approved parser supplies syntax proposals. Only complete canonical actor /
availability / clock structures can establish a different field for role
inspection. Unknown instructions, qualifications and nominal edges stay unknown.
"""

import re

from app.services.answer_requirements import Requirement
from app.services.curated_source_closure import (
    captured_units,
    closed_nominal,
    consume_clause,
)
from app.services.requirement_binding import support_claim

CONTRACT = "captured-role-source-closure-v1"
_CLOCK = re.compile(r"\d{1,2}:\d{2}\Z")


def _clock(graph, head):
    if not _CLOCK.fullmatch(graph.tokens[head]["text"]):
        return None
    nominal = closed_nominal(graph, head, allow_numeric_head=True)
    return nominal if nominal == {head} else None


def _interval(graph, start):
    """An exact from-clock/to-clock production, with bounded and-from peers."""
    if graph.tokens[start]["pos"] != "ADP" or graph.lemma(start) != "from":
        return None
    first = graph.children(start, {"pobj"})
    ends = graph.children(start, {"prep"})
    if len(first) != 1 or len(ends) != 1:
        return None
    last = graph.children(ends[0], {"pobj"})
    if (
        graph.tokens[ends[0]]["pos"] != "ADP"
        or graph.lemma(ends[0]) != "to"
        or len(last) != 1
        or _clock(graph, first[0]) is None
        or _clock(graph, last[0]) is None
    ):
        return None
    used = {start, first[0], ends[0], last[0]}
    ranges = [graph.span({first[0], ends[0], last[0]})]
    peers = graph.children(start, {"conj"})
    connectors = graph.children(start, {"cc"})
    if peers:
        if len(peers) != 1 or len(connectors) != 1:
            return None
        connector = connectors[0]
        if graph.tokens[connector]["pos"] != "CCONJ" or graph.lemma(connector) != "and":
            return None
        other = _interval(graph, peers[0])
        if other is None:
            return None
        used |= {connector} | other[0]
        ranges.extend(other[1])
    elif connectors:
        return None
    return used, ranges


def _availability_predicate(graph, literal, predicate):
    if graph.tokens[predicate]["pos"] != "AUX" or graph.lemma(predicate) != "be":
        return None
    subjects = graph.children(predicate, {"nsubj"})
    complements = graph.children(predicate, {"acomp"})
    if len(subjects) != 1 or len(complements) != 1:
        return None
    actor = closed_nominal(graph, subjects[0])
    adjective = complements[0]
    if (
        actor is None
        or graph.tokens[adjective]["pos"] != "ADJ"
        or graph.lemma(adjective) not in {"available", "present"}
    ):
        return None
    preps = graph.children(adjective, {"prep"})
    if len(preps) != 1:
        return None
    interval = _interval(graph, preps[0])
    if interval is None:
        return None
    actor_literal = graph.span(actor)
    question = f"What is {actor_literal['text']}'s availability?"
    typed = Requirement(
        "role-other-field",
        question,
        0,
        len(question),
        question,
        "availability",
        actor_literal["text"],
        (),
        relation="availability",
        attribute="availability",
    )
    for value in interval[1]:
        claim = support_claim(
            typed,
            literal["text"],
            value["start"] - literal["start"],
            value["end"] - literal["start"],
            reading_profile="contextual_source_v2",
        )
        if claim.rejection or not claim.hypothesis or claim.checks or claim.proof_edges:
            return None
    return (
        {predicate, adjective} | actor | interval[0],
        {
            "actor": actor_literal,
            "predicate": graph.span({predicate, adjective}),
            "intervals": interval[1],
        },
    )


def availability_clause(graph, literal):
    roots = [i for i in graph.indices if graph.tokens[i]["head"] == i]
    if len(roots) != 1:
        return None
    root = roots[0]
    predicates = [root, *graph.children(root, {"conj"})]
    used, actors = set(), []
    for predicate in predicates:
        result = _availability_predicate(graph, literal, predicate)
        if result is None:
            return None
        used |= result[0]
        actors.append(result[1])
    connectors = graph.children(root, {"cc"})
    if len(predicates) > 1:
        if len(predicates) != 2 or len(connectors) != 1:
            return None
        connector = connectors[0]
        if graph.tokens[connector]["pos"] != "CCONJ" or graph.lemma(connector) != "and":
            return None
        used.add(connector)
    elif connectors:
        return None
    proof = consume_clause(graph, used)
    if not proof["complete"]:
        return None
    return {
        "kind": "availability",
        "actors": actors,
        "dependency_closure": proof,
        "meaning": "typed other field in source; no support or role assignment claim",
    }


def source_closure(snapshot, source_windows, requirement):
    from app.services.curated_conflict_proof import fact_scope

    capture, units = captured_units(snapshot, source_windows)
    # Existing695 temporal productions supply their own complete NP/clause
    # closure. Only its positive other-field proof is reusable here.
    temporal = fact_scope(requirement, snapshot, source_windows)["scope_cover"]
    rows = []
    for graph, literal, uncertainty in units:
        parsed = (
            availability_clause(graph, literal)
            if graph and uncertainty is None
            else None
        )
        rows.append(
            {
                "source_range": {k: literal[k] for k in ("start", "end")},
                "text": literal["text"],
                "uncertainty": uncertainty,
                "availability": parsed,
                "other_temporal": next(
                    (
                        row["other_relation_proof"]
                        for row in temporal
                        if row["source_range"]
                        == {k: literal[k] for k in ("start", "end")}
                        and row["exclusion_reason"] == "closed_other_field"
                    ),
                    None,
                ),
            }
        )
    return {"contract": CONTRACT, "source_capture": capture, "units": rows}


def closure_inventory(findings, snapshots, requirements):
    """Validate complete repeated captures before accepting any role finding."""
    observed = {}
    for finding in findings:
        if finding.get("inspection_method") != CONTRACT:
            raise ValueError("V2 role scope requires captured source closure")
        rows = finding["source_closures"]
        identifiers = [
            row["source_capture"]["source_identity"]["document_id"] for row in rows
        ]
        if identifiers != sorted(snapshots) or len(set(identifiers)) != len(
            identifiers
        ):
            raise ValueError("Complete all-source role capture inventory required")
        for row in rows:
            identifier = row["source_capture"]["source_identity"]["document_id"]
            windows = row["source_capture"]["source_windows"]
            actual = source_closure(
                snapshots[identifier], windows, requirements[finding["requirement_id"]]
            )
            # JSON comparison preserves bool/int distinctions in captured graphs.
            from app.services.contextual_output import _same

            _same(row, actual, "Role captured closure differs from actual source")
            if identifier in observed:
                _same(
                    windows,
                    observed[identifier],
                    "Role captures differ across requirements",
                )
            observed[identifier] = windows
    return observed
