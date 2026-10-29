"""Captured request/source integration; only retained UNITONLY planning logits."""

import json
from dataclasses import asdict

from app.services import staged_source_proof
from app.services.captured_plan_inputs import capture_inputs_v2

from tests.captured_inputs_unit932.fixtures import authoritative
from tests.captured_plan_unit937.test_adversarial import supported


def test_original_complete_procedure_is_bound_through_new_request_inputs():
    args, plan = supported("same-activity-full")
    assert plan.resolved_request
    record = capture_inputs_v2(**args)
    snapshots = authoritative(record)
    requirement = next(row for row in plan.requirements if row.kind == "procedure")
    snapshot = next(row for row in args["snapshots"] if "Frobnicate" in row.body)
    captured = next(
        row for row in args["source_captures"] if row.identity == snapshot.identity
    )
    windows = [
        {"start": row.start, "end": row.end, "capture": json.loads(row.capture_json)}
        for row in captured.windows
    ]
    envelope = staged_source_proof.build_envelope(
        snapshot.body,
        asdict(snapshot.identity),
        requirement.topic,
        windows,
        question=args["question"],
        requirement_id=requirement.id,
        planning_inputs=record,
        retained_inputs=record,
        authoritative_snapshots=snapshots,
        require_runtime=False,
        reading_profile="contextual_source_v4",
    )
    assert envelope["contract"] == "complete-immutable-procedure-v7"
    assert envelope["reading_profile"] == "contextual_source_v4"
    assert envelope["source_body"] == snapshot.body
