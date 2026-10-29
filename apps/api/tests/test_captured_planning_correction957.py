"""Request/source separation; actual captured requests, UNITONLY NI only."""

import json
from dataclasses import replace

from app.evidence_policy import EvidencePolicy
from app.services.captured_plan_binding import (
    prepare_candidate_plan,
    reconstruct_captured_plan,
)
from app.services.captured_planning_support import prepare_planning_assertions

from tests.captured_inputs_unit932.fixtures import profile
from tests.captured_plan_unit937.test_plan import case
from tests.planning_library_unit830.test_support import metadata, retained
from tests.staged_plan_unit837.fixtures_source import source, universe
from tests.test_captured_request_repair953 import observed


def arguments(name=None, *, bound=False):
    args = case(name or "labels")
    if name is None:
        row = observed("reranked-001")
        args.update(question=row["question"], capture=row["capture"])
    unknown, captures = source(
        [
            [
                ("Unexplained", "ADJ", "unexplained", "amod", 1),
                ("material", "NOUN", "material", "ROOT", 1),
                (".", "PUNCT", ".", "punct", 1),
            ]
        ],
        doc="UNITONLY957-unknown",
    )
    args.update(
        snapshots=(*args["snapshots"], unknown),
        source_captures=(*args["source_captures"], captures),
    )
    args["manifest"] = universe(args["snapshots"])
    args["evidence_profile"] = (
        replace(
            EvidencePolicy(
                "qa_plus_source_patterns_v1",
                "ordinary_session_activity_v1",
                "source_declared_procedure_copy_v1",
                "scoped_note_context_v2",
                "contextual_source_v4",
                "literal_source_count_v1",
            ),
            source_governance_profile="requirement_bound_v1",
        ).record()
        if bound
        else profile()
    )
    args["support_metadata"] = metadata()
    return args


def replay(args, kind="positive"):
    prepared = prepare_planning_assertions(**args)
    obs, executions = retained(prepared, kind)
    return reconstruct_captured_plan(
        **args, observations=obs, actual_executions=executions
    ), prepared


def test_actual_procedure_request_enters_consumer_with_unknown_inventory_pending():
    old, old_ni = replay(arguments())
    new, new_ni = replay(arguments(bound=True))
    assert not old.resolved_request
    assert new.resolved_request
    assert new.structure_resolved and new.planning_supported
    assert new.governance_status == "SOURCE_EVIDENCE_CHECKS_PENDING"
    assert new.unresolved_json == "[]"
    assert not new.publication_ready
    assert new.source_authority == "NOT_ASSESSED"
    assert [r.kind for r in new.requirements] == ["procedure"]
    assert new_ni.pending == ()
    assert old_ni.pending
    assert new.source_productions_json == old.source_productions_json
    assert new.operation_ledger_json == old.operation_ledger_json
    assert new.read_set_json == old.read_set_json
    assert new.sql_read_set_json == old.sql_read_set_json
    pending = json.loads(new.remaining_external_governing_json)
    assert any(r["disposition"] == "UNRESOLVED_POSSIBLE_GOVERNANCE" for r in pending)
    assert len(json.loads(new.source_productions_json)["sources"]) == 5


def test_catalogue_planning_pairs_remain_mandatory_in_requirement_bound_mode():
    args = arguments("labels", bound=True)
    plan, prepared = replay(args)
    assert plan.resolved_request
    assert len(prepared.assertions) == 12
    rejected, _ = replay(args, "negative")
    assert not rejected.resolved_request
    assert not rejected.planning_supported
    assert "mandatory_planning_relation_not_supported" in rejected.unresolved_json


def test_represented_copy_qualifier_enters_consumer_with_source_obligation_pending():
    args = arguments(bound=True)
    row = observed("reranked-002")
    args.update(question=row["question"], capture=row["capture"])
    plan, prepared = replay(args)
    assert plan.structure_resolved
    assert plan.resolved_request
    assert plan.unresolved_json == "[]"
    pending = [
        r
        for r in json.loads(plan.remaining_external_governing_json)
        if r.get("reason") == "pending_source_applicability"
    ]
    assert pending == json.loads(plan.structure_json)["pending_source_applicability"]
    assert pending[0]["original_frame"]["condition_ast"][0]["operator"] == "with"
    assert "governed" in pending[0]["original_frame"]["attribute"]
    assert not plan.publication_ready
    assert prepared.pending == ()
    assert all(len(u.condition_ast) == 1 for u in plan.uses)

    args["evidence_profile"] = profile()
    old, _ = replay(args)
    assert not old.resolved_request
    assert "pending_source_applicability" in old.unresolved_json


def test_raw_marker_cannot_activate_requirement_bound_behavior():
    import pytest

    args = arguments()
    args.pop("support_metadata")
    args["evidence_profile"]["source_governance_profile"] = "requirement_bound_v1"
    with pytest.raises(ValueError, match="canonical"):
        prepare_candidate_plan(**args)
