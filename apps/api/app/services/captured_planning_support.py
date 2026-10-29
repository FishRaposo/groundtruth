"""New-profile planning NI over reconstructed source-faithful clauses."""

import json
from dataclasses import asdict, dataclass

from app.services import planning_support as retained
from app.services.captured_governing_context import reconstruct_governing_context
from app.services.captured_plan_binding import (
    _requirement_bound,
    prepare_candidate_plan,
)
from app.services.captured_plan_inputs import _profile
from app.services.planning_declarations import (
    RawRange,
    SourceIdentity,
    canonical,
    digest,
)


@dataclass(frozen=True)
class CapturedAssertionSet(retained.AssertionSet):
    def record(self):
        result = super().record()
        result["contract"] = "captured-planning-assertions-v1"
        return result


def prepare_planning_assertions(*args, support_metadata, **kwargs):
    if args:
        raise ValueError("Named original captured input arguments required")
    candidate = prepare_candidate_plan(**kwargs)
    profile_record, profile = _profile(kwargs["evidence_profile"])
    requirement_bound = _requirement_bound(profile_record)
    structure = json.loads(candidate.structure_json)
    ledger = json.loads(candidate.source_productions_json)
    declarations = ledger["source_inventory"]["declarations"]
    assertions, pending = [], []
    for blocker in json.loads(candidate.unresolved_json):
        pending.append(
            retained.PendingObligation(
                digest(blocker),
                "request_structure",
                blocker["reason"] if requirement_bound else canonical(blocker),
            )
        )
    for requirement, use in zip(candidate.requirements, candidate.uses, strict=True):
        if requirement.kind != "role_catalogue":
            continue
        sources = json.loads(use.source_uses_json)
        if len(sources) != 1:
            continue
        catalogue = next(
            r for r in declarations if r["id"] == sources[0]["declaration_id"]
        )
        node = next(n for n in structure["nodes"] if n["id"] == use.node_id)
        scope = catalogue["scope"][0]["text"]
        members = [
            m
            for m in json.loads(candidate.members_json)
            if m["group_id"] == requirement.id
        ]
        hypotheses = [
            ("catalogue_scope", "The roles stated here are for " + scope + ".", None),
            (
                "catalogue_literal_set",
                "The stated role labels for "
                + scope
                + " are "
                + retained._join([m["literal"]["text"] for m in members])
                + ".",
                None,
            ),
            *[
                (
                    "catalogue_member_relation",
                    m["literal"]["text"] + " is a role for " + scope + ".",
                    m,
                )
                for m in members
            ],
        ]
        _emit(
            assertions,
            pending,
            kwargs,
            profile,
            requirement.id,
            node,
            catalogue,
            hypotheses,
        )
        names = [
            r
            for r in declarations
            if r["kind"] == "literal_name" and r["literal"]["text"] == scope
        ]
        if len(names) == 1:
            _emit(
                assertions,
                pending,
                kwargs,
                profile,
                requirement.id,
                node,
                names[0],
                [("literal_name_relation", "The stated name is " + scope + ".", None)],
            )
        else:
            pending.append(
                retained.PendingObligation(
                    requirement.id,
                    "literal_name",
                    "Missing or ambiguous actual declared literal scope name",
                )
            )
    return CapturedAssertionSet(
        canonical(candidate.record()),
        canonical(retained._metadata(support_metadata)),
        kwargs["sql_read_set_json"],
        tuple(assertions),
        tuple(pending),
    )


def _emit(
    assertions, pending, arguments, profile, requirement_id, node, row, hypotheses
):
    original = {
        k: arguments[k]
        for k in (
            "question",
            "capture",
            "manifest",
            "snapshots",
            "source_captures",
            "sql_read_set_json",
        )
    }
    if row["kind"] == "literal_name":
        # Fixed conservative context for names, outside the narrow931 fact selector.
        snapshot = next(
            s for s in arguments["snapshots"] if asdict(s.identity) == row["source"]
        )
        context = {
            "contract": "captured-name-whole-source-context-v1",
            "source_identity": row["source"],
            "selected_clause": row["raw"],
            "context": {"start": 0, "end": len(snapshot.body), "text": snapshot.body},
            "governing_opposition_status": "MANDATORY_INDEPENDENT_REPLAY",
            "publication_ready": False,
            "original_declaration": row,
        }
        features = json.loads(row["features_json"])
        if any(
            features.get(k)
            for k in (
                "conditions",
                "modality",
                "negation",
                "references",
                "governors",
                "unbound_condition_markers",
            )
        ):
            context["context"] = None
    else:
        context = reconstruct_governing_context(
            **original,
            source_identity=row["source"],
            selected_clause=row["raw"],
            reading_profile=profile,
        )
    if context["context"] is None:
        pending.append(
            retained.PendingObligation(
                requirement_id,
                row["kind"],
                "Captured governing context remains unresolved",
            )
        )
        return
    for kind, hypothesis, member in hypotheses:
        for channel, premise_range in (
            ("local", row["raw"]),
            ("context", context["context"]),
        ):
            relation = {
                "requirement_id": requirement_id,
                "kind": kind,
                "member_binding_id": member["id"] if member else None,
                "literal_member_binding": member,
                "original_node": node,
                "original_declaration": row,
                "context": context,
                "premise_range": premise_range,
                "channel": channel,
                "hypothesis": hypothesis,
            }
            identifier = "cpa-" + digest(relation)
            pair = retained.PlanningPair(
                premise_range["text"],
                hypothesis,
                requirement_id,
                row["source"]["document_id"] + ":" + identifier,
            )
            assertions.append(
                retained.PlanningAssertion(
                    identifier,
                    node["id"],
                    kind + ":" + channel,
                    row["id"],
                    SourceIdentity(**row["source"]),
                    RawRange(**premise_range),
                    canonical(relation),
                    pair,
                    member["id"] if member else None,
                )
            )


@dataclass(frozen=True)
class CapturedPlanningSupport(retained.PlanningSupportResult):
    accepted_scope: str = "captured_planning_source_relations_only"

    def record(self):
        result = super().record()
        result["contract"] = "captured-planning-support-v1"
        return result


def reconstruct_planning_support(*args, observations, actual_executions, **kwargs):
    from app.services.captured_support_receipts import replay_assertions

    prepared = prepare_planning_assertions(*args, **kwargs)
    result = replay_assertions(prepared, observations, actual_executions)
    fields = asdict(result)
    fields.pop("accepted_scope")
    # Reuse typed transports, not asdict's recursively mutable projections.
    fields.update(assertion_set=prepared, assessments=result.assessments)
    return CapturedPlanningSupport(**fields)


def validate_planning_support(record, *args, **kwargs):
    try:
        retained.source._native(record)
        return canonical(record) == canonical(
            reconstruct_planning_support(*args, **kwargs).record()
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RecursionError,
    ):
        return False


# Shared immutable805 execution transports, not duplicate verifier semantics.
NliExecution = retained.NliExecution
NliObservation = retained.NliObservation
PlanningPair = retained.PlanningPair
PlanningAssertion = retained.PlanningAssertion
