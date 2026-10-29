"""Replay one immutable actual618 record; no new model/SQL/HTTP execution."""

import json
from copy import deepcopy
from pathlib import Path

from app.evidence_policy import EvidencePolicy
from app.services.contextual_output import verify_output


def actual_record():
    record = json.loads(
        (
            Path(__file__).parent / "fixtures/actual-completed-contextual-v3-618.json"
        ).read_text(encoding="utf-8")
    )
    record.pop("origin")
    return record


def test_actual_completed_v3_history_remains_valid_after_new_registry_versions():
    record = actual_record()
    selection = record.pop("selection")
    assert verify_output(selection, **record)
    profile = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v1",
    ).record()
    assert profile == selection["evidence_profile"]


def test_actual_old_certificate_cannot_certify_changed_answer_or_source():
    original = actual_record()
    answer = deepcopy(original)
    selection = answer.pop("selection")
    answer["answer"] += " Additional unsupported answer."
    assert not verify_output(selection, **answer)
    source = deepcopy(original)
    selection = source.pop("selection")
    document = next(iter(source["source_snapshots"].values()))
    document["body"] = document["body"].replace("7 minutes", "9 minutes")
    assert not verify_output(selection, **source)
