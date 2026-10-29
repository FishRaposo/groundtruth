"""Boundary probes only: no corpus, actual model, HTTP port or application edits."""

import uuid
from types import SimpleNamespace

from app.config import Settings
from app.evidence_policy import EvidencePolicy
from app.models.query import QueryRequest
from app.services import connected_query as connected
from app.services import requirement_answers as subject
from app.services.answer_reader import ReaderSelection
from app.services.answer_requirements import Requirement
from app.services.answer_support import SupportAssessment

from tests.test_requirement_cover_boundaries import chunk, requirement, valid, witness


async def test_01_document_cover_is_not_truncated_by_actual_answer_renderer(
    monkeypatch,
):
    r1, r2 = (
        requirement("r1", "Who leads Quartz review?"),
        requirement("r2", "How long does it last?"),
    )
    chunks = [
        chunk(f"Alice leads Quartz review candidate {i}.", i + 1) for i in range(8)
    ]
    chunks.append(chunk("Quartz review lasts 19 minutes.", 9))
    for c in chunks:
        c.document_id = uuid.UUID(int=999)
    entries = [witness(r1, c, "Alice", "Alice leads Quartz review") for c in chunks[:8]]
    entries.append(
        witness(r2, chunks[-1], "19 minutes", "Quartz review lasts 19 minutes")
    )
    selected = subject._cover(entries, ["r1", "r2"])
    assert len(selected) == 9 and len({w.chunk.document_id for w in selected}) == 1
    spans = {w.chunk.id: w.span for w in selected}
    answer = subject.RequirementAnswer(
        tuple(chunks),
        spans,
        [],
        [],
        [],
        [],
        [],
        None,
        {k: (s,) for k, s in spans.items()},
        evidence_profile=EvidencePolicy("qa_only_v1", "literal_v1").record(),
    )

    async def retrieve(*args, **kwargs):
        return SimpleNamespace(
            chunks=chunks,
            vector_count=0,
            keyword_count=9,
            elapsed_ms=0,
            method="keyword",
            provenance={"embedding": {"dimension": 32}},
        )

    async def memory(*args, **kwargs):
        return []

    async def status(*args, **kwargs):
        return "current"

    async def select(*args, **kwargs):
        return answer

    async def assess(*args, **kwargs):
        return []

    class DB:
        async def get(self, *args, **kwargs):
            return SimpleNamespace()

    config = Settings().model_copy(
        update={
            "ANSWER_SELECTION_MODE": "reader",
            "ANSWER_SUPPORT_MODE": "local_nli",
            "GENERATION_MODE": "extractive",
            "EMBEDDING_MODE": "deterministic",
        }
    )
    monkeypatch.setattr(connected, "settings", config)
    monkeypatch.setattr(connected, "retrieve_scoped", retrieve)
    monkeypatch.setattr(connected, "scoped_memory", memory)
    monkeypatch.setattr(connected, "citation_status", status)
    monkeypatch.setattr(subject, "select_requirement_answer", select)
    monkeypatch.setattr(subject.support_service, "assess", assess)
    monkeypatch.setattr(subject.reader_service, "select_atomic", assess)
    monkeypatch.setattr(
        subject.reader_service,
        "metadata",
        lambda *args, **kwargs: {"contract": "double"},
    )
    monkeypatch.setattr(
        subject.support_service, "metadata", lambda *args, **kwargs: {"mode": "double"}
    )
    row = SimpleNamespace(id=uuid.UUID(int=500), answer=None)
    request = QueryRequest(
        question="Who leads Quartz review, and how long does it last?",
        retrieval_method="keyword",
    )
    await connected.prepare_answer(DB(), row, request, {"id": "u", "workspace_id": "w"})
    assert not row.refused
    assert "19 minutes" in row.answer, row.answer
    assert len(row.sources) == 9


async def test_02_typed_edge_cannot_replace_its_missing_mandatory_support_checks(
    monkeypatch,
):
    text = (
        "Quartz worksheet convention. Ordinary worksheets apply here. "
        "Step 1 read a card."
    )
    req = Requirement(
        "r1",
        "Give Quartz worksheet procedure",
        0,
        30,
        "What is first step for Quartz worksheet?",
        "procedure",
        "Quartz worksheet",
        ("quartz",),
    )
    value = "read a card"
    start = text.index(value)
    edge = SimpleNamespace(
        name="worksheet_namespace_to_applicability",
        source_start=0,
        source_end=26,
        target_start=28,
        target_end=57,
        requirement_id="r1",
        depends_on=(),
    )
    claim = SimpleNamespace(
        start=start,
        end=start + len(value),
        value=value,
        rejection=None,
        hypothesis="A card is read.",
        premise=text,
        premise_start=0,
        premise_end=len(text),
        support_start=start,
        support_end=start + len(value),
        checks=(),
        proof_edges=(edge,),
    )

    async def predict(*args, **kwargs):
        return [
            ReaderSelection(
                None,
                {
                    "raw_candidates": [
                        {"start": start, "end": start + len(value), "null_margin": -9}
                    ]
                },
            )
        ]

    async def entail(pairs, config=None):
        assert len(pairs) == 1  # Only the primary, no namespace/applicability decision.
        return [SupportAssessment("entailment", (-5, 5, -5), 10, True)]

    monkeypatch.setattr(subject, "support_claim", lambda *args: claim)
    monkeypatch.setattr(subject.reader_service, "select_atomic", predict)
    monkeypatch.setattr(subject.support_service, "assess", entail)
    assert not await subject._find_witnesses(req, [chunk(text, 10)], Settings(), [])


async def test_03_role_scope_cannot_come_from_a_separate_object_sentence(
    monkeypatch,
):
    req = subject.plan_requirements("Who leads Quartz review?")[0]
    selected = chunk("Alice leads Quartz review.", 20)
    opponents = [
        chunk(
            f"Quartz review stores the archive. {name} leads Willow review.",
            21 + i,
            "foreign",
        )
        for i, name in enumerate(("Bob", "Carol"))
    ]

    async def found(*args, **kwargs):
        return [witness(req, selected, "Alice", "Alice leads Quartz review.")]

    async def inspect(*args, **kwargs):
        return opponents, False

    async def contradict(pairs, config=None):
        return [
            SupportAssessment("contradiction", (5, -5, -5), -10, False) for _ in pairs
        ]

    monkeypatch.setattr(subject, "_find_witnesses", found)
    monkeypatch.setattr(subject, "inspect_curated_group", inspect)
    monkeypatch.setattr(subject.support_service, "assess", contradict)
    result = await subject.select_requirement_answer(
        None,
        QueryRequest(question=req.question),
        None,
        [selected, *opponents],
        Settings(),
        validate_current=valid,
    )
    assert result.reason is None, result.conflicts


def test_04_foreign_dependency_and_wrong_edge_type_remain_rejected():
    text = "Quartz convention. Ordinary procedure."
    req = Requirement(
        "r1", "Procedure", 0, 9, "Procedure?", "procedure", "Quartz", ("quartz",)
    )
    edge = SimpleNamespace(
        name="scoped_deputy_to_permission",
        source_start=0,
        source_end=17,
        target_start=19,
        target_end=len(text),
        requirement_id="r1",
        depends_on=(),
    )
    claim = SimpleNamespace(premise=text, checks=(), proof_edges=(edge,))
    assert (
        subject._claim_edges_error(claim, req, text)
        == "proof_edge_not_bound_to_requirement"
    )
    edge.name = "worksheet_namespace_to_applicability"
    edge.depends_on = ("foreign",)
    assert (
        subject._claim_edges_error(claim, req, text)
        == "proof_edge_not_bound_to_requirement"
    )


async def test_05_inspected_non_cited_identity_still_requires_current_access():
    first, second = uuid.UUID(int=100), uuid.UUID(int=101)
    row = SimpleNamespace(
        sources=[],
        retrieval_trace={"scores": []},
        provenance={
            "answer_selection": {
                "contract": "requirement-evidence-v1",
                "inspected_sources": [
                    {"document_id": str(first), "chunk_id": str(uuid.UUID(int=102))},
                    {"document_id": str(second), "chunk_id": str(uuid.UUID(int=103))},
                ],
                "candidates": [],
            }
        },
    )

    class DB:
        async def scalars(self, statement):
            return SimpleNamespace(all=lambda: [first])

    assert not await connected.source_access(
        DB(), row, {"id": "u", "workspace_id": "w"}
    )


async def test_06_known_group_does_not_make_explicit_foreign_subject_an_opponent(
    monkeypatch,
):
    req = subject.plan_requirements("Who leads Quartz review?")[0]
    selected = chunk("Alice leads Quartz review.", 30, "shared")
    foreign = chunk("Bob leads Willow review.", 31, "shared")

    async def found(*args, **kwargs):
        return [witness(req, selected, "Alice", "Alice leads Quartz review.")]

    async def inspect(*args, **kwargs):
        return [selected, foreign], False

    async def sound_decisions(pairs, config=None):
        return [
            SupportAssessment("entailment", (-5, 5, -5), 10, True)
            if pair.premise == selected.content
            else SupportAssessment("neutral", (-5, -5, 5), -10, False)
            for pair in pairs
        ]

    monkeypatch.setattr(subject, "_find_witnesses", found)
    monkeypatch.setattr(subject, "inspect_curated_group", inspect)
    monkeypatch.setattr(subject.support_service, "assess", sound_decisions)
    result = await subject.select_requirement_answer(
        None,
        QueryRequest(question=req.question),
        None,
        [selected, foreign],
        Settings(),
        validate_current=valid,
    )
    assert result.reason is None, result.conflicts
