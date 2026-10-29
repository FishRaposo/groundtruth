"""Exact exposed captures; UNITONLY boundaries, no quality claim."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from app.services import planning_declarations as source
from app.services.literal_quantity import produce_quantity_candidate

from tests.staged_plan_unit837.fixtures_source import universe
from tests.test_captured_planning_correction957 import arguments, replay
from tests.test_captured_request_repair953 import observed


def actual():
    raw = json.loads(
        (Path(__file__).parent / "fixtures/actual-count-source968.json").read_text(
            encoding="utf-8"
        )
    )
    row = raw["snapshot"]
    snapshot = source.SourceSnapshot(
        **{
            **row,
            "identity": source.SourceIdentity(**row["identity"]),
            "chunks": tuple(
                source.SourceChunk(**{**c, "literal": source.RawRange(**c["literal"])})
                for c in row["chunks"]
            ),
        }
    )
    cap = raw["source_capture"]
    captures = source.SourceCaptures(
        source.SourceIdentity(**cap["identity"]),
        tuple(source.CaptureWindow(**w) for w in cap["windows"]),
    )
    args = arguments(bound=True)
    request = observed("reranked-003")
    args.update(
        question=request["question"],
        capture=request["capture"],
        manifest=universe((snapshot,)),
        snapshots=(snapshot,),
        source_captures=(captures,),
    )
    plan, _ = replay(args)
    requirement = next(r for r in plan.requirements if r.kind == "quantity")
    identity = {
        k: v for k, v in asdict(snapshot.identity).items() if k != "snapshot_id"
    }
    return requirement, snapshot, identity, plan, args


@pytest.mark.parametrize("raw", ["6 datagram fragments", "6"])
def test_exact_actual_typed_quantity_enters_existing_count_proof(raw):
    requirement, snapshot, identity, plan, _ = actual()
    body = snapshot.body
    start = body.index(raw)
    claim, binding = produce_quantity_candidate(
        requirement,
        body,
        source_identity=identity,
        chunk_content=body,
        chunk_start=0,
        raw_start=start,
        raw_end=start + len(raw),
        evidence_profile=json.loads(plan.evidence_profile_json),
        request_plan=plan,
    )
    assert binding["method"] == "typed_atomic_count_field_v1"
    assert binding["canonical_value"] == {"number": "6", "unit": "datagram fragments"}
    assert claim.value == "6 datagram fragments"
    assert claim.proof_edges == ()


async def test_real_count_capture_replay_and_initial_wrapper_claim_agree():
    import uuid

    from app.config import Settings
    from app.models.chunk import ChunkWithScore
    from app.services.captured_answer_planning import CapturedAnswerContext
    from app.services.captured_plan_inputs import capture_inputs_v2
    from app.services.count_runtime import (
        capture_count,
        count_identity,
        reconstruct_count,
    )
    from app.services.linguistic_quantities import scoped_quantity_claim
    from app.services.procedure_evidence import LocatedChunk, ProcedureSource

    from tests.captured_inputs_unit932.fixtures import authoritative

    requirement, snapshot, identity, plan, args = actual()
    policy = json.loads(plan.evidence_profile_json)
    inputs = capture_inputs_v2(**args, observations=(), actual_executions=())
    context = CapturedAnswerContext(
        plan, source.canonical(inputs), source.canonical(authoritative(inputs))
    )
    member = ChunkWithScore(
        id=uuid.UUID(snapshot.chunks[0].chunk_id),
        document_id=uuid.UUID(identity["document_id"]),
        content=snapshot.body,
        chunk_index=0,
        relevance_score=1.0,
        metadata=identity,
    )
    actual_source = ProcedureSource(
        snapshot.body,
        (LocatedChunk(member, 0, len(snapshot.body)),),
        identity,
        json.loads(snapshot.metadata_json),
        None,
    )
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
    identities = []
    for text in ("6", "6 datagram fragments"):
        start = snapshot.body.index(text)
        raw = {"start": start, "end": start + len(text)}
        initial = scoped_quantity_claim(
            requirement,
            snapshot.body,
            **raw,
            evidence_profile=policy,
            request_plan=context,
        )
        full, record = await capture_count(
            requirement,
            actual_source,
            member,
            raw,
            config,
            evidence_profile=policy,
            request_plan=context,
        )
        assert initial == full
        assert (
            full.hypothesis
            == "The batch quantity for Citrine fragment desk is 6 datagram fragments."
        )
        assert (
            full.premise
            == "A Citrine fragment desk batch contains 6 datagram fragments."
        )
        assert full.proof_edges == ()
        assert (
            record["request_capture"]
            == json.loads(plan.structure_json)["original_capture"]
        )
        restored, exact = reconstruct_count(
            record,
            requirement,
            actual_source,
            member,
            raw,
            evidence_profile=policy,
            request_plan=plan,
        )
        assert restored == full and exact == record
        identities.append(count_identity(record))
        for key in ("unit", "source", "capture"):
            bad = deepcopy(record)
            if key == "unit":
                bad["binding"]["canonical_value"]["unit"] = "simulated seconds"
            elif key == "source":
                bad["binding"]["source_identity"]["document_version"] += 1
            else:
                bad["source_capture"]["annotation"]["tokens"][120]["lemma"] = (
                    "manufacture"
                )
            with pytest.raises(ValueError):
                reconstruct_count(
                    bad,
                    requirement,
                    actual_source,
                    member,
                    raw,
                    evidence_profile=policy,
                    request_plan=plan,
                )
    assert len(set(identities)) == 1


def test_wrong_unit_span_and_unrepresented_qualification_refuse_before_ni():
    from app.services.linguistic_quantities import scoped_quantity_claim
    from app.services.literal_quantity import QuantityUnresolved

    req, snapshot, identity, plan, _ = actual()
    policy = json.loads(plan.evidence_profile_json)
    for text in ("14 simulated seconds", "14", "6 datagram"):
        start = snapshot.body.index(text)
        claim = scoped_quantity_claim(
            req,
            snapshot.body,
            start,
            start + len(text),
            evidence_profile=policy,
            request_plan=plan,
        )
        assert claim.rejection
    start = snapshot.body.index("6 datagram fragments")
    raw = {"start": start, "end": start + 20}
    use = next(u for u in plan.uses if u.requirement_id == req.id)
    qualified = replace(
        plan,
        uses=tuple(
            replace(u, modality=(u.original,)) if u is use else u for u in plan.uses
        ),
    )
    assert scoped_quantity_claim(
        req, snapshot.body, **raw, evidence_profile=policy, request_plan=qualified
    ).rejection
    assert scoped_quantity_claim(
        replace(req, attribute="minute quantity"),
        snapshot.body,
        **raw,
        evidence_profile=policy,
        request_plan=plan,
    ).rejection
    with pytest.raises(QuantityUnresolved):
        produce_quantity_candidate(
            req,
            snapshot.body,
            source_identity=identity,
            chunk_content=snapshot.body,
            chunk_start=0,
            raw_start=start,
            raw_end=start + 20,
        )
