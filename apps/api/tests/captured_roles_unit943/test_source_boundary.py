"""UNITONLY partition change keeps original bodies/captures; no truncation."""

from copy import deepcopy
from dataclasses import replace

import pytest
from app.services import captured_planning_support as support
from app.services import captured_role_evidence as role
from app.services import planning_declarations as source
from app.services.captured_plan_inputs import capture_inputs_v2

from tests.captured_inputs_unit932.fixtures import authoritative
from tests.captured_plan_unit937.test_adversarial import supported
from tests.planning_library_unit830.test_support import retained


def test_source_clause_split_across_chunks_refuses_without_body_or_question_rewrite():
    args, plan = supported("labels")
    snapshot = args["snapshots"][0]
    inventory = source.declaration_inventory(
        args["manifest"], args["snapshots"], args["source_captures"]
    )
    catalogue = next(r for r in inventory.declarations if r.kind == "role_catalogue")
    cut = catalogue.raw.start + 1
    first = source.SourceChunk(
        snapshot.chunks[0].chunk_id, 0, source.RawRange(0, cut, snapshot.body[:cut])
    )
    second = source.SourceChunk(
        "00000000-0000-0000-0000-000000094301",
        1,
        source.RawRange(cut, len(snapshot.body), snapshot.body[cut:]),
    )
    args["snapshots"] = (
        replace(snapshot, chunks=(first, second)),
        *args["snapshots"][1:],
    )
    prepared = support.prepare_planning_assertions(
        **{
            k: v
            for k, v in args.items()
            if k not in {"observations", "actual_executions"}
        }
    )
    observations, executions = retained(prepared)
    args.update(observations=observations, actual_executions=executions)
    record = capture_inputs_v2(**args)
    assert (
        record["question"] == plan.question
        and record["snapshots"][0]["body"] == snapshot.body
    )
    with pytest.raises(role.RoleSourceUnrepresentable):
        role.prepare_role_evidence(
            requirement_id=plan.requirements[0].id,
            question=args["question"],
            planning_inputs=record,
            retained_inputs=deepcopy(record),
            authoritative_snapshots=authoritative(record),
            require_runtime=False,
        )
