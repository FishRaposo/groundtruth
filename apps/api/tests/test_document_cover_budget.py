"""The evidence budget counts documents, while retaining every required chunk."""

import uuid
from dataclasses import replace

from app.services.requirement_answers import _cover

from tests.test_requirement_cover_boundaries import chunk, requirement, witness


def test_more_than_eight_required_chunks_in_one_document_fit_document_budget():
    entries = []
    for index in range(10):
        req = requirement(f"r{index}", f"fact {index}")
        source = chunk(f"fact {index}", index + 1)
        source.document_id = uuid.UUID(int=999)
        entries.append(witness(req, source, f"fact {index}", f"fact {index}"))
    selected = _cover(entries, [f"r{i}" for i in range(10)])
    assert {w.requirement for w in selected} == {f"r{i}" for i in range(10)}
    assert len({w.chunk.document_id for w in selected}) == 1


def test_nine_required_documents_still_exceed_the_budget():
    entries = []
    for index in range(9):
        req = requirement(f"r{index}", f"fact {index}")
        source = chunk(f"fact {index}", index + 1)
        entries.append(witness(req, source, f"fact {index}", f"fact {index}"))
    assert _cover(entries, [f"r{i}" for i in range(9)]) == []


def test_document_cover_prefers_one_document_over_two_single_chunk_sources():
    first, second = requirement("r1", "one"), requirement("r2", "two")
    shared1, shared2 = chunk("one", 1), chunk("two", 2)
    shared2.document_id = shared1.document_id
    a, b = witness(first, shared1, "one", "one"), witness(second, shared2, "two", "two")
    other1, other2 = chunk("one", 3), chunk("two", 4)
    entries = [replace(a, chunk=other1), replace(b, chunk=other2), a, b]
    selected = _cover(entries, ["r1", "r2"])
    assert {w.chunk.document_id for w in selected} == {shared1.document_id}
