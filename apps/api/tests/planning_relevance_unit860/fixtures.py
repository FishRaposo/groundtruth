"""UNITONLY source/capture/trace fixtures, explicit actual bridge opt-in."""

import json
import uuid
from copy import deepcopy
from dataclasses import asdict, replace

from app.services import planning_support as support
from app.services.planning_scope_bridge import reconstruct_scope_bridge
from app.services.staged_plan_replay import capture_inputs, reconstruct_request
from app.services.staged_request import compile_request

from tests.planning_library_unit830.test_support import retained
from tests.staged_plan_unit837.fixtures_request import LABELS
from tests.staged_plan_unit837.fixtures_source import ASSIGN, CAT, NAME, source
from tests.staged_plan_unit837.test_binding import args


def routine(namespace="Larch", *, qualified=False):
    rows = [
        ("This", "DET", "this", "det", 1),
        ("note", "NOUN", "note", "nsubj", 2),
        ("applies", "VERB", "apply", "ROOT", 2),
        ("to", "ADP", "to", "prep", 2),
        (namespace, "PROPN", namespace, "compound", 5),
        ("inspection", "NOUN", "inspection", "pobj", 3),
    ]
    if qualified:
        rows.extend(
            [
                ("before", "ADP", "before", "prep", 5),
                ("approval", "NOUN", "approval", "pobj", 6),
            ]
        )
    rows.append((".", "PUNCT", ".", "punct", 2))
    return source(
        [
            rows,
            [
                ("Move", "VERB", "move", "ROOT", 0),
                ("the", "DET", "the", "det", 2),
                ("card", "NOUN", "card", "dobj", 0),
                (".", "PUNCT", ".", "punct", 0),
            ],
        ],
        doc="UNITONLY-routine",
    )


def raw(*, extra=None, groups=(NAME, CAT, ASSIGN), rows=LABELS):
    actual = args(
        rows=rows, groups=groups, extra=(routine(),) if extra is None else extra
    )
    actual["support_metadata"]["minimum_entailment_margin"] = 2.0
    snapshots, captures = [], []
    for index, (snapshot, capture) in enumerate(
        zip(actual["snapshots"], actual["source_captures"], strict=True)
    ):
        identity = replace(
            snapshot.identity,
            document_id=str(uuid.UUID(int=8600 + index)),
            snapshot_id=str(uuid.UUID(int=860000 + index)),
        )
        chunks = tuple(
            replace(chunk, chunk_id=str(uuid.UUID(int=86000 + index * 10 + number)))
            for number, chunk in enumerate(snapshot.chunks)
        )
        snapshots.append(replace(snapshot, identity=identity, chunks=chunks))
        captures.append(replace(capture, identity=identity))
    actual.update(
        manifest=replace(
            actual["manifest"], publications=tuple(s.identity for s in snapshots)
        ),
        snapshots=tuple(snapshots),
        source_captures=tuple(captures),
    )
    return actual


def bridge(actual):
    return reconstruct_scope_bridge(
        compile_request(actual["question"], actual["capture"]),
        actual["manifest"],
        actual["snapshots"],
        actual["source_captures"],
    )


def prepare(actual, *, opt_in=True):
    selected = {
        key: value
        for key, value in actual.items()
        if key not in {"observations", "actual_executions"}
    }
    if opt_in:
        selected["scope_bridge_record"] = bridge(actual)
    return support.prepare_planning_assertions(**selected)


def retained_inputs(actual):
    selected = deepcopy(actual)
    selected["observations"], selected["actual_executions"] = retained(
        prepare(selected)
    )
    inputs = capture_inputs(**selected)
    snapshots = {
        row.identity.document_id: {
            **asdict(row.identity),
            "title": row.title,
            "body": row.body,
            "metadata": json.loads(row.metadata_json),
            "chunks": [
                {
                    "id": chunk.chunk_id,
                    "index": chunk.ordinal,
                    "content": chunk.literal.text,
                    "metadata": json.loads(chunk.metadata_json),
                }
                for chunk in row.chunks
            ],
        }
        for row in selected["snapshots"]
    }
    plan = reconstruct_request(
        inputs,
        question=selected["question"],
        retained_inputs=deepcopy(inputs),
        authoritative_snapshots=snapshots,
        require_runtime=False,
    )
    return {
        "question": selected["question"],
        "planning_inputs": inputs,
        "retained_inputs": deepcopy(inputs),
        "authoritative_snapshots": snapshots,
        "require_runtime": False,
    }, plan
