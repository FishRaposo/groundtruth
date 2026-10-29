"""Actual saved role syntax; UNITONLY replay, no live SQL or model authority."""

import hashlib
import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest
from app.evidence_policy import recorded_evidence_policy
from app.services.answer_requirements import Requirement
from app.services.requirement_binding import (
    activity_role_claim,
    role_discovery_candidates,
)
from app.services.role_scope_inspection import (
    RoleScopeManifest,
    RoleScopeSource,
    _digest,
    inspect_role_contexts,
)
from app.services.role_scope_policy import plan_activity_role


@lru_cache
def actual():
    return json.loads(
        (Path(__file__).parent / "fixtures/ordinary_role_actual975.json").read_text(
            encoding="utf-8"
        )
    )


def role(kind):
    value = next(row for row in actual()["requirements"] if row["kind"] == kind)
    requirement = Requirement(
        **{
            **value,
            "anchors": tuple(value["anchors"]),
            "depends_on": tuple(value["depends_on"]),
        }
    )
    plan = plan_activity_role(
        requirement, recorded_evidence_policy(actual()["evidence_profile"])
    )
    assert plan is not None
    return plan


def positive_source():
    return next(
        row
        for row in actual()["snapshots"]
        if row["body"].startswith("For ordinary Citrine fragment desk sessions,")
    )


def manifest_and_captures():
    snapshots = {row["identity"]["document_id"]: row for row in actual()["snapshots"]}
    sources = []
    for identity in actual()["read_set"]["documents"]:
        snapshot = snapshots[identity["document_id"]]
        assert (
            _digest(json.loads(snapshot["metadata_json"])) == identity["metadata_hash"]
        )
        sources.append(
            RoleScopeSource(
                snapshot["body"], json.dumps(identity), snapshot["metadata_json"]
            )
        )
    captures = {
        row["identity"]["document_id"]: [
            {
                "start": w["start"],
                "end": w["end"],
                "capture": json.loads(w["capture_json"]),
            }
            for w in row["windows"]
        ]
        for row in actual()["source_captures"]
    }
    return RoleScopeManifest(tuple(sources), actual()["read_set"]), captures


@pytest.mark.parametrize(
    ("kind", "value"),
    [("owner", "the fragment steward"), ("deputy", "the buffer clerk")],
)
def test_actual_activity_fields_retain_shared_scope_and_exact_value(kind, value):
    body = positive_source()["body"]
    candidates = role_discovery_candidates(
        role(kind).prepared("session"), body, activity_fields=True
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["target"] == "ordinary Citrine fragment desk sessions"
    assert candidate["value"] == value
    assert (
        body[candidate["value_range"]["start"] : candidate["value_range"]["end"]]
        == value
    )
    assert candidate["rejection"] is None
    assert candidate["declared_role_scope"] == "activity"


@pytest.mark.parametrize("kind", ["owner", "deputy"])
def test_actual_full_universe_records_bounded_role_inspection_without_global_absence(
    kind,
):
    manifest, captures = manifest_and_captures()
    finding = inspect_role_contexts(
        manifest,
        role(kind),
        source_windows=captures,
        evidence_profile=actual()["evidence_profile"],
    )
    assert finding["complete"], finding["reason"]
    assert len(finding["contexts"]) == len(manifest.sources) == 46
    assert finding["session_documents"] == []
    assert finding["activity_documents"] == [
        positive_source()["identity"]["document_id"]
    ]
    assert finding["implicit_role_alias_absence"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("span", ["partial", "whole", "period"])
def test_exact_activity_field_expansion_preserves_source_and_has_no_special_edges(span):
    body = positive_source()["body"]
    kind = "deputy" if span == "period" else "owner"
    value = "the buffer clerk" if kind == "deputy" else "the fragment steward"
    first, last = body.index(value), body.index(value) + len(value)
    start = first + len("the fragment ") if span == "partial" else first
    end = last + 1 if span == "period" else last
    claim = activity_role_claim(role(kind).prepared("activity"), body, start, end)
    assert claim is not None and claim.rejection is None
    assert (claim.start, claim.end, claim.value) == (first, last, value)
    assert body[claim.premise_start : claim.premise_end] == claim.premise
    assert claim.proof_edges == ()
    assert "ordinary Citrine fragment desk sessions" in claim.hypothesis


def test_plain_legacy_role_field_alone_declines_new_helper():
    body = "The lead for Citrine fragment desk is the fragment steward."
    first = body.index("the fragment steward")
    assert (
        activity_role_claim(
            role("owner").prepared("activity"), body, first, len(body) - 1
        )
        is None
    )


@pytest.mark.parametrize("variant", ["modal", "foreign", "dependency"])
def test_existing_but_unsupported_activity_field_rejects_without_legacy_fallback(
    variant,
):
    body = positive_source()["body"]
    request = role("owner").prepared("activity")
    if variant == "modal":
        body = body.replace("lead is", "lead may be")
    elif variant == "foreign":
        body = body.replace("Citrine", "UNITONLYForeign")
    else:
        request = replace(request, depends_on=("UNITONLY-prior",))
    first = body.index("the fragment steward")
    claim = activity_role_claim(
        request, body, first, first + len("the fragment steward")
    )
    assert claim is not None and claim.rejection is not None


@pytest.mark.parametrize(
    "kind,expected",
    [
        ("owner", "46a66e3d904919cc4797b3cb50439a07566bb8401708849eabd6be551ad4f2ae"),
        ("deputy", "fffe4cca6cd8b26683b90f386d5ea1f6b777c37b0aadb8e20d5f01bbd57c8663"),
    ],
)
def test_old_default_actual_findings_remain_exact_saved_bytes(kind, expected):
    manifest, captures = manifest_and_captures()
    finding = inspect_role_contexts(manifest, role(kind), source_windows=captures)
    raw = json.dumps(finding, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert hashlib.sha256(raw.encode()).hexdigest() == expected


@pytest.mark.parametrize(
    "kind", ["reference", "override", "record_actor", "assign_actor"]
)
def test_unitonly_unknown_role_changing_material_remains_unresolved(kind):
    from dataclasses import asdict

    from tests.staged_plan_unit837.fixtures_source import EXTERNAL
    from tests.staged_plan_unit837.fixtures_source import source as make_source

    groups = [EXTERNAL]
    if kind == "override":
        groups = [
            [
                ("The", "DET", "the", "det", 2),
                ("separate", "ADJ", "separate", "amod", 2),
                ("assignment", "NOUN", "assignment", "nsubj", 3),
                ("changes", "VERB", "change", "ROOT", 3),
                (".", "PUNCT", ".", "punct", 3),
            ]
        ]
    elif kind == "record_actor":
        groups = [
            [
                ("Record", "VERB", "record", "ROOT", 0),
                ("the", "DET", "the", "det", 2),
                ("token", "NOUN", "token", "dobj", 0),
                ("as", "ADP", "as", "prep", 0),
                ("the", "DET", "the", "det", 5),
                ("lead", "NOUN", "lead", "pobj", 3),
                (".", "PUNCT", ".", "punct", 0),
            ]
        ]
    elif kind == "assign_actor":
        groups = [
            [
                ("Assign", "VERB", "assign", "ROOT", 0),
                ("the", "DET", "the", "det", 2),
                ("assistant", "NOUN", "assistant", "dobj", 0),
                ("as", "ADP", "as", "prep", 0),
                ("the", "DET", "the", "det", 5),
                ("owner", "NOUN", "owner", "pobj", 3),
                (".", "PUNCT", ".", "punct", 0),
            ]
        ]
    snapshot, captured = make_source(groups)
    source = RoleScopeSource(
        snapshot.body, json.dumps(asdict(snapshot.identity)), snapshot.metadata_json
    )
    manifest = RoleScopeManifest(
        (source,), {"complete": True, "reason": None, "fixture": "UNITONLY_NOT_SQL"}
    )
    windows = [
        {"start": w.start, "end": w.end, "capture": json.loads(w.capture_json)}
        for w in captured.windows
    ]
    finding = inspect_role_contexts(
        manifest,
        role("owner"),
        source_windows={snapshot.identity.document_id: windows},
        evidence_profile=actual()["evidence_profile"],
    )
    assert not finding["complete"]
    assert any(
        u["disposition"] == "unresolved"
        for c in finding["contexts"]
        for u in c["units"]
    )


def test_unassessed_condition_metadata_cannot_become_an_activity_assignment():
    manifest, captures = manifest_and_captures()
    identifier = positive_source()["identity"]["document_id"]
    source = next(
        s for s in manifest.sources if s.identity["document_id"] == identifier
    )
    source = replace(
        source,
        metadata_json=json.dumps({**source.metadata, "condition": "UNITONLY_unknown"}),
    )
    finding = inspect_role_contexts(
        RoleScopeManifest(
            (source,), {"complete": True, "reason": None, "fixture": "UNITONLY_NOT_SQL"}
        ),
        role("owner"),
        source_windows={identifier: captures[identifier]},
        evidence_profile=actual()["evidence_profile"],
    )
    assert not finding["complete"] and finding["activity_documents"] == []


def test_unitonly_split_condition_without_role_words_remains_governing():
    from dataclasses import asdict

    from tests.staged_plan_unit837.fixtures_source import source as make_source

    original = positive_source()
    captured = next(
        c for c in actual()["source_captures"] if c["identity"] == original["identity"]
    )
    tokens = json.loads(captured["windows"][0]["capture_json"])["annotation"]["tokens"]
    end = original["body"].index(" and the activity deputy")
    group = [
        (t["text"], t["pos"], t["lemma"], t["dep"], t["head"])
        for t in tokens
        if t["end"] <= end
    ]
    root = next(i for i, row in enumerate(group) if row[3] == "ROOT")
    n = len(group)
    group.extend(
        [
            (",", "PUNCT", ",", "punct", root),
            ("unless", "SCONJ", "unless", "mark", n + 4),
            ("the", "DET", "the", "det", n + 3),
            ("register", "NOUN", "register", "nsubj", n + 4),
            ("is", "AUX", "be", "advcl", root),
            ("blank", "ADJ", "blank", "acomp", n + 4),
            (".", "PUNCT", ".", "punct", root),
        ]
    )
    snapshot, capture = make_source([group])
    source = RoleScopeSource(
        snapshot.body, json.dumps(asdict(snapshot.identity)), snapshot.metadata_json
    )
    finding = inspect_role_contexts(
        RoleScopeManifest(
            (source,),
            {
                "complete": True,
                "reason": None,
                "fixture": "UNITONLY_conditional_NOT_SQL",
            },
        ),
        role("owner"),
        source_windows={
            snapshot.identity.document_id: [
                {"start": w.start, "end": w.end, "capture": json.loads(w.capture_json)}
                for w in capture.windows
            ]
        },
        evidence_profile=actual()["evidence_profile"],
    )
    assert not finding["complete"]


def test_captured_unavailable_source_stays_controlled_incomplete():
    manifest, _ = manifest_and_captures()
    identifier = positive_source()["identity"]["document_id"]
    source = next(
        row for row in manifest.sources if row.identity["document_id"] == identifier
    )
    finding = inspect_role_contexts(
        RoleScopeManifest(
            (source,), {"complete": True, "reason": None, "fixture": "UNITONLY_NOT_SQL"}
        ),
        role("owner"),
        source_windows={identifier: None},
        evidence_profile=actual()["evidence_profile"],
    )
    assert not finding["complete"]
    assert finding["source_closures"][0]["status"] == "unavailable"
