"""Retain complete curated groups; unresolved comparison blocks publication."""

from app.services import curated_conflict_proof as curated
from app.services.planning_declarations import canonical
from app.services.staged_typed_conflicts import source_chunks as source_chunks

CONTRACT = "captured-typed-curated-comparison-v1"


def records(plan, requirements, evidence, snapshots):
    if plan.record().get("contract") != "staged-request-plan-v2":
        raise ValueError("Actual captured request plan required")
    groups = {}
    for chunk in sorted(source_chunks(snapshots), key=lambda row: str(row.id)):
        metadata = snapshots[str(chunk.document_id)]["metadata"]
        name = metadata.get("conflict_group")
        if name is None:
            continue
        if type(name) is not str or not name:
            raise ValueError("Actual curated group must be a nonempty string")
        groups.setdefault(name, []).append(curated.inspection_identity(chunk, metadata))
    # No inferred semantic irrelevance or source exclusion. A pending group
    # remains a refusal until its requirement-specific comparison is discharged.
    return [
        {
            "group": name,
            "requirement_id": requirement.id,
            "inspection_method": CONTRACT,
            "inspection_sources": members,
            "inspection_complete": False,
            "relevant": True,
            "reason": "captured_curated_comparison_unresolved",
            "truncated": False,
        }
        for name, members in groups.items()
        for requirement in requirements
    ]


def reconstruct(selection, requirements, evidence, snapshots, chunks, plan):
    memberships = curated.reconstruct_membership(selection, snapshots, chunks)
    expected = records(plan, requirements, evidence, snapshots)
    identifiers = {requirement.id for requirement in requirements}
    actual = [
        row for row in selection["conflicts"] if row["requirement_id"] in identifiers
    ]
    if canonical(actual) != canonical(expected):
        raise ValueError("Complete captured curated comparison ledger differs")
    if memberships or expected:
        raise ValueError("Captured curated comparison remains unresolved")
    return []
