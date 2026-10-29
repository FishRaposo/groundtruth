"""Complete group scope replay over UNITONLY procedure NLI observations."""

import hashlib
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from app.services.curated_conflict_proof import (
    fact_claim,
    fact_inputs,
    fact_outcome,
    procedure_outcome,
    scope_input,
    scope_row,
)

from tests.test_contextual_mixed_output import (
    collect_source_proposals,
    manual_plan,
    mirror,
    mixed_fixture,
    output,
    produce,
)


def procedure_group_fixture(*, neutral=False, truncated=False):
    data = mixed_fixture()
    selection = data["selection"]
    req = data["request_reconstructor"](data["question"], {}).requirements[1]
    req = replace(req, input_start=0, input_end=len(req.original_text))
    manual_plan(data, (req,), req.original_text)
    data["source_snapshots"].pop("00000000-0000-0000-0000-000000000001")
    selection["requirements"] = [selection["requirements"][1]]
    selection["requirements"][0]["input_range"] = {
        "start": 0,
        "end": len(req.original_text),
    }
    selection["candidates"] = [
        c for c in selection["candidates"] if c["requirement_id"] == req.id
    ]
    selection["proposals"] = [
        p for p in selection["proposals"] if p["requirement_id"] == req.id
    ]
    selection["qa_observations"] = [
        o for o in selection["qa_observations"] if o["requirement_id"] == req.id
    ]
    selection["selected_proposal_ids"] = [
        p["proposal_id"] for p in selection["proposals"]
    ]
    body = (
        "This complete procedure applies to isolated Cedar trials. Discard the record."
    )
    doc = "00000000-0000-0000-0000-000000000099"
    data["source_snapshots"][doc] = {
        "document_id": doc,
        "document_version": 1,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
        "workspace_id": None,
        "body": body,
        "chunks": [
            {"id": "10000000-0000-0000-0000-000000000099", "index": 0, "content": body}
        ],
        "metadata": {},
    }
    entries = []
    for source in data["source_snapshots"].values():
        group = "procedure-opponents"
        source["metadata"] = {"condition": None, "conflict_group": group}
        for chunk in source["chunks"]:
            entries.append(
                dict(
                    **{
                        k: source[k]
                        for k in (
                            "document_id",
                            "document_version",
                            "content_hash",
                            "workspace_id",
                        )
                    },
                    chunk_id=chunk["id"],
                    condition=None,
                    conflict_group=group,
                    chunk_hash=hashlib.sha256(chunk["content"].encode()).hexdigest(),
                )
            )
    entries.sort(key=lambda e: e["chunk_id"])
    members = [e for e in entries if e["conflict_group"]]
    selection["inspected_sources"] = [
        {
            k: e[k]
            for k in ("chunk_id", "document_id", "document_version", "content_hash")
        }
        for e in entries
    ]
    selection["procedure_read_set"] = {
        "contract": "procedure-inspection-read-set-v1",
        "document_ids": None,
        "collection_ids": None,
        "sources": entries,
        "groups": [{"group": "procedure-opponents", "sources": members}],
        "after_proofs": {"consistent": True},
    }
    chunks, inventory, sources = output._sources(data["source_snapshots"], selection)
    plan = data["request_reconstructor"](data["question"], {})
    patterns, observations = [], []
    for req in plan.requirements:
        batch = collect_source_proposals(
            req, sources, reading_profile="contextual_source_v2"
        )
        patterns.extend(p.record() for p in batch.proposals)
        observations.extend(batch.observations)
    selection["proposals"] = [
        p for p in selection["proposals"] if p["origin"] == "qa_reader"
    ] + patterns
    selection["pattern_observations"] = observations
    settings = {"support": selection["evidence_support"]}
    positive = {
        "label": "entailment",
        "logits": [-1.0, 5.0, 0.0],
        "entailment_margin": 5.0,
        "supported": True,
        "pair_tokens": 80,
    }
    negative = {
        "label": "neutral" if neutral else "contradiction",
        "logits": [-1.0, 0.0, 5.0] if neutral else [5.0, -1.0, 0.0],
        "entailment_margin": -5.0 if neutral else -6.0,
        "supported": False,
        "pair_tokens": 80,
    }
    records = []
    for req in plan.requirements:
        if req.kind == "procedure":
            rows = []
            for identifier in sorted({m["document_id"] for m in members}):
                snapshot = data["source_snapshots"][identifier]
                identity = {
                    k: snapshot[k]
                    for k in ("document_id", "document_version", "content_hash")
                }
                rows.append(
                    scope_row(
                        scope_input(req, identity, snapshot["body"]),
                        negative if identifier == doc else positive,
                        settings,
                    )
                )
            record = procedure_outcome(req, rows, members, truncated, True)
        else:
            candidate = selection["candidates"][0]
            witness = selection["requirements"][0]["witnesses"][0]
            claim = fact_claim(
                witness, witness["span"], witness["value"], candidate["hypothesis"]
            )
            scopes, claims, inputs = fact_inputs(
                req, data["source_snapshots"], members, [claim]
            )
            record = fact_outcome(
                req,
                members,
                scopes,
                claims,
                [{**r, "assessment": positive} for r in inputs],
                truncated,
            )
        record["group"] = "procedure-opponents"
        records.append(record)
    selection["conflicts"] = records
    mirror(data)
    return data


def test_procedure_exclusion_replays_before_actual_copy():
    data = procedure_group_fixture()
    actual = produce(data)
    assert "Never reopen the register." in actual["answer"]
    assert "Discard the record." not in actual["answer"]
    proof = actual["certificate"]["curated_inspections"][0]
    assert proof["excluded_documents"] == ["00000000-0000-0000-0000-000000000099"]
    assert proof["source_extent_checks"][1]["assessment"]["label"] == "contradiction"


@pytest.mark.parametrize(
    "change",
    [
        "neutral",
        "truncated",
        "premise",
        "hypothesis",
        "scope_flag",
        "excluded",
        "missing_row",
        "wrong_version",
        "negative_logits",
        "extra_model_field",
    ],
)
def test_procedure_scope_cannot_hide_unknown_or_forged_opponent(change):
    data = procedure_group_fixture(
        neutral=change == "neutral", truncated=change == "truncated"
    )
    record = data["selection"]["conflicts"][0]
    row = record["source_extent_checks"][1]
    if change == "premise":
        row["premise"] = "invented"
    elif change == "hypothesis":
        row["hypothesis"] = "no conflict"
    elif change == "scope_flag":
        row["scope_excluded"] = False
    elif change == "excluded":
        record["excluded_documents"] = []
    elif change == "missing_row":
        record["source_extent_checks"].pop()
    elif change == "wrong_version":
        row["source_identity"]["document_version"] += 1
    elif change == "negative_logits":
        row["assessment"]["logits"][0] = False
    elif change == "extra_model_field":
        row["assessment"]["verified"] = True
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_truncation_with_all_visible_members_excluded_is_still_unconfirmed():
    data = procedure_group_fixture()
    record = data["selection"]["conflicts"][0]
    rows = deepcopy(record["source_extent_checks"])
    for row in rows:
        row["scope_excluded"] = True
    req = data["request_reconstructor"](data["question"], {}).requirements[0]
    result = procedure_outcome(req, rows, record["inspection_sources"], True, True)
    assert result["relevant"] is True
    assert result["inspection_complete"] is False
    assert result["outcome"] == "comparison_unconfirmed"


async def test_failed_source_inspection_never_fabricates_a_document_identity(
    monkeypatch,
):
    from app.services import linguistic_conflicts, procedure_evidence
    from app.services.answer_requirements import Requirement

    from tests.test_composite_procedures import chunk
    from tests.test_linguistic_runtime_dispatch import config

    question = "Give the complete Alder review routine."
    req = Requirement(
        "r1",
        question,
        0,
        len(question),
        question,
        "procedure",
        "Alder review",
        ("alder",),
    )
    member = chunk(
        "This complete procedure applies to Alder review. Retain the record."
    )

    async def unavailable(*args, **kwargs):
        raise procedure_evidence.ProcedureRejected("actual source version unavailable")

    monkeypatch.setattr(procedure_evidence, "resolve_version", unavailable)
    result = await linguistic_conflicts.inspect_group(
        None,
        None,
        None,
        req,
        config(),
        [member],
        False,
        [SimpleNamespace(value="selected")],
        {},
        [],
    )
    assert result["relevant"] is True
    assert result["inspection_complete"] is False
    known = {r["document_id"] for r in result["inspection_sources"]}
    assert all(
        r.get("source_identity", {}).get("document_id") in known
        for r in result["source_extent_checks"]
        if "source_identity" in r
    )
