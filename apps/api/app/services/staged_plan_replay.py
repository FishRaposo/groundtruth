"""Replay staged planning from retained execution and authoritative snapshots.

This validates represented request semantics, not factual answers, permissions,
source applicability, completeness of catalogues, or publication/history output.
"""

import json
from dataclasses import asdict

from app.services import planning_declarations as declarations
from app.services import planning_support as support
from app.services.staged_plan_binding import reconstruct_staged_plan

CONTRACT = "staged-request-inputs-v1"
canonical = declarations.canonical
_FIELDS = frozenset(
    {
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
    }
)


def capture_inputs(
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    *,
    support_metadata,
    sql_read_set_json,
    observations,
    actual_executions,
):
    """Detach actual typed runtime inputs; this alone grants no execution proof."""
    return json.loads(
        canonical(
            {
                "contract": CONTRACT,
                "question": question,
                "capture": capture,
                "manifest": asdict(manifest),
                "snapshots": [asdict(row) for row in snapshots],
                "source_captures": [asdict(row) for row in source_captures],
                "support_metadata": support_metadata,
                "sql_read_set_json": sql_read_set_json,
                "observations": [asdict(row) for row in observations],
                "actual_executions": [asdict(row) for row in actual_executions],
            }
        )
    )


def _snapshot(row):
    return declarations.SourceSnapshot(
        **{
            **row,
            "identity": declarations.SourceIdentity(**row["identity"]),
            "chunks": tuple(
                declarations.SourceChunk(
                    **{**chunk, "literal": declarations.RawRange(**chunk["literal"])}
                )
                for chunk in row["chunks"]
            ),
        }
    )


def _captures(row):
    return declarations.SourceCaptures(
        **{
            **row,
            "identity": declarations.SourceIdentity(**row["identity"]),
            "windows": tuple(
                declarations.CaptureWindow(**window) for window in row["windows"]
            ),
        }
    )


def _actual_source(snapshot, authoritative_snapshots):
    identity = asdict(snapshot.identity)
    actual = authoritative_snapshots[identity["document_id"]]
    for key, value in {
        **identity,
        "body": snapshot.body,
        "title": snapshot.title,
    }.items():
        if type(actual.get(key)) is not type(value) or actual[key] != value:
            raise ValueError("Independent planning snapshot differs: " + key)
    if canonical(actual["metadata"]) != snapshot.metadata_json:
        raise ValueError("Independent planning source metadata differs")
    expected_chunks = [
        {
            "id": row.chunk_id,
            "index": row.ordinal,
            "content": row.literal.text,
            "metadata": json.loads(row.metadata_json),
        }
        for row in snapshot.chunks
    ]
    actual_chunks = [
        {key: row[key] for key in ("id", "index", "content", "metadata")}
        for row in actual["chunks"]
    ]
    if canonical(actual_chunks) != canonical(expected_chunks):
        raise ValueError("Independent planning chunk inventory differs")


def _arguments(record, authoritative_snapshots):
    manifest = record["manifest"]
    universe = declarations.PlanningUniverse(
        **{
            **manifest,
            "publications": tuple(
                declarations.SourceIdentity(**row) for row in manifest["publications"]
            ),
        }
    )
    snapshots = tuple(_snapshot(row) for row in record["snapshots"])
    for snapshot in snapshots:
        _actual_source(snapshot, authoritative_snapshots)
    return {
        "question": record["question"],
        "capture": record["capture"],
        "manifest": universe,
        "snapshots": snapshots,
        "source_captures": tuple(_captures(row) for row in record["source_captures"]),
        "support_metadata": record["support_metadata"],
        "sql_read_set_json": record["sql_read_set_json"],
        "observations": tuple(
            support.NliObservation(
                **{**row, "pair": support.PlanningPair(**row["pair"])}
            )
            for row in record["observations"]
        ),
        "actual_executions": tuple(
            support.NliExecution(**{**row, "pair": support.PlanningPair(**row["pair"])})
            for row in record["actual_executions"]
        ),
    }


def reconstruct_request(
    record, *, question, authoritative_snapshots, retained_inputs, require_runtime=False
):
    """Use separately retained execution inputs and independently loaded bodies.

    Runtime-tag checking only prevents UNITONLY material entering production;
    actual inference attribution comes from the trusted adapter at execution.
    """
    declarations._native(record)
    declarations._native(retained_inputs)
    if (
        type(record) is not dict
        or set(record) != _FIELDS
        or record.get("contract") != CONTRACT
        or record.get("question") != question
        or type(retained_inputs) is not dict
        or canonical(record) != canonical(retained_inputs)
    ):
        raise ValueError("Actual retained staged request inputs differ or are missing")
    if type(require_runtime) is not bool:
        raise ValueError("Runtime capture policy must be an explicit boolean")
    try:
        arguments = _arguments(record, authoritative_snapshots)
        if require_runtime and any(
            row.capture_kind != "runtime_capture"
            for row in arguments["actual_executions"]
        ):
            raise ValueError("Only runtime execution receipts can enter publication")
        plan = reconstruct_staged_plan(**arguments)
        # Every field must survive the typed decode/encode without omissions.
        if canonical(capture_inputs(**arguments)) != canonical(record):
            raise ValueError("Staged request transport differs after typed replay")
        return plan
    except (KeyError, TypeError, AttributeError, IndexError, RecursionError) as exc:
        raise ValueError("Staged request inputs do not reconstruct") from exc
