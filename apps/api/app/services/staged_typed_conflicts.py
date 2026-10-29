"""Full curated membership for typed declarations, with unknowns retained.

Metadata selects comparisons only. Each source needs actual typed evidence or
an independently replayed scope/production ownership proof.
"""

import json
import uuid

from app.models.chunk import ChunkWithScore
from app.services import curated_conflict_proof as curated
from app.services import planning_declarations as declarations

CONTRACT = "staged-typed-curated-comparison-v1"


def source_chunks(snapshots, *, evidence_profile=None):
    canonical = evidence_profile is not None
    if canonical:
        from app.evidence_policy import reading_version, recorded_evidence_policy
        from app.services.contextual_output import _source_inventory

        policy = recorded_evidence_policy(evidence_profile)
        if (
            policy.record() != evidence_profile
            or policy.evidence_reading_profile != "contextual_source_v4"
            or policy.source_governance_profile != "requirement_bound_v1"
        ):
            raise ValueError("Canonical captured source projection required")
        _source_inventory(
            snapshots,
            max_documents=reading_version(
                policy.evidence_reading_profile
            ).scope_documents,
        )
    result = []
    for snapshot in snapshots.values():
        for raw in snapshot["chunks"]:
            metadata = {
                **raw["metadata"],
                **snapshot["metadata"],
                **{
                    key: snapshot[key]
                    for key in ("document_version", "content_hash", "workspace_id")
                },
            }
            if canonical:
                metadata.update(
                    document_title=snapshot["title"],
                    condition=snapshot["metadata"].get("condition"),
                    conflict_group=snapshot["metadata"].get("conflict_group"),
                    score_status="not_ranked",
                    ranking_score=None,
                    origin="captured-planning-source-inspection",
                )
            result.append(
                ChunkWithScore(
                    id=uuid.UUID(raw["id"]),
                    document_id=uuid.UUID(snapshot["document_id"]),
                    content=raw["content"],
                    chunk_index=raw["index"],
                    metadata=metadata,
                    relevance_score=0.0,
                )
            )
    return result


def _ownership(plan):
    candidate = json.loads(plan.effective_candidate_json)
    record = candidate.get("candidate_selection_json")
    owned = (
        json.loads(record).get("procedure_obligations_json", "[]") if record else "[]"
    )
    return json.loads(owned)


def _source_check(sid, evidence, bridge, inventory, owned):
    decision = next(
        row for row in bridge["source_decisions"] if row["source"]["document_id"] == sid
    )
    if sid in bridge["excluded"]:
        return {
            "document_id": sid,
            "disposition": "independently_excluded_other_namespace",
            "scope_proof": decision,
        }
    if (
        evidence is not None
        and evidence.supported
        and evidence.prepared.source_declaration.source.document_id == sid
    ):
        return {
            "document_id": sid,
            "disposition": "actual_supported_typed_declaration",
            "declaration_id": evidence.prepared.source_declaration.id,
            "proposal_ids": [row.proposal_id for row in evidence.proposals],
        }
    units = {
        row["id"]
        for row in inventory["units"]
        if row["source"]["document_id"] == sid and row["raw"]["text"].strip()
    }
    proofs = [row for row in owned if row["source"]["document_id"] == sid]
    if units and units <= {row["unit_id"] for row in proofs}:
        return {
            "document_id": sid,
            "disposition": "separately_owned_complete_copy_production",
            "obligations": proofs,
            "factual_authority": "NOT_ASSESSED",
        }
    return {
        "document_id": sid,
        "disposition": "unresolved_curated_source_semantics",
        "scope_proof": decision,
    }


def records(plan, requirements, evidence, snapshots):
    bridge = json.loads(plan.scope_bridge_json)
    inventory = json.loads(json.loads(plan.effective_candidate_json)["inventory_json"])
    owned = _ownership(plan)
    groups = {}
    for chunk in sorted(source_chunks(snapshots), key=lambda row: str(row.id)):
        snapshot = snapshots[str(chunk.document_id)]
        name = snapshot["metadata"].get("conflict_group")
        if name is not None:
            if type(name) is not str or not name:
                raise ValueError("Actual curated group must be a nonempty string")
            groups.setdefault(name, []).append(
                curated.inspection_identity(chunk, snapshot["metadata"])
            )
    result = []
    for name, members in groups.items():
        for req in requirements:
            checks = [
                _source_check(sid, evidence.get(req.id), bridge, inventory, owned)
                for sid in sorted({row["document_id"] for row in members})
            ]
            unresolved = any(
                row["disposition"] == "unresolved_curated_source_semantics"
                for row in checks
            )
            result.append(
                {
                    "group": name,
                    "requirement_id": req.id,
                    "inspection_method": CONTRACT,
                    "inspection_sources": members,
                    "source_checks": checks,
                    "inspection_complete": not unresolved,
                    "relevant": unresolved,
                    "reason": "unresolved_typed_curated_member"
                    if unresolved
                    else "all_actual_typed_curated_members_accounted",
                    "truncated": False,
                }
            )
    return result


def reconstruct(selection, requirements, evidence, snapshots, chunks, plan):
    memberships = curated.reconstruct_membership(selection, snapshots, chunks)
    expected = records(plan, requirements, evidence, snapshots)
    actual = [
        row
        for row in selection["conflicts"]
        if row["requirement_id"] in {req.id for req in requirements}
    ]
    if declarations.canonical(actual) != declarations.canonical(expected):
        raise ValueError("Complete actual typed curated comparison ledger differs")
    if {(row["group"], row["requirement_id"]) for row in actual} != {
        (name, req.id) for name in memberships for req in requirements
    }:
        raise ValueError("Missing typed curated request/member comparison")
    if any(row["relevant"] or not row["inspection_complete"] for row in expected):
        raise ValueError("Typed curated opposition is not independently discharged")
    return expected
