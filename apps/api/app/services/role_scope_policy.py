"""Declared ordinary-session interpretation, separate from source fact support.

This proposes two exact scopes for a lead/deputy requirement. It never establishes
that an activity assignment applies: the caller must inspect all authorized
session exceptions, prefer explicit assignments, and assess the source claim.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from typing import ClassVar, Literal

from app.evidence_policy import ROLE_POLICY_CONTRACT, EvidencePolicy
from app.services.answer_requirements import Requirement


def replay_native_request_use(record, requirement, use):
    """Replay local features and inherited frame ownership as separate records."""
    from app.services.captured_plan_binding import prepare_structure
    from app.services.captured_plan_requirements import (
        closed_original_frames,
        derive_requirements,
    )
    from app.services.planning_declarations import canonical
    from app.services.request_parser import validate_capture

    question = record["question"]
    structure = json.loads(record["structure_json"])
    capture = structure["original_capture"]
    rebuilt = prepare_structure(
        question, capture, reading_profile="contextual_source_v4"
    )
    if canonical(structure) != canonical(rebuilt):
        raise ValueError("Original native request structure differs")
    annotation = validate_capture(question, capture)
    if canonical(annotation) != canonical(json.loads(record["graph_json"])):
        raise ValueError("Original native request graph differs")
    frames, _ = closed_original_frames(
        question, capture, structure["historical_partial"]
    )
    if use["node_id"] not in frames:
        raise ValueError("One closed native request frame required")
    requirements, uses, *_ = derive_requirements(
        structure, {"source_inventory": {"declarations": []}}
    )
    expected_req = [r for r in requirements if r.id == requirement["id"]]
    expected_use = [u for u in uses if u.requirement_id == requirement["id"]]
    if (
        len(expected_req) != 1
        or len(expected_use) != 1
        or canonical(asdict(expected_req[0])) != canonical(requirement)
        or canonical(asdict(expected_use[0])) != canonical(use)
    ):
        raise ValueError("Complete inherited native requirement/use differs")
    return asdict(frames[use["node_id"]][1])


class NativeGivenContextUnresolved(ValueError):
    """A retained premise is outside the bounded given-context interpretation."""


def _plan_record(request_plan):
    if isinstance(request_plan, dict):
        return request_plan
    if request_plan is None:
        raise ValueError("Original captured request plan required")
    return request_plan.record()


def native_given_context(record, requirement, use, policy):
    """Interpret one replayed negative-possession premise as GIVEN, never true."""
    from app.services.dependency_frames import (
        HEADS,
        WHOLE,
        Graph,
        _request_assumption_contexts,
    )
    from app.services.planning_declarations import canonical
    from app.services.request_parser import validate_capture

    if (
        policy.procedure_scope_profile not in {"activity_quote_v1", "activity_quote_v2"}
        or policy.source_governance_profile != "requirement_bound_v1"
        or not any(c["operator"] == "request_assumption" for c in use["condition_ast"])
    ):
        return None
    if json.loads(record["evidence_profile_json"]) != policy.record():
        raise ValueError("Original given-context policy differs")
    frame = replay_native_request_use(record, requirement, use)
    if (
        requirement["kind"] not in {"owner", "deputy", "procedure"}
        or requirement["depends_on"]
        or frame["dependencies"]
        or frame["order"]
        or len(frame["condition_ast"]) != 1
        or len(use["conditions"]) != 1
        or len(use["scopes"]) != 1
        or use["units"]
    ):
        raise NativeGivenContextUnresolved("Unbound native given-context requirements")
    structure = json.loads(record["structure_json"])
    question = record["question"]
    graph = Graph(question, validate_capture(question, structure["original_capture"]))
    clause = frame["condition_ast"][0]
    # JSON detaches NamedTuple ranges without changing their coordinates.
    clause = json.loads(canonical(clause))
    contexts, _ = _request_assumption_contexts(graph)
    matches = [
        c for c, _ in contexts.values() if canonical(asdict(c)) == canonical(clause)
    ]
    if len(matches) != 1 or clause["modality"] or len(clause["complements"]) != 1:
        raise NativeGivenContextUnresolved(
            "Native premise has no unique closed ownership"
        )
    ids = set(clause["token_indices"])
    predicates = ids & graph.predicates
    objects = [
        i
        for p in predicates
        for i in graph.children[p]
        if graph.ts[i]["dep"] in {"dobj", "obj"}
    ]
    object_ids = graph.nominal(objects[0]) if len(objects) == 1 else set()
    negatives = [
        {"start": a, "end": b, "text": text} for a, b, text in clause["negation"]
    ]
    scope = requirement["topic"]
    ordinary = re.match(r"(?:ordinary|normal|standard)\s+", scope, re.I)
    if (
        ordinary is None
        or not re.fullmatch(r".+\s+sessions?", scope[ordinary.end() :], re.I)
        or len(clause["subjects"]) != 1
        or canonical_role_scope(clause["subjects"][0][2]) != canonical_role_scope(scope)
        or len(predicates) != 1
        or len(objects) != 1
        or len(negatives) != 1
        or negatives[0]["text"].casefold() != "no"
        or any(graph.ts[i]["tag"] == "MD" for i in use["consumed_token_indices"])
        or graph.reference(ids)
        or graph.literal_units(ids)
        or any(
            HEADS.get(graph.lemma(i)) in {"owner", "deputy"}
            or graph.ts[i]["pos"] == "NUM"
            or graph.lemma(i) in WHOLE
            for i in object_ids
        )
        or canonical(use["modality"]) != canonical(negatives)
        or canonical(use["negation"]) != canonical(negatives)
    ):
        raise NativeGivenContextUnresolved("Unknown native context remains pending")
    # Only an owned role-head possessive may point back to the unique premise.
    for reference in use["references"]:
        matching = [
            t
            for t in graph.ts
            if (t["start"], t["end"], t["text"])
            == (reference["start"], reference["end"], reference["text"])
        ]
        if (
            len(matching) != 1
            or matching[0]["text"].casefold() != "its"
            or requirement["kind"] not in {"owner", "deputy"}
            or HEADS.get(graph.lemma(matching[0]["head"])) != requirement["kind"]
        ):
            raise NativeGivenContextUnresolved("Unbound given-context reference")
    premise = dict(zip(("start", "end", "text"), clause["evidence"], strict=True))
    return {
        "status": "UNVERIFIED_GIVEN_CONTEXT",
        "premise": premise,
        "condition_ast": [clause],
        "subject": clause["subjects"][0],
        "negative_possession": clause["complements"][0],
        "assignment_absence": "NOT_ESTABLISHED",
        "session_applicability": "NOT_CERTIFIED",
        "disclosure": (
            f"Given context (unverified): «{premise['text']}». "
            "This is the requested premise, not a verified absence fact or "
            "a certification that the documented activity applies to this session."
        ),
    }


def session_role_scope(requirement: Requirement) -> str | None:
    """A session role cannot be established by an activity-only predicate."""
    if requirement.kind not in {"owner", "deputy"}:
        return None
    return (
        requirement.topic
        if re.search(r"\bsessions?\b", requirement.topic, re.I)
        else None
    )


def canonical_role_scope(text: str) -> str:
    """Only the approved ordinary frame and terminal session number normalize."""
    from app.services.requirement_binding import role_argument_identity

    text = role_argument_identity(" ".join(text.split()))
    text = re.sub(r"^(?:ordinary|normal|standard)\s+", "", text)
    return re.sub(r"\bsessions$", "session", text)


def literal_role_candidate_matches(
    requirement: Requirement, context: str, start: int, end: int, target: str
) -> bool:
    from app.services.requirement_binding import role_discovery_candidates

    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(context)
    ):
        return False
    return any(
        item["value_range"]["start"] <= start < end <= item["value_range"]["end"]
        and canonical_role_scope(item["target"]) == canonical_role_scope(target)
        for item in role_discovery_candidates(
            requirement, context, include_ownership=True
        )
    )


def _approved_role_use(
    question, original, use, interpretation, *, request_plan=None, policy=None
):
    if policy is not None and interpretation.given_context_json:
        given = native_given_context(
            _plan_record(request_plan),
            asdict(original),
            json.loads(json.dumps(asdict(use))),
            policy,
        )
        return given == json.loads(interpretation.given_context_json)

    def literal(value):
        return (
            type(value.start) is int
            and type(value.end) is int
            and 0 <= value.start < value.end <= len(question)
            and question[value.start : value.end] == value.text
        )

    if (use.original.start, use.original.end, use.original.text) != (
        original.input_start,
        original.input_end,
        original.original_text,
    ) or not literal(use.original):
        return False
    if (
        len(use.scopes) != 1
        or not literal(use.scopes[0])
        or canonical_role_scope(use.scopes[0].text)
        != canonical_role_scope(interpretation.requested_scope)
    ):
        return False
    if any(
        getattr(use, name, ())
        for name in (
            "units",
            "governors",
            "references",
            "order_after",
            "order_evidence",
            "execution_dependencies",
            "quantifiers",
        )
    ):
        return False
    if not use.conditions:
        return not (use.condition_ast or use.modality or getattr(use, "negation", ()))
    if len(use.conditions) != 1 or len(use.condition_ast) != 1:
        return False
    condition = use.conditions[0]
    if (
        not literal(condition)
        or " ".join(condition.text.casefold().split()) != "with no separate assignment"
    ):
        return False
    markers = (*use.modality, *getattr(use, "negation", ()))
    if any(
        not literal(m)
        or m.text.casefold() != "no"
        or not condition.start <= m.start < m.end <= condition.end
        for m in markers
    ):
        return False
    clause = use.condition_ast[0]
    return (
        clause.operator == "with"
        and literal(clause.evidence)
        and tuple(clause.evidence) == (condition.start, condition.end, condition.text)
        and literal(clause.predicate)
        and clause.predicate.text.casefold() == "assignment"
        and not clause.modality
        and not clause.complements
        and len(clause.negation)
        == len(use.modality)
        == len(getattr(use, "negation", ()))
        == 1
        and len(clause.subjects) == 1
        and tuple(clause.subjects[0])
        == (use.scopes[0].start, use.scopes[0].end, use.scopes[0].text)
        and all(
            literal(m)
            and m.text.casefold() == "no"
            and condition.start <= m.start < m.end <= condition.end
            for m in clause.negation
        )
    )


def _original_activity_interpretation(current, policy, request_plan):
    record = request_plan.record()
    if (
        record.get("contract") != policy.record()["request_plan_contract"]
        or json.loads(record.get("evidence_profile_json", "{}")) != policy.record()
    ):
        raise ValueError("Original role plan profile differs")
    originals = [r for r in request_plan.requirements if r.id == current.id]
    uses = [u for u in request_plan.uses if u.requirement_id == current.id]
    if len(originals) != 1 or len(uses) != 1:
        raise ValueError("One original role requirement/use required")
    original = originals[0]
    interpretation = plan_activity_role(original, policy, request_plan=request_plan)
    if interpretation is None:
        if current != original:
            raise ValueError("Original role is not an approved interpretation")
        return None
    if current == interpretation.prepared("session"):
        return None
    if (
        current != interpretation.prepared("activity")
        or record.get("question") != request_plan.question
        or json.loads(json.dumps(asdict(original), allow_nan=False))
        not in record.get("requirements", [])
    ):
        raise ValueError("Effective role preparation differs")
    if not _approved_role_use(
        request_plan.question,
        original,
        uses[0],
        interpretation,
        request_plan=request_plan,
        policy=policy,
    ):
        raise ValueError("Original role use differs")
    return interpretation


def activity_role_candidate_scope(
    current, context, start, end, metadata, *, policy=None, request_plan=None
):
    """Rebuild the approved ordinary/activity bridge; never factual NI support."""
    from app.evidence_policy import recorded_evidence_policy
    from app.services.requirement_binding import (
        activity_role_claim,
        condition_relation,
        role_discovery_candidates,
    )

    if (
        policy is None
        or recorded_evidence_policy(policy.record()).source_governance_profile
        != "requirement_bound_v1"
        or request_plan is None
        or current.kind not in {"owner", "deputy"}
    ):
        return None
    try:
        interpretation = _original_activity_interpretation(
            current, policy, request_plan
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return "unknown", False
    if interpretation is None:
        return None
    claim = activity_role_claim(current, context, start, end)
    if claim is None:
        return None
    if claim.rejection or re.search(
        r"\b(?:according|pursuant)\s+to\b", claim.premise, re.I
    ):
        return "unknown", False
    fields = [
        r
        for r in role_discovery_candidates(current, context, activity_fields=True)
        if r.get("declared_role_scope") == "activity"
        and r.get("frame_complete")
        and r["value_range"] == {"start": claim.start, "end": claim.end}
    ]
    if len(fields) != 1 or canonical_role_scope(fields[0]["target"]) not in {
        canonical_role_scope(interpretation.requested_scope),
        canonical_role_scope(interpretation.activity_scope),
        canonical_role_scope(interpretation.requested_scope) + " session",
        canonical_role_scope(interpretation.activity_scope) + " session",
    }:
        return "unknown", False
    if metadata.get("conflict_group") is not None:
        return "unknown", False
    if metadata.get("condition") is not None:
        relation = condition_relation(
            interpretation.prepared("session"), context, metadata
        )
        return relation, relation == "applies"
    return "applies", True


@dataclass(frozen=True)
class ActivityRoleInterpretation:
    requirement: Requirement
    requested_scope: str
    session_scope: str
    activity_scope: str
    prepared_relation: str | None = None
    session_only: ClassVar[bool] = False

    @property
    def given_context_json(self) -> str:
        return ""

    def prepared(self, scope: Literal["session", "activity"]) -> Requirement:
        target = self.requested_scope if scope == "session" else self.activity_scope
        question = (
            f"Who leads {target}?"
            if self.requirement.kind == "owner"
            else f"Who is the deputy for {target}?"
        )
        return replace(
            self.requirement,
            topic=target,
            question=question,
            relation=self.prepared_relation or self.requirement.relation,
        )

    def record(self, scope: Literal["session", "activity"]) -> dict[str, object]:
        result = {
            "contract": ROLE_POLICY_CONTRACT,
            "requirement_id": self.requirement.id,
            "requested_scope": self.requested_scope,
            "session_scope": self.session_scope,
            "activity_scope": self.activity_scope,
            "effective_scope": scope,
            "activity_fallback": scope == "activity",
            "disclosure": self.disclosure() if scope == "activity" else None,
            "basis": "activity_role"
            if scope == "activity"
            else "documented_session_assignment",
            "kind": self.requirement.kind,
            "original_text": self.requirement.original_text,
            "input_range": {
                "start": self.requirement.input_start,
                "end": self.requirement.input_end,
            },
            "prepared_question": self.prepared(scope).question,
            "effective_target": self.prepared(scope).topic,
            "source_workspace": self.requirement.source_workspace,
        }
        if self.given_context_json:
            result["given_context"] = json.loads(self.given_context_json)
            if scope == "session":
                result["disclosure"] = json.loads(self.given_context_json)["disclosure"]
        return result

    def disclosure(self) -> str:
        role = "lead" if self.requirement.kind == "owner" else "deputy"
        result = (
            f"Activity scope: the documented {role} for {self.activity_scope} is used "
            "for this ordinary-session question. The source documents an activity "
            "role, rather than a separate session assignment."
        )
        if self.given_context_json:
            result += " " + json.loads(self.given_context_json)["disclosure"]
        return result


@dataclass(frozen=True)
class SessionOnlyActivityRoleInterpretation(ActivityRoleInterpretation):
    session_only: ClassVar[bool] = True


@dataclass(frozen=True)
class GivenActivityRoleInterpretation(ActivityRoleInterpretation):
    native_context_json: str = ""

    @property
    def given_context_json(self) -> str:
        return self.native_context_json


def _role_given_context(requirement, policy, request_plan):
    if policy.procedure_scope_profile not in {"activity_quote_v1", "activity_quote_v2"}:
        return True, None
    if request_plan is None:
        return False, None
    record = _plan_record(request_plan)
    uses = [u for u in record["uses"] if u["requirement_id"] == requirement.id]
    if len(uses) != 1:
        raise ValueError("One original native role use required")
    try:
        return True, native_given_context(record, asdict(requirement), uses[0], policy)
    except NativeGivenContextUnresolved:
        return False, None


def _role_activity_scope(
    requirement: Requirement,
) -> tuple[str, str, bool] | None:
    topic = requirement.topic.strip()
    ordinary = re.match(r"(?:ordinary|normal|standard)\s+", topic, re.I)
    session = topic[ordinary.end() :] if ordinary else topic
    match = re.fullmatch(r"(?P<activity>.+?)\s+sessions?", session, re.I)
    if match is not None:
        return session, match.group("activity").strip(), False
    # The topic carries no session token; the session premise then lives in
    # the original request text. An ordinary premise still permits the
    # activity fallback; a documented non-ordinary premise (demonstration,
    # specific or special assignment) requires session evidence only.
    if re.search(
        r"\b(?:ordinary|normal|standard)[-\s]+sessions?\b",
        requirement.original_text,
        re.I,
    ):
        return session, session, False
    if re.search(
        r"\b(?:demonstration|specific|special)[-\s]+(?:sessions?|assignments?)\b"
        r"|\b(?:sessions?|assignments?)\s+overrides?\b",
        requirement.original_text,
        re.I,
    ):
        return session, session, True
    # The ordinary premise can live in the topic itself ("ordinary X"): the
    # declared ordinary-session scope is the same activity scope.
    if ordinary:
        return session, session, False
    return None


def plan_activity_role(
    requirement: Requirement, policy: EvidencePolicy, *, request_plan=None
) -> ActivityRoleInterpretation | None:
    """Recognize the approved frame without dropping other scope conditions."""
    if not policy.activity_roles or requirement.depends_on:
        return None
    relation = requirement.relation
    if policy.dependency_reading:
        relation = {
            ("owner", "lead"): "leads",
            ("deputy", "deputizes"): "deputy",
            ("owner", "role"): "leads",
            ("deputy", "role"): "deputy",
            ("owner", "roles"): "leads",
            ("deputy", "roles"): "deputy",
            ("owner", "is"): "leads",
            ("deputy", "is"): "deputy",
            ("owner", "staffing"): "leads",
            ("deputy", "staffing"): "deputy",
        }.get((requirement.kind, relation), relation)
    if (requirement.kind, relation) not in {
        ("owner", "leads"),
        ("deputy", "deputy"),
    }:
        return None
    resolved = _role_activity_scope(requirement)
    if resolved is None:
        return None
    session, activity, session_only = resolved
    topic = requirement.topic.strip()
    # Explicitly qualified or materially conditional ordinary sessions need
    # their own source assignment. Unknown descriptive text is retained in the
    # activity target, where the unchanged binder must establish it exactly.
    # Documented-session interpretations are exempt: their qualifiers are the
    # premise itself, resolved by the session read set rather than fallback.
    if not session_only and re.search(
        r"\b(?:if|unless|except|only|after|before|during|under|without|"
        r"specific|particular|special|emergency|temporary|not)\b",
        session + " " + requirement.original_text,
        re.I,
    ):
        return None
    if not activity or not requirement.anchors:
        return None
    eligible, given = _role_given_context(requirement, policy, request_plan)
    if not eligible:
        return None
    if session_only or given is None:
        cls = (
            SessionOnlyActivityRoleInterpretation
            if session_only
            else ActivityRoleInterpretation
        )
        return cls(
            requirement,
            topic,
            session,
            activity,
            relation if relation != requirement.relation else None,
        )
    return GivenActivityRoleInterpretation(
        requirement,
        topic,
        session,
        activity,
        relation if relation != requirement.relation else None,
        native_context_json=json.dumps(given, sort_keys=True),
    )
