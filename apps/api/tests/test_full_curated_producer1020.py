"""Actual1016 shapes; UNITONLY SQL/NLI boundaries, no actual quality claim."""

import json
import uuid
from copy import deepcopy
from dataclasses import replace
from functools import cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.evidence_policy import recorded_evidence_policy
from app.models.query import QueryRequest
from app.services import procedure_evidence
from app.services import requirement_answers as answers
from app.services import staged_typed_conflicts as projection
from app.services.answer_requirements import Requirement
from app.services.answer_support import SupportAssessment, support_service
from app.services.captured_answer_planning import CapturedAnswerContext
from app.services.curated_conflict_proof import inspection_identity
from app.services.planning_declarations import canonical

from tests.planning_library_unit830.test_support import metadata
from tests.test_curated_quote_scope995 import config
from tests.test_declared_copy_consumer958 import prepared


@cache
def actual():
    return json.loads(
        (Path(__file__).parent / "fixtures/full-curated-producer1020.json").read_text()
    )


def members():
    data = actual()
    return projection.source_chunks(data["snapshots"], evidence_profile=data["profile"])


def test_actual_full_projection_has_all_physical_identity_and_curated_groups():
    data = actual()
    rows = [inspection_identity(c) for c in members()]
    assert len(rows) == 46
    assert {r["conflict_group"] for r in rows if r["conflict_group"]} == {
        "d526-amber-parent",
        "d526-duplicate-tail",
        "d526-half-range",
        "d526-zero-dot",
    }
    assert all(r["content_hash"] and r["workspace_id"] == "ops-a" for r in rows)
    bad = data["case002_readset"]["sources"]
    assert sum(r["content_hash"] is None for r in bad) == 41
    assert sum(r["workspace_id"] is None for r in bad) == 41
    assert {r["chunk_id"] for r in bad} == {r["chunk_id"] for r in rows}


def test_document_none_wins_over_raw_chunk_curation_only_in_opt_in():
    data = actual()
    snapshot = deepcopy(
        next(
            s
            for s in data["snapshots"].values()
            if not s["metadata"].get("conflict_group")
        )
    )
    snapshot["chunks"][0]["metadata"].update(
        condition="raw stale", conflict_group="raw stale"
    )
    one = {snapshot["document_id"]: snapshot}
    assert projection.source_chunks(one)[0].metadata["condition"] == "raw stale"
    fresh = projection.source_chunks(one, evidence_profile=data["profile"])[0]
    assert (
        fresh.metadata["condition"] is None and fresh.metadata["conflict_group"] is None
    )
    assert fresh.metadata["score_status"] == "not_ranked" and fresh.relevance_score == 0


@pytest.fixture(scope="module")
def context():
    _, _, _, plan, kwargs = prepared()
    return CapturedAnswerContext(
        plan,
        canonical(kwargs["planning_inputs"]),
        canonical(kwargs["authoritative_snapshots"]),
    )


def test_seed_preserves_ranked_identity_order_and_score_before_role_additions(context):
    policy = recorded_evidence_policy(json.loads(context.plan.evidence_profile_json))
    full = projection.source_chunks(
        context.snapshots(), evidence_profile=policy.record()
    )
    first = full[-1].model_copy(
        update={
            "relevance_score": 0.83,
            "metadata": {**full[-1].metadata, "score_status": "ranked"},
        }
    )
    inspected = {first.id: first}
    answers._seed_captured_inspection(inspected, context, policy)
    assert len(inspected) == 3 and next(iter(inspected)) == first.id
    assert inspected[first.id] is first and inspected[first.id].relevance_score == 0.83
    raw_role = first.model_copy(update={"metadata": {}, "relevance_score": 0.0})
    inspected.setdefault(first.id, raw_role)
    assert inspected[first.id] is first


@pytest.mark.parametrize(
    "damage", ["missing", "foreign", "body", "version", "chunk", "retrieved"]
)
def test_seed_rejects_missing_foreign_or_tampered_authority(context, damage):
    policy = recorded_evidence_policy(json.loads(context.plan.evidence_profile_json))
    snapshots = context.snapshots()
    first = next(iter(snapshots))
    inspected = {}
    if damage == "missing":
        del snapshots[first]
    elif damage == "foreign":
        snapshots[str(uuid.UUID(int=9001))] = snapshots.pop(first)
    elif damage == "body":
        snapshots[first]["body"] += " altered"
    elif damage == "version":
        snapshots[first]["document_version"] += 1
    elif damage == "chunk":
        snapshots[first]["chunks"][0]["id"] = str(uuid.UUID(int=9001))
    else:
        member = projection.source_chunks(snapshots, evidence_profile=policy.record())[
            0
        ]
        inspected[member.id] = member.model_copy(
            update={"metadata": {**member.metadata, "content_hash": "0" * 64}}
        )
    changed = replace(context, snapshots_json=canonical(snapshots))
    with pytest.raises((ValueError, KeyError)):
        answers._seed_captured_inspection(inspected, changed, policy)


def test_legacy_seed_is_noop_without_new_context(context):
    policy = replace(
        recorded_evidence_policy(json.loads(context.plan.evidence_profile_json)),
        source_governance_profile="all_sources_v1",
    )
    inspected = {}
    answers._seed_captured_inspection(inspected, None, policy)
    assert inspected == {}


async def test_all_four_groups_reach_existing_sql_inspection_and_every_ni_pair(
    monkeypatch,
):
    data = actual()
    all_members = members()
    inspected = {c.id: c for c in all_members}
    by_document = {str(c.document_id): c for c in all_members}
    sources = {}
    for identifier, snapshot in data["snapshots"].items():
        c = by_document[identifier]
        sources[identifier] = SimpleNamespace(
            identity={
                k: snapshot[k]
                for k in (
                    "document_id",
                    "document_version",
                    "content_hash",
                    "workspace_id",
                )
            },
            body=snapshot["body"],
            chunks=(SimpleNamespace(chunk=c),),
        )
    requested = []
    pairs = []

    async def sql_group(_db, group, **kwargs):
        requested.append(group)
        return [
            c for c in all_members if c.metadata.get("conflict_group") == group
        ], False

    async def version(_db, _principal, _request, member, _inspected):
        return sources[str(member.document_id)]

    async def current(_):
        return True

    async def assess(inputs, **kwargs):
        pairs.extend(inputs)
        return [
            SupportAssessment("neutral", (0.0, 0.0, 5.0), -5.0, False, 80)
            for _ in inputs
        ]

    monkeypatch.setattr(answers, "inspect_curated_group", sql_group)
    monkeypatch.setattr(procedure_evidence, "resolve_version", version)
    monkeypatch.setattr(support_service, "metadata", lambda *_: metadata())
    monkeypatch.setattr(support_service, "assess", assess)
    req = Requirement(**data["requirement"])
    root = data["root_inventory"]["source_identity"]["document_id"]
    witness = SimpleNamespace(
        chunk=by_document[root], completeness={"inventory": data["root_inventory"]}
    )
    records, unresolved = await answers._inspect_conflicts(
        None,
        QueryRequest(question=req.original_text),
        None,
        inspected,
        (req,),
        {req.id: req},
        {req.id: [witness]},
        config(),
        current,
        [],
    )
    assert len(requested) == 4 and len(set(requested)) == 4
    assert len(pairs) == 8 and len({p.reference_id for p in pairs}) == 8
    assert len(records) == 4 and unresolved
    assert all(
        r["outcome"] == "comparison_unconfirmed" and r["relevant"] for r in records
    )
    readset = procedure_evidence.capture_read_set(
        list(inspected.values()),
        records,
        QueryRequest(question=req.original_text),
        include_factual_groups=True,
    )
    assert len(readset["sources"]) == 46 and len(readset["groups"]) == 4
    live = []
    for c in all_members:
        s = data["snapshots"][str(c.document_id)]
        doc = SimpleNamespace(
            version_number=s["document_version"],
            content_hash=s["content_hash"],
            workspace_id=s["workspace_id"],
            metadata_=s["metadata"],
        )
        live.append((c, doc))

    class SQLBoundary:
        async def execute(self, statement):
            params = statement.compile().params
            group = next(
                (v for v in params.values() if isinstance(v, str) and v in requested),
                None,
            )
            rows = (
                live
                if group is None
                else [
                    (c, d)
                    for c, d in live
                    if d.metadata_.get("conflict_group") == group
                ]
            )
            return SimpleNamespace(all=lambda: rows)

    check = await procedure_evidence.check_read_set(
        SQLBoundary(), None, QueryRequest(question=req.original_text), readset
    )
    assert (
        check["consistent"]
        and check["changed_source_ids"] == []
        and check["changed_groups"] == []
    )
