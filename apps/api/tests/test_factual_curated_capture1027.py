"""Actual1023 inputs/witnesses; UNITONLY reconstructed pre-error producer path."""

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.config import Settings
from app.models.query import AnswerSpan, QueryRequest
from app.services import linguistic_conflicts, procedure_evidence, requirement_answers
from app.services.answer_requirements import Requirement
from app.services.answer_support import SupportAssessment, support_service
from app.services.curated_conflict_proof import (
    FACT_CONTRACT,
    fact_claim,
    reconstruct_fact_group,
)
from app.services.curated_source_closure import recorded_capture_inventory
from app.services.staged_typed_conflicts import source_chunks

from tests.planning_library_unit830.test_support import metadata
from tests.test_curated_quote_scope995 import config


@lru_cache
def actual():
    return json.loads(
        (Path(__file__).parent / "fixtures/factual_curated_actual1027.json").read_text(
            encoding="utf-8"
        )
    )


def setup(monkeypatch, *, stale=False):
    data = actual()
    snapshots = {
        s["identity"]["document_id"]: {
            **{k: v for k, v in s["identity"].items() if k != "snapshot_id"},
            "body": s["body"],
            "title": s["title"],
            "metadata": json.loads(s["metadata_json"]),
            "chunks": [
                {
                    "id": c["chunk_id"],
                    "index": c["ordinal"],
                    "content": c["literal"]["text"],
                    "metadata": json.loads(c["metadata_json"]),
                }
                for c in s["chunks"]
            ],
        }
        for s in data["snapshots"]
    }
    members = source_chunks(snapshots, evidence_profile=data["profile"])
    by_chunk = {str(c.id): c for c in members}
    sources = {}
    windows = {}
    for raw in data["snapshots"]:
        identifier = raw["identity"]["document_id"]
        identity = {k: v for k, v in raw["identity"].items() if k != "snapshot_id"}
        sources[identifier] = procedure_evidence.ProcedureSource(
            raw["body"],
            tuple(
                procedure_evidence.LocatedChunk(
                    by_chunk[c["chunk_id"]], c["literal"]["start"], c["literal"]["end"]
                )
                for c in raw["chunks"]
            ),
            identity,
            json.loads(raw["metadata_json"]),
            None,
        )
        capture = next(
            c for c in data["source_captures"] if c["identity"] == raw["identity"]
        )
        windows[raw["body"]] = [
            {
                "start": w["start"],
                "end": w["end"],
                "capture": json.loads(w["capture_json"]),
            }
            for w in capture["windows"]
        ]
    reqs = tuple(
        Requirement(
            **{
                **r,
                "anchors": tuple(r["anchors"]),
                "depends_on": tuple(r["depends_on"]),
            }
        )
        for r in data["requirements"]
    )
    witnesses = {r.id: [] for r in reqs}
    for row in data["witnesses"]:
        witnesses[row["requirement_id"]].append(
            SimpleNamespace(
                chunk=by_chunk[row["chunk_id"]],
                span=AnswerSpan(**row["span"]),
                value=row["value"],
                hypothesis=row["hypothesis"],
            )
        )
    calls = {"groups": [], "captures": [], "pairs": []}

    async def sql_group(_db, group, **kwargs):
        calls["groups"].append(group)
        return [c for c in members if c.metadata.get("conflict_group") == group], False

    async def resolve(_db, _principal, _request, member, _inspected):
        return sources[str(member.document_id)]

    async def capture(body, _config, cache):
        calls["captures"].append(body)
        return deepcopy(windows[body])

    async def assess(pairs, **kwargs):
        calls["pairs"].extend(pairs)
        return [
            SupportAssessment("neutral", (0.0, 0.0, 5.0), -5.0, False, 80)
            for _ in pairs
        ]

    async def current(_):
        return not stale

    monkeypatch.setattr(requirement_answers, "inspect_curated_group", sql_group)
    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    monkeypatch.setattr(linguistic_conflicts, "capture_fact_source_windows", capture)
    monkeypatch.setattr(support_service, "metadata", lambda *_: metadata())
    monkeypatch.setattr(support_service, "assess", assess)
    return snapshots, members, reqs, witnesses, calls, current


async def inspect(monkeypatch, *, stale=False, legacy=False):
    snapshots, members, reqs, witnesses, calls, current = setup(
        monkeypatch, stale=stale
    )
    selected = (
        Settings(
            GENERATION_MODE="extractive",
            ANSWER_SELECTION_MODE="reader",
            ANSWER_SUPPORT_MODE="local_nli",
        )
        if legacy
        else config()
    )
    records, relevant = await requirement_answers._inspect_conflicts(
        None,
        QueryRequest(question=reqs[0].original_text),
        None,
        {c.id: c for c in members},
        reqs,
        {r.id: r for r in reqs},
        witnesses,
        selected,
        current,
        [],
    )
    return snapshots, members, reqs, witnesses, calls, records, relevant


@pytest.mark.parametrize("stale", [False, True])
async def test_actual_all_four_groups_use_captured_factual_inspection(
    monkeypatch, stale
):
    snapshots, members, reqs, witnesses, calls, records, relevant = await inspect(
        monkeypatch, stale=stale
    )
    assert (
        len(members) == 46
        and len(calls["groups"]) == 4
        and len(set(calls["groups"])) == 4
    )
    assert len(reqs) == 3 and len(records) == 12
    assert all(r.get("inspection_method") == FACT_CONTRACT for r in records)
    captures = recorded_capture_inventory(
        records, {r.id: r for r in reqs}, snapshots, FACT_CONTRACT
    )
    assert len(captures) == 8
    assert sum(len(r["source_scope_decisions"]) for r in records) == 24
    assert len(calls["captures"]) == 24
    if stale:
        assert all(r["truncated"] and not r["inspection_complete"] for r in records)
    else:
        for record in records:
            req = next(r for r in reqs if r.id == record["requirement_id"])
            claims = [
                fact_claim(
                    requirement_answers.source_identity(w.chunk),
                    w.span.model_dump(),
                    w.value,
                    w.hypothesis,
                )
                for w in witnesses[req.id]
            ]
            assert (
                reconstruct_fact_group(
                    record, req, snapshots, {"support": metadata()}, claims
                )
                == record
            )


async def test_legacy_default_keeps_original_uncaptured_record_path(monkeypatch):
    _, _, _, _, calls, records, _ = await inspect(monkeypatch, legacy=True)
    assert not calls["captures"]
    assert all("inspection_method" not in r for r in records)


async def test_missing_or_forged_opponent_capture_cannot_certify(monkeypatch):
    snapshots, _, reqs, _, _, records, _ = await inspect(monkeypatch)
    for damage in ("missing", "identity"):
        changed = deepcopy(records)
        cap = changed[0]["source_scope_decisions"][0]
        if damage == "missing":
            del cap["source_capture"]
        else:
            cap["source_capture"]["source_identity"]["content_hash"] = "0" * 64
        with pytest.raises((ValueError, KeyError)):
            recorded_capture_inventory(
                changed, {r.id: r for r in reqs}, snapshots, FACT_CONTRACT
            )
