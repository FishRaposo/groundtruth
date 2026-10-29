"""Local retained actual917 bytes; setup uses only the legacy structural decode."""

import json
from pathlib import Path

from app.evidence_policy import EvidencePolicy
from app.services import staged_plan_replay as legacy


def actual():
    return json.loads(
        (Path(__file__).parent / "data/actual917.json").read_text(encoding="utf-8")
    )


def profile():
    return EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v4",
        "literal_source_count_v1",
    ).record()


def authoritative(record):
    return {
        s["identity"]["document_id"]: {
            **s["identity"],
            "body": s["body"],
            "title": s["title"],
            "metadata": json.loads(s["metadata_json"]),
            "chunks": [
                {
                    "id": c["chunk_id"],
                    "index": c["ordinal"],
                    "content": c["literal"]["text"],
                    "metadata": json.loads(c["metadata_json"]),
                }
                for c in s["chunks"]
            ],
        }
        for s in record["snapshots"]
    }


def arguments():
    record = actual()
    record.update(support_metadata={}, observations=[], actual_executions=[])
    return legacy._arguments(record, authoritative(record))
