"""Conditional source COPY preparation/replay, with no actual model evidence."""

import hashlib
import json
import uuid
from copy import deepcopy
from dataclasses import asdict

import pytest
from app.evidence_policy import recorded_evidence_policy
from app.services import contextual_source_proof as body_proof
from app.services import staged_source_proof as consumer
from app.services.contextual_source_proof import SourceGuardError
from app.services.planning_declarations import canonical
from app.services.request_parser import make_capture
from app.services.role_scope_inspection import (
    RoleScopeManifest,
    RoleScopeSource,
    inspect_role_contexts,
)
from app.services.role_scope_policy import plan_activity_role

from tests.staged_plan_unit837.fixtures_source import capture
from tests.test_captured_request_repair953 import observed
from tests.test_declared_copy_consumer958 import prepared


def conditional(request=None):
    return prepared(
        request_override=observed("reranked-002") if request is None else request
    )


def envelope_for(values):
    snapshot, windows, requirement, _plan, kwargs = values
    return consumer.build_envelope(
        snapshot.body, asdict(snapshot.identity), requirement.topic, windows, **kwargs
    )


def test_actual002_prepares_source_specific_conditional_NI_without_absence_fact():
    # Break: a fully represented original frame is permanently rejected before NI.
    values = conditional()
    snapshot, _windows, requirement, plan, _kwargs = values
    assert plan.resolved_request and not plan.publication_ready
    result = envelope_for(values)
    bound = result["request_applicability"]
    assert canonical(bound["original_requirement"]) == canonical(asdict(requirement))
    assert canonical(bound["original_use"]) == canonical(
        asdict(next(u for u in plan.uses if u.requirement_id == requirement.id))
    )
    assert bound["activity_scope"] == "Citrine fragment desk"
    assert bound["assignment_absence"] == "NOT_ESTABLISHED"
    assert bound["source_identity"] == asdict(snapshot.identity)
    assert bound["condition_semantics"] == "requested_hypothetical_context"
    assert result["source_body"] == snapshot.body
    assert result["envelope_range"] == {"start": 0, "end": len(snapshot.body)}
    gates = {row["name"]: row for row in result["nli_obligations"]}
    assert set(gates) == {"namespace", "applicability"}
    assert "procedure" in gates["namespace"]["hypothesis"]
    assert (
        "ordinary Citrine fragment desk session" in gates["applicability"]["hypothesis"]
    )
    assert "with no separate assignment" in gates["applicability"]["hypothesis"]
    assert requirement.attribute == "the complete governed procedure"
    assert result["requirement"]["attribute"] == requirement.attribute
    assert canonical(result["request_use"]) == canonical(bound["original_use"])
    coverage = result["request_obligation_inventory"][0]
    assert coverage["original_requirement"]["attribute"] == requirement.attribute
    assert canonical(coverage["original_use"]) == canonical(bound["original_use"])
    assert gates["applicability"]["hypothesis"].endswith("is the governed procedure.")
    assert "complete" not in gates["applicability"]["hypothesis"]
    assert gates["namespace"]["hypothesis"] != gates["applicability"]["hypothesis"]
    assert (
        result["pending_external_checks"]["ordinary_session_assignments"]
        == "required_separately"
    )
    assert "supported" not in result


def rewritten(word, replacement, lemma):
    original = observed("reranked-002")
    tokens = original["capture"]["annotation"]["tokens"]
    specs = [
        (
            replacement if t["text"] == word else t["text"],
            t["pos"],
            lemma if t["text"] == word else t["lemma"],
            t["dep"],
            t["head"],
        )
        for t in tokens
    ]
    raw, compiled = capture([specs])
    annotation = compiled["annotation"]
    for old, new in zip(tokens, annotation["tokens"], strict=True):
        new["tag"], new["morph"] = old["tag"], old["morph"]
    return {"question": raw, "capture": make_capture(annotation)}


@pytest.mark.parametrize(
    "mutation",
    [
        ("assignment", "authorization", "authorization"),
        ("ordinary", "emergency", "emergency"),
        ("governed", "certified", "certify"),
    ],
)
def test_unimplemented_condition_mode_or_modifier_still_refuses(mutation):
    with pytest.raises((SourceGuardError, ValueError)):
        envelope_for(conditional(rewritten(*mutation)))


def test_explicit_session_assignment_still_prevents_activity_absence_inference():
    values = conditional()
    _snapshot, _windows, _requirement, plan, _kwargs = values
    owner = next(r for r in plan.requirements if r.kind == "owner")
    policy = recorded_evidence_policy(json.loads(plan.evidence_profile_json))
    interpretation = plan_activity_role(owner, policy)
    assert interpretation is not None
    bodies = [
        "The record steward leads Citrine fragment desk.",
        "The session marshal leads Citrine fragment desk sessions.",
    ]
    sources = tuple(
        RoleScopeSource(
            body,
            json.dumps(
                {
                    "document_id": str(uuid.UUID(int=i + 1)),
                    "workspace_id": "ops-a",
                    "document_version": 1,
                    "content_hash": hashlib.sha256(body.encode()).hexdigest(),
                }
            ),
            "{}",
        )
        for i, body in enumerate(bodies)
    )
    finding = inspect_role_contexts(
        RoleScopeManifest(sources, {"complete": True, "reason": None}), interpretation
    )
    assert finding["complete"]
    assert finding["session_documents"] == [str(uuid.UUID(int=2))]
    result = envelope_for(values)
    assert result["request_applicability"]["assignment_absence"] == "NOT_ESTABLISHED"
    assert (
        result["pending_external_checks"]["ordinary_session_assignments"]
        == "required_separately"
    )


def test_conditional_source_guard_replays_same_original_request_and_NI_pairs():
    from tests.test_contextual_source_proof import settings

    values = conditional()
    snapshot, windows, requirement, plan, kwargs = values
    envelope = envelope_for(values)
    selection = {
        "contract": "requirement-evidence-v5",
        "evidence_profile": json.loads(plan.evidence_profile_json),
        "evidence_support": settings(),
        "source_guard_records": [
            {
                "requirement_id": requirement.id,
                "source_identity": asdict(snapshot.identity),
                "requested_subject": requirement.topic,
                "source_windows": windows,
                "envelope_inventory": envelope,
                "nli_assessments": [
                    {
                        **obligation,
                        "assessment": {
                            "label": "entailment",
                            "logits": [-1.0, 5.0, 0.0],
                            "entailment_margin": 5.0,
                            "supported": True,
                            "pair_tokens": 80,
                        },
                    }
                    for obligation in envelope["nli_obligations"]
                ],
            }
        ],
    }
    # Explicit UNITONLY numeric replay; no actual NI, factual or absence evidence.
    guard_kwargs = {
        key: value for key, value in kwargs.items() if key != "requirement_id"
    }
    actual = kwargs["authoritative_snapshots"][snapshot.identity.document_id]
    guard = consumer.reconstruct_source_guard(
        selection, requirement, actual, **guard_kwargs
    )
    assert guard["request_applicability"] == envelope["request_applicability"]
    changed = deepcopy(selection)
    changed["source_guard_records"][0]["nli_assessments"][1]["hypothesis"] = (
        "This procedure applies without the original condition."
    )
    with pytest.raises(SourceGuardError):
        consumer.reconstruct_source_guard(changed, requirement, actual, **guard_kwargs)


def test_other_workspace_role_plan_cannot_supply_ordinary_exception_inspection():
    _snapshot, _windows, requirement, plan, _kwargs = conditional()
    record = plan.record()
    for peer in record["requirements"]:
        if peer["kind"] in {"owner", "deputy"}:
            peer["source_workspace"] = "UNITONLY962-other-workspace"
    actual = next(row for row in record["requirements"] if row["id"] == requirement.id)
    use = next(row for row in record["uses"] if row["requirement_id"] == requirement.id)
    # Compiler seam: different explicit workspaces cannot close this scope.
    with pytest.raises(SourceGuardError, match="ordinary-session inspection"):
        body_proof._request_source_applicability(
            record, actual, use, "contextual_source_v4"
        )
