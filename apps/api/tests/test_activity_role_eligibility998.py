"""Actual990 captured fields/QA; eligibility only, never NI/plan acceptance."""

import json
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path

import pytest
from app.evidence_policy import recorded_evidence_policy
from app.models.chunk import ChunkWithScore
from app.services.answer_requirements import Requirement
from app.services.captured_plan_binding import CapturedRequestPlan
from app.services.captured_plan_requirements import CapturedRequirementUse
from app.services.dependency_frames import ConditionClause, Span
from app.services.linguistic_requirements import LiteralRange
from app.services.requirement_answers import _bind_candidate
from app.services.role_scope_policy import (
    activity_role_candidate_scope,
    plan_activity_role,
)


@lru_cache
def actual():
    return json.loads(
        (Path(__file__).parent / "fixtures/activity_role_actual998.json").read_text(
            encoding="utf-8"
        )
    )


def transport_plan():
    """Typed projection of actual native fields; no fake resolved/supported flags."""
    raw = actual()["plan"]
    requirements = tuple(
        Requirement(
            **{
                **r,
                "anchors": tuple(r["anchors"]),
                "depends_on": tuple(r["depends_on"]),
            }
        )
        for r in raw["requirements"]
    )
    uses = []
    for source in raw["uses"]:
        value = dict(source)
        value["original"] = LiteralRange(**value["original"])
        for key in (
            "scopes",
            "conditions",
            "modality",
            "units",
            "governors",
            "references",
            "order_evidence",
            "quantifiers",
            "negation",
        ):
            value[key] = tuple(LiteralRange(**r) for r in value[key])
        for key in (
            "order_after",
            "head_token_indices",
            "consumed_token_indices",
            "execution_dependencies",
        ):
            value[key] = tuple(value[key])
        value["condition_ast"] = tuple(
            ConditionClause(
                **{
                    **c,
                    "evidence": Span(*c["evidence"]),
                    "predicate": Span(*c["predicate"]),
                    **{
                        k: tuple(Span(*r) for r in c[k])
                        for k in ("subjects", "negation", "modality", "complements")
                    },
                    "token_indices": tuple(c["token_indices"]),
                }
            )
            for c in value["condition_ast"]
        )
        uses.append(CapturedRequirementUse(**value))
    return CapturedRequestPlan(
        structure_json="{}",
        source_productions_json="{}",
        question=raw["question"],
        evidence_profile_json=raw["evidence_profile_json"],
        requirements=requirements,
        uses=tuple(uses),
    )


def arguments(index):
    row = actual()["candidates"][index]
    plan = transport_plan()
    policy = recorded_evidence_policy(json.loads(plan.evidence_profile_json))
    original = next(r for r in plan.requirements if r.id == row["requirement_id"])
    role = plan_activity_role(original, policy, request_plan=plan)
    assert role is not None
    snapshot = actual()["snapshot"]
    chunk = ChunkWithScore(
        id=row["chunk_id"],
        document_id=row["document_id"],
        content=snapshot["body"],
        chunk_index=0,
        relevance_score=0.0,
        metadata={
            **json.loads(snapshot["metadata_json"]),
            "document_version": row["document_version"],
            "content_hash": row["content_hash"],
            "workspace_id": snapshot["identity"]["workspace_id"],
        },
    )
    return row, plan, policy, role.prepared("activity"), chunk


@pytest.mark.parametrize(
    "index",
    [
        i
        for i, r in enumerate(actual()["candidates"])
        if r["decision"] == "source_condition_not_established"
    ],
)
def test_actual_six_fields_reach_pending_ni_without_losing_original_scope(index):
    row, plan, policy, effective, chunk = arguments(index)
    diagnostics = []
    bound = _bind_candidate(
        effective,
        chunk,
        row["raw_span"],
        row["null_margin"],
        diagnostics,
        role_target=effective.topic,
        reading_profile=policy.evidence_reading_profile,
        policy=policy,
        request_plan=plan,
    )
    assert bound is not None, diagnostics[-1]["decision"]
    assert diagnostics[-1]["decision"] == "support_pending"
    assert diagnostics[-1]["condition"] == "applies"
    assert diagnostics[-1]["validated_answer_span"] == row["validated_answer_span"]
    assert diagnostics[-1]["hypothesis"] == row["hypothesis"]
    assert "support" not in diagnostics[-1]


def test_period_and_nonperiod_share_complete_literal_ni_input():
    claims = []
    for index in (0, 2):
        row, plan, policy, effective, chunk = arguments(index)
        before = asdict(plan)
        diagnostics = []
        bound = _bind_candidate(
            effective,
            chunk,
            row["raw_span"],
            row["null_margin"],
            diagnostics,
            role_target=effective.topic,
            policy=policy,
            request_plan=plan,
            reading_profile=policy.evidence_reading_profile,
        )
        assert bound is not None
        claim = bound[1]
        assert claim.premise == chunk.content
        assert claim.premise_end == claim.support_end == 131
        assert asdict(plan) == before
        claims.append(claim)
    assert claims[0] == claims[1]


@pytest.mark.parametrize(
    "variant",
    [
        "effective",
        "use_reference",
        "use_condition_ast",
        "source_condition",
        "curated",
        "foreign",
        "prohibition",
        "reference",
        "assigned",
    ],
)
def test_unknown_or_unapproved_scope_never_becomes_ni_eligible(variant):
    row, plan, policy, effective, chunk = arguments(0)
    metadata = dict(chunk.metadata)
    content = chunk.content
    if variant == "effective":
        effective = replace(effective, topic="UNITONLY-other-activity")
    elif variant in {"use_reference", "use_condition_ast"}:
        uses = list(plan.uses)
        i = next(i for i, u in enumerate(uses) if u.requirement_id == effective.id)
        if variant == "use_reference":
            uses[i] = replace(uses[i], references=(uses[i].conditions[0],))
        else:
            uses[i] = replace(
                uses[i],
                condition_ast=(replace(uses[i].condition_ast[0], operator="unless"),),
            )
        plan = replace(plan, uses=tuple(uses))
    elif variant == "source_condition":
        metadata["condition"] = "unknown approval condition"
    elif variant == "curated":
        metadata["conflict_group"] = "uninspected"
    elif variant == "foreign":
        content = content.replace("Citrine", "UNITONLYForeign")
    elif variant == "prohibition":
        content = content.replace("deputy is", "deputy is not")
    elif variant == "reference":
        content = content[:-1] + " according to the roster."
    elif variant == "assigned":
        content = content.replace("activity deputy", "assigned deputy")
    value = row["validated_answer_span"]["text"]
    first = content.index(value)
    result = activity_role_candidate_scope(
        effective,
        content,
        first,
        first + len(value),
        metadata,
        policy=policy,
        request_plan=plan,
    )
    assert result is not None and result != ("applies", True)


def test_broader_actual_owner_qa_span_remains_rejected():
    i = next(
        i
        for i, r in enumerate(actual()["candidates"])
        if r["decision"] == "activity_role_field_unbound"
    )
    row, plan, policy, effective, chunk = arguments(i)
    diagnostics = []
    assert (
        _bind_candidate(
            effective,
            chunk,
            row["raw_span"],
            row["null_margin"],
            diagnostics,
            role_target=effective.topic,
            policy=policy,
            request_plan=plan,
            reading_profile=policy.evidence_reading_profile,
        )
        is None
    )
    assert diagnostics[-1]["decision"] == "activity_role_field_unbound"
