"""UNITONLY protocol facts; no classifier or application success is simulated."""

import hashlib
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from tests.curated_capture_fixtures import (
    actual_source_windows,
)
from tests.curated_capture_fixtures import (
    curated_capture_runtime as curated_capture_runtime,
)
from tests.test_contextual_mixed_output import (
    collect_source_proposals,
    mirror,
    output,
    produce,
    role_fixture,
)


def factual_group_fixture(
    *, full_inputs=True, foreign_body="The caretaker leads Birch review."
):
    data = role_fixture()
    selection = data["selection"]
    original = next(iter(data["source_snapshots"].values()))
    body = foreign_body
    foreign = {
        "document_id": "00000000-0000-0000-0000-000000000099",
        "document_version": 3,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
        "workspace_id": None,
        "body": body,
        "chunks": [
            {"id": "10000000-0000-0000-0000-000000000099", "index": 0, "content": body}
        ],
        "metadata": {},
    }
    data["source_snapshots"][foreign["document_id"]] = foreign
    for source in data["source_snapshots"].values():
        source["metadata"] = {"conflict_group": "curated-review", "condition": None}
        if full_inputs:
            source["source_windows"] = actual_source_windows(source["body"])
    member = {
        k: foreign[k] for k in ("document_id", "document_version", "content_hash")
    }
    member["chunk_id"] = foreign["chunks"][0]["id"]
    selection["inspected_sources"].append(member)
    req = data["request_reconstructor"](data["question"], {}).requirements[0]
    chunks, inventory, sources = output._sources(data["source_snapshots"], selection)
    batch = collect_source_proposals(
        req, sources, reading_profile="contextual_source_v2"
    )
    qa = [p for p in selection["proposals"] if p["origin"] == "qa_reader"]
    selection["proposals"] = qa + [p.record() for p in batch.proposals]
    selection["pattern_observations"] = list(batch.observations)
    entries = [
        {
            **{
                k: source[k]
                for k in (
                    "document_id",
                    "document_version",
                    "content_hash",
                    "workspace_id",
                )
            },
            "chunk_id": chunk["id"],
            "condition": None,
            "conflict_group": "curated-review",
            "chunk_hash": hashlib.sha256(chunk["content"].encode()).hexdigest(),
        }
        for source in (original, foreign)
        for chunk in source["chunks"]
    ]
    selection["procedure_read_set"] = {
        "contract": "procedure-inspection-read-set-v1",
        "document_ids": None,
        "collection_ids": None,
        "sources": entries,
        "groups": [{"group": "curated-review", "sources": deepcopy(entries)}],
        "after_proofs": {"consistent": True},
    }
    # Current producer shape: foreign source is explicitly scoped out, so no
    # opponent QA answer is manufactured. The missing consumer currently blocks.
    selection["conflicts"] = [
        {
            "group": "curated-review",
            "requirement_id": "r1",
            "applicable_documents": [original["document_id"]],
            "relevant": False,
            "requested_fact_agreement": False,
            "agreement_method": None,
            "inspection_complete": True,
            "subject_scope_excluded_documents": [foreign["document_id"]],
            "source_scope_decisions": [
                {
                    **selection["inspected_sources"][0],
                    "relation_scope": "applies",
                    "included": True,
                },
                {**member, "relation_scope": "irrelevant", "included": False},
            ],
            "outcome": "not_relevant",
            "assessments": [deepcopy(selection["candidates"][0]["support"])],
        }
    ]
    if full_inputs:
        from app.services.curated_conflict_proof import (
            fact_claim,
            fact_inputs,
            fact_outcome,
        )

        witness = selection["requirements"][0]["witnesses"][0]
        claim = fact_claim(
            witness,
            witness["span"],
            witness["value"],
            selection["candidates"][0]["hypothesis"],
        )
        scopes, claims, inputs = fact_inputs(
            req, data["source_snapshots"], entries, [claim]
        )
        rows = [
            {**row, "assessment": deepcopy(selection["candidates"][0]["support"])}
            for row in inputs
        ]
        record = fact_outcome(req, entries, scopes, claims, rows, False)
        record["group"] = "curated-review"
        selection["conflicts"] = [record]
    mirror(data)
    return data


def test_foreign_curated_opponent_is_independently_excluded_before_publication():
    """Break: mixed consumer rejects a completely inspected irrelevant group."""
    data = factual_group_fixture()
    actual = produce(data)
    assert "The archivist leads Alder review." in actual["answer"]
    assert "caretaker" not in actual["answer"]
    proof = actual["certificate"]["curated_inspections"][0]
    assert proof["relevant"] is False
    assert proof["subject_scope_excluded_documents"] == [
        "00000000-0000-0000-0000-000000000099"
    ]


def test_group_free_v2_certificate_keeps_its_existing_shape():
    actual = produce(role_fixture())
    assert "curated_inspections" not in actual["certificate"]


@pytest.mark.parametrize(
    "change",
    [
        "missing_group",
        "duplicate_group",
        "unknown_group",
        "unknown_requirement",
        "missing_member",
        "member_identity",
        "member_version",
        "member_hash",
        "source_metadata",
        "source_body",
        "source_chunk",
        "read_set_group",
        "read_set_source",
        "read_set_stale",
        "read_set_scope",
        "invalid_collection",
        "empty_collection",
        "wrong_claim",
        "wrong_premise",
        "wrong_hypothesis",
        "negative_nli",
        "bool_tokens",
        "missing_comparison",
        "truncated",
        "false_agreement",
        "false_exclusion",
        "scope_cover",
        "downgrade",
    ],
)
def test_curated_proof_cannot_be_forged_or_pruned(change):  # noqa: C901 - explicit mutation cases
    data = factual_group_fixture()
    selection = data["selection"]
    record = selection["conflicts"][0]
    source = next(iter(data["source_snapshots"].values()))
    if change == "missing_group":
        selection["conflicts"] = []
    elif change == "duplicate_group":
        selection["conflicts"].append(deepcopy(record))
    elif change == "unknown_group":
        record["group"] = "unbound"
    elif change == "unknown_requirement":
        record["requirement_id"] = "r999"
    elif change == "missing_member":
        record["inspection_sources"].pop()
    elif change == "member_identity":
        record["inspection_sources"][0]["document_id"] = "unbound"
    elif change == "member_version":
        record["inspection_sources"][0]["document_version"] += 1
    elif change == "member_hash":
        record["inspection_sources"][0]["chunk_hash"] = "0" * 64
    elif change == "source_metadata":
        source["metadata"]["conflict_group"] = "other"
    elif change == "source_body":
        source["body"] += " stale"
    elif change == "source_chunk":
        source["chunks"][0]["content"] = "changed"
    elif change == "read_set_group":
        selection["procedure_read_set"]["groups"] = []
    elif change == "read_set_source":
        selection["procedure_read_set"]["sources"].pop()
    elif change == "read_set_stale":
        selection["procedure_read_set"]["after_proofs"]["consistent"] = False
    elif change == "read_set_scope":
        selection["procedure_read_set"]["document_ids"] = [source["document_id"]]
    elif change == "invalid_collection":
        selection["procedure_read_set"]["collection_ids"] = ["not-a-uuid"]
    elif change == "empty_collection":
        selection["procedure_read_set"]["collection_ids"] = []
    elif change == "wrong_claim":
        record["witness_claims"][0]["value"] = "caretaker"
    elif change == "wrong_premise":
        record["comparisons"][0]["premise"] = "invented"
    elif change == "wrong_hypothesis":
        record["comparisons"][0]["hypothesis"] = "different fact"
    elif change == "negative_nli":
        record["comparisons"][0]["assessment"].update(
            label="neutral",
            logits=[-1.0, 0.0, 5.0],
            entailment_margin=-5.0,
            supported=False,
        )
    elif change == "bool_tokens":
        record["comparisons"][0]["assessment"]["pair_tokens"] = True
    elif change == "missing_comparison":
        record["comparisons"] = []
    elif change == "truncated":
        record["truncated"] = True
    elif change == "false_agreement":
        record["requested_fact_agreement"] = True
    elif change == "false_exclusion":
        record["source_scope_decisions"][0]["included"] = False
    elif change == "scope_cover":
        record["source_scope_decisions"][1]["scope_cover"] = []
    else:
        record.pop("inspection_method")
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_retained_capture_prevents_coherent_comparison_pruning():
    data = factual_group_fixture()
    data["selection"]["conflicts"] = []
    data["selection"]["procedure_read_set"]["groups"] = []
    for source in data["source_snapshots"].values():
        source["metadata"]["conflict_group"] = None
    with pytest.raises(ValueError, match="retained execution"):
        produce(data)


def test_legacy_incomplete_factual_dto_cannot_downgrade_v2():
    with pytest.raises(ValueError):
        produce(factual_group_fixture(full_inputs=False))


def test_unknown_opponent_neutral_comparison_cannot_certify_nonconflict():
    data = factual_group_fixture(
        foreign_body="An unparsed instruction about the review remains binding."
    )
    record = data["selection"]["conflicts"][0]
    assert len(record["comparisons"]) == 2
    record["comparisons"][1]["assessment"].update(
        label="neutral",
        logits=[-1.0, 0.0, 5.0],
        entailment_margin=-5.0,
        supported=False,
    )
    from app.services.curated_conflict_proof import fact_outcome

    req = data["request_reconstructor"](data["question"], {}).requirements[0]
    updated = fact_outcome(
        req,
        record["inspection_sources"],
        record["source_scope_decisions"],
        record["witness_claims"],
        record["comparisons"],
        False,
    )
    updated["group"] = record["group"]
    data["selection"]["conflicts"] = [updated]
    mirror(data)
    assert updated["outcome"] == "comparison_unconfirmed"
    with pytest.raises(ValueError, match="relevant or unconfirmed"):
        produce(data)


@pytest.mark.parametrize(
    "body",
    [
        "An unparsed role mandate for Alder review remains binding. "
        "The caretaker leads Birch review.",
        "An unparsed role mandate for Alder review remains binding. "
        "The inspection lasts 8 minutes.",
        "Retest: keep the temporary sheet. "
        "An unparsed role mandate for Alder review remains binding.",
    ],
)
def test_known_foreign_clause_cannot_erase_unparsed_opponent_material(body):
    data = factual_group_fixture(foreign_body=body)
    with pytest.raises(ValueError):
        produce(data)


def test_actual_validated_member_witnesses_can_establish_requested_fact_agreement():
    data = factual_group_fixture(foreign_body="The archivist leads Alder review.")
    selection = data["selection"]
    foreign = data["source_snapshots"]["00000000-0000-0000-0000-000000000099"]
    proposal = next(
        p for p in selection["proposals"] if p["document_id"] == foreign["document_id"]
    )
    member = {
        k: foreign[k] for k in ("document_id", "document_version", "content_hash")
    }
    member["chunk_id"] = foreign["chunks"][0]["id"]
    candidate = deepcopy(selection["candidates"][0])
    candidate.update(
        member,
        proposal=proposal,
        raw_span=proposal["chunk_range"],
        null_margin=None,
        origin="source_pattern",
    )
    candidate.pop("duplicate_proposals", None)
    candidate["whole_source_support"]["source_identity"] = {
        k: foreign[k]
        for k in ("document_id", "document_version", "content_hash", "workspace_id")
    }
    witness = deepcopy(selection["requirements"][0]["witnesses"][0])
    witness.update(member, proposals=[proposal])
    selection["candidates"].append(candidate)
    selection["requirements"][0]["witnesses"].append(witness)
    selection["selected_proposal_ids"].append(proposal["proposal_id"])
    from app.services.curated_conflict_proof import (
        fact_claim,
        fact_inputs,
        fact_outcome,
    )

    req = data["request_reconstructor"](data["question"], {}).requirements[0]
    claims = [
        fact_claim(w, w["span"], w["value"], candidate["hypothesis"])
        for w in selection["requirements"][0]["witnesses"]
    ]
    members = selection["procedure_read_set"]["sources"]
    scopes, claims, inputs = fact_inputs(req, data["source_snapshots"], members, claims)
    rows = [{**row, "assessment": deepcopy(candidate["support"])} for row in inputs]
    record = fact_outcome(req, members, scopes, claims, rows, False)
    record["group"] = "curated-review"
    selection["conflicts"] = [record]
    mirror(data)
    actual = produce(data)
    assert (
        actual["certificate"]["curated_inspections"][0]["requested_fact_agreement"]
        is True
    )
    assert len(actual["certificate"]["curated_inspections"][0]["comparisons"]) == 4


def test_curated_certificate_replays_actual_history_output():
    data = factual_group_fixture()
    actual = produce(data)
    data["selection"][output.CERTIFICATE_FIELD] = deepcopy(actual["certificate"])
    context = {k: v for k, v in data.items() if k != "selection"}
    context.update(answer=actual["answer"], citations=actual["citations"])
    assert output.verify_output(data["selection"], **context)
    data["selection"][output.CERTIFICATE_FIELD]["curated_inspections"] = []
    assert not output.verify_output(data["selection"], **context)


def test_retrieval_order_does_not_change_authoritative_group_membership():
    data = factual_group_fixture()
    data["selection"]["inspected_sources"].reverse()
    mirror(data)
    assert "archivist" in produce(data)["answer"]


@pytest.mark.parametrize("stale", [False, True])
async def test_typed_producer_inspects_qa_abstaining_foreign_source_then_pure_replay(
    monkeypatch,
    stale,
):
    from app.models.chunk import ChunkWithScore
    from app.models.query import AnswerSpan, QueryRequest
    from app.services import procedure_evidence
    from app.services import requirement_answers as controller
    from app.services.answer_support import SupportAssessment

    from tests.test_linguistic_runtime_dispatch import config

    data = factual_group_fixture(full_inputs=False)
    selection = data["selection"]
    req = data["request_reconstructor"](data["question"], {}).requirements[0]
    members = [
        ChunkWithScore(
            id=s["chunks"][0]["id"],
            document_id=s["document_id"],
            content=s["body"],
            chunk_index=0,
            relevance_score=1.0,
            metadata={
                **s["metadata"],
                **{
                    k: s[k]
                    for k in (
                        "document_id",
                        "document_version",
                        "content_hash",
                        "workspace_id",
                    )
                },
            },
        )
        for s in data["source_snapshots"].values()
    ]
    sources = {m.id: procedure_evidence.single_chunk_source(m) for m in members}
    resolved = []

    async def resolve(db, principal, request, member, inspected):
        resolved.append(member.id)
        return sources[member.id]

    async def retrieve(*args, **kwargs):
        return members, False

    async def current(member):
        return not (stale and member.id == members[1].id)

    async def assess(pairs, **kwargs):
        assert all(
            pair.premise == "The archivist leads Alder review." for pair in pairs
        )
        return [
            SupportAssessment("entailment", (-1.0, 5.0, 0.0), 5.0, True, 80)
            for _ in pairs
        ]

    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    monkeypatch.setattr(controller, "inspect_curated_group", retrieve)
    monkeypatch.setattr(controller.support_service, "assess", assess)
    witness = selection["requirements"][0]["witnesses"][0]
    actual_witness = controller.Witness(
        req.id,
        members[0],
        AnswerSpan(**witness["span"]),
        witness["value"],
        selection["candidates"][0]["hypothesis"],
        5.0,
        -3.0,
    )
    records, relevant = await controller._inspect_conflicts(
        cast(Any, None),
        QueryRequest(question=data["question"]),
        {},
        {members[0].id: members[0]},
        (req,),
        {req.id: req},
        {req.id: [actual_witness]},
        config(),
        current,
        [],
    )
    if stale:
        assert set(resolved) == {members[0].id}
        assert relevant is True
        assert records[0]["truncated"] is True
    else:
        assert set(resolved) == {m.id for m in members}
        assert relevant is False
    assert (
        records[0]["inspection_method"] == "curated-captured-source-fact-comparison-v3"
    )
    selection["conflicts"] = records
    mirror(data)
    if stale:
        with pytest.raises(ValueError):
            produce(data)
    else:
        assert "archivist" in produce(data)["answer"]


def test_pure_curated_output_has_no_runtime_sql_or_model_imports():
    script = """
import importlib.abc,runpy,sys,types,app
from pathlib import Path
p=types.ModuleType('app.services')
p.__path__=[str(Path(sys.argv[2])/'app/services')]
sys.modules['app.services']=p;app.services=p
blocked=('sqlalchemy','torch','transformers','spacy','app.db','app.models',
 'app.services.answer_support','app.services.procedure_evidence',
 'app.services.requirement_answers','app.services.source_pattern_proposals')
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if any(name==x or name.startswith(x+'.') for x in blocked):
   raise RuntimeError('Forbidden runtime import '+name)
sys.meta_path.insert(0,Guard())
t=runpy.run_path(sys.argv[1]);t['produce'](t['factual_group_fixture']())
from app.services.linguistic_conflicts import reconstruct_group
"""
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-B",
            "-c",
            script,
            str(Path(__file__).resolve()),
            str(Path(__file__).parents[1]),
        ],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stderr
