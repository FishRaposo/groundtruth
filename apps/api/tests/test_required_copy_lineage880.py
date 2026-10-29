"""Recorded v3 lineage only; independent source/NLI replay stays mandatory."""

import copy

from app.services import requirement_contract as contract

from tests.test_required_copy_runtime880 import run

pytest_plugins = ["tests.test_connected_contract"]


async def test_required_copy_recorded_fragments_match_each_original_document(
    connected_db, monkeypatch
):
    found, _, ctx, _ = await run(connected_db, monkeypatch)
    witness = found[0]
    proof = witness.completeness
    known = {}
    contexts = []
    for doc in proof["required_copy"]["documents"]:
        sources = []
        for part in doc["fragments"]:
            row = {
                **doc["identity"],
                "chunk_id": part["chunk_id"],
                "document_range": {
                    "start": part["document_start"] - part["chunk_start"],
                    "end": part["document_end"],
                },
            }
            sources.append(row)
            known[part["chunk_id"]] = row
        contexts.append({**doc["identity"], "sources": sources})
    assert contract._procedure_fragments_lineage(proof, known, contexts)
    part = proof["fragments"][0]
    row = {
        **proof["required_copy"]["root_identity"],
        "chunk_id": part["chunk_id"],
        "value": witness.value,
        "span": witness.span.model_dump(),
        "document_range": {
            "start": part["document_start"],
            "end": part["document_end"],
        },
    }
    assert contract._procedure_witness_mapping(row, proof)
    changed = copy.deepcopy(proof)
    changed["required_copy"]["documents"][1]["body"] += " Changed"
    assert not contract._procedure_fragments_lineage(changed, known, contexts)
    assert not contract._procedure_witness_mapping(
        {**row, "value": proof["source_body"]}, proof
    )
