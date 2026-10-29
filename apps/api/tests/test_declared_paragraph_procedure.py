"""Invented explicit paragraph declarations; controller NI doubles use token12."""

import hashlib
from copy import deepcopy

import pytest
from app.models.query import QueryRequest
from app.services import procedure_evidence, requirement_answers
from app.services.answer_requirements import plan_requirements
from app.services.procedure_evidence import LocatedChunk, ProcedureSource
from app.services.requirement_contract import complete_procedure
from app.services.source_pattern_proposals import collect_source_proposals

from tests.test_composite_procedures import chunk, config, current, doubles
from tests.test_procedure_http import procedure_client as procedure_client

pytest_plugins = ["tests.test_connected_contract"]

QUESTION = (
    "Give the entire ordinary procedure for the Lumen token bench, including "
    "prerequisites, parameters, prohibitions, and closure."
)
PARAGRAPHS = (
    "Before beginning an ordinary token run, obtain the signed card "
    "and check that the tray is open.",
    "Place one token in the tray, with the marked edge facing the label.",
    "Do not remove a marked token or close the tray before the count is recorded.",
    "Count both compartments, write both totals on the card, and close the tray.",
)


def body(paragraphs=PARAGRAPHS, *, count="four", ordinal="fourth"):
    return (
        "Lumen token bench: current operation note\n\n"
        "The activity owner is the records clerk.\n\nComplete ordinary procedure\n\n"
        f"The next {count} instruction paragraphs are the entire ordinary procedure, "
        "in the stated order. Its prerequisites, inspection, prohibited actions, "
        "and final reconciliation are part of completion. The procedure ends at "
        "the explicit End of ordinary procedure marker immediately after the "
        f"{ordinal} instruction paragraph. It applies to an ordinary unflagged run, "
        "not a postponed audit.\n\n"
        + "\n\n".join(paragraphs)
        + "\n\nEnd of ordinary procedure\n\nRecord governance commentary\n\n"
        f"The ordinary run is complete once the {count} preceding instruction "
        "paragraphs have been satisfied. The following commentary describes "
        "separate post-completion record governance, not an additional "
        "ordinary-run instruction or completion condition.\n\n"
        "After the final paragraph, the signed record is stored in the station folder. "
        "Storage does not grant a recorder authority to destroy it."
    )


def source_for(text, *, multichunk=False):
    left = chunk(text)
    if not multichunk:
        parts = (LocatedChunk(left, 0, len(text)),)
    else:
        split = text.index(PARAGRAPHS[2])
        right = chunk(text[split:], document=left.document_id)
        left.content = text[: split + 20]
        right.chunk_index = 1
        parts = (
            LocatedChunk(left, 0, split + 20),
            LocatedChunk(right, split, len(text)),
        )
        for part in parts:
            part.chunk.metadata["content_hash"] = hashlib.sha256(
                text.encode()
            ).hexdigest()
    return ProcedureSource(
        text,
        parts,
        {
            "document_id": str(left.document_id),
            "document_version": 1,
            "content_hash": hashlib.sha256(text.encode()).hexdigest(),
        },
        {},
        None,
    )


async def select(
    monkeypatch,
    text=None,
    *,
    multichunk=False,
    reject=False,
    stale=False,
    profile="qa_plus_source_patterns_v1",
):
    source = source_for(text or body(), multichunk=multichunk)
    member = source.chunks[0].chunk
    calls = doubles(monkeypatch, member, reject=reject)

    async def resolve(*args):
        return source

    async def validate(member):
        return not stale

    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    candidates = []
    found = await requirement_answers._find_procedure_witnesses(
        None,
        QueryRequest(question=QUESTION),
        {},
        plan_requirements(QUESTION)[0],
        config(profile),
        candidates,
        {member.id: member},
        [],
        validate,
    )
    return found, candidates, calls, source


# The source explicitly declares the paragraph count, order and end; neither
# discourse numbering nor a guessed chunk boundary is needed to discover it.
async def test_declared_paragraphs_keep_full_block_and_all_mandatory_proofs(
    monkeypatch,
):
    found, candidates, calls, source = await select(monkeypatch)
    assert len(found) == 1, candidates
    witness = found[0]
    assert witness.value == "\n\n".join(PARAGRAPHS)
    proof = witness.completeness
    assert proof["structure"] == "declared_paragraphs"
    assert proof["step_count"] is None and proof["step_ranges"] == []
    assert proof["raw_seed"]["text"] == PARAGRAPHS[0]
    assert proof["raw_seed"]["origin"] == "source_pattern"
    assert "declared-paragraph" in witness.proposals[0]["pattern_id"]
    inventory = proof["required_inventory"]
    descriptor = inventory["declared_paragraphs"]
    assert descriptor["contract"] == "declared-paragraph-procedure-v1"
    assert descriptor["declared_count"] == 4
    assert len(descriptor["paragraph_ranges"]) == 4
    for paragraph, interval in zip(
        PARAGRAPHS, descriptor["paragraph_ranges"], strict=True
    ):
        assert source.body[interval["start"] : interval["end"]] == paragraph
    assert complete_procedure(proof)
    assert len(calls) == len(inventory["units"])
    assert any(
        pair.premise == "\n\n".join(PARAGRAPHS)
        or "\n\n".join(PARAGRAPHS) in pair.premise
        for pair in calls
    )
    assert all(
        any(paragraph in pair.premise for pair in calls) for paragraph in PARAGRAPHS
    )
    assert [
        row["qa_observation"]["span"] for row in candidates if "qa_observation" in row
    ] == [None]


async def test_declared_paragraphs_use_real_first_seed_and_full_multichunk_cover(
    monkeypatch,
):
    found, candidates, _, _ = await select(monkeypatch, multichunk=True)
    assert len(found) == 1, candidates
    assert len(found[0].completeness["fragments"]) == 2
    assert "".join(span.text for _, span in found[0].fragments) == "\n\n".join(
        PARAGRAPHS
    )
    assert complete_procedure(found[0].completeness)


@pytest.mark.parametrize(
    "text",
    [
        body().replace("End of ordinary procedure\n\nRecord", "Record"),
        body().replace("next four instruction", "next five instruction"),
        body().replace("fourth instruction paragraph", "third instruction paragraph"),
        body().replace(
            PARAGRAPHS[2] + "\n\n",
            "",
        ),
        body().replace(
            "\n\nEnd of ordinary procedure",
            "\n\nClose the hatch.\n\nEnd of ordinary procedure",
        ),
        body().replace("Record governance commentary", "Unknown unfinished section"),
    ],
)
async def test_missing_count_closure_or_material_paragraph_never_truncates(
    monkeypatch, text
):
    found, _, calls, _ = await select(monkeypatch, text)
    assert not found and not calls


async def test_qa_only_null_and_rejected_nli_and_stale_source_remain_refusals(
    monkeypatch,
):
    found, _, calls, _ = await select(monkeypatch, profile="qa_only_v1")
    assert not found and not calls
    found, _, calls, _ = await select(monkeypatch, reject=True)
    assert not found and calls
    found, _, calls, _ = await select(monkeypatch, stale=True)
    assert not found and calls


async def test_independent_inventory_rejects_paragraph_or_proof_corruption(monkeypatch):
    found, candidates, _, _ = await select(monkeypatch)
    assert len(found) == 1, candidates
    original = found[0].completeness
    for damage in (
        "count",
        "range",
        "closure",
        "source_text",
        "required_unit",
        "assessed_unit",
        "raw_later",
    ):
        proof = deepcopy(original)
        descriptor = proof["required_inventory"]["declared_paragraphs"]
        if damage == "count":
            descriptor["declared_count"] = 3
        elif damage == "range":
            descriptor["paragraph_ranges"][0]["start"] += 1
        elif damage == "closure":
            descriptor["end_marker_range"]["start"] += 1
        elif damage == "source_text":
            descriptor["source_body"] += " hidden instruction"
        elif damage == "required_unit":
            proof["required_inventory"]["units"].pop()
        elif damage == "assessed_unit":
            proof["proof_units"].pop()
            proof["mandatory_proof_count"] -= 1
        else:
            proof["raw_seed"]["text"] = "token"
        assert not complete_procedure(proof), damage


def test_roster_caption_is_not_a_procedure_discovery_or_incomplete_batch():
    text = (
        "Lumen token bench: consultation roster and session notice\n\n"
        "This fictional roster concerns the ordinary station named in the heading.\n\n"
        "The records clerk is available on Monday. The session begins at 09:00."
    )
    batch = collect_source_proposals(plan_requirements(QUESTION)[0], [source_for(text)])
    assert batch.complete and not batch.proposals


def test_legacy_narrative_open_verbs_keep_existing_full_source_discovery():
    text = "Lumen token bench: fold the fabric, stitch the seam, and rinse the tray."
    batch = collect_source_proposals(plan_requirements(QUESTION)[0], [source_for(text)])
    assert batch.complete and len(batch.proposals) == 1
    assert batch.proposals[0].pattern_id == "complete-narrative-procedure-v1"


@pytest.mark.parametrize(
    "text",
    [
        body().replace(
            "Complete ordinary procedure",
            "Before beginning this run, obtain the separate permit.\n\n"
            "Complete ordinary procedure",
        ),
        body() + "\n\nClose the gate before completion.",
        body().replace(
            "an ordinary unflagged run, not a postponed audit",
            "a postponed audit, not an ordinary unflagged run",
        ),
    ],
)
async def test_omitted_governing_prelude_tail_or_reversed_applicability_refuses_pre_nli(
    monkeypatch, text
):
    found, _, calls, _ = await select(monkeypatch, text)
    assert not found and not calls


async def test_oversize_pairs_remain_content_refusal_and_runtime_failure_remains_error(
    monkeypatch,
):
    from app.services.answer_support import (
        SupportInputBudgetExceeded,
        SupportUnavailableError,
    )

    original = doubles

    async def run(error):
        source = source_for(body())
        member = source.chunks[0].chunk
        original(monkeypatch, member)

        async def resolve(*args, source=source):
            return source

        async def assess(pairs, config=None):
            raise error

        monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
        monkeypatch.setattr(requirement_answers.support_service, "assess", assess)
        candidates = []
        found = await requirement_answers._find_procedure_witnesses(
            None,
            QueryRequest(question=QUESTION),
            {},
            plan_requirements(QUESTION)[0],
            config(),
            candidates,
            {member.id: member},
            [],
            current,
        )
        return found, candidates

    found, candidates = await run(
        SupportInputBudgetExceeded("invented content budget", (513,))
    )
    assert not found and any(
        r.get("decision") == "procedure_support_budget_exceeded" for r in candidates
    )
    with pytest.raises(SupportUnavailableError):
        await run(SupportUnavailableError("invented unavailable configured asset"))


async def test_raw_partial_later_step_or_marker_never_becomes_first_literal_seed(
    monkeypatch,
):
    from app.models.query import AnswerSpan
    from app.services.answer_reader import ReaderSelection

    for raw_text in ("signed card", PARAGRAPHS[1], "End of ordinary procedure"):
        source = source_for(body())
        member = source.chunks[0].chunk
        calls = doubles(monkeypatch, member)

        async def resolve(*args, source=source):
            return source

        async def reader(
            question, contexts, config=None, source=source, raw_text=raw_text
        ):
            first = source.body.index(raw_text)
            span = AnswerSpan(start=first, end=first + len(raw_text), text=raw_text)
            return [
                ReaderSelection(
                    span,
                    {
                        "decision": "answer",
                        "raw_candidates": [
                            {
                                "start": span.start,
                                "end": span.end,
                                "text": raw_text,
                                "null_margin": -4.0,
                            }
                        ],
                    },
                )
                for _ in contexts
            ]

        monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
        monkeypatch.setattr(requirement_answers.reader_service, "select_atomic", reader)
        found = await requirement_answers._find_procedure_witnesses(
            None,
            QueryRequest(question=QUESTION),
            {},
            plan_requirements(QUESTION)[0],
            config("qa_only_v1"),
            [],
            {member.id: member},
            [],
            current,
        )
        assert not found and not calls


async def test_malformed_declared_history_stays_readable_and_unverified(monkeypatch):
    from app.services.requirement_contract import procedure_completeness

    found, _, _, _ = await select(monkeypatch)
    for malformed in (None, [], "invalid"):
        proof = deepcopy(found[0].completeness)
        proof["required_inventory"] = malformed
        selection = {
            "contract": "requirement-evidence-v2",
            "requirements": [
                {
                    "kind": "procedure",
                    "status": "supported",
                    "original_text": QUESTION,
                    "procedure_completeness": proof,
                }
            ],
        }
        assert procedure_completeness(selection) is False


async def test_declared_count_is_source_variable_and_unicode_coordinates_are_literal(
    monkeypatch,
):
    paragraphs = (
        PARAGRAPHS[0].replace("signed card", "signed café card"),
        PARAGRAPHS[2],
        PARAGRAPHS[3],
    )
    text = body(paragraphs, count="three", ordinal="third")
    found, candidates, _, _ = await select(monkeypatch, text)
    assert len(found) == 1, candidates
    assert found[0].value == "\n\n".join(paragraphs)
    assert (
        found[0].completeness["required_inventory"]["declared_paragraphs"][
            "declared_count"
        ]
        == 3
    )
    assert complete_procedure(found[0].completeness)


async def test_cancellation_is_propagated_before_witness_publication(monkeypatch):
    import asyncio

    source = source_for(body())
    member = source.chunks[0].chunk
    doubles(monkeypatch, member)

    async def resolve(*args):
        return source

    async def cancelled(pairs, config=None):
        raise asyncio.CancelledError()

    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    monkeypatch.setattr(requirement_answers.support_service, "assess", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await requirement_answers._find_procedure_witnesses(
            None,
            QueryRequest(question=QUESTION),
            {},
            plan_requirements(QUESTION)[0],
            config(),
            [],
            {member.id: member},
            [],
            current,
        )


async def test_declared_normal_stream_and_history_keep_complete_literal_block(
    procedure_client, monkeypatch
):
    import json

    from app.services.connected_query import settings

    from tests.test_procedure_extent import external_boundaries, seed_procedure

    client, db = procedure_client
    selected = settings.model_copy(
        update={"ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1"}
    )
    monkeypatch.setattr("app.services.connected_query.settings", selected)
    monkeypatch.setattr("app.api.queries.settings", selected)
    external_boundaries(monkeypatch, qa_null=True)
    text = body()
    document, _ = await seed_procedure(db, body=text, pieces=[text])
    request = {
        "question": QUESTION,
        "document_ids": [str(document.id)],
        "retrieval_method": "keyword",
        "top_k": 1,
    }
    normal = await client.post("/api/queries", json=request)
    assert normal.status_code == 200, normal.text
    result = normal.json()
    assert result["outcome"] == "completed", result
    assert "\n\n".join(PARAGRAPHS) in result["answer"]
    proof = result["provenance"]["answer_selection"]["requirements"][0][
        "procedure_completeness"
    ]
    assert complete_procedure(proof)
    stream = await client.post("/api/queries/stream", json=request)
    events = [
        json.loads(line[6:])
        for line in stream.text.splitlines()
        if line.startswith("data: ")
    ]
    done = next(event for event in events if event["type"] == "done")
    assert done["answer"] == result["answer"] and done["sources"] == result["sources"]
    saved = await client.get(f"/api/queries/{result['id']}")
    assert saved.status_code == 200
    assert saved.json()["answer"] == result["answer"]


@pytest.mark.parametrize(
    "title",
    [
        "Lumen token bench: current operation note. Obtain the separate permit first.",
        "Lumen token bench: current operation note\nA permit is needed before work.",
        "Lumen token bench: current operation note\nUnclassified title commentary.",
    ],
)
async def test_entire_namespace_paragraph_must_be_classified(monkeypatch, title):
    text = body().replace("Lumen token bench: current operation note", title)
    found, _, calls, _ = await select(monkeypatch, text)
    assert not found and not calls


@pytest.mark.parametrize(
    "instruction",
    [
        "Before starting, perform the mandatory calibration procedure in Appendix R.",
        "Follow the inspection procedure in Annex B before placing the token.",
        "The operator must complete the preparation procedure in Attachment 12 "
        "before starting.",
        "Do not skip the calibration procedure in Appendix 4.",
        "The calibration procedure in Appendix D is required before starting.",
        "Do not perform the procedure in Appendix R; "
        "follow the calibration procedure in Annex B.",
        "Do not perform the procedure in Appendix R and "
        "follow the calibration procedure in Annex B.",
    ],
)
async def test_explicit_required_external_procedure_is_unresolved(
    monkeypatch, instruction
):
    text = body((instruction, *PARAGRAPHS[1:]))
    found, _, calls, _ = await select(monkeypatch, text)
    assert not found and not calls


@pytest.mark.parametrize(
    "instruction",
    [
        "Record the Appendix K label on the card.",
        "Do not perform the calibration procedure in Appendix R.",
        "Copy the phrase calibration procedure in Appendix K onto the card.",
    ],
)
async def test_literal_label_copy_and_prohibition_are_not_external_execution(
    monkeypatch, instruction
):
    found, candidates, calls, _ = await select(
        monkeypatch, body((instruction, *PARAGRAPHS[1:]))
    )
    assert len(found) == 1, candidates
    assert calls and instruction in found[0].value


async def test_stored_unconsumed_namespace_cannot_be_recertified(monkeypatch):
    found, _, _, _ = await select(monkeypatch)
    proof = deepcopy(found[0].completeness)
    descriptor = proof["required_inventory"]["declared_paragraphs"]
    old = "current operation note"
    replacement = "obtain permit first".ljust(len(old))
    changed = descriptor["source_body"].replace(old, replacement, 1)
    assert len(changed) == proof["body_length"]
    descriptor["source_body"] = changed
    digest = hashlib.sha256(changed.encode()).hexdigest()
    proof["content_hash"] = proof["required_inventory"]["content_hash"] = digest
    assert not complete_procedure(proof)
