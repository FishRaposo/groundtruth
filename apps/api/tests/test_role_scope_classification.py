"""Complete source classification, with invented immutable controller contexts."""

import hashlib
import json
import uuid

import pytest
from app.evidence_policy import EvidencePolicy
from app.services.answer_requirements import plan_requirements
from app.services.role_scope_inspection import (
    RoleScopeManifest,
    RoleScopeSource,
    inspect_role_contexts,
)
from app.services.role_scope_policy import plan_activity_role


def classify(*bodies):
    requirement = plan_requirements("Who leads ordinary Meridian review sessions?")[0]
    plan = plan_activity_role(
        requirement, EvidencePolicy("qa_only_v1", "ordinary_session_activity_v1")
    )
    sources = tuple(
        RoleScopeSource(
            body,
            json.dumps(
                {
                    "document_id": str(uuid.uuid4()),
                    "workspace_id": "ops-a",
                    "document_version": 1,
                    "content_hash": hashlib.sha256(body.encode()).hexdigest(),
                }
            ),
            "{}",
        )
        for body in bodies
    )
    return inspect_role_contexts(
        RoleScopeManifest(sources, {"complete": True, "reason": None}), plan
    )


@pytest.mark.parametrize(
    "restriction",
    [
        "For Meridian review sessions unless separately nominated, "
        "the lead is the duty supervisor.",
        "For Meridian review sessions, the lead is the duty supervisor "
        "if separately appointed.",
        "For Meridian review sessions, the lead is the duty supervisor "
        "subject to qualification.",
    ],
)
def test_unparsed_condition_cannot_be_relabelled_as_irrelevant_assignment(restriction):
    value = classify(
        "The record steward leads Meridian review.",
        restriction,
    )
    assert value["complete"] is False


def test_typed_different_attribute_exception_is_not_a_role_exception():
    value = classify(
        "The record steward leads Meridian review.",
        "For emergency Meridian review sessions, the duration is 12 minutes.",
    )
    assert value["complete"] is True
    assert (
        value["contexts"][1]["units"][0]["disposition"] == "irrelevant_typed_attribute"
    )


def test_unparsed_governing_cross_reference_without_role_keyword_blocks_fallback():
    value = classify(
        "The record steward leads Meridian review. Follow the qualification appendix."
    )
    assert value["complete"] is False


def test_known_distinct_special_session_and_full_typed_method_are_irrelevant():
    value = classify(
        "The record steward leads Meridian review.",
        "For emergency Meridian review sessions, the lead is the duty supervisor.",
        "Meridian review: inspect the card, record the result, and close the review.",
    )
    assert value["complete"] is True
    assert len(value["activity_documents"]) == 1 and value["session_documents"] == []


def test_unknown_nomination_without_repeating_namespace_is_not_absence_evidence():
    assert (
        classify(
            "The record steward leads Meridian review.",
            "Each session requires a separate nomination.",
        )["complete"]
        is False
    )
