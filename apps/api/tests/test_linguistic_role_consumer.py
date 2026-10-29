"""UNITONLY protocol records: no classifier, HTTP, or quality observations."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from app.evidence_policy import EvidencePolicy, reading_version
from app.services.answer_requirements import Requirement
from app.services.linguistic_dependencies import resolve_linguistic_requirement
from app.services.requirement_binding import support_claim
from app.services.role_scope_inspection import (
    RoleScopeManifest,
    RoleScopeSource,
    inspect_role_contexts,
)
from app.services.role_scope_policy import plan_activity_role
from app.services.source_pattern_grammar import collect_source_proposals

from tests.test_contextual_mixed_output import (
    fixture,
    manual_plan,
    mirror,
    observed_proposal,
    output,
    produce,
    role_fixture,
    whole,
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def role_data():
    data = role_fixture()
    selection = data["selection"]
    plan = data["request_reconstructor"](data["question"], {})
    first = plan.requirements[0]
    question = "Who leads ordinary Alder review sessions?"
    original = replace(
        first,
        question=question,
        original_text=question,
        input_start=0,
        input_end=len(question),
        topic="ordinary Alder review sessions",
    )
    manual_plan(data, (original,), question)
    for snapshot in data["source_snapshots"].values():
        snapshot.update(
            workspace_id="ops-a",
            owner_id="owner-a",
            status="ready",
            snapshot_id="20000000-0000-0000-0000-000000000001",
        )
        snapshot["role_live_chunks"] = [
            {**part, "metadata": {}} for part in snapshot["chunks"]
        ]
    for candidate in selection["candidates"]:
        candidate["whole_source_support"]["source_identity"]["workspace_id"] = "ops-a"
    install_role_records(data, original)
    role = plan_activity_role(
        original,
        EvidencePolicy("qa_plus_source_patterns_v1", "ordinary_session_activity_v1"),
    )
    assert role is not None
    prepared = role.prepared("activity")
    chunks, _, _ = output._sources(data["source_snapshots"], selection)
    candidate = selection["candidates"][0]
    entry = chunks[candidate["chunk_id"]]
    raw = candidate["raw_span"]
    observed, proposal = observed_proposal(
        selection, prepared, entry["source"], entry["chunk"], raw["start"], raw["end"]
    )
    old = candidate["proposal"]["proposal_id"]
    selection["qa_observations"] = [observed.record()]
    selection["proposals"] = [
        proposal if p["proposal_id"] == old else p for p in selection["proposals"]
    ]
    candidate["proposal"] = proposal
    selection["requirements"][0]["witnesses"][0]["proposals"][0] = proposal
    selection["requirements"][0]["prepared_question"] = prepared.question
    selection["selected_proposal_ids"] = [
        proposal["proposal_id"] if p == old else p
        for p in selection["selected_proposal_ids"]
    ]
    mirror(data)
    return data


def install_role_records(data, requirement):
    from pathlib import Path

    captures = json.loads(
        (Path(__file__).parent / "fixtures/role_source_captures_v702.json").read_text()
    )
    by_body = {row["body"]: row["source_windows"] for row in captures["sources"]}
    source_windows = {
        identifier: by_body[snapshot["body"]]
        for identifier, snapshot in data["source_snapshots"].items()
    }
    selection = data["selection"]
    records = []
    sources = []
    for _identifier, snapshot in sorted(data["source_snapshots"].items()):
        record = {
            key: snapshot[key]
            for key in (
                "document_id",
                "document_version",
                "content_hash",
                "workspace_id",
                "owner_id",
                "status",
                "snapshot_id",
            )
        }
        record.update(
            metadata_hash=digest(snapshot["metadata"]),
            snapshot_chunk_hash=digest(snapshot["chunks"]),
            live_chunk_hash=digest(snapshot["role_live_chunks"]),
        )
        records.append(record)
        sources.append(
            RoleScopeSource(
                snapshot["body"], json.dumps(record), json.dumps(snapshot["metadata"])
            )
        )
    read_set = {
        "contract": reading_version("contextual_source_v2").role_manifest,
        "document_ids": None,
        "collection_ids": None,
        "workspace_id": "ops-a",
        "complete": True,
        "reason": None,
        "documents": records,
        "limits": {
            "documents": 128,
            "body_bytes": 131072,
            "total_body_bytes": 524288,
            "chunks_per_document": 256,
        },
        "total_body_bytes": sum(
            len(s["body"].encode()) for s in data["source_snapshots"].values()
        ),
        "selector": {"mode": "unavailable", "subjects": [requirement.topic]},
        "index_universe": [
            {
                **{
                    k: r[k]
                    for k in (
                        "document_id",
                        "document_version",
                        "content_hash",
                        "workspace_id",
                        "owner_id",
                    )
                },
                "index_hash": digest(None),
            }
            for r in records
        ],
        "after_proofs": {"consistent": True, "reason": None},
    }
    profile = selection["evidence_profile"]
    policy = EvidencePolicy(
        profile["proposal_profile"],
        profile["role_scope_policy"],
        profile["procedure_verification_profile"],
        profile["source_context_policy"],
        "contextual_source_v2",
    )
    selection.update(
        role_scope_read_set=read_set,
        role_scope_findings=[],
        role_scope_interpretations=[],
    )
    originals = data["request_reconstructor"](data["question"], {}).requirements
    for original in originals:
        role = plan_activity_role(original, policy)
        if role is None:
            continue
        finding = inspect_role_contexts(
            RoleScopeManifest(tuple(sources), read_set),
            role,
            source_windows=source_windows,
        )
        scope = "session" if finding["session_documents"] else "activity"
        record = role.record(scope)
        selection["role_scope_findings"].append(finding)
        selection["role_scope_interpretations"].append(record)
        row = next(r for r in selection["requirements"] if r["id"] == original.id)
        row.update(
            original_text=original.original_text,
            input_range={"start": original.input_start, "end": original.input_end},
            role_scope_inspection=deepcopy(finding),
            role_scope_interpretation=deepcopy(record),
        )
    mirror(data)


def test_public_mixed_replays_activity_fallback_and_renders_disclosure():
    # Break: the mixed verifier rejects every otherwise complete role record.
    actual = produce(role_data())
    assert actual["certificate"]["role_scope"]["findings"][0]["complete"] is True
    disclosure = actual["certificate"]["disclosures"][0]
    assert disclosure["kind"] == "activity_role_scope"
    assert "rather than a separate session assignment" in disclosure["text"]
    offset = disclosure["answer_range"]
    assert actual["answer"][offset["start"] : offset["end"]] == disclosure["text"]
    assert (
        actual["certificate"]["effective_requirements"][0]["requirement"]["question"]
        == "Who leads Alder review?"
    )


@pytest.mark.parametrize(
    "mutation",
    ["finding", "interpretation", "metadata", "body", "receipt", "missing_opponent"],
)
def test_coherent_role_capture_tampering_cannot_replace_authoritative_sources(mutation):
    data = role_data()
    selection = data["selection"]
    if mutation == "finding":
        selection["role_scope_findings"][0]["contexts"][0]["units"][0]["text"] = (
            "invented"
        )
    elif mutation == "interpretation":
        selection["role_scope_interpretations"][0]["activity_scope"] = "Birch review"
    elif mutation == "metadata":
        selection["role_scope_read_set"]["documents"][0]["metadata_hash"] = digest(
            {"condition": "special"}
        )
    elif mutation == "body":
        selection["role_scope_findings"][0]["contexts"][0]["body"] = (
            "The clerk leads Alder review."
        )
    elif mutation == "receipt":
        selection["role_scope_read_set"]["after_proofs"]["consistent"] = 1
    else:
        selection["role_scope_read_set"]["documents"] = []
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_role_history_replays_actual_answer_and_certificate():
    data = role_data()
    actual = produce(data)
    data["selection"][output.CERTIFICATE_FIELD] = actual["certificate"]
    context = {
        k: v for k, v in data.items() if k not in {"selection", "answer", "citations"}
    }
    assert output.verify_output(
        data["selection"],
        answer=actual["answer"],
        citations=actual["citations"],
        **context,
    )
    assert not output.verify_output(
        data["selection"],
        answer=actual["answer"] + " changed",
        citations=actual["citations"],
        **context,
    )


def add_source(data, body, number):
    identifier = f"00000000-0000-0000-0000-{number:012d}"
    snapshot: dict[str, Any] = {
        "document_id": identifier,
        "document_version": 3,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
        "workspace_id": "ops-a",
        "owner_id": "owner-a",
        "status": "ready",
        "metadata": {},
        "body": body,
        "snapshot_id": f"20000000-0000-0000-0000-{number:012d}",
        "chunks": [
            {
                "id": f"10000000-0000-0000-0000-{number:012d}",
                "index": 0,
                "content": body,
            }
        ],
    }
    snapshot["role_live_chunks"] = [{**p, "metadata": {}} for p in snapshot["chunks"]]
    data["source_snapshots"][identifier] = snapshot
    return identifier


def rebuild_rows(data, effective, values):
    """Manufactured protocol inputs only; literal assertions below are oracles."""
    selection = data["selection"]
    originals = data["request_reconstructor"](data["question"], {}).requirements
    for name in (
        "requirements",
        "candidates",
        "proposals",
        "qa_observations",
        "selected_proposal_ids",
        "pattern_observations",
        "inspected_sources",
    ):
        selection[name] = []
    for snapshot in data["source_snapshots"].values():
        selection["inspected_sources"].extend(
            [
                {
                    "chunk_id": p["id"],
                    **{
                        k: snapshot[k]
                        for k in ("document_id", "document_version", "content_hash")
                    },
                }
                for p in snapshot["chunks"]
            ]
        )
    chunks, _, sources = output._sources(data["source_snapshots"], selection)
    reader = {
        "mode": "reader",
        "contract": selection["reader_contract"],
        "model": selection["model"],
        "revision": selection["revision"],
        "threshold": selection["threshold"],
    }
    # observed_proposal uses this actual boundary schema, overwritten per row.
    selection["qa_observations"] = [{"reader": reader}]
    for original in originals:
        req, binding = effective[original.id]
        identifier, value = values[req.id]
        source = next(s for s in sources if s.identity["document_id"] == identifier)
        chunk = source.chunks[0].chunk
        a = chunk.content.index(value)
        b = a + len(value)
        observed, proposal = observed_proposal(selection, req, source, chunk, a, b)
        batch = collect_source_proposals(
            req, [source], reading_profile="contextual_source_v2"
        )
        patterns = [p.record() for p in batch.proposals]
        claim = support_claim(
            req, chunk.content, a, b, reading_profile="contextual_source_v2"
        )
        assert not claim.rejection and not claim.checks and not claim.proof_edges
        member = chunks[chunk.id]["identity"]
        assessment = {
            "label": "entailment",
            "logits": [-1.0, 5.0, 0.0],
            "entailment_margin": 5.0,
            "supported": True,
            "pair_tokens": 28,
        }
        span = {
            "start": claim.support_start,
            "end": claim.support_end,
            "text": chunk.content[claim.support_start : claim.support_end],
        }
        candidate = dict(
            **member,
            requirement_id=req.id,
            raw_span={"start": a, "end": b},
            null_margin=-3.0,
            hypothesis=claim.hypothesis,
            validated_answer_span={
                "start": claim.start,
                "end": claim.end,
                "text": claim.value,
            },
            condition="applies",
            decision="supported",
            proof_edges=[],
            primary_support_range={
                "start": claim.premise_start,
                "end": claim.premise_end,
            },
            support=assessment,
            support_checks=[],
            origin="qa_reader",
            proposal=proposal,
            duplicate_proposals=patterns,
        )
        candidate["whole_source_support"] = whole(
            candidate, data["source_snapshots"][identifier]
        )
        witness = dict(
            **member,
            value=claim.value,
            span=span,
            document_range={k: span[k] for k in ("start", "end")},
            entailment_margin=5.0,
            proof_edges=[],
            proposals=[proposal, *patterns],
        )
        selection["requirements"].append(
            dict(
                id=original.id,
                kind=original.kind,
                original_text=original.original_text,
                input_range={"start": original.input_start, "end": original.input_end},
                prepared_question=req.question,
                source_workspace=original.source_workspace,
                depends_on=list(original.depends_on),
                status="supported",
                witnesses=[witness],
                **({"dependency_binding": binding} if binding else {}),
            )
        )
        selection["candidates"].append(candidate)
        if (
            len(selection["qa_observations"]) == 1
            and "observation_id" not in selection["qa_observations"][0]
        ):
            selection["qa_observations"] = []
        selection["qa_observations"].append(observed.record())
        selection["proposals"].extend([proposal, *patterns])
        selection["pattern_observations"].extend(batch.observations)
        selection["selected_proposal_ids"].extend(
            p["proposal_id"] for p in [proposal, *patterns]
        )
    mirror(data)


def session_data(*, dependent=False):
    data = role_data()
    original = data["request_reconstructor"](data["question"], {}).requirements[0]
    doc = add_source(data, "The clerk leads Alder review sessions.", 2)
    role = plan_activity_role(
        original,
        EvidencePolicy("qa_plus_source_patterns_v1", "ordinary_session_activity_v1"),
    )
    assert role is not None
    effective = {original.id: (role.prepared("session"), {})}
    values = {original.id: (doc, "The clerk")}
    if dependent:
        question = data["question"] + " What is that role's availability?"
        text = "What is that role's availability?"
        second = Requirement(
            "r2",
            text,
            question.index(text),
            len(question),
            text,
            "availability",
            "that role",
            (),
            depends_on=("r1",),
            relation="availability",
            attribute="availability",
        )
        manual_plan(data, (original, second), question)
        callback = data["request_reconstructor"]
        left = question.index("that role")

        def planned(actual, context):
            plan = callback(actual, context)
            plan.uses = (
                SimpleNamespace(
                    requirement_id="r2",
                    references=(
                        SimpleNamespace(start=left, end=left + 9, text="that role"),
                    ),
                ),
            )
            return plan

        data["request_reconstructor"] = planned
        bound, binding = resolve_linguistic_requirement(
            second, planned(question, {}), {"r1": "The clerk"}
        )
        effective["r2"] = (bound, binding)
        third = add_source(data, "The clerk is available from 09:00 to 11:00.", 3)
        values["r2"] = (third, "09:00 to 11:00")
    rebuild_rows(data, effective, values)
    install_role_records(data, original)
    return data


def test_explicit_session_assignment_precedes_activity_without_fallthrough():
    actual = produce(session_data())
    role = actual["certificate"]["role_scope"]
    assert role["interpretations"][0]["effective_scope"] == "session"
    assert not actual["certificate"]["disclosures"]
    assert "The clerk" in actual["answer"] and "archivist" not in actual["answer"]


def test_positive_activity_scores_cannot_bypass_a_retained_session_assignment():
    data = role_data()
    original = data["request_reconstructor"](data["question"], {}).requirements[0]
    identifier = add_source(data, "The clerk leads Alder review sessions.", 2)
    snapshot = data["source_snapshots"][identifier]
    data["selection"]["inspected_sources"].append(
        {
            "chunk_id": snapshot["chunks"][0]["id"],
            **{
                k: snapshot[k]
                for k in ("document_id", "document_version", "content_hash")
            },
        }
    )
    install_role_records(data, original)
    with pytest.raises(ValueError, match="preferred session"):
        produce(data)


def test_dependent_availability_uses_the_selected_session_role_across_documents():
    actual = produce(session_data(dependent=True))
    dependent = actual["certificate"]["effective_requirements"][1]
    assert dependent["requirement"]["question"] == "What is The clerk's availability?"
    assert dependent["dependency_binding"]["bindings"][0]["source_value"] == "The clerk"
    assert len(actual["citations"]) == 2
    assert {
        p["origin"]
        for g in actual["certificate"]["assessed_inventory"]
        for p in g["origins"]
    } == {"qa_reader", "source_pattern"}


@pytest.mark.parametrize(
    "body",
    [
        "Follow the qualification appendix.",
        "For Alder review sessions unless appointed, the lead is the clerk.",
        (
            "The clerk leads Alder review sessions. "
            "The registrar leads Alder review sessions."
        ),
    ],
)
def test_unknown_governing_or_conflicting_source_cannot_be_declared_irrelevant(body):
    data = role_data()
    original = data["request_reconstructor"](data["question"], {}).requirements[0]
    add_source(data, body, 2)
    install_role_records(data, original)
    with pytest.raises(ValueError):
        produce(data)


def test_missing_role_opponent_is_detected_even_after_coherent_record_rewrite():
    data = session_data()
    selection = data["selection"]
    omitted = selection["role_scope_read_set"]["documents"].pop()
    selection["role_scope_read_set"]["total_body_bytes"] -= len(
        data["source_snapshots"][omitted["document_id"]]["body"].encode()
    )
    for finding in selection["role_scope_findings"]:
        finding["contexts"] = finding["contexts"][:1]
        finding["session_documents"] = []
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_publication_annotation_is_typed_and_stable_for_history():
    data = role_data()
    first = produce(data)
    data["selection"]["role_scope_read_set"]["before_publication"] = {
        "consistent": True,
        "reason": None,
    }
    assert produce(data) == first
    data["selection"]["role_scope_read_set"]["before_publication"]["consistent"] = 1
    with pytest.raises(ValueError):
        produce(data)


def test_legacy_source_limit_remains_64_and_mixed_profile_allows_128():
    from app.services import contextual_output

    data = fixture()
    data["source_snapshots"] = {}
    for number in range(1, 130):
        add_source(data, f"The inventory entry is {number}.", number)
    snapshots = data["source_snapshots"]
    with pytest.raises(ValueError):
        contextual_output._source_inventory(dict(list(snapshots.items())[:65]))
    assert (
        len(
            contextual_output._source_inventory(
                dict(list(snapshots.items())[:128]),
                max_documents=reading_version("contextual_source_v2").scope_documents,
            )[1]
        )
        == 128
    )
    with pytest.raises(ValueError):
        contextual_output._source_inventory(
            snapshots,
            max_documents=reading_version("contextual_source_v2").scope_documents,
        )
    selected = dict(list(snapshots.items())[:128])
    data["selection"]["inspected_sources"] = [
        {
            "chunk_id": snapshot["chunks"][0]["id"],
            **{
                k: snapshot[k]
                for k in ("document_id", "document_version", "content_hash")
            },
        }
        for snapshot in selected.values()
    ]
    assert len(output._sources(selected, data["selection"])[1]) == 128
    with pytest.raises(ValueError):
        output._sources(snapshots, data["selection"])


def test_default_immutable_request_replay_consumes_both_activity_roles():
    from app.services.linguistic_requirements import plan_request

    from tests.test_linguistic_requirements import actual_capture

    question = (
        "For the ordinary Onyx calibration session, identify the lead and deputy."
    )
    capture = actual_capture(question)
    plan = plan_request(question, capture)
    assert plan.resolved_request
    data = fixture()
    data["question"] = question
    data["source_snapshots"] = {}
    identifier = add_source(
        data,
        (
            "The archivist leads Onyx calibration. "
            "The clerk is deputy for Onyx calibration."
        ),
        1,
    )
    data["request_reconstructor"] = lambda actual, context: plan
    data["selection"]["request_plan"] = plan.record()
    data["selection"]["request_capture"] = capture
    effective = {}
    profile = data["selection"]["evidence_profile"]
    policy = EvidencePolicy(
        profile["proposal_profile"],
        profile["role_scope_policy"],
        profile["procedure_verification_profile"],
        profile["source_context_policy"],
        "contextual_source_v2",
    )
    for req in plan.requirements:
        role = plan_activity_role(req, policy)
        assert role is not None
        effective[req.id] = (role.prepared("activity"), {})
    rebuild_rows(
        data,
        effective,
        {"r1": (identifier, "The archivist"), "r2": (identifier, "The clerk")},
    )
    install_role_records(data, plan.requirements[0])
    data["request_reconstructor"] = None
    actual = produce(data)
    assert len(actual["certificate"]["role_scope"]["interpretations"]) == 2
    assert len(actual["certificate"]["disclosures"]) == 2
    assert actual["certificate"]["request_plan"] == plan.record()


def test_nominal_lead_inflection_is_v2_only_and_keeps_original_requirement():
    data = role_data()
    req = data["request_reconstructor"](data["question"], {}).requirements[0]
    req = replace(req, relation="lead")
    old = EvidencePolicy("qa_plus_source_patterns_v1", "ordinary_session_activity_v1")
    assert plan_activity_role(req, old) is None
    profile = data["selection"]["evidence_profile"]
    policy = EvidencePolicy(
        profile["proposal_profile"],
        profile["role_scope_policy"],
        profile["procedure_verification_profile"],
        profile["source_context_policy"],
        "contextual_source_v2",
    )
    role = plan_activity_role(req, policy)
    assert role is not None and role.requirement is req
    assert req.relation == "lead" and role.prepared("activity").relation == "leads"
    for relation in ("owns", "responsible", "coordinates", "may_lead"):
        assert plan_activity_role(replace(req, relation=relation), policy) is None
