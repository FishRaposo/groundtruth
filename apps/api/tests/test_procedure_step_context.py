"""Literal same-step context cannot replace clause inventory or seed authority."""

from copy import deepcopy

import pytest
from app.config import Settings
from app.models.query import QueryRequest
from app.services.answer_reader import ReaderSelection, passage_span, reader_service
from app.services.answer_support import SupportInputBudgetExceeded, support_service
from app.services.requirement_answers import select_requirement_answer
from app.services.requirement_contract import complete_procedure

from tests.test_procedure_extent import (
    CONTROL,
    LONG,
    PRINCIPAL,
    QUESTION,
    external_boundaries,
    seed_procedure,
)

pytest_plugins = ["tests.test_connected_contract"]
FIRST = (
    "Verify the signed supervisor approval before starting the Harbor docket transfer."
)


async def prepared(
    db, monkeypatch, *, body=LONG, raw=FIRST, qa_null=False, candidates=None
):
    document, chunks = await seed_procedure(
        db, body, [body[:1292], body[1171:]] if len(body) > 1292 else [body]
    )
    calls = external_boundaries(monkeypatch)

    async def reader(question, contexts, config=None):
        selections = []
        for context in contexts:
            proposals = []
            for text in candidates or [raw]:
                start = context.find(
                    text, context.find("1. ") + (0 if text == "1." else 3)
                )
                if start >= 0:
                    proposals.append(
                        {
                            "start": start,
                            "end": start + len(text),
                            "text": text,
                            "null_margin": -9.0,
                        }
                    )
            proposal = proposals[0] if proposals else None
            selections.append(
                ReaderSelection(
                    passage_span(context, proposal["start"], proposal["end"])
                    if proposal and not qa_null
                    else None,
                    {"decision": "answer", "raw_candidates": proposals},
                )
            )
        return selections

    monkeypatch.setattr(reader_service, "select_atomic", reader)

    async def current(chunk):
        return True

    result = await select_requirement_answer(
        db,
        QueryRequest(
            question=QUESTION, document_ids=[document.id], retrieval_method="keyword"
        ),
        PRINCIPAL,
        chunks[:1],
        Settings(
            ANSWER_SELECTION_MODE="reader",
            ANSWER_SUPPORT_MODE="local_nli",
            GENERATION_MODE="extractive",
            READER_NULL_THRESHOLD=8,
        ),
        validate_current=current,
    )
    return result, calls


async def test_every_clause_uses_only_its_complete_literal_numbered_step(
    connected_db, monkeypatch
):
    # A clause-only premise loses mandatory original ordinal/adjacent context.
    db, _ = connected_db
    result, calls = await prepared(db, monkeypatch)
    assert result.reason is None, result.requirements
    proof = result.requirements[0]["procedure_completeness"]
    inventory = proof["required_inventory"]
    by_name = {pair.reference_id.split(":", 1)[1]: pair for pair in calls}
    assert len(by_name) == len(proof["proof_units"]) == len(calls)
    for required, assessed in zip(
        inventory["units"], proof["proof_units"], strict=True
    ):
        source = required["source_range"]
        step = required["step"]
        expected = proof["step_ranges"][step - 1] if step else source
        interval = {"start": expected["start"], "end": expected["end"]}
        assert (
            required.get("premise_range") == assessed.get("premise_range") == interval
        )
        pair = by_name[required["name"]]
        assert pair.premise == LONG[interval["start"] : interval["end"]]
        assert pair.hypothesis == required["hypothesis"] == assessed["hypothesis"]
        if step:
            assert pair.premise.startswith(f"{step}. ")
            assert (
                source["start"] >= interval["start"]
                and source["end"] <= interval["end"]
            )
            assert interval != source
    assert proof["step_count"] == 8
    assert result.requirements[0]["witnesses"][0]["value"] == LONG[46:]
    assert len(result.chunks) == 2 and complete_procedure(proof)
    assert proof["contract"] == "complete-immutable-procedure-v2"


@pytest.mark.parametrize(
    "raw",
    [
        "Harbor docket transfer",
        "the signed supervisor approval",
        "Verify",
        "1.",
        "Copy the docket identifier onto the transfer register.",
        FIRST
        + (
            " Check that the approval names the docket identifier and the current "
            "operating date, and place the approval beside the register."
        ),
    ],
)
async def test_incomplete_nonfirst_or_across_clause_seed_cannot_authorize_method(
    connected_db, monkeypatch, raw
):
    # Literal containment alone can approve an object-only QA span.
    db, _ = connected_db
    result, calls = await prepared(db, monkeypatch, raw=raw)
    assert result.reason is not None
    assert not result.passages and not result.chunks
    assert not calls, "Ineligible seeds must fail before support inference"


@pytest.mark.parametrize("raw", [FIRST, FIRST[:-1]])
async def test_full_first_clause_seed_allows_only_omitted_terminal_punctuation(
    connected_db, monkeypatch, raw
):
    db, _ = connected_db
    result, _ = await prepared(db, monkeypatch, raw=raw)
    assert result.reason is None, result.requirements
    proof = result.requirements[0]["procedure_completeness"]
    interval = proof["raw_seed"]["document_range"]
    assert LONG[interval["start"] : interval["end"]] == raw


async def test_later_existing_complete_clause_candidate_can_replace_noun_seed(
    connected_db, monkeypatch
):
    db, _ = connected_db
    result, _ = await prepared(
        db, monkeypatch, candidates=["the signed supervisor approval", FIRST]
    )
    assert result.reason is None
    raw = result.requirements[0]["procedure_completeness"]["raw_seed"]["document_range"]
    assert LONG[raw["start"] : raw["end"]] == FIRST


async def test_full_clause_proposal_cannot_override_qa_null(connected_db, monkeypatch):
    db, _ = connected_db
    result, calls = await prepared(db, monkeypatch, qa_null=True)
    assert result.reason is not None and not result.chunks and not calls


@pytest.mark.parametrize("negative", ["Do not copy", "Never copy", "Do  not COPY"])
async def test_exact_internal_opposition_refuses_even_when_all_model_pairs_entail(
    connected_db, monkeypatch, negative
):
    # An entailment-only classifier cannot choose a winner between opposed rules.
    db, _ = connected_db
    opposite = negative + " the docket identifier onto the transfer register."
    body = CONTROL.replace(
        "2. Copy the docket identifier onto the transfer register.",
        "2. Copy the docket identifier onto the transfer register. " + opposite,
    )
    result, calls = await prepared(db, monkeypatch, body=body)
    assert result.reason is not None and not result.chunks
    rejected = next(
        c
        for c in result.candidates
        if c.get("decision") == "procedure_internal_opposition"
    )
    units = rejected.get("opposed_source_units")
    assert units and len(units) == 2
    assert {u["kind"] for u in units} == {"instruction", "prohibition"}
    assert {
        body[u["source_range"]["start"] : u["source_range"]["end"]] for u in units
    } == {
        "Copy the docket identifier onto the transfer register.",
        opposite,
    }
    assert not calls


@pytest.mark.parametrize(
    "opposite",
    [
        "Do not copy the docket identifier onto the supervisor register.",
        "Do not copy the docket identifier onto the transfer register before approval.",
        "Do not copy the supervisor identifier onto the transfer register.",
    ],
)
async def test_distinct_whole_predicates_do_not_claim_exact_opposition(
    connected_db, monkeypatch, opposite
):
    db, _ = connected_db
    body = CONTROL.replace(
        "2. Copy the docket identifier onto the transfer register.",
        "2. Copy the docket identifier onto the transfer register. " + opposite,
    )
    result, _ = await prepared(db, monkeypatch, body=body)
    assert not any(
        c.get("decision") == "procedure_internal_opposition" for c in result.candidates
    )


@pytest.mark.parametrize(
    "unsupported",
    [
        "The supervisor should copy the docket identifier onto the transfer register.",
        "You may copy the docket identifier onto the transfer register.",
        '"Copy the docket identifier onto the transfer register."',
        "For Raven intake: copy the docket identifier onto the transfer register.",
        "Do not use this procedure.",
    ],
)
async def test_context_cannot_revive_unsupported_governing_forms(
    connected_db, monkeypatch, unsupported
):
    db, _ = connected_db
    body = CONTROL.replace(
        "2. Copy the docket identifier onto the transfer register.", "2. " + unsupported
    )
    result, calls = await prepared(db, monkeypatch, body=body)
    assert result.reason is not None and not result.chunks and not calls


@pytest.mark.parametrize(
    "mutation", ["missing", "assessed_shift", "inventory_shift", "both_clause_only"]
)
async def test_premise_range_cannot_disappear_or_move_outside_associated_step(
    connected_db, monkeypatch, mutation
):
    # Matching old counts/source ranges must not bless a changed context premise.
    db, _ = connected_db
    result, _ = await prepared(db, monkeypatch)
    proof = deepcopy(result.requirements[0]["procedure_completeness"])
    required = next(
        u
        for u in proof["required_inventory"]["units"]
        if u["name"] == "step_4_action_2"
    )
    assessed = next(u for u in proof["proof_units"] if u["name"] == required["name"])
    if mutation == "missing":
        assessed.pop("premise_range", None)
    elif mutation == "assessed_shift":
        assessed["premise_range"] = {"start": 0, "end": len(LONG)}
    elif mutation == "inventory_shift":
        required["premise_range"] = {"start": 0, "end": len(LONG)}
    else:
        assessed["premise_range"] = required["source_range"]
        required["premise_range"] = required["source_range"]
    assert not complete_procedure(proof)


async def test_prior_procedure_subcontract_is_readable_but_not_certified(
    connected_db, monkeypatch
):
    db, _ = connected_db
    result, _ = await prepared(db, monkeypatch)
    proof = deepcopy(result.requirements[0]["procedure_completeness"])
    proof["contract"] = "complete-immutable-procedure-v1"
    assert not complete_procedure(proof)


async def test_overbudget_same_step_is_explicit_content_refusal(
    connected_db, monkeypatch
):
    # Full-step context may exceed the unchanged classifier budget; never clip it.
    db, _ = connected_db
    document, chunks = await seed_procedure(db)
    external_boundaries(monkeypatch, raw_text=FIRST)

    async def budget(pairs, config=None):
        if any(pair.premise.startswith("1. ") for pair in pairs):
            raise SupportInputBudgetExceeded("test input budget", (513,))
        from app.services.answer_support import SupportAssessment

        return [
            SupportAssessment("entailment", (-5.0, 5.0, -5.0), 10.0, True, 12)
            for _ in pairs
        ]

    monkeypatch.setattr(support_service, "assess", budget)

    async def current(chunk):
        return True

    result = await select_requirement_answer(
        db,
        QueryRequest(
            question=QUESTION, document_ids=[document.id], retrieval_method="keyword"
        ),
        PRINCIPAL,
        chunks[:1],
        Settings(
            ANSWER_SELECTION_MODE="reader",
            ANSWER_SUPPORT_MODE="local_nli",
            GENERATION_MODE="extractive",
            READER_NULL_THRESHOLD=8,
        ),
        validate_current=current,
    )
    assert result.reason is not None and not result.chunks
    assert result.requirements[0]["reason"] == "procedure_support_budget_exceeded"


def mutate_governance(proof, inventory, mutation):
    if mutation == "missing_governance":
        proof["proof_units"] = [
            u for u in proof["proof_units"] if u["name"] != "namespace"
        ]
        inventory["units"] = [u for u in inventory["units"] if u["name"] != "namespace"]
        proof["mandatory_proof_count"] -= 1
    elif mutation.startswith("untyped_"):
        name = {
            "untyped_namespace": "namespace",
            "untyped_applicability": "applicability",
            "untyped_request_scope": "requested_scope",
        }[mutation]
        for units in (proof["proof_units"], inventory["units"]):
            next(u for u in units if u["name"] == name)["kind"] = "bound_condition"
    else:
        for target in (proof, inventory):
            target["structure_edges"][0]["name"] = "unrelated_governance"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_structure",
        "unknown_structure",
        "step_gap",
        "missing_terminal_step_end",
        "missing_governance",
        "untyped_namespace",
        "untyped_applicability",
        "untyped_request_scope",
        "wrong_governing_edge",
        "raw_later_step",
        "raw_outside_origin",
        "assessed_wrong_step",
        "assessed_boolean_step",
    ],
)
async def test_p63_record_cannot_certify_missing_structure_or_shifted_authority(
    connected_db, monkeypatch, mutation
):
    # UI certification must not bless a malformed source-bound proof record.
    db, _ = connected_db
    result, _ = await prepared(db, monkeypatch)
    proof = deepcopy(result.requirements[0]["procedure_completeness"])
    inventory = proof["required_inventory"]
    if mutation in {"missing_structure", "unknown_structure"}:
        for target in (proof, inventory):
            if mutation == "missing_structure":
                target.pop("structure")
            else:
                target["structure"] = "unknown"
    elif mutation in {"step_gap", "missing_terminal_step_end"}:
        for target in (proof, inventory):
            if mutation == "step_gap":
                target["step_ranges"][1]["start"] += 1
            else:
                target["step_ranges"][-1]["end"] -= 1
    elif mutation in {
        "missing_governance",
        "untyped_namespace",
        "untyped_applicability",
        "untyped_request_scope",
        "wrong_governing_edge",
    }:
        mutate_governance(proof, inventory, mutation)
    elif mutation in {"raw_later_step", "raw_outside_origin"}:
        name = "step_2_action_1" if mutation == "raw_later_step" else "step_8_action_1"
        clause = next(u for u in proof["proof_units"] if u["name"] == name)[
            "source_range"
        ]
        origin = next(
            p
            for p in proof["fragments"]
            if p["chunk_id"] == proof["raw_seed"]["chunk_id"]
        )
        delta = origin["document_start"] - origin["chunk_start"]
        proof["raw_seed"]["document_range"] = clause
        proof["raw_seed"]["chunk_range"] = {
            "start": clause["start"] - delta,
            "end": clause["end"] - delta,
        }
    else:
        next(u for u in proof["proof_units"] if u["name"] == "step_1_action_1")[
            "step"
        ] = True if mutation == "assessed_boolean_step" else 2
    assert not complete_procedure(proof)
