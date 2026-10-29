"""Actual990 curated scope inputs; UNITONLY new NI, never quality acceptance."""

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.config import Settings
from app.services import linguistic_conflicts as runtime
from app.services.answer_requirements import Requirement
from app.services.answer_support import SupportAssessment

from tests.planning_library_unit830.test_support import metadata


def actual():
    return json.loads(
        (Path(__file__).parent / "fixtures/actual-curated-quote995.json").read_text(
            encoding="utf-8"
        )
    )


def config():
    return Settings(
        GENERATION_MODE="extractive",
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1",
        ROLE_SCOPE_POLICY="ordinary_session_activity_v1",
        PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1",
        SOURCE_CONTEXT_POLICY="scoped_note_context_v2",
        EVIDENCE_READING_PROFILE="contextual_source_v4",
        QUANTITY_VERIFICATION_PROFILE="literal_source_count_v1",
        REQUEST_PARSER_MODE="local_dependency",
        SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1",
        PROCEDURE_SCOPE_PROFILE="activity_quote_v1",
    )


def source_rows(data):
    sources = {}
    for row in data["snapshots"]:
        identity = {k: v for k, v in row["identity"].items() if k != "snapshot_id"}
        chunks = tuple(
            SimpleNamespace(
                chunk=SimpleNamespace(
                    id=c["chunk_id"],
                    document_id=identity["document_id"],
                    content=c["literal"]["text"],
                    metadata={**identity, **json.loads(row["metadata_json"])},
                )
            )
            for c in row["chunks"]
        )
        sources[identity["document_id"]] = SimpleNamespace(
            identity=identity,
            body=row["body"],
            metadata=json.loads(row["metadata_json"]),
            chunks=chunks,
        )
    return sources


async def test_actual_quote_target_is_used_before_curated_ni(monkeypatch):
    from app.services import procedure_evidence
    from app.services.answer_support import support_service

    data = actual()
    req = Requirement(**data["requirement"])
    sources = source_rows(data)
    record = data["conflict"]
    ids = {i["document_id"] for i in record["inspection_sources"]}
    root = data["selected_root_inventory"]["source_identity"]["document_id"]
    witness = SimpleNamespace(
        chunk=sources[root].chunks[0].chunk, completeness=data["selected_completeness"]
    )
    calls = []

    async def resolved(*args):
        return [sources[i] for i in sorted(ids)], record["inspection_sources"]

    async def version(db, principal, request, member, inspected):
        return sources[str(member.document_id)]

    async def assess(pairs, **kwargs):
        calls.extend(pairs)
        return [
            SupportAssessment("neutral", (0.0, 0.0, 5.0), -5.0, False, 80)
            for _ in pairs
        ]

    monkeypatch.setattr(runtime, "_resolve_sources", resolved)
    monkeypatch.setattr(procedure_evidence, "resolve_version", version)
    monkeypatch.setattr(support_service, "metadata", lambda *_: metadata())
    monkeypatch.setattr(support_service, "assess", assess)
    result = await runtime.inspect_group(
        None, None, None, req, config(), [], False, [witness], {}, []
    )
    assert len(calls) == 2
    assert {p.hypothesis for p in calls} == {
        "The procedure described here applies to "
        "standard Citrine fragment desk routine."
    }
    assert {p.premise for p in calls} == {
        r["premise"] for r in record["source_extent_checks"]
    }
    assert result["inspection_method"] == "curated-selected-declaration-scope-v2"
    assert result["outcome"] == "comparison_unconfirmed" and result["relevant"]


def quote_record(label="contradiction", *, truncated=False):
    from app.evidence_policy import resolve_evidence_policy
    from app.services import curated_conflict_proof as proof

    data = actual()
    req = Requirement(**data["requirement"])
    snapshots = {
        row["identity"]["document_id"]: {**row["identity"], "body": row["body"]}
        for row in data["snapshots"]
    }
    inventory = data["selected_completeness"]["inventory"]
    basis = proof.selected_quote_scope(req, [inventory], snapshots)
    logits = (5.0, 0.0, 0.0) if label == "contradiction" else (0.0, 5.0, 0.0)
    margin = logits[1] - max(logits[0], logits[2])
    decision = asdict(
        SupportAssessment(label, logits, margin, label == "entailment", 80)
    )
    settings = {
        "support": metadata(),
        "evidence_profile": resolve_evidence_policy(config()).record(),
    }
    ids = data["conflict"]["inspection_sources"]
    rows = []
    for identifier in sorted({i["document_id"] for i in ids}):
        snap = snapshots[identifier]
        identity = {k: v for k, v in snap.items() if k not in {"snapshot_id", "body"}}
        rows.append(
            proof.quote_scope_row(
                proof.quote_scope_input(req, identity, snap["body"], basis),
                decision,
                settings,
            )
        )
    root_body = snapshots[basis["source_identity"]["document_id"]]["body"]
    result = proof.quote_procedure_outcome(
        req, rows, ids, truncated, dict(basis, body=root_body)
    )
    result["group"] = data["conflict"]["group"]
    return result, req, snapshots, settings, [inventory]


def test_new_pairs_replay_and_old_real_scores_cannot_be_reused():
    from app.services import curated_conflict_proof as proof

    record, req, snapshots, settings, inventories = quote_record()
    assert record["outcome"] == "not_relevant"
    assert len(record["excluded_documents"]) == 2
    assert (
        proof.reconstruct_quote_group(record, req, snapshots, settings, inventories)
        == record
    )
    old = actual()["conflict"]
    # Old actual observations had different classifier targets. Their outcomes
    # cannot certify these new inputs; numeric replay remains unconfirmed.
    altered = deepcopy(record)
    for row, original in zip(
        altered["source_extent_checks"], old["source_extent_checks"], strict=True
    ):
        row["assessment"] = original["assessment"]
    with pytest.raises(ValueError):
        proof.reconstruct_quote_group(altered, req, snapshots, settings, inventories)


@pytest.mark.parametrize(
    "mutation", ["target", "hypothesis", "identity", "missing", "body", "policy"]
)
def test_new_scope_replay_rejects_tampering(mutation):
    from app.services import curated_conflict_proof as proof

    record, req, snapshots, settings, inventories = quote_record()
    if mutation == "target":
        record["source_extent_checks"][0]["selected_declaration"]["target"]["text"] = (
            req.topic
        )
    elif mutation == "hypothesis":
        record["source_extent_checks"][0]["hypothesis"] = proof.scope_input(
            req, {}, ""
        )["hypothesis"]
    elif mutation == "identity":
        inventories[0]["source_identity"]["document_version"] += 1
    elif mutation == "missing":
        record["source_extent_checks"].pop()
    elif mutation == "body":
        root = inventories[0]["source_identity"]["document_id"]
        snapshots[root]["body"] += " Changed."
    else:
        settings["evidence_profile"]["procedure_scope_profile"] = "requested_scope_v1"
    with pytest.raises(ValueError):
        proof.reconstruct_quote_group(record, req, snapshots, settings, inventories)


def test_applicable_opponents_and_truncation_still_refuse():
    from app.services import curated_conflict_proof as proof

    record, req, snapshots, settings, inventories = quote_record("entailment")
    assert record["outcome"] == "curated_conflict" and record["relevant"]
    assert (
        proof.reconstruct_quote_group(record, req, snapshots, settings, inventories)
        == record
    )
    record, req, snapshots, settings, inventories = quote_record(truncated=True)
    assert (
        record["outcome"] == "comparison_unconfirmed"
        and not record["inspection_complete"]
    )
    assert (
        proof.reconstruct_quote_group(record, req, snapshots, settings, inventories)
        == record
    )


def test_ambiguous_or_missing_selected_declarations_remain_unresolved():
    from app.services import curated_conflict_proof as proof

    _, req, snapshots, _, inventories = quote_record()
    with pytest.raises(proof.SelectedQuoteScopeUnresolved):
        proof.selected_quote_scope(req, [], snapshots)
    other = deepcopy(inventories[0])
    other["request_use"]["node_id"] = "different-owned-node"
    with pytest.raises(proof.SelectedQuoteScopeUnresolved):
        proof.selected_quote_scope(req, [inventories[0], other], snapshots)


def test_old_saved_record_replays_unchanged():
    from app.services import curated_conflict_proof as proof

    data = actual()
    _, req, snapshots, settings, _ = quote_record()
    record = data["conflict"]
    assert (
        proof.reconstruct_procedure_group(
            record, req, snapshots, settings, supported_group=True
        )
        == record
    )


def test_public_curated_consumer_rebuilds_scope_and_full_membership():
    from app.services import curated_conflict_proof as proof

    record, req, snapshots, settings, inventories = quote_record()
    sources = source_rows(actual())
    entries, chunks = [], {}
    for identifier, source in sources.items():
        snapshots[identifier]["metadata"] = source.metadata
        for item in source.chunks:
            entries.append(proof.inspection_identity(item.chunk))
            chunks[str(item.chunk.id)] = {
                "identity": source.identity,
                "chunk": item.chunk,
            }
    entries.sort(key=lambda e: e["chunk_id"])
    members = [e for e in entries if e["conflict_group"]]
    selection = {
        "conflicts": [record],
        "inspected_sources": [
            {
                k: e[k]
                for k in ("chunk_id", "document_id", "document_version", "content_hash")
            }
            for e in entries
        ],
        "procedure_read_set": {
            "contract": "procedure-inspection-read-set-v1",
            "document_ids": None,
            "collection_ids": None,
            "sources": entries,
            "groups": [{"group": record["group"], "sources": members}],
            "after_proofs": {"consistent": True},
        },
    }
    # This interface receives the already independently replayed guard, as the
    # actual mixed-output caller does; UNITONLY NI observations above are new.
    groups = [
        {
            "requirement_id": req.id,
            "supported": True,
            "value": inventories[0]["source_body"],
            "source_guard": {"consumer_proof": {"envelope_inventory": inventories[0]}},
        }
    ]
    assert proof.reconstruct_curated(
        selection, [req], groups, snapshots, chunks, settings
    ) == [record]
    groups[0]["source_guard"]["consumer_proof"]["envelope_inventory"][
        "declared_relation"
    ]["declared_subject"]["text"] = req.topic
    with pytest.raises(ValueError):
        proof.reconstruct_curated(selection, [req], groups, snapshots, chunks, settings)
