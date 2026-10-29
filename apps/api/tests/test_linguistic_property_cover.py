"""UNITONLY models; actual immutable multi-chunk source and public reader gate."""

import hashlib

from app.services import requirement_answers
from app.services.answer_reader import ReaderSelection, passage_span
from app.services.answer_support import SupportAssessment
from app.services.linguistic_dependencies import resolve_linguistic_requirement
from app.services.procedure_evidence import LocatedChunk, ProcedureSource

from tests.test_composite_procedures import chunk
from tests.test_dependency_frames import planned
from tests.test_linguistic_runtime_dispatch import config


async def test_availability_cannot_publish_only_the_first_of_two_source_chunks(
    monkeypatch,
):
    plan = planned("e628-explicit-data-reference")
    requirement, _ = resolve_linguistic_requirement(
        plan.requirements[1], plan, {"r1": "The records steward"}
    )
    first = chunk("The records steward is available from 09:00 to 12:00.")
    second = chunk(
        "The records steward is also available from 13:00 to 17:00.",
        document=first.document_id,
    )
    body = first.content + " " + second.content
    for member in (first, second):
        member.metadata["content_hash"] = hashlib.sha256(body.encode()).hexdigest()
    source = ProcedureSource(
        body,
        (
            LocatedChunk(first, 0, len(first.content)),
            LocatedChunk(second, len(first.content) + 1, len(body)),
        ),
        {"document_id": str(first.document_id), **first.metadata},
        {},
        None,
    )

    async def qa(question, contexts, config=None):
        start = first.content.index("09:00")
        return [
            ReaderSelection(
                passage_span(first.content, start, start + 5),
                {
                    "raw_span": {"start": start, "end": start + 5, "text": "09:00"},
                    "null_margin": -3.0,
                },
            )
        ]

    async def nli(pairs, config=None):
        return [
            SupportAssessment("entailment", (0.0, 5.0, 0.0), 5.0, True, 32)
            for _ in pairs
        ]

    async def resolve(member):
        return source

    monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", qa)
    monkeypatch.setattr(requirement_answers.support_service, "assess", nli)
    candidates = []
    found = await requirement_answers._find_witnesses(
        requirement, [first], config(), candidates, resolve_source=resolve
    )
    assert not found or all(
        "13:00" in witness.value and "17:00" in witness.value for witness in found
    )
