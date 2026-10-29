"""The procedural seed names its real first carrier, never an inferred QA origin."""

from copy import deepcopy
from dataclasses import asdict

import pytest
from app.config import Settings
from app.models.query import QueryRequest
from app.services.requirement_answers import select_requirement_answer
from app.services.requirement_contract import validate_discovery_lineage

from tests.test_procedure_extent import (
    CONTROL,
    PRINCIPAL,
    QUESTION,
    external_boundaries,
    seed_procedure,
)

pytest_plugins = ["tests.test_connected_contract"]


async def chosen(connected_db, monkeypatch, qa_null=False, padded=False):
    db, _ = connected_db
    doc, chunks = await seed_procedure(db, CONTROL, [CONTROL])
    first = (
        "Verify the signed supervisor approval before starting the "
        "Harbor docket transfer."
    )
    external_boundaries(
        monkeypatch, qa_null=qa_null, raw_text=f" {first} " if padded else first
    )
    config = Settings(
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1",
    )

    async def current(chunk):
        return True

    result = await select_requirement_answer(
        db,
        QueryRequest(question=QUESTION, document_ids=[doc.id]),
        PRINCIPAL,
        chunks,
        config,
        validate_current=current,
    )
    assert result.reason is None, result.requirements
    return asdict(result)


@pytest.mark.parametrize(
    "qa_null,padded", [(False, False), (False, True), (True, False)]
)
async def test_raw_seed_retains_actual_original_carrier(
    connected_db, monkeypatch, qa_null, padded
):
    selection = await chosen(connected_db, monkeypatch, qa_null, padded)
    raw = selection["requirements"][0]["procedure_completeness"]["raw_seed"]
    assert raw.get("origin") == ("source_pattern" if qa_null else "qa_reader")
    assert raw.get("proposal_id")
    proposal = next(
        p for p in selection["proposals"] if p["proposal_id"] == raw["proposal_id"]
    )
    assert all(
        raw[key] == proposal[key]
        for key in ("origin", "chunk_id", "text", "chunk_range", "document_range")
    )
    assert validate_discovery_lineage(selection)["valid"] is True
    if not qa_null:
        assert {
            p["origin"]
            for p in selection["requirements"][0]["witnesses"][0]["proposals"]
        } == {"qa_reader", "source_pattern"}


@pytest.mark.parametrize("mutation", ["missing", "forged", "contradictory"])
async def test_new_profile_raw_seed_crosslink_is_required(
    connected_db, monkeypatch, mutation
):
    selection = await chosen(connected_db, monkeypatch)
    selection = deepcopy(selection)
    raw = selection["requirements"][0]["procedure_completeness"]["raw_seed"]
    if mutation == "missing":
        raw.pop("proposal_id", None)
    else:
        raw["proposal_id"] = (
            "invented"
            if mutation == "forged"
            else selection["proposals"][0]["proposal_id"]
        )
        raw["origin"] = "source_pattern"
    assert validate_discovery_lineage(selection)["valid"] is False
