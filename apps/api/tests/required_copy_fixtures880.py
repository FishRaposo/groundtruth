"""Actual exposed parser captures; UNITONLY snapshots/readset/NLI inference."""

import hashlib
import json
import uuid
from dataclasses import asdict
from pathlib import Path

from app.services import planning_declarations as d
from app.services import staged_plan_binding, staged_plan_replay
from app.services.staged_answer_planning import StagedAnswerContext
from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS, NLI

CAPTURES = json.loads(
    (Path(__file__).parent / "fixtures/required_copy_actual880.json").read_text()
)["captures"]


def arguments(root="root", appendix="appendix"):
    snapshots, captures, actual = [], [], {}
    for ordinal, name in enumerate([root] + ([appendix] if appendix else []), 1):
        body = CAPTURES[name]["annotation"]["raw_text"]
        ident = d.SourceIdentity(
            str(uuid.UUID(int=ordinal)),
            1,
            hashlib.sha256(body.encode()).hexdigest(),
            "UNITONLY-workspace",
            str(uuid.UUID(int=100 + ordinal)),
        )
        chunkid = str(uuid.UUID(int=200 + ordinal))
        source = d.SourceSnapshot(
            ident,
            "Appendix Alpha" if ordinal > 1 else "UNITONLY root",
            body,
            "{}",
            (d.SourceChunk(chunkid, 0, d.RawRange(0, len(body), body), "{}"),),
        )
        snapshots.append(source)
        captures.append(
            d.SourceCaptures(
                ident, (d.CaptureWindow(0, len(body), d.canonical(CAPTURES[name])),)
            )
        )
        actual[ident.document_id] = {
            **asdict(ident),
            "body": body,
            "title": source.title,
            "metadata": {},
            "chunks": [{"id": chunkid, "index": 0, "content": body, "metadata": {}}],
        }
    args = {
        "question": CAPTURES["question"]["annotation"]["raw_text"],
        "capture": CAPTURES["question"],
        "manifest": d.PlanningUniverse(
            "{}", tuple(x.identity for x in snapshots), "bounded_authorized_scan"
        ),
        "snapshots": tuple(snapshots),
        "source_captures": tuple(captures),
        "support_metadata": {
            "mode": "local_nli",
            "model": NLI.model,
            "revision": NLI.revision,
            "license": NLI.license,
            "device": "cpu",
            "minimum_entailment_margin": 2,
            "max_pair_tokens": MAX_PAIR_TOKENS,
            "batch_size": BATCH_SIZE,
            "score_semantics": (
                "raw contradiction/entailment/neutral logits; uncalibrated"
            ),
        },
        "sql_read_set_json": d.canonical(
            {
                "contract": "request-planning-publications-v1",
                "selection_mode": "all_authorized_publications_v1",
                "UNITONLY": "pure fixture only; not actual SQL authorization",
            }
        ),
        "observations": (),
        "actual_executions": (),
    }
    return args, actual


def context(root="root", appendix="appendix"):
    args, actual = arguments(root, appendix)
    plan = staged_plan_binding.reconstruct_staged_plan(**args)
    raw = staged_plan_replay.capture_inputs(**args)
    return StagedAnswerContext(plan, d.canonical(raw), d.canonical(actual))


def extra_context(name, metadata=None):
    args, actual = arguments()
    body = CAPTURES[name]["annotation"]["raw_text"]
    identity = d.SourceIdentity(
        str(uuid.UUID(int=3)),
        1,
        hashlib.sha256(body.encode()).hexdigest(),
        "UNITONLY-workspace",
        str(uuid.UUID(int=103)),
    )
    chunkid = str(uuid.UUID(int=203))
    source = d.SourceSnapshot(
        identity,
        "UNITONLY unknown governing source",
        body,
        d.canonical(metadata or {}),
        (d.SourceChunk(chunkid, 0, d.RawRange(0, len(body), body), "{}"),),
    )
    args["snapshots"] += (source,)
    args["source_captures"] += (
        d.SourceCaptures(
            identity, (d.CaptureWindow(0, len(body), d.canonical(CAPTURES[name])),)
        ),
    )
    args["manifest"] = d.PlanningUniverse(
        "{}", tuple(s.identity for s in args["snapshots"]), "bounded_authorized_scan"
    )
    actual[identity.document_id] = {
        **asdict(identity),
        "body": body,
        "title": source.title,
        "metadata": metadata or {},
        "chunks": [{"id": chunkid, "index": 0, "content": body, "metadata": {}}],
    }
    return StagedAnswerContext(
        staged_plan_binding.reconstruct_staged_plan(**args),
        d.canonical(staged_plan_replay.capture_inputs(**args)),
        d.canonical(actual),
    )


def envelope_args(ctx):
    snapshot = next(iter(ctx.snapshots().values()))
    row = ctx.inputs()["source_captures"][0]
    return {
        "body": snapshot["body"],
        "identity": {
            key: snapshot[key]
            for key in (
                "document_id",
                "document_version",
                "content_hash",
                "workspace_id",
                "snapshot_id",
            )
        },
        "requested_subject": "Moss inspection",
        "source_windows": [
            {
                "start": w["start"],
                "end": w["end"],
                "capture": json.loads(w["capture_json"]),
            }
            for w in row["windows"]
        ],
        "question": ctx.question,
        "requirement_id": "r1",
        "planning_inputs": ctx.inputs(),
        "retained_inputs": ctx.inputs(),
        "authoritative_snapshots": ctx.snapshots(),
    }
