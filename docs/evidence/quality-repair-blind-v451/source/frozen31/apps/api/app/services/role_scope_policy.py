"""Declared ordinary-session interpretation, separate from source fact support.

This proposes two exact scopes for a lead/deputy requirement. It never establishes
that an activity assignment applies: the caller must inspect all authorized
session exceptions, prefer explicit assignments, and assess the source claim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal

from app.evidence_policy import ROLE_POLICY_CONTRACT, EvidencePolicy
from app.services.answer_requirements import Requirement


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


@dataclass(frozen=True)
class ActivityRoleInterpretation:
    requirement: Requirement
    requested_scope: str
    session_scope: str
    activity_scope: str

    def prepared(self, scope: Literal["session", "activity"]) -> Requirement:
        target = self.requested_scope if scope == "session" else self.activity_scope
        question = (
            f"Who leads {target}?"
            if self.requirement.kind == "owner"
            else f"Who is the deputy for {target}?"
        )
        return replace(self.requirement, topic=target, question=question)

    def record(self, scope: Literal["session", "activity"]) -> dict[str, object]:
        return {
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

    def disclosure(self) -> str:
        role = "lead" if self.requirement.kind == "owner" else "deputy"
        return (
            f"Activity scope: the documented {role} for {self.activity_scope} is used "
            "for this ordinary-session question. The source documents an activity "
            "role, rather than a separate session assignment."
        )


def plan_activity_role(
    requirement: Requirement, policy: EvidencePolicy
) -> ActivityRoleInterpretation | None:
    """Recognize the approved frame without dropping other scope conditions."""
    if not policy.activity_roles or requirement.depends_on:
        return None
    if (requirement.kind, requirement.relation) not in {
        ("owner", "leads"),
        ("deputy", "deputy"),
    }:
        return None
    topic = requirement.topic.strip()
    ordinary = re.match(r"(?:ordinary|normal|standard)\s+", topic, re.I)
    session = topic[ordinary.end() :] if ordinary else topic
    match = re.fullmatch(r"(?P<activity>.+?)\s+sessions?", session, re.I)
    if match is None:
        return None
    activity = match.group("activity").strip()
    # Explicitly qualified or materially conditional sessions need their own
    # source assignment. Unknown descriptive text is retained in the activity
    # target, where the unchanged binder must establish it exactly.
    if re.search(
        r"\b(?:if|unless|except|only|after|before|during|under|without|"
        r"specific|particular|special|emergency|temporary|not)\b",
        session + " " + requirement.original_text,
        re.I,
    ):
        return None
    if not activity or not requirement.anchors:
        return None
    return ActivityRoleInterpretation(requirement, topic, session, activity)
