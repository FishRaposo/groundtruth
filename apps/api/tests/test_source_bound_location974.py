"""Actual failed961 location origins; UNITONLY inference, no quality verdict."""

import json
import uuid
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from app.evidence_policy import recorded_evidence_policy
from app.services import planning_declarations as source
from app.services.linguistic_property_cover import factual_claim
from app.services.requirement_answers import witness_value_identity

from tests.staged_plan_unit837.fixtures_source import universe
from tests.test_captured_planning_correction957 import arguments, replay


def actual():
    raw = json.loads(
        (Path(__file__).parent / "fixtures/actual-location-source974.json").read_text(
            encoding="utf-8"
        )
    )
    identity = source.SourceIdentity(**raw["identity"])
    snapshot = source.SourceSnapshot(
        identity,
        raw["metadata"].get("document_title", ""),
        raw["body"],
        source.canonical(raw["metadata"]),
        (
            source.SourceChunk(
                raw["chunk_id"],
                0,
                source.RawRange(0, len(raw["body"]), raw["body"]),
                source.canonical(raw["identity"]),
            ),
        ),
    )
    captures = source.SourceCaptures(
        identity,
        (
            source.CaptureWindow(
                0, len(raw["body"]), source.canonical(raw["source_capture"])
            ),
        ),
    )
    args = arguments(bound=True)
    args.update(
        question=raw["question"],
        capture=raw["request_capture"],
        manifest=universe((snapshot,)),
        snapshots=(snapshot,),
        source_captures=(captures,),
    )
    plan, _ = replay(args)
    req = next(r for r in plan.requirements if r.kind == "location")
    policy = recorded_evidence_policy(json.loads(plan.evidence_profile_json))
    return raw, req, plan, policy


def test_exact_actual_supported_origins_do_not_become_conflicting_field_values():
    raw, req, plan, policy = actual()
    claims = []
    for proposal in raw["origins"]:
        a, b = proposal["document_range"]["start"], proposal["document_range"]["end"]
        assert raw["body"][a:b] == proposal["text"]
        claims.append(factual_claim(req, raw["body"], a, b, policy=policy, plan=plan))
    assert all(not c.rejection for c in claims)
    identities = {
        witness_value_identity(req, c.value, reading_profile="contextual_source_v4")
        for c in claims
    }
    assert len(identities) == 1
    assert {c.value for c in claims} == {"virtual bay P"}
    assert {(c.start, c.end) for c in claims} == {(817, 830)}
    old = replace(policy, source_governance_profile="all_sources_v1")
    assert factual_claim(req, raw["body"], 825, 830, policy=old, plan=plan).rejection
    ledger = json.loads(plan.source_productions_json)
    window = ledger["original_inputs"]["source_captures"][0]["windows"][0]
    captured = json.loads(window["capture_json"])
    captured["annotation_sha256"] = "0" * 64
    window["capture_json"] = source.canonical(captured)
    corrupt = replace(plan, source_productions_json=source.canonical(ledger))
    with pytest.raises(ValueError):
        factual_claim(req, raw["body"], 825, 830, policy=policy, plan=corrupt)


async def test_actual_raw_origins_are_preserved_and_consumer_rebuilds_field(
    monkeypatch,
):
    from app.config import Settings
    from app.models.chunk import ChunkWithScore
    from app.services import contextual_mixed_output as output
    from app.services import requirement_answers
    from app.services.answer_reader import ReaderSelection, passage_span
    from app.services.answer_support import SupportAssessment
    from app.services.procedure_evidence import LocatedChunk, ProcedureSource

    from tests.planning_library_unit830.test_support import metadata

    raw, req, plan, policy = actual()
    body = raw["body"]
    identity = {k: v for k, v in raw["identity"].items() if k != "snapshot_id"}
    member = ChunkWithScore(
        id=uuid.UUID(raw["chunk_id"]),
        document_id=uuid.UUID(identity["document_id"]),
        content=body,
        chunk_index=0,
        relevance_score=1.0,
        metadata=identity,
    )
    actual_source = ProcedureSource(
        body, (LocatedChunk(member, 0, len(body)),), identity, raw["metadata"], None
    )
    choices = [
        {**p["chunk_range"], "text": p["text"], "null_margin": -3.0}
        for p in raw["origins"]
    ]
    calls = []

    async def qa(*args, **kwargs):
        first = choices[0]
        return [
            ReaderSelection(
                passage_span(body, first["start"], first["end"]),
                {"raw_candidates": choices, "null_margin": -3.0},
            )
        ]

    async def assess(pairs, **kwargs):
        calls.extend(pairs)
        return [
            SupportAssessment("entailment", (-3.0, 3.0, 0.0), 3.0, True, 32)
            for _ in pairs
        ]

    async def resolve(_):
        return actual_source

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", assess)
    config = Settings(
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
    )
    candidates = []
    found = await requirement_answers._find_witnesses(
        req, [member], config, candidates, resolve_source=resolve, request_plan=plan
    )
    assert len(found) == 1 and found[0].value == "virtual bay P"
    assert len(calls) == 2
    assert all(
        p.hypothesis
        == "The virtual location for Citrine fragment desk is virtual bay P."
        for p in calls
    )
    assert {p["text"] for p in found[0].proposals} == {
        p["text"] for p in raw["origins"]
    }
    assert {tuple(p["chunk_range"].values()) for p in found[0].proposals} == {
        tuple(p["chunk_range"].values()) for p in raw["origins"]
    }
    candidate = next(c for c in candidates if c.get("decision") == "supported")
    snapshot = {
        **identity,
        "body": body,
        "metadata": raw["metadata"],
        "chunks": [{"id": raw["chunk_id"], "index": 0, "content": body}],
    }
    chunks, _ = output.factual._source_inventory({identity["document_id"]: snapshot})
    chunks[raw["chunk_id"]]["source"].identity["workspace_id"] = identity[
        "workspace_id"
    ]
    chunks[raw["chunk_id"]]["source"].metadata = raw["metadata"]
    settings = {"evidence_profile": policy.record(), "support": metadata()}
    descriptor, supported, _, value = output._fact_assessment(
        req, candidate, candidate["proposal"], chunks, settings, plan
    )
    assert supported and value == descriptor["value"] == "virtual bay P"
    for field in ("value", "version", "raw"):
        bad = deepcopy(candidate)
        proposal = deepcopy(candidate["proposal"])
        if field == "value":
            bad["validated_answer_span"]["text"] = "bay P"
        elif field == "version":
            bad["fact_context_support"]["source_identity"]["document_version"] += 1
        else:
            proposal["chunk_range"] = {"start": 809, "end": 813}
        with pytest.raises(ValueError):
            output._fact_assessment(req, bad, proposal, chunks, settings, plan)


def test_distinct_location_clauses_remain_distinct_and_unclosed_coordination_refuses():
    from tests.staged_plan_unit837.fixtures_source import source as unit_source
    from tests.test_captured_request_repair953 import observed

    group = [
        ("Citrine", "NOUN", "citrine", "compound", 2),
        ("fragment", "NOUN", "fragment", "compound", 2),
        ("desk", "NOUN", "desk", "nsubjpass", 4),
        ("is", "AUX", "be", "auxpass", 4),
        ("held", "VERB", "hold", "ROOT", 4),
        ("in", "ADP", "in", "prep", 4),
        ("virtual", "ADJ", "virtual", "amod", 7),
        ("bay", "NOUN", "bay", "compound", 8),
        ("P", "PROPN", "P", "pobj", 5),
        (".", "PUNCT", ".", "punct", 4),
    ]
    other = list(group)
    other[8] = ("Q", "PROPN", "Q", "pobj", 5)
    snapshot, caps = unit_source([group, other], doc="UNITONLY974-two-location-clauses")
    args = arguments(bound=True)
    request = observed("reranked-003")
    args.update(
        question=request["question"],
        capture=request["capture"],
        manifest=universe((snapshot,)),
        snapshots=(snapshot,),
        source_captures=(caps,),
    )
    plan, _ = replay(args)
    req = next(r for r in plan.requirements if r.kind == "location")
    policy = recorded_evidence_policy(json.loads(plan.evidence_profile_json))
    claims = []
    for text in ("bay P", "bay Q"):
        at = snapshot.body.index(text)
        claims.append(
            factual_claim(
                req, snapshot.body, at, at + len(text), policy=policy, plan=plan
            )
        )
    assert {c.value for c in claims} == {"virtual bay P", "virtual bay Q"}
    assert (
        len(
            {
                witness_value_identity(
                    req, c.value, reading_profile="contextual_source_v4"
                )
                for c in claims
            }
        )
        == 2
    )
    one, one_cap = unit_source([group], doc="UNITONLY974-location-version1")
    two, two_cap = unit_source([other], doc="UNITONLY974-location-version3")
    two = replace(two, identity=replace(two.identity, document_version=3))
    two_cap = replace(two_cap, identity=two.identity)
    args.update(
        manifest=universe((one, two)),
        snapshots=(one, two),
        source_captures=(one_cap, two_cap),
    )
    versioned, _ = replay(args)
    version_req = next(r for r in versioned.requirements if r.kind == "location")
    values = set()
    for item, text in ((one, "bay P"), (two, "bay Q")):
        at = item.body.index(text)
        values.add(
            factual_claim(
                version_req,
                item.body,
                at,
                at + len(text),
                policy=policy,
                plan=versioned,
            ).value
        )
    assert values == {"virtual bay P", "virtual bay Q"}
    coordinated = group[:-1] + [
        ("and", "CCONJ", "and", "cc", 8),
        ("Q", "PROPN", "Q", "conj", 8),
        (".", "PUNCT", ".", "punct", 4),
    ]
    bad, caps = unit_source(
        [coordinated], doc="UNITONLY974-unclosed-location-coordination"
    )
    args.update(manifest=universe((bad,)), snapshots=(bad,), source_captures=(caps,))
    bad_plan, _ = replay(args)
    bad_req = next(r for r in bad_plan.requirements if r.kind == "location")
    at = bad.body.index("bay P")
    assert (
        factual_claim(
            bad_req, bad.body, at, at + 5, policy=policy, plan=bad_plan
        ).rejection
        == "captured_location_argument_unresolved"
    )
