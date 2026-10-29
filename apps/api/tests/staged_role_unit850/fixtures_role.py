"""Immutable UUID/chunk mapped UNITONLY sources; no physical model observation."""

import json
import uuid
from copy import deepcopy
from dataclasses import replace

from app.services import planning_declarations as d
from app.services import planning_support as support
from app.services.staged_plan_replay import (
    _arguments,
    capture_inputs,
    reconstruct_request,
)

from tests.planning_library_unit830.test_support import retained
from tests.staged_plan_unit837.fixtures_request import ACTORS, LABELS
from tests.staged_plan_unit837.fixtures_source import ASSIGN, CAT, NAME
from tests.staged_plan_unit837.test_binding import args


def role_inputs(rows=LABELS, groups=(NAME, CAT, ASSIGN), extra=()):
    actual = args(rows=rows, groups=groups, extra=extra)
    # Settings captures this actual public threshold as float, including when
    # the caller supplied2; keep the fixture's model receipt byte-compatible.
    actual["support_metadata"]["minimum_entailment_margin"] = 2.0
    snapshots, captures = [], []
    for index, (snapshot, capture) in enumerate(
        zip(actual["snapshots"], actual["source_captures"], strict=True)
    ):
        identity = replace(
            snapshot.identity,
            document_id=str(uuid.UUID(int=8500 + index)),
            snapshot_id="UNITONLY850-snapshot-" + str(index),
        )
        metadata = d.canonical(
            {
                "document_version": identity.document_version,
                "content_hash": identity.content_hash,
                "workspace_id": identity.workspace_id,
            }
        )
        chunks = tuple(
            replace(
                chunk,
                chunk_id=str(uuid.UUID(int=85000 + index * 10 + number)),
                metadata_json=metadata,
            )
            for number, chunk in enumerate(snapshot.chunks)
        )
        snapshots.append(replace(snapshot, identity=identity, chunks=chunks))
        captures.append(replace(capture, identity=identity))
    actual.update(
        manifest=replace(
            actual["manifest"],
            publications=tuple(snapshot.identity for snapshot in snapshots),
        ),
        snapshots=tuple(snapshots),
        source_captures=tuple(captures),
    )
    prepared = support.prepare_planning_assertions(
        **{
            key: value
            for key, value in actual.items()
            if key not in {"observations", "actual_executions"}
        }
    )
    actual["observations"], actual["actual_executions"] = retained(prepared)
    planning = capture_inputs(**actual)
    authority = {
        snapshot.identity.document_id: {
            **d.asdict(snapshot.identity),
            "title": snapshot.title,
            "body": snapshot.body,
            "metadata": json.loads(snapshot.metadata_json),
            "chunks": [
                {
                    "id": chunk.chunk_id,
                    "index": chunk.ordinal,
                    "content": chunk.literal.text,
                    "metadata": json.loads(chunk.metadata_json),
                }
                for chunk in snapshot.chunks
            ],
        }
        for snapshot in snapshots
    }
    inputs = {
        "question": actual["question"],
        "planning_inputs": planning,
        "retained_inputs": deepcopy(planning),
        "authoritative_snapshots": authority,
        "require_runtime": False,
    }
    plan = reconstruct_request(
        planning,
        question=actual["question"],
        retained_inputs=planning,
        authoritative_snapshots=authority,
        require_runtime=False,
    )
    return inputs, plan


def select(inputs, plan, kind):
    requirement = next(row for row in plan.requirements if row.kind == kind)
    return {**inputs, "requirement_id": requirement.id}


def actor_inputs():
    inputs, plan = role_inputs(rows=ACTORS)
    return select(inputs, plan, "role_assignment")


def role_receipts(prepared, *, neutral_whole=False):
    observations, executions = [], []
    for index, check in enumerate(prepared.checks):
        neutral = neutral_whole and check.kind == "staged_role_whole_body"
        assessment = d.canonical(
            {
                "label": "neutral" if neutral else "entailment",
                "logits": [-3.0, 0.0, 3.0] if neutral else [-3.0, 3.0, 0.0],
                "entailment_margin": -3.0 if neutral else 3.0,
                "supported": not neutral,
                "pair_tokens": 40,
            }
        )
        identifier = "UNITONLY850-role-" + str(index)
        executions.append(
            support.NliExecution(
                identifier,
                check.id,
                check.pair,
                prepared.support_metadata_json,
                assessment,
                40,
                "UNITONLY",
            )
        )
        observations.append(
            support.NliObservation(
                check.id,
                identifier,
                check.pair,
                prepared.support_metadata_json,
                assessment,
            )
        )
    return tuple(observations), tuple(executions)


def split_source(inputs, offset):
    result = deepcopy(inputs)
    row = result["planning_inputs"]["snapshots"][0]
    body = row["body"]
    metadata = row["chunks"][0]["metadata_json"]
    row["chunks"] = [
        {
            "chunk_id": str(uuid.UUID(int=85900 + index)),
            "ordinal": index,
            "literal": {"start": start, "end": end, "text": body[start:end]},
            "metadata_json": metadata,
        }
        for index, (start, end) in enumerate(((0, offset), (offset, len(body))))
    ]
    authority = result["authoritative_snapshots"][row["identity"]["document_id"]]
    authority["chunks"] = [
        {
            "id": chunk["chunk_id"],
            "index": chunk["ordinal"],
            "content": chunk["literal"]["text"],
            "metadata": json.loads(chunk["metadata_json"]),
        }
        for chunk in row["chunks"]
    ]
    typed = _arguments(result["planning_inputs"], result["authoritative_snapshots"])
    prepared = support.prepare_planning_assertions(
        **{
            key: value
            for key, value in typed.items()
            if key not in {"observations", "actual_executions"}
        }
    )
    typed["observations"], typed["actual_executions"] = retained(prepared)
    result["planning_inputs"] = capture_inputs(**typed)
    result["retained_inputs"] = deepcopy(result["planning_inputs"])
    return result
