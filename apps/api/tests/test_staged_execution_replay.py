"""Retained execution inputs cannot establish their own source truth."""

import json
from copy import deepcopy
from dataclasses import asdict

import pytest
from app.services import staged_plan_binding as binding
from app.services import staged_plan_replay as replay

from tests.staged_plan_unit837.test_binding import args


def example():
    inputs = args()
    record = replay.capture_inputs(**inputs)
    snapshots = {
        s.identity.document_id: {
            **asdict(s.identity),
            "body": s.body,
            "title": s.title,
            "metadata": json.loads(s.metadata_json),
            "chunks": [
                {
                    "id": c.chunk_id,
                    "index": c.ordinal,
                    "content": c.literal.text,
                    "metadata": json.loads(c.metadata_json),
                }
                for c in s.chunks
            ],
        }
        for s in inputs["snapshots"]
    }
    plan = binding.reconstruct_staged_plan(**inputs).record()
    return inputs, record, snapshots, plan


def test_reconstructs_actual_whole_plan_from_independent_inputs():
    inputs, record, snapshots, plan = example()
    actual = replay.reconstruct_request(
        record,
        question=inputs["question"],
        authoritative_snapshots=snapshots,
        retained_inputs=deepcopy(record),
    )
    assert actual.record() == plan
    assert actual.resolved_request
    assert actual.answer_fact_nli == "NOT_ASSESSED"
    assert actual.output_history == "NOT_ASSESSED"


@pytest.mark.parametrize(
    "field",
    [
        "body",
        "content_hash",
        "document_version",
        "workspace_id",
        "snapshot_id",
        "chunks",
        "title",
        "metadata",
    ],
)
def test_independent_snapshot_changes_are_not_source_truth(field):
    inputs, record, snapshots, _ = example()
    source = next(iter(snapshots.values()))
    source[field] = (
        [] if field == "chunks" else 99 if field == "document_version" else "tampered"
    )
    with pytest.raises(ValueError):
        replay.reconstruct_request(
            record,
            question=inputs["question"],
            authoritative_snapshots=snapshots,
            retained_inputs=deepcopy(record),
        )


@pytest.mark.parametrize(
    "mutation", ["capture", "source", "observations", "executions", "sql", "extra"]
)
def test_presented_receipt_cannot_replace_retained_execution(mutation):
    inputs, record, snapshots, _ = example()
    actual = deepcopy(record)
    if mutation == "capture":
        actual["capture"] = {}
    elif mutation == "source":
        actual["snapshots"] = []
    elif mutation == "observations":
        actual["observations"] = []
    elif mutation == "executions":
        actual["actual_executions"] = []
    elif mutation == "sql":
        actual["sql_read_set_json"] = "{}"
    else:
        actual["approved"] = True
    with pytest.raises(ValueError):
        replay.reconstruct_request(
            actual,
            question=inputs["question"],
            authoritative_snapshots=snapshots,
            retained_inputs=record,
        )


def test_missing_retained_capture_never_infers_execution():
    inputs, record, snapshots, _ = example()
    with pytest.raises(ValueError):
        replay.reconstruct_request(
            record,
            question=inputs["question"],
            authoritative_snapshots=snapshots,
            retained_inputs=None,
        )


def test_runtime_mode_rejects_explicit_unitonly_receipt():
    inputs, record, snapshots, _ = example()
    with pytest.raises(ValueError, match="runtime"):
        replay.reconstruct_request(
            record,
            question=inputs["question"],
            authoritative_snapshots=snapshots,
            retained_inputs=deepcopy(record),
            require_runtime=True,
        )
