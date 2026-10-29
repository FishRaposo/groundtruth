import json
from copy import deepcopy
from pathlib import Path

from app.evidence_policy import EvidencePolicy
from app.services import captured_plan_inputs as inputs
from app.services import planning_declarations as source
from app.services import staged_plan_replay as legacy
from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS, NLI

from tests.staged_plan_unit837.fixtures_source import ASSIGN, universe
from tests.staged_plan_unit837.fixtures_source import source as make_source


def metadata():
    return {
        "mode": "local_nli",
        "model": NLI.model,
        "revision": NLI.revision,
        "license": NLI.license,
        "minimum_entailment_margin": 2.0,
        "max_pair_tokens": MAX_PAIR_TOKENS,
        "batch_size": BATCH_SIZE,
        "device": "cpu",
        "score_semantics": "raw contradiction/entailment/neutral logits; uncalibrated",
        "readiness": "ready",
    }


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
        row["identity"]["document_id"]: {
            **row["identity"],
            "body": row["body"],
            "title": row["title"],
            "metadata": json.loads(row["metadata_json"]),
            "chunks": [
                {
                    "id": c["chunk_id"],
                    "index": c["ordinal"],
                    "content": c["literal"]["text"],
                    "metadata": json.loads(c["metadata_json"]),
                }
                for c in row["chunks"]
            ],
        }
        for row in record["snapshots"]
    }


def case(groups=None, *, curated=None, actual=False, observed=None):
    old = json.loads(
        (Path(__file__).parent / "data/actual917.json").read_text(encoding="utf-8")
    )
    old.update(support_metadata=metadata(), observations=[], actual_executions=[])
    args = legacy._arguments(old, authoritative(old))
    args.update(support_metadata=metadata(), observations=(), actual_executions=())
    if not actual:
        snapshot, capture = make_source(groups or [ASSIGN], doc="UNITONLY939-source")
        if curated is not None:
            from dataclasses import replace

            snapshot = replace(snapshot, metadata_json=source.canonical(curated))
        args.update(
            manifest=universe((snapshot,)),
            snapshots=(snapshot,),
            source_captures=(capture,),
            sql_read_set_json=source.canonical(
                {
                    "contract": "request-planning-publications-v1",
                    "selection_mode": "all_authorized_publications_v1",
                    "fixture": "UNITONLY939_NO_SQL_AUTHORITY",
                }
            ),
        )
    if observed is not None:
        args.update(question=observed["text"], capture=observed["capture"])
    record = inputs.capture_inputs_v2(**args, evidence_profile=profile())
    selected = next(
        row
        for row in record["source_productions"]["sources"]
        for row in row["relation_candidates"]
    )
    return record, {
        "question": args["question"],
        "authoritative_snapshots": authoritative(record),
        "retained_inputs": deepcopy(record),
        "source_identity": selected["source"],
        "selected_clause": selected["raw"],
        "expected_support_metadata": metadata(),
    }
