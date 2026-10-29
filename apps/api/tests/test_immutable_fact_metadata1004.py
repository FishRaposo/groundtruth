"""UNITONLY producer/replay receipt metadata; no actual inference/SQL claim."""

import json
import uuid
from copy import deepcopy
from dataclasses import replace

import pytest
from app.models.chunk import ChunkWithScore
from app.services import contextual_mixed_output as output
from app.services import requirement_answers
from app.services.answer_reader import ReaderSelection, passage_span
from app.services.answer_support import SupportAssessment
from app.services.linguistic_property_cover import (
    factual_claim,
    factual_support_context,
)
from app.services.procedure_evidence import LocatedChunk, ProcedureSource

from tests.planning_library_unit830.test_support import metadata
from tests.test_captured_policy928 import configured
from tests.test_source_bound_location974 import actual


@pytest.fixture(scope="module")
def bound_source():
    raw, requirement, plan, policy = actual()
    identity = {k: v for k, v in raw["identity"].items() if k != "snapshot_id"}
    member = ChunkWithScore(
        id=uuid.UUID(raw["chunk_id"]),
        document_id=uuid.UUID(identity["document_id"]),
        content=raw["body"],
        chunk_index=0,
        relevance_score=1.0,
        metadata=identity,
    )
    snapshot = json.loads(plan.source_productions_json)["original_inputs"]["snapshots"][
        0
    ]
    immutable = json.loads(snapshot["metadata_json"])
    retrieved = {
        "document_title": "UNITONLY retrieval projection",
        **identity,
        "condition": None,
        "conflict_group": None,
    }
    producer = ProcedureSource(
        raw["body"],
        (LocatedChunk(member, 0, len(raw["body"])),),
        identity,
        retrieved,
        None,
    )
    replay = replace(producer, metadata=immutable)
    origin = next(
        (p for p in raw["origins"] if p["text"] == "virtual bay P"), raw["origins"][0]
    )
    interval = origin["chunk_range"]
    claim = factual_claim(
        requirement,
        raw["body"],
        interval["start"],
        interval["end"],
        policy=policy,
        plan=plan,
    )
    assert not claim.rejection
    return (
        raw,
        requirement,
        plan,
        policy,
        member,
        producer,
        replay,
        interval,
        claim,
        immutable,
    )


def receipt(values, source=None, plan="original", policy=None):
    (
        _,
        requirement,
        original,
        original_policy,
        member,
        producer,
        _,
        interval,
        claim,
        _,
    ) = values
    return factual_support_context(
        requirement,
        producer if source is None else source,
        member,
        interval,
        claim,
        policy=original_policy if policy is None else policy,
        plan=original if plan == "original" else plan,
    )


def test_producer_and_replay_bind_same_immutable_metadata_without_pair_change(
    bound_source,
):
    values = bound_source
    _, _, _, _, _, producer, replay, _, _, immutable = values
    before = deepcopy(producer.metadata)
    key, produced = receipt(values)
    replay_key, reconstructed = receipt(values, source=replay)
    assert key == replay_key == "fact_context_support"
    assert produced["source_metadata"] == reconstructed["source_metadata"] == immutable
    assert produced == reconstructed
    assert producer.metadata == before  # No mutation of retrieved source context.


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "ambiguous",
        "foreign",
        "version",
        "hash",
        "body",
        "metadata_missing",
        "metadata_list",
        "no_plan",
    ],
)
def test_unknown_or_unbound_snapshot_metadata_refuses(bound_source, damage):
    plan = bound_source[2]
    ledger = json.loads(plan.source_productions_json)
    rows = ledger["original_inputs"]["snapshots"]
    if damage == "missing":
        rows.clear()
    elif damage == "ambiguous":
        rows.append(deepcopy(rows[0]))
    elif damage == "foreign":
        rows[0]["identity"]["document_id"] = str(uuid.UUID(int=9004))
    elif damage == "version":
        rows[0]["identity"]["document_version"] += 1
    elif damage == "hash":
        rows[0]["identity"]["content_hash"] = "0" * 64
    elif damage == "body":
        rows[0]["body"] += " altered"
    elif damage == "metadata_missing":
        del rows[0]["metadata_json"]
    elif damage == "metadata_list":
        rows[0]["metadata_json"] = "[]"
    damaged = (
        None
        if damage == "no_plan"
        else replace(plan, source_productions_json=json.dumps(ledger))
    )
    with pytest.raises(ValueError):
        receipt(bound_source, plan=damaged)


def test_historical_all_sources_retains_exact_whole_source_receipt(bound_source):
    values = bound_source
    old = replace(values[3], source_governance_profile="all_sources_v1")
    key, record = receipt(values, policy=old, plan=None)
    assert key == "whole_source_support"
    assert record == {
        "contract": "whole-source-fact-support-v1",
        "verification_method": "nli_entailment",
        "requirement_id": values[1].id,
        "source_identity": values[5].identity,
        "source_range": {"start": 0, "end": len(values[5].body)},
        "premise": values[5].body,
        "hypothesis": values[8].hypothesis,
    }


async def test_new_producer_receipt_replays_and_metadata_tampering_still_rejects(
    bound_source, monkeypatch
):
    raw, requirement, plan, policy, member, producer, _, interval, _, immutable = (
        bound_source
    )

    async def qa(*args, **kwargs):
        return [
            ReaderSelection(
                passage_span(raw["body"], interval["start"], interval["end"]),
                {
                    "raw_span": {
                        **interval,
                        "text": raw["body"][interval["start"] : interval["end"]],
                    },
                    "null_margin": -3.0,
                },
            )
        ]

    async def nli(pairs, **kwargs):
        return [
            SupportAssessment("entailment", (-3.0, 3.0, 0.0), 3.0, True, 32)
            for _ in pairs
        ]

    async def resolve(_):
        return producer

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", nli)
    candidates = []
    found = await requirement_answers._find_witnesses(
        requirement,
        [member],
        configured(SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1"),
        candidates,
        resolve_source=resolve,
        request_plan=plan,
    )
    assert found
    candidate = next(c for c in candidates if c.get("decision") == "supported")
    assert candidate["fact_context_support"]["source_metadata"] == immutable
    snapshot = {
        **producer.identity,
        "body": producer.body,
        "metadata": immutable,
        "chunks": [{"id": str(member.id), "index": 0, "content": member.content}],
    }
    chunks, _ = output.factual._source_inventory(
        {producer.identity["document_id"]: snapshot}
    )
    source = chunks[str(member.id)]["source"]
    source.metadata = immutable
    source.identity["workspace_id"] = producer.identity["workspace_id"]
    settings = {"evidence_profile": policy.record(), "support": metadata()}
    assert output._fact_assessment(
        requirement, candidate, candidate["proposal"], chunks, settings, plan
    )[1]
    forged = deepcopy(candidate)
    forged["fact_context_support"]["source_metadata"] = {"condition": "unverified"}
    with pytest.raises(ValueError, match="input/identity"):
        output._fact_assessment(
            requirement, forged, forged["proposal"], chunks, settings, plan
        )
