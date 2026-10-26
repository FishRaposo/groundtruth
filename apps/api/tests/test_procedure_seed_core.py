"""Independent first-clause core must discharge the original accepted QA literal."""

from copy import deepcopy

import pytest
from app.services.requirement_contract import complete_procedure

from tests.test_procedure_extent import (
    LONG,
    external_boundaries,
    seed_procedure,
    select,
)
from tests.test_procedure_step_context import FIRST

pytest_plugins = ["tests.test_connected_contract", "tests.test_procedure_http"]


async def result_for(db, monkeypatch, body=LONG, raw=FIRST):
    document, chunks = await seed_procedure(
        db, body, [body[:1292], body[1171:]] if len(body) > 1292 else [body]
    )
    return await select(db, chunks[:1], document, monkeypatch, raw_text=raw)


def first_unit(proof):
    return next(u for u in proof["proof_units"] if u["name"] == "step_1_action_1")


def set_raw_range(proof, first, last):
    origin = next(
        p for p in proof["fragments"] if p["chunk_id"] == proof["raw_seed"]["chunk_id"]
    )
    delta = origin["document_start"] - origin["chunk_start"]
    proof["raw_seed"]["document_range"] = {"start": first, "end": last}
    proof["raw_seed"]["chunk_range"] = {"start": first - delta, "end": last - delta}


def rename_first_unit(proof, inventory):
    for units in (proof["proof_units"], inventory["units"]):
        next(u for u in units if u["name"] == "step_1_action_1")["name"] = (
            "other_action"
        )
    for edges in (proof["structure_edges"], inventory["structure_edges"]):
        next(e for e in edges if e.get("target") == "step_1_action_1")["target"] = (
            "other_action"
        )


@pytest.mark.parametrize("raw", ["Verify", "the signed supervisor approval"])
@pytest.mark.parametrize("update_text", [False, True])
async def test_partial_raw_cannot_discharge_independent_full_clause_core(
    connected_db, monkeypatch, raw, update_text
):
    # Previously changing only these two ranges still certified the subcontract.
    db, _ = connected_db
    result = await result_for(db, monkeypatch)
    original = result.requirements[0]["procedure_completeness"]
    assert complete_procedure(original)
    proof = deepcopy(original)
    start = LONG.index(raw, first_unit(proof)["source_range"]["start"])
    set_raw_range(proof, start, start + len(raw))
    if update_text:
        proof["raw_seed"]["text"] = raw
    assert not complete_procedure(proof)


@pytest.mark.parametrize("padding", ["leading", "trailing", "both", "unicode"])
async def test_full_source_whitespace_envelope_preserves_original_raw(
    connected_db, monkeypatch, padding
):
    # Source-trimmed clause coordinates must not discard actual eligible QA space.
    db, _ = connected_db
    body = LONG
    if padding == "unicode":
        body = body.replace("1. " + FIRST, "1. \t\u2003" + FIRST + "\u2003\t")
        raw = "\t\u2003" + FIRST + "\u2003\t"
    else:
        raw = (
            (" " if padding in {"leading", "both"} else "")
            + FIRST
            + (" " if padding in {"trailing", "both"} else "")
        )
    result = await result_for(db, monkeypatch, body, raw)
    assert result.reason is None, result.requirements
    proof = result.requirements[0]["procedure_completeness"]
    seed = proof["raw_seed"]
    origin = seed["document_range"]
    assert seed.get("text") == raw == body[origin["start"] : origin["end"]]
    assert origin == {"start": body.index(raw), "end": body.index(raw) + len(raw)}
    clause = proof["required_inventory"].get("seed_clause")
    unit = first_unit(proof)
    assert clause == {
        "unit_name": unit["name"],
        "source_range": unit["source_range"],
        "text": FIRST,
    }
    assert complete_procedure(proof)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_core",
        "wrong_unit",
        "shifted_clause",
        "short_clause_text",
        "altered_clause_text",
        "missing_raw_text",
        "wrong_raw_text",
        "wrong_raw_length",
        "missing_first_unit",
    ],
)
async def test_seed_core_metadata_is_required_and_independent(
    connected_db, monkeypatch, mutation
):
    db, _ = connected_db
    result = await result_for(db, monkeypatch)
    proof = deepcopy(result.requirements[0]["procedure_completeness"])
    inventory = proof["required_inventory"]
    clause = deepcopy(
        inventory.get("seed_clause")
        or {
            "unit_name": "step_1_action_1",
            "source_range": first_unit(proof)["source_range"],
            "text": FIRST,
        }
    )
    inventory["seed_clause"] = clause
    if mutation == "missing_core":
        inventory.pop("seed_clause")
    elif mutation == "wrong_unit":
        clause["unit_name"] = "step_2_action_1"
    elif mutation == "shifted_clause":
        clause["source_range"] = {"start": 0, "end": len(FIRST)}
    elif mutation == "short_clause_text":
        clause["text"] = FIRST[:-1]
    elif mutation == "altered_clause_text":
        clause["text"] = FIRST.replace("Harbor", "Ravens")
    elif mutation == "missing_raw_text":
        proof["raw_seed"].pop("text", None)
    elif mutation == "wrong_raw_text":
        proof["raw_seed"]["text"] = FIRST.replace("Harbor", "Ravens")
    elif mutation == "missing_first_unit":
        rename_first_unit(proof, inventory)
    else:
        proof["raw_seed"]["text"] = FIRST + " "
    assert not complete_procedure(proof)


@pytest.mark.parametrize("terminal", [".", "!", "?"])
async def test_only_actual_terminal_punctuation_may_be_omitted(
    connected_db, monkeypatch, terminal
):
    db, _ = connected_db
    body = LONG.replace(FIRST, FIRST[:-1] + terminal)
    result = await result_for(db, monkeypatch, body, FIRST[:-1])
    assert result.reason is None
    proof = result.requirements[0]["procedure_completeness"]
    assert (
        proof["required_inventory"].get("seed_clause", {}).get("text")
        == FIRST[:-1] + terminal
    )
    assert proof["raw_seed"].get("text") == FIRST[:-1]
    assert complete_procedure(proof)


async def test_nonpunctuation_final_character_cannot_be_dropped_from_record(
    connected_db, monkeypatch
):
    db, _ = connected_db
    # Record-only no-punctuation clause fixture: the existing source binder may
    # independently refuse an unterminated procedure body, which is unchanged.
    result = await result_for(db, monkeypatch)
    proof = deepcopy(result.requirements[0]["procedure_completeness"])
    source = dict(first_unit(proof)["source_range"])
    source["end"] -= 1
    for units in (proof["proof_units"], proof["required_inventory"]["units"]):
        next(u for u in units if u["name"] == "step_1_action_1")["source_range"] = (
            source
        )
    proof["required_inventory"]["seed_clause"] = {
        "unit_name": "step_1_action_1",
        "source_range": source,
        "text": FIRST[:-1],
    }
    set_raw_range(proof, source["start"], source["end"])
    proof["raw_seed"]["text"] = FIRST[:-1]
    assert complete_procedure(proof)
    raw = proof["raw_seed"]["document_range"]
    set_raw_range(proof, raw["start"], raw["end"] - 1)
    proof["raw_seed"]["text"] = FIRST[:-2]
    assert not complete_procedure(proof)


@pytest.mark.parametrize("raw", ["1. " + FIRST, FIRST + " Check", FIRST[:-2]])
async def test_whitespace_allowance_never_absorbs_marker_or_other_action(
    connected_db, monkeypatch, raw
):
    db, _ = connected_db
    result = await result_for(db, monkeypatch, raw=raw)
    assert result.reason is not None and not result.chunks


async def test_original_padded_raw_survives_normal_sse_history_and_source(
    procedure_client, monkeypatch
):
    import json

    from tests.test_procedure_http import request

    client, db = procedure_client
    document, _ = await seed_procedure(db)
    raw = " " + FIRST + " "
    external_boundaries(monkeypatch, raw_text=raw)
    normal = (await client.post("/api/queries", json=request(document))).json()
    assert normal["outcome"] == "completed", normal
    proof = normal["provenance"]["answer_selection"]["requirements"][0][
        "procedure_completeness"
    ]
    assert proof["raw_seed"]["text"] == raw
    assert complete_procedure(proof)
    cited = await client.get(f"/api/queries/{normal['id']}/sources/1")
    local = proof["raw_seed"]["chunk_range"]
    assert cited.json()["quoted_text"][local["start"] : local["end"]] == raw
    saved = (await client.get(f"/api/queries/{normal['id']}")).json()
    assert saved["answer"] == normal["answer"]
    assert (
        saved["provenance"]["answer_selection"]["requirements"][0][
            "procedure_completeness"
        ]
        == proof
    )
    streamed = await client.post("/api/queries/stream", json=request(document))
    output = [
        json.loads(line[6:])
        for line in streamed.text.splitlines()
        if line.startswith("data: ")
    ]
    assert output[-1]["type"] == "done" and output[-1]["answer"] == normal["answer"]
    assert (
        output[-1]["provenance"]["answer_selection"]["requirements"][0][
            "procedure_completeness"
        ]["raw_seed"]["text"]
        == raw
    )
