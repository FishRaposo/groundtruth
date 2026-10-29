"""Versioned source ingress uses complete actual request/capture lineage."""

import json
from copy import deepcopy
from dataclasses import asdict

import pytest
from app.evidence_policy import EvidencePolicy
from app.services import contextual_source_proof as legacy
from app.services import planning_declarations as d
from app.services import staged_plan_replay as replay
from app.services import staged_source_proof as proof
from app.services.request_parser import make_capture

from tests.staged_plan_unit837.test_binding import args as catalogue_args
from tests.test_contextual_source_proof import fixture, settings


def inputs():
    body, identity, windows, old, _ = fixture()
    identity["snapshot_id"] = "UNITONLY-immutable-version"
    source_id = d.SourceIdentity(**identity)
    source = d.SourceSnapshot(
        source_id,
        "UNITONLY routine",
        body,
        "{}",
        (d.SourceChunk("UNITONLY-chunk", 0, d.RawRange(0, len(body), body), "{}"),),
    )
    captures = d.SourceCaptures(
        source_id,
        tuple(
            d.CaptureWindow(x["start"], x["end"], d.canonical(x["capture"]))
            for x in windows
        ),
    )
    raw = replay.capture_inputs(
        question=old.question,
        capture=make_capture(json.loads(old.graph_json)),
        manifest=d.PlanningUniverse("{}", (source_id,), "bounded_authorized_scan"),
        snapshots=(source,),
        source_captures=(captures,),
        support_metadata=settings(),
        sql_read_set_json=catalogue_args()["sql_read_set_json"],
        observations=(),
        actual_executions=(),
    )
    actual = {
        source_id.document_id: {
            **asdict(source_id),
            "body": body,
            "title": source.title,
            "metadata": {},
            "chunks": [
                {"id": "UNITONLY-chunk", "index": 0, "content": body, "metadata": {}}
            ],
        }
    }
    return raw, actual, windows, identity, old


def build(raw, actual, windows, identity, old):
    return proof.build_envelope(
        next(iter(actual.values()))["body"],
        identity,
        "Onyx calibration",
        windows,
        question=old.question,
        requirement_id="r1",
        planning_inputs=raw,
        retained_inputs=deepcopy(raw),
        authoritative_snapshots=actual,
        require_runtime=False,
    )


def test_staged_full_procedure_binds_original_request_and_complete_body():
    raw, actual, windows, identity, old = inputs()
    envelope = build(raw, actual, windows, identity, old)
    assert envelope["contract"] == "complete-immutable-procedure-v6"
    assert envelope["reading_profile"] == "contextual_source_v3"
    assert envelope["source_body"] == actual[identity["document_id"]]["body"]
    assert envelope["requirement"]["original_text"] == old.requirements[0].original_text
    assert envelope["request_use"]["governors"]
    assert envelope["request_obligation_inventory"]
    assert envelope["nli_obligations"]
    assert all(
        row["name"] in {"namespace", "applicability"}
        or row["name"].startswith("reference_")
        for row in envelope["nli_obligations"]
    )


def test_staged_source_assessment_replays_without_claiming_output_complete():
    raw, actual, windows, identity, old = inputs()
    envelope = build(raw, actual, windows, identity, old)
    policy = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v3",
    )
    selection = {
        "contract": policy.requirement_contract,
        "evidence_profile": policy.record(),
        "evidence_support": settings(),
        "source_guard_records": [
            {
                "requirement_id": "r1",
                "source_identity": identity,
                "requested_subject": "Onyx calibration",
                "source_windows": windows,
                "envelope_inventory": envelope,
                "nli_assessments": [
                    {
                        **row,
                        "assessment": {
                            "label": "entailment",
                            "logits": [-1, 5, 0],
                            "entailment_margin": 5,
                            "supported": True,
                            "pair_tokens": 80,
                        },
                    }
                    for row in envelope["nli_obligations"]
                ],
            }
        ],
    }
    snapshot = actual[identity["document_id"]]
    result = proof.reconstruct_source_guard(
        selection,
        old.requirements[0],
        snapshot,
        question=old.question,
        planning_inputs=raw,
        retained_inputs=deepcopy(raw),
        authoritative_snapshots=actual,
        require_runtime=False,
    )
    assert result["supported"] is True
    assert (
        result["independent_factual_role_output_access_history"]
        == "required_separately"
    )
    bad = deepcopy(selection)
    bad["source_guard_records"][0]["envelope_inventory"]["source_body"] += "altered"
    with pytest.raises(legacy.SourceGuardError):
        proof.reconstruct_source_guard(
            bad,
            old.requirements[0],
            snapshot,
            question=old.question,
            planning_inputs=raw,
            retained_inputs=deepcopy(raw),
            authoritative_snapshots=actual,
            require_runtime=False,
        )
