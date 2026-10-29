"""Actual990 inputs, reconstructed real plan; UNITONLY NI is explicit."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path

import pytest
from app.services import planning_declarations as source
from app.services.literal_quantity import (
    QuantityUnresolved,
    consume_quantity_candidate,
    produce_quantity_candidate,
)

from tests.planning_library_unit830.test_support import metadata
from tests.test_captured_planning_correction957 import replay


@lru_cache
def actual():
    raw = json.loads(
        (
            Path(__file__).parent / "fixtures/source_stated_quantity_actual1010.json"
        ).read_text(encoding="utf-8")
    )
    snapshots = tuple(
        source.SourceSnapshot(
            **{
                **s,
                "identity": source.SourceIdentity(**s["identity"]),
                "chunks": tuple(
                    source.SourceChunk(
                        **{**c, "literal": source.RawRange(**c["literal"])}
                    )
                    for c in s["chunks"]
                ),
            }
        )
        for s in raw["snapshots"]
    )
    captures = tuple(
        source.SourceCaptures(
            source.SourceIdentity(**c["identity"]),
            tuple(source.CaptureWindow(**w) for w in c["windows"]),
        )
        for c in raw["source_captures"]
    )
    manifest = source.PlanningUniverse(
        **{
            **raw["original_manifest"],
            "publications": tuple(
                source.SourceIdentity(**s)
                for s in raw["original_manifest"]["publications"]
            ),
        }
    )
    args = {
        "question": raw["plan"]["question"],
        "capture": raw["request_capture"],
        "snapshots": snapshots,
        "source_captures": captures,
        "manifest": manifest,
        "sql_read_set_json": raw["sql_read_set_json"],
        "evidence_profile": json.loads(raw["plan"]["evidence_profile_json"]),
        "support_metadata": metadata(),
    }
    plan, _ = replay(args)
    req = next(
        r for r in plan.requirements if r.id == raw["plan"]["requirements"][0]["id"]
    )
    snapshot = next(
        s
        for s in snapshots
        if s.identity.document_id == raw["candidates"][0]["document_id"]
    )
    identity = {
        k: v for k, v in asdict(snapshot.identity).items() if k != "snapshot_id"
    }
    return raw, req, snapshot, identity, plan, args


def produce(index=0, *, plan=None, req=None):
    raw, original, snapshot, identity, original_plan, _ = actual()
    row = raw["candidates"][index]
    selected = next(
        s
        for s in actual()[5]["snapshots"]
        if s.identity.document_id == row["document_id"]
    )
    identity = {
        k: v for k, v in asdict(selected.identity).items() if k != "snapshot_id"
    }
    chunk = next(c for c in selected.chunks if c.chunk_id == row["chunk_id"])
    options = {
        "source_identity": identity,
        "chunk_content": chunk.literal.text,
        "chunk_start": chunk.literal.start,
        "raw_start": row["raw_span"]["start"],
        "raw_end": row["raw_span"]["end"],
        "evidence_profile": json.loads((plan or original_plan).evidence_profile_json),
        "request_plan": plan or original_plan,
    }
    return produce_quantity_candidate(
        req or original, selected.body, **options
    ), options


@pytest.mark.parametrize("index", [0, 1])
def test_actual_number_and_qualified_amount_copy_whole_source_statement(index):
    (claim, binding), options = produce(index)
    _, req, snapshot, identity, plan, _ = actual()
    assert plan.resolved_request and not plan.publication_ready
    clause = "A Copper Index lower-bound trace uses 12 sorted integer entries."
    assert binding["method"] == "source_stated_qualified_quantity_v1"
    assert binding["source_stated_scope"]["unqualified_total"] == "NOT_ASSERTED"
    assert binding["canonical_value"]["unit"] == "sorted integer entries"
    assert binding["model_support"] == "NOT_ASSERTED"
    assert claim.value == claim.premise == claim.hypothesis == clause
    assert snapshot.body[claim.start : claim.end] == clause
    assert binding["source_identity"] == identity
    assert consume_quantity_candidate(binding, req, snapshot.body, **options) == (
        claim,
        binding,
    )
    for key in ("canonical_value", "source_stated_scope"):
        bad = deepcopy(binding)
        bad[key]["unit" if key == "canonical_value" else "unqualified_total"] = "forged"
        with pytest.raises(QuantityUnresolved):
            consume_quantity_candidate(bad, req, snapshot.body, **options)


@pytest.mark.parametrize("index", [2, 3, 4])
def test_actual_partial_amount_and_foreign_role_fields_remain_invalid(index):
    with pytest.raises(QuantityUnresolved):
        produce(index)


@pytest.mark.parametrize("variant", ["broad_subject_number", "partial_number"])
def test_full_clause_value_never_relaxes_raw_proposal_eligibility(variant):
    (_, binding), options = produce()
    _, req, snapshot, _, _, _ = actual()
    if variant == "broad_subject_number":
        options["raw_start"] = (
            binding["source_clause"]["start"] - options["chunk_start"]
        )
    else:
        options["raw_end"] -= 1
    with pytest.raises(QuantityUnresolved, match="raw_span_not_exact"):
        produce_quantity_candidate(req, snapshot.body, **options)


@pytest.mark.parametrize(
    "variant",
    [
        "condition",
        "modality",
        "reference",
        "negation",
        "quantifier",
        "unit",
        "no_quote",
    ],
)
def test_original_operator_guards_and_explicit_mode_are_mandatory(variant):
    _, _, _, _, plan, _ = actual()
    if variant == "no_quote":
        from app.evidence_policy import recorded_evidence_policy

        policy = recorded_evidence_policy(json.loads(plan.evidence_profile_json))
        plan = replace(
            plan,
            evidence_profile_json=json.dumps(
                replace(policy, procedure_scope_profile="requested_scope_v1").record()
            ),
        )
    else:
        field = {
            "condition": "conditions",
            "modality": "modality",
            "reference": "references",
            "negation": "negation",
            "quantifier": "quantifiers",
            "unit": "units",
        }[variant]
        uses = tuple(
            replace(u, **{field: (u.original,)})
            if u.requirement_id == actual()[1].id
            else u
            for u in plan.uses
        )
        plan = replace(plan, uses=uses)
    with pytest.raises(QuantityUnresolved):
        produce(plan=plan)


@pytest.mark.parametrize(
    "variant", ["duplicate_field", "condition_metadata", "conflict_metadata"]
)
def test_all_retained_same_scope_fields_and_curated_metadata_are_checked(variant):
    """UNITONLY retained-inventory mutations; no new source authority is claimed."""
    from app.services.literal_quantity import _stated_cover, _stated_request

    _, req, snapshot, _, plan, _ = actual()
    op = _stated_request(
        req,
        next(u for u in plan.uses if u.requirement_id == req.id),
        json.loads(plan.structure_json),
        plan.question,
    )
    record = json.loads(plan.source_productions_json)
    original = record["original_inputs"]
    selected = next(
        s
        for s in original["snapshots"]
        if s["identity"]["document_id"] == snapshot.identity.document_id
    )
    if variant == "duplicate_field":
        clone = deepcopy(selected)
        clone["identity"]["document_id"] = "UNITONLY1010-duplicate-publication"
        cap = deepcopy(
            next(
                c
                for c in original["source_captures"]
                if c["identity"] == selected["identity"]
            )
        )
        cap["identity"] = clone["identity"]
        original["snapshots"].append(clone)
        original["source_captures"].append(cap)
    else:
        props = json.loads(selected["metadata_json"])
        props["condition" if variant == "condition_metadata" else "conflict_group"] = (
            "unknown"
        )
        selected["metadata_json"] = json.dumps(props)
    with pytest.raises(QuantityUnresolved):
        _stated_cover(
            req, replace(plan, source_productions_json=json.dumps(record)), op
        )


@pytest.mark.parametrize(
    "variant", ["predicate", "unit", "target", "required_reference"]
)
def test_literal_source_mismatches_refuse_without_retagging(variant):
    """UNITONLY same-length lexical mutations; original dependency/POS retained."""
    import hashlib

    from app.services import request_parser as parser
    from app.services.literal_quantity import _stated_clause, _stated_request

    _, req, snapshot, _, plan, args = actual()
    cap = next(c for c in args["source_captures"] if c.identity == snapshot.identity)
    annotation = deepcopy(json.loads(cap.windows[0].capture_json)["annotation"])
    body = snapshot.body
    changes = {
        "predicate": (168, "adds", "add"),
        "unit": (172, "records", "record"),
        "target": (162, "Silver", "Silver"),
        "required_reference": (168, "read", "read"),
    }
    index, value, lemma = changes[variant]
    token = annotation["tokens"][index]
    body = body[: token["start"]] + value + body[token["end"] :]
    token["text"], token["lemma"] = value, lemma
    annotation["raw_text"], annotation["raw_sha256"] = (
        body,
        hashlib.sha256(body.encode()).hexdigest(),
    )
    for sentence in annotation["sentences"]:
        sentence["text"] = body[sentence["start"] : sentence["end"]]
    annotation["lossless_input_cover"] = parser._cover(body, annotation["tokens"])
    annotation["linguistic_proposals"] = parser._proposals(
        annotation["tokens"], annotation["sentences"]
    )
    rebuilt = parser.validate_capture(body, parser.make_capture(annotation))
    operator = _stated_request(
        req,
        next(u for u in plan.uses if u.requirement_id == req.id),
        json.loads(plan.structure_json),
        plan.question,
    )
    sentence = next(s for s in rebuilt["sentences"] if s["start"] == 817)
    with pytest.raises(QuantityUnresolved):
        _stated_clause(req, body, rebuilt, sentence, operator)


@pytest.mark.parametrize("variant", ["conflicting_value", "required_reference"])
def test_competing_values_and_potential_same_field_reference_block_scan(variant):
    """UNITONLY duplicate-publication lexical mutations, never source authority."""
    import hashlib

    from app.services import request_parser as parser
    from app.services.literal_quantity import _stated_cover, _stated_request

    _, req, snapshot, _, plan, _ = actual()
    record = json.loads(plan.source_productions_json)
    original = record["original_inputs"]
    clone = deepcopy(
        next(
            s
            for s in original["snapshots"]
            if s["identity"]["document_id"] == snapshot.identity.document_id
        )
    )
    cap = deepcopy(
        next(
            c for c in original["source_captures"] if c["identity"] == clone["identity"]
        )
    )
    annotation = json.loads(cap["windows"][0]["capture_json"])["annotation"]
    index, word = (169, "13") if variant == "conflicting_value" else (168, "read")
    token = annotation["tokens"][index]
    body = clone["body"][: token["start"]] + word + clone["body"][token["end"] :]
    token["text"], token["lemma"] = word, word
    annotation["raw_text"], annotation["raw_sha256"] = (
        body,
        hashlib.sha256(body.encode()).hexdigest(),
    )
    for sentence in annotation["sentences"]:
        sentence["text"] = body[sentence["start"] : sentence["end"]]
    annotation["lossless_input_cover"] = parser._cover(body, annotation["tokens"])
    annotation["linguistic_proposals"] = parser._proposals(
        annotation["tokens"], annotation["sentences"]
    )
    capture = parser.make_capture(annotation)
    parser.validate_capture(body, capture)
    clone["body"] = body
    clone["identity"]["document_id"] = "UNITONLY1010-competing-publication"
    clone["identity"]["content_hash"] = hashlib.sha256(body.encode()).hexdigest()
    cap["identity"] = clone["identity"]
    cap["windows"][0]["capture_json"] = json.dumps(capture)
    original["snapshots"].append(clone)
    original["source_captures"].append(cap)
    operator = _stated_request(
        req,
        next(u for u in plan.uses if u.requirement_id == req.id),
        json.loads(plan.structure_json),
        plan.question,
    )
    with pytest.raises(QuantityUnresolved, match="ambiguous|reference"):
        _stated_cover(
            req, replace(plan, source_productions_json=json.dumps(record)), operator
        )


async def test_full_clause_lineage_count_replay_and_factual_publication(monkeypatch):
    """UNITONLY QA/NI seams, actual captured46-source plan and metadata authority."""
    import uuid

    from app.config import Settings
    from app.models.chunk import ChunkWithScore
    from app.services import contextual_mixed_output as output
    from app.services import requirement_answers
    from app.services.answer_reader import ReaderSelection, passage_span
    from app.services.answer_support import SupportAssessment
    from app.services.procedure_discovery import LocatedChunk, ProcedureSource

    raw, req, snapshot, identity, plan, _ = actual()
    part = next(
        c for c in snapshot.chunks if c.chunk_id == raw["candidates"][0]["chunk_id"]
    )
    member = ChunkWithScore(
        id=uuid.UUID(part.chunk_id),
        document_id=uuid.UUID(identity["document_id"]),
        content=part.literal.text,
        chunk_index=part.ordinal,
        relevance_score=0.8,
        metadata={
            **json.loads(part.metadata_json),
            "document_version": identity["document_version"],
            "content_hash": identity["content_hash"],
        },
    )
    immutable = ProcedureSource(
        snapshot.body,
        (LocatedChunk(member, part.literal.start, part.literal.end),),
        identity,
        json.loads(snapshot.metadata_json),
        None,
    )
    span = raw["candidates"][0]["raw_span"]
    calls = []

    async def qa(*args, **kwargs):
        return [
            ReaderSelection(
                passage_span(member.content, span["start"], span["end"]),
                {"raw_span": {**span, "text": "12"}, "null_margin": -3.0},
            )
        ]

    async def ni(pairs, **kwargs):
        calls.extend(pairs)
        return [
            SupportAssessment("entailment", (-3.0, 3.0, 0.0), 3.0, True, 32)
            for _ in pairs
        ]

    async def resolve(_):
        return immutable

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", ni)
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
        PROCEDURE_SCOPE_PROFILE="activity_quote_v1",
    )
    candidates = []
    witnesses = await requirement_answers._find_witnesses(
        req, [member], config, candidates, resolve_source=resolve, request_plan=plan
    )
    assert witnesses and calls, [
        (c.get("decision"), c.get("reason")) for c in candidates
    ]
    clause = "A Copper Index lower-bound trace uses 12 sorted integer entries."
    assert witnesses[0].value == clause
    candidate = next(c for c in candidates if c.get("decision") == "supported")
    proposal = candidate["proposal"]
    assert proposal["chunk_range"] == span
    assert candidate["validated_answer_span"]["text"] == clause
    wire = {
        **identity,
        "body": snapshot.body,
        "metadata": immutable.metadata,
        "chunks": [
            {
                "id": str(member.id),
                "index": member.chunk_index,
                "content": member.content,
            }
        ],
    }
    chunks, _ = output.factual._source_inventory({identity["document_id"]: wire})
    chunks[str(member.id)]["source"].metadata = immutable.metadata
    chunks[str(member.id)]["source"].identity["workspace_id"] = identity["workspace_id"]
    settings = {
        "evidence_profile": json.loads(plan.evidence_profile_json),
        "support": metadata(),
    }
    descriptor, supported, _, _ = output._fact_assessment(
        req, candidate, proposal, chunks, settings, plan
    )
    assert supported and descriptor["value"] == clause
    assert descriptor["quantity_binding"] == candidate["quantity_binding"]
    assert (
        descriptor["quantity_binding"]["binding"]["method"]
        == "source_stated_qualified_quantity_v1"
    )
    bad = deepcopy(candidate)
    bad["quantity_binding"]["binding"]["source_stated_scope"]["unqualified_total"] = (
        "asserted"
    )
    with pytest.raises(ValueError):
        output._fact_assessment(req, bad, proposal, chunks, settings, plan)
