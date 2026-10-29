"""Catch trusted flags, retained-channel replacement and incomplete raw replay."""

import json
from copy import deepcopy

import pytest
from app.services import captured_plan_inputs as transport
from app.services import staged_plan_binding, staged_plan_replay

from .fixtures import arguments, authoritative, profile


@pytest.fixture(scope="module")
def encoded():
    return transport.capture_inputs_v2(**arguments(), evidence_profile=profile())


def decode(record, *, retained=None, snapshots=None, question=None):
    return transport.decode_inputs_v2(
        record,
        question=question if question is not None else record["question"],
        authoritative_snapshots=snapshots
        if snapshots is not None
        else authoritative(record),
        retained_inputs=deepcopy(record) if retained is None else retained,
    )


@pytest.mark.parametrize("field", ["request_productions", "source_productions"])
def test_full_records_are_replayed_even_when_both_presented_and_retained_are_forged(
    encoded, field
):
    record = deepcopy(encoded)
    record[field]["source_NI_authority_currentness"] = "VERIFIED"
    with pytest.raises(ValueError):
        decode(record)


@pytest.mark.parametrize(
    "field",
    [
        "contract",
        "question",
        "capture",
        "manifest",
        "snapshots",
        "source_captures",
        "support_metadata",
        "sql_read_set_json",
        "observations",
        "actual_executions",
        "evidence_profile",
        "request_productions",
        "source_productions",
    ],
)
def test_every_separately_retained_channel_must_match(encoded, field):
    retained = deepcopy(encoded)
    retained[field] = None
    with pytest.raises(ValueError):
        decode(encoded, retained=retained)


@pytest.mark.parametrize(
    "field",
    [
        "body",
        "title",
        "metadata",
        "document_id",
        "document_version",
        "workspace_id",
        "snapshot_id",
        "content_hash",
        "chunks",
    ],
)
def test_authoritative_source_is_independent_of_both_transport_records(encoded, field):
    snapshots = authoritative(encoded)
    row = next(iter(snapshots.values()))
    row[field] = (
        [] if field == "chunks" else 2 if field == "document_version" else "forged"
    )
    with pytest.raises(ValueError):
        decode(encoded, snapshots=snapshots)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "old",
        "wrong_question",
        "native_tuple",
        "bool_version",
        "body",
        "chunk_literal",
    ],
)
def test_invalid_structural_views_and_profile_downgrades_fail_closed(encoded, mutation):
    record = deepcopy(encoded)
    question = record["question"]
    if mutation == "missing":
        del record["request_productions"]
    elif mutation == "extra":
        record["producer_success"] = True
    elif mutation == "old":
        record["contract"] = "staged-request-inputs-v1"
    elif mutation == "wrong_question":
        question += " extra"
    elif mutation == "native_tuple":
        record["observations"] = ()
    elif mutation == "bool_version":
        record["snapshots"][0]["identity"]["document_version"] = True
    elif mutation == "body":
        record["snapshots"][0]["body"] += " unseen"
    elif mutation == "chunk_literal":
        record["snapshots"][0]["chunks"][0]["literal"]["text"] += " unseen"
    with pytest.raises(ValueError):
        decode(record, question=question)


@pytest.mark.parametrize(
    "mutation",
    [
        "capture_hash",
        "source_tail",
        "duplicate_source",
        "missing_source",
        "capture_identity",
        "profile",
        "readset",
        "depth",
    ],
)
def test_capture_membership_and_native_budget_tampers_fail_closed(encoded, mutation):
    record = deepcopy(encoded)
    if mutation == "capture_hash":
        record["capture"]["capture_sha256"] = "0" * 64
    elif mutation == "source_tail":
        record["source_captures"][0]["windows"][-1]["end"] -= 1
    elif mutation == "duplicate_source":
        record["snapshots"].append(deepcopy(record["snapshots"][0]))
    elif mutation == "missing_source":
        record["snapshots"].pop()
        record["source_captures"].pop()
    elif mutation == "capture_identity":
        record["source_captures"][0]["identity"]["snapshot_id"] += "-other"
    elif mutation == "profile":
        record["evidence_profile"]["scope_document_limit"] = 999
    elif mutation == "readset":
        record["sql_read_set_json"] = "{ }"
    else:
        nested = {}
        for _ in range(34):
            nested = {"child": nested}
        record["support_metadata"] = nested
    with pytest.raises(ValueError):
        decode(record)


def test_wire_roundtrip_is_detached_and_never_calls_legacy_semantic_planner(
    encoded, monkeypatch
):
    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Old semantic planner must not resolve new input transport"
        )

    monkeypatch.setattr(staged_plan_binding, "reconstruct_staged_plan", forbidden)
    monkeypatch.setattr(staged_plan_replay, "reconstruct_staged_plan", forbidden)
    record = json.loads(json.dumps(encoded))
    result = decode(record)
    assert result.arguments == arguments()
    assert not result.request_productions["complete_plan"]
    assert not result.source_productions["full_plan_accepted"]
    assert (
        result.source_productions["source_NI_authority_currentness"] == "NOT_ASSESSED"
    )
    result.arguments["capture"]["annotation"]["tokens"][0]["pos"] = "forged"
    result.request_productions["productions"].clear()
    result.evidence_profile.clear()
    assert record == encoded
