"""Existing COPY ingress over exposed captures; no actual NI or quality claim."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from app.evidence_policy import EvidencePolicy
from app.services import captured_plan_binding as binding
from app.services import contextual_source_proof as body_proof
from app.services import staged_source_proof as consumer
from app.services.captured_plan_inputs import capture_inputs_v2
from app.services.contextual_source_proof import SourceGuardError

from tests.captured_inputs_unit932.fixtures import authoritative
from tests.planning_library_unit830.test_support import metadata
from tests.test_captured_source_ownership954 import actual_inputs


def prepared(
    logical_id="d526-01-routine",
    *,
    mode="requirement_bound_v1",
    base_args=None,
    request_override=None,
):
    args = actual_inputs() if base_args is None else base_args
    request = json.loads(
        (Path(__file__).parent / "fixtures/captured_copy_request958.json").read_text(
            encoding="utf-8"
        )
    )
    if request_override is not None:
        request = request_override
    args.update(question=request["question"], capture=request["capture"])
    args.update(
        evidence_profile=EvidencePolicy(
            "qa_plus_source_patterns_v1",
            "ordinary_session_activity_v1",
            "source_declared_procedure_copy_v1",
            "scoped_note_context_v2",
            "contextual_source_v4",
            "literal_source_count_v1",
            mode,
        ).record(),
        support_metadata=metadata(),
        observations=(),
        actual_executions=(),
    )
    inputs = capture_inputs_v2(**args)
    snapshots = authoritative(inputs)
    plan = binding.reconstruct_request(
        inputs,
        question=args["question"],
        authoritative_snapshots=snapshots,
        retained_inputs=inputs,
        require_runtime=False,
    )
    snapshot = (
        args["snapshots"][0]
        if logical_id is None
        else next(
            row
            for row in args["snapshots"]
            if json.loads(row.metadata_json)["portfolio_logical_id"] == logical_id
        )
    )
    captured = next(
        row for row in args["source_captures"] if row.identity == snapshot.identity
    )
    windows = [
        {"start": row.start, "end": row.end, "capture": json.loads(row.capture_json)}
        for row in captured.windows
    ]
    requirement = next(row for row in plan.requirements if row.kind == "procedure")
    kwargs = {
        "question": args["question"],
        "requirement_id": requirement.id,
        "planning_inputs": inputs,
        "retained_inputs": inputs,
        "authoritative_snapshots": snapshots,
        "require_runtime": False,
        "reading_profile": "contextual_source_v4",
    }
    return snapshot, windows, requirement, plan, kwargs


def test_selected_actual_source_prepares_full_copy_and_mandatory_NI():
    # Break: historical directive grammar rejects actual declared opaque COPY.
    snapshot, windows, requirement, plan, kwargs = prepared()
    assert plan.resolved_request and not plan.publication_ready
    envelope = consumer.build_envelope(
        snapshot.body, asdict(snapshot.identity), requirement.topic, windows, **kwargs
    )
    assert envelope["source_body"] == snapshot.body
    assert envelope["envelope_range"] == {"start": 0, "end": len(snapshot.body)}
    assert envelope["closure"] == {
        "kind": "immutable_eof",
        "offset": len(snapshot.body),
    }
    assert [row["name"] for row in envelope["nli_obligations"]] == [
        "namespace",
        "applicability",
    ]
    assert all(
        row["premise"] == snapshot.body[:132] for row in envelope["nli_obligations"]
    )
    assert all(
        row["source_range"] == {"start": 0, "end": 132}
        for row in envelope["nli_obligations"]
    )
    assert envelope["selected_source_scope"]["source_identity"] == asdict(
        snapshot.identity
    )
    assert envelope["pending_external_checks"]
    assert "supported" not in envelope
    assert envelope["request_use"]["extent"] == "whole_requested"


def test_cobalt_actual_data_operand_has_opaque_copy_receipts_without_request_grant():
    snapshot, _windows, _requirement, plan, _kwargs = prepared("d526-15-routine")
    ledger = json.loads(plan.source_productions_json)
    domain = next(
        row["instruction_domain"]
        for row in ledger["sources"]
        if row["identity"] == asdict(snapshot.identity)
    )
    references, locality = body_proof._owned_copy_references(
        snapshot.body, asdict(snapshot.identity), domain
    )
    assert not locality
    assert "comment attachment" in "".join(
        row["clause"]["text"] for row in references["entries"]
    )
    assert references["captured_source_ownership"] == domain
    assert references["semantic_authority_support"] == "NOT_ESTABLISHED_BY_COPY"
    # No synthetic request or parser correction admits this body for Citrine.
    with pytest.raises(SourceGuardError):
        consumer.build_envelope(
            snapshot.body,
            asdict(snapshot.identity),
            "Citrine fragment desk",
            _windows,
            **_kwargs,
        )


def test_old_all_sources_mode_does_not_gain_new_consumer_admission():
    snapshot, windows, requirement, plan, kwargs = prepared(mode="all_sources_v1")
    assert json.loads(plan.evidence_profile_json)["contract"] == "evidence-profile-v9"
    with pytest.raises(SourceGuardError):
        consumer.build_envelope(
            snapshot.body,
            asdict(snapshot.identity),
            requirement.topic,
            windows,
            **kwargs,
        )


@pytest.mark.parametrize(
    "change", ["body", "identity", "windows", "authority", "retained"]
)
def test_new_consumer_requires_actual_full_source_and_separate_retained_inputs(change):
    snapshot, windows, requirement, _plan, kwargs = prepared()
    body = snapshot.body
    identity = asdict(snapshot.identity)
    if change == "body":
        body = body[:132]
    elif change == "identity":
        identity["document_version"] += 1
    elif change == "windows":
        windows = windows[:-1]
    elif change == "authority":
        kwargs["authoritative_snapshots"] = deepcopy(kwargs["authoritative_snapshots"])
        kwargs["authoritative_snapshots"][identity["document_id"]]["body"] += " altered"
    else:
        kwargs["retained_inputs"] = deepcopy(kwargs["retained_inputs"])
        kwargs["retained_inputs"]["question"] += " altered"
    with pytest.raises((SourceGuardError, ValueError)):
        consumer.build_envelope(body, identity, requirement.topic, windows, **kwargs)


@pytest.mark.parametrize("kind", ["external", "curated"])
def test_pending_selected_source_governance_cannot_fall_back_to_old_copy(kind):
    from app.services.planning_declarations import canonical

    from tests.staged_plan_unit837.fixtures_source import EXTERNAL
    from tests.test_captured_source_ownership954 import declared_inputs

    args = declared_inputs(EXTERNAL) if kind == "external" else actual_inputs()
    if kind == "curated":
        args["snapshots"] = tuple(
            replace(
                row,
                metadata_json=canonical(
                    {
                        **json.loads(row.metadata_json),
                        "conflict_group": "UNITONLY958-pending",
                    }
                ),
            )
            for row in args["snapshots"]
        )
    snapshot, windows, requirement, plan, kwargs = prepared(
        None if kind == "external" else "d526-01-routine", base_args=args
    )
    assert plan.resolved_request and not plan.publication_ready
    with pytest.raises(SourceGuardError, match="unresolved instruction governance"):
        consumer.build_envelope(
            snapshot.body,
            asdict(snapshot.identity),
            requirement.topic,
            windows,
            **kwargs,
        )


def test_actual_governed_request_constraints_require_full_conditional_NI():
    from tests.test_captured_request_repair953 import observed

    snapshot, windows, requirement, plan, kwargs = prepared(
        request_override=observed("reranked-002")
    )
    assert plan.resolved_request and not plan.publication_ready
    pending = [
        row
        for row in json.loads(plan.remaining_external_governing_json)
        if row.get("reason") == "pending_source_applicability"
    ]
    assert pending and pending[0]["original_frame"]["condition_ast"]
    envelope = consumer.build_envelope(
        snapshot.body, asdict(snapshot.identity), requirement.topic, windows, **kwargs
    )
    assert (
        envelope["request_applicability"]["original_frame"]
        == pending[0]["original_frame"]
    )
    assert "with no separate assignment" in envelope["nli_obligations"][1]["hypothesis"]
    assert envelope["request_applicability"]["assignment_absence"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize(
    "change", [None, "boolean", "pair", "missing_gate", "legacy_profile"]
)
def test_existing_numeric_replay_still_binds_every_mandatory_selected_NI(change):
    from tests.test_contextual_source_proof import settings

    snapshot, windows, requirement, plan, kwargs = prepared()
    envelope = consumer.build_envelope(
        snapshot.body, asdict(snapshot.identity), requirement.topic, windows, **kwargs
    )
    assessments = [
        {
            **obligation,
            "assessment": {
                "label": "entailment",
                "logits": [-1.0, 5.0, 0.0],
                "entailment_margin": 5.0,
                "supported": True,
                "pair_tokens": 80,
            },
        }
        for obligation in envelope["nli_obligations"]
    ]  # UNITONLY numbers; no actual model execution or factual claim.
    selection = {
        "contract": "requirement-evidence-v5",
        "evidence_profile": json.loads(plan.evidence_profile_json),
        "evidence_support": settings(),
        "source_guard_records": [
            {
                "requirement_id": requirement.id,
                "source_identity": asdict(snapshot.identity),
                "requested_subject": requirement.topic,
                "source_windows": windows,
                "envelope_inventory": envelope,
                "nli_assessments": assessments,
            }
        ],
    }
    if change == "boolean":
        assessments[0]["assessment"].update(
            logits=[5.0, -1.0, 0.0], entailment_margin=-6.0, label="contradiction"
        )
    elif change == "pair":
        assessments[0]["premise"] = snapshot.body
    elif change == "missing_gate":
        assessments.pop()
    elif change == "legacy_profile":
        selection["evidence_profile"] = EvidencePolicy(
            "qa_plus_source_patterns_v1",
            "ordinary_session_activity_v1",
            "source_declared_procedure_copy_v1",
            "scoped_note_context_v2",
            "contextual_source_v4",
            "literal_source_count_v1",
        ).record()
    guard_kwargs = {
        key: value for key, value in kwargs.items() if key != "requirement_id"
    }
    if change is not None:
        with pytest.raises(SourceGuardError):
            consumer.reconstruct_source_guard(
                selection,
                requirement,
                kwargs["authoritative_snapshots"][snapshot.identity.document_id],
                **guard_kwargs,
            )
    else:
        result = consumer.reconstruct_source_guard(
            selection,
            requirement,
            kwargs["authoritative_snapshots"][snapshot.identity.document_id],
            **guard_kwargs,
        )
        assert result["supported"]  # Pure UNITONLY recomputation, never actual NI.
        assert (
            result["selected_source_scope"]["other_source_governance"]
            == "NOT_DISCHARGED"
        )
        assert result["pending_external_checks"]
