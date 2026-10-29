"""Actual engineering input transport, without model or database execution."""

import json
from dataclasses import replace
from pathlib import Path

from app.services import planning_declarations as source


def actual():
    return json.loads(
        (Path(__file__).parent / "data/actual917.json").read_text(encoding="utf-8")
    )


def arguments():
    record = actual()
    manifest = record["manifest"]
    return {
        "question": record["question"],
        "capture": record["capture"],
        "manifest": source.PlanningUniverse(
            **{
                **manifest,
                "publications": tuple(
                    source.SourceIdentity(**row) for row in manifest["publications"]
                ),
            }
        ),
        "snapshots": tuple(
            source.SourceSnapshot(
                **{
                    **row,
                    "identity": source.SourceIdentity(**row["identity"]),
                    "chunks": tuple(
                        source.SourceChunk(
                            **{**c, "literal": source.RawRange(**c["literal"])}
                        )
                        for c in row["chunks"]
                    ),
                }
            )
            for row in record["snapshots"]
        ),
        "source_captures": tuple(
            source.SourceCaptures(
                source.SourceIdentity(**row["identity"]),
                tuple(source.CaptureWindow(**window) for window in row["windows"]),
            )
            for row in record["source_captures"]
        ),
        "sql_read_set_json": record["sql_read_set_json"],
    }


def unit_inputs(groups, *, metadata=None):
    """Fresh manual UNITONLY source graphs; actual request capture stays untouched."""
    from tests.staged_plan_unit837.fixtures_source import source as make_source
    from tests.staged_plan_unit837.fixtures_source import universe

    record = actual()
    snapshot, captures = make_source(groups, doc="UNITONLY931-source")
    if metadata is not None:
        snapshot = replace(snapshot, metadata_json=source.canonical(metadata))
    return {
        "question": record["question"],
        "capture": record["capture"],
        "manifest": universe((snapshot,)),
        "snapshots": (snapshot,),
        "source_captures": (captures,),
        "sql_read_set_json": source.canonical(
            {
                "contract": "request-planning-publications-v1",
                "selection_mode": "all_authorized_publications_v1",
                "fixture": "UNITONLY931_NO_SQL_AUTHORIZATION",
            }
        ),
    }
