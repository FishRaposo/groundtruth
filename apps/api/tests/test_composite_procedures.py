"""Invented controller doubles: proposal discovery never substitutes for proof."""

import hashlib
import uuid

import pytest
from app.config import Settings
from app.models.chunk import ChunkWithScore
from app.models.query import QueryRequest
from app.services import procedure_evidence, requirement_answers
from app.services.answer_reader import ReaderSelection
from app.services.answer_requirements import plan_requirements
from app.services.answer_support import SupportAssessment
from app.services.procedure_evidence import LocatedChunk, ProcedureSource

BODY = (
    "Larch transfer procedure. This complete procedure applies to ordinary "
    "Larch transfers. 1. Verify the approval before starting the Larch transfer. "
    "2. Copy the identifier onto the register. Do not reopen the register."
)
QUESTION = "Give the complete ordered method for ordinary Larch transfers."


def chunk(text, *, document=None):
    return ChunkWithScore(
        id=uuid.uuid4(),
        document_id=document or uuid.uuid4(),
        content=text,
        chunk_index=0,
        relevance_score=0.8,
        metadata={
            "document_version": 1,
            "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        },
    )


def config(profile="qa_plus_source_patterns_v1"):
    return Settings(
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        ANSWER_PROPOSAL_PROFILE=profile,
    )


def doubles(monkeypatch, member, *, reject=False, reader_error=False):
    async def reader(question, contexts, config=None):
        if reader_error:
            raise RuntimeError("invented configured reader unavailable")
        return [
            ReaderSelection(None, {"decision": "no_answer", "null_margin": 9.0})
            for _ in contexts
        ]

    calls = []

    async def nli(pairs, config=None):
        calls.extend(pairs)
        return [
            SupportAssessment(
                "neutral" if reject else "entailment",
                (-5.0, 5.0, -5.0),
                10.0,
                not reject,
                12,
            )
            for _ in pairs
        ]

    source = ProcedureSource(
        member.content,
        (LocatedChunk(member, 0, len(member.content)),),
        {"document_id": str(member.document_id), **member.metadata},
        {},
        None,
    )

    async def resolve(*args):
        return source

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", reader)
    monkeypatch.setattr(requirement_answers.support_service, "assess", nli)
    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    return calls


async def current(member):
    return True


async def procedure(monkeypatch, *, profile="qa_plus_source_patterns_v1", reject=False):
    member = chunk(BODY)
    calls = doubles(monkeypatch, member, reject=reject)
    candidates = []
    result = await requirement_answers._find_procedure_witnesses(
        None,
        QueryRequest(question=QUESTION),
        {},
        plan_requirements(QUESTION)[0],
        config(profile),
        candidates,
        {member.id: member},
        [],
        current,
    )
    return result, candidates, calls


# Defect: healthy QA null currently prevents the strict immutable source reaching NI.
async def test_healthy_qa_null_strict_procedure_reaches_all_mandatory_proofs(
    monkeypatch,
):
    found, candidates, calls = await procedure(monkeypatch)
    assert len(found) == 1, candidates
    assert found[0].value.endswith("Do not reopen the register.")
    assert found[0].null_margin is None
    assert len(calls) >= 5
    assert any(row["decision"] == "qa_no_answer" for row in candidates)
    assert [
        row["qa_observation"]["span"] for row in candidates if "qa_observation" in row
    ] == [None]
    assert (
        found[0].completeness["raw_seed"]["text"]
        == "Verify the approval before starting the Larch transfer."
    )


async def test_qa_only_null_retains_refusal_without_support(monkeypatch):
    found, candidates, calls = await procedure(monkeypatch, profile="qa_only_v1")
    assert not found and not calls
    assert any(row["decision"] == "qa_no_answer" for row in candidates)


async def test_pattern_without_every_mandatory_support_refuses(monkeypatch):
    found, candidates, calls = await procedure(monkeypatch, reject=True)
    assert not found
    assert calls
    assert any(
        row["decision"] == "procedure_mandatory_support_rejected" for row in candidates
    )


# Defect: role facts are currently gated entirely on an accepted reader candidate.
async def test_healthy_qa_null_literal_lead_keeps_actual_null_observation(monkeypatch):
    member = chunk("The records clerk leads Larch review.")
    calls = doubles(monkeypatch, member)
    candidates = []
    found = await requirement_answers._find_witnesses(
        plan_requirements("Who leads Larch review?")[0], [member], config(), candidates
    )
    assert [item.value for item in found] == ["The records clerk"]
    assert found[0].null_margin is None
    assert calls
    assert any(row["decision"] == "qa_no_answer" for row in candidates)


async def test_reader_failure_remains_error_before_pattern_discovery(monkeypatch):
    member = chunk("The records clerk leads Larch review.")
    doubles(monkeypatch, member, reader_error=True)
    with pytest.raises(RuntimeError, match="configured reader unavailable"):
        await requirement_answers._find_witnesses(
            plan_requirements("Who leads Larch review?")[0], [member], config(), []
        )


async def test_qa_pattern_same_literal_share_proof_retain_both_origins(monkeypatch):
    from app.models.query import AnswerSpan

    member = chunk("The records clerk leads Larch review.")
    calls = doubles(monkeypatch, member)

    async def reader(question, contexts, config=None):
        return [
            ReaderSelection(
                AnswerSpan(start=0, end=len(text), text=text),
                {
                    "decision": "answer",
                    "raw_candidates": [
                        {
                            "start": 0,
                            "end": 17,
                            "text": "The records clerk",
                            "null_margin": -9.0,
                        }
                    ],
                },
            )
            for text in contexts
        ]

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", reader)
    found = await requirement_answers._find_witnesses(
        plan_requirements("Who leads Larch review?")[0], [member], config(), []
    )
    assert len(found) == 1
    assert len(calls) == 1
    assert {item["origin"] for item in found[0].proposals} == {
        "qa_reader",
        "source_pattern",
    }


async def test_incomplete_support_cardinality_stays_runtime_error(monkeypatch):
    member = chunk("The records clerk leads Larch review.")
    doubles(monkeypatch, member)

    async def incomplete(pairs, config=None):
        return []

    monkeypatch.setattr(requirement_answers.support_service, "assess", incomplete)
    with pytest.raises(RuntimeError, match="incomplete decisions"):
        await requirement_answers._find_witnesses(
            plan_requirements("Who leads Larch review?")[0], [member], config(), []
        )


async def test_distinct_supported_literal_assignments_cannot_hide_behind_sort(
    monkeypatch,
):
    member = chunk(
        "The records clerk leads Larch review. The desk steward leads Larch review."
    )
    doubles(monkeypatch, member)
    result = await requirement_answers.select_requirement_answer(
        None,
        QueryRequest(question="Who leads Larch review?"),
        {},
        [member],
        config(),
        validate_current=current,
    )
    assert result.reason is not None
    assert not result.chunks and not result.passages
    assert len(result.requirements[0]["witnesses"]) == 2


async def test_narrative_pattern_keeps_whole_typed_method(monkeypatch):
    text = (
        "Larch seal review: inspect the seal, record the result, and close the review. "
        "Never reopen the review."
    )
    question = "What are the steps for Larch seal review?"
    member = chunk(text)
    calls = doubles(monkeypatch, member)
    candidates = []
    found = await requirement_answers._find_procedure_witnesses(
        None,
        QueryRequest(question=question),
        {},
        plan_requirements(question)[0],
        config(),
        candidates,
        {member.id: member},
        [],
        current,
    )
    assert len(found) == 1, candidates
    assert found[0].value == text
    assert found[0].completeness["structure"] == "narrative"
    assert calls


async def test_full_seed_must_fit_one_real_cited_origin(monkeypatch):
    first = BODY.index("approval")
    left = chunk(BODY[:first])
    right = chunk(BODY[first:], document=left.document_id)
    digest = hashlib.sha256(BODY.encode()).hexdigest()
    for item in (left, right):
        item.metadata["content_hash"] = digest
    right.chunk_index = 1
    calls = doubles(monkeypatch, left)
    source = ProcedureSource(
        BODY,
        (LocatedChunk(left, 0, first), LocatedChunk(right, first, len(BODY))),
        {
            "document_id": str(left.document_id),
            "document_version": 1,
            "content_hash": digest,
        },
        {},
        None,
    )

    async def resolve(*args):
        return source

    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    candidates = []
    found = await requirement_answers._find_procedure_witnesses(
        None,
        QueryRequest(question=QUESTION),
        {},
        plan_requirements(QUESTION)[0],
        config(),
        candidates,
        {left.id: left, right.id: right},
        [],
        current,
    )
    assert not found and not calls
    assert any(
        row["decision"] == "procedure_pattern_seed_unrepresentable"
        for row in candidates
    )


async def test_source_change_after_mandatory_proofs_refuses(monkeypatch):
    member = chunk(BODY)
    calls = doubles(monkeypatch, member)

    async def stale(member):
        return False

    found = await requirement_answers._find_procedure_witnesses(
        None,
        QueryRequest(question=QUESTION),
        {},
        plan_requirements(QUESTION)[0],
        config(),
        [],
        {member.id: member},
        [],
        stale,
    )
    assert calls and not found


async def test_selected_internal_lineage_maps_to_captured_source(monkeypatch):
    from dataclasses import asdict

    from app.services.requirement_contract import validate_discovery_lineage

    member = chunk("The records clerk leads Larch review.")
    doubles(monkeypatch, member)
    result = await requirement_answers.select_requirement_answer(
        None,
        QueryRequest(question="Who leads Larch review?"),
        {},
        [member],
        config(),
        validate_current=current,
    )
    assert result.reason is None
    assert validate_discovery_lineage(asdict(result))["valid"] is True


async def test_pattern_method_keeps_full_real_multichunk_cover(monkeypatch):
    split = BODY.index("2.")
    left = chunk(BODY[: split + 10])
    right = chunk(BODY[split:], document=left.document_id)
    digest = hashlib.sha256(BODY.encode()).hexdigest()
    for member in (left, right):
        member.metadata["content_hash"] = digest
    right.chunk_index = 1
    calls = doubles(monkeypatch, left)
    source = ProcedureSource(
        BODY,
        (LocatedChunk(left, 0, split + 10), LocatedChunk(right, split, len(BODY))),
        {
            "document_id": str(left.document_id),
            "document_version": 1,
            "content_hash": digest,
        },
        {},
        None,
    )

    async def resolve(*args):
        return source

    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    candidates = []
    found = await requirement_answers._find_procedure_witnesses(
        None,
        QueryRequest(question=QUESTION),
        {},
        plan_requirements(QUESTION)[0],
        config(),
        candidates,
        {left.id: left, right.id: right},
        [],
        current,
    )
    assert len(found) == 1, candidates
    assert calls and len(found[0].fragments) == 2
    assert found[0].chunk.id == left.id
    assert "".join(span.text for _, span in found[0].fragments) == found[0].value
