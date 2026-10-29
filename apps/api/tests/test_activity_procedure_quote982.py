"""Owner-approved activity quote scope, UNITONLY model-boundary replay."""

import json
from copy import deepcopy
from dataclasses import asdict, replace

import pytest
from app.evidence_policy import recorded_evidence_policy, source_copy_version
from app.services import captured_plan_binding as binding
from app.services import contextual_mixed_output as presentation
from app.services import staged_source_proof as consumer
from app.services.captured_plan_inputs import capture_inputs_v2, decode_inputs_v2
from app.services.contextual_source_proof import SourceGuardError
from app.services.planning_declarations import canonical
from app.services.procedure_output import render_extractive

from tests.test_contextual_source_proof import settings
from tests.test_procedure_applicability962 import conditional, envelope_for


def quoted():
    snapshot, windows, requirement, plan, kwargs = conditional()
    policy = replace(
        recorded_evidence_policy(json.loads(plan.evidence_profile_json)),
        procedure_scope_profile="activity_quote_v1",
    )
    decoded = decode_inputs_v2(
        kwargs["planning_inputs"],
        question=kwargs["question"],
        authoritative_snapshots=kwargs["authoritative_snapshots"],
        retained_inputs=kwargs["retained_inputs"],
    )
    inputs = capture_inputs_v2(**decoded.arguments, evidence_profile=policy.record())
    kwargs = {**kwargs, "planning_inputs": inputs, "retained_inputs": inputs}
    plan = binding.reconstruct_request(
        inputs,
        question=kwargs["question"],
        authoritative_snapshots=kwargs["authoritative_snapshots"],
        retained_inputs=inputs,
        require_runtime=False,
    )
    return snapshot, windows, requirement, plan, kwargs


def test_actual002_activity_quote_keeps_original_condition_and_full_source():
    values = quoted()
    snapshot, _windows, requirement, plan, _kwargs = values
    envelope = envelope_for(values)
    gates = {g["name"]: g for g in envelope["nli_obligations"]}
    assert gates["namespace"]["hypothesis"] == (
        "The source-declared standard Citrine fragment desk routine is a procedure "
        "for Citrine fragment desk."
    )
    assert gates["applicability"]["hypothesis"] == (
        "The source-declared standard Citrine fragment desk routine applies to "
        "Citrine fragment desk."
    )
    assert all(g["premise"] == snapshot.body[:132] for g in gates.values())
    bound = envelope["request_applicability"]
    assert bound["procedure_scope_contract"] == "activity-procedure-quote-v1"
    assert bound["session_applicability"] == "NOT_CERTIFIED"
    assert bound["assignment_absence"] == "NOT_ESTABLISHED"
    assert bound["condition_semantics"] == "requested_hypothetical_context"
    assert bound["condition"]["text"] == "with no separate assignment"
    assert canonical(bound["original_requirement"]) == canonical(asdict(requirement))
    use = next(u for u in plan.uses if u.requirement_id == requirement.id)
    assert canonical(bound["original_use"]) == canonical(asdict(use))
    assert requirement.attribute == "the complete governed procedure"
    assert envelope["source_body"] == snapshot.body
    assert envelope["envelope_range"] == {"start": 0, "end": len(snapshot.body)}
    assert envelope["closure"] == {
        "kind": "immutable_eof",
        "offset": len(snapshot.body),
    }
    assert envelope["request_obligation_inventory"][0]["method"] == (
        "exact_original_frame_activity_quote_policy_and_source_NI"
    )
    assert envelope["pending_external_checks"]["ordinary_session_assignments"] == (
        "required_separately"
    )
    assert not plan.publication_ready


def replay_selection(values):
    snapshot, windows, requirement, plan, kwargs = values
    envelope = envelope_for(values)
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
                "nli_assessments": [
                    {
                        **g,
                        "assessment": {
                            "label": "entailment",
                            "logits": [-1.0, 5.0, 0.0],
                            "entailment_margin": 5.0,
                            "supported": True,
                            "pair_tokens": 80,
                        },
                    }
                    for g in envelope["nli_obligations"]
                ],
            }
        ],
    }
    guard_kwargs = {k: v for k, v in kwargs.items() if k != "requirement_id"}
    actual = kwargs["authoritative_snapshots"][snapshot.identity.document_id]
    return selection, requirement, actual, guard_kwargs


def test_independent_replay_and_existing_renderer_require_quote_disclosure():
    selection, requirement, actual, kwargs = replay_selection(quoted())
    guard = consumer.reconstruct_source_guard(selection, requirement, actual, **kwargs)
    assert guard["supported"]  # UNITONLY raw numeric boundary; no actual NI claim.
    assert guard["request_applicability"]["session_applicability"] == "NOT_CERTIFIED"
    disclosures = presentation._verified_disclosures(
        [
            {
                "requirement_id": requirement.id,
                "source_guard": {"consumer_proof": guard},
            }
        ]
    )
    text = disclosures[0]["text"]
    assert "Documented activity procedure." in text
    assert "does not certify a session-specific procedure" in text
    assert "not a source-verified absence fact" in text
    answer, _ = render_extractive([], disclosures=[text])
    assert text in answer
    changed = deepcopy(selection)
    changed["source_guard_records"][0]["envelope_inventory"]["literal_scope"][
        "disclosure"
    ] = "certified"
    with pytest.raises(SourceGuardError):
        consumer.reconstruct_source_guard(changed, requirement, actual, **kwargs)
    changed = deepcopy(selection)
    changed["source_guard_records"][0]["nli_assessments"][1]["assessment"] = {
        "label": "contradiction",
        "logits": [5.0, -1.0, 0.0],
        "entailment_margin": -6.0,
        "supported": False,
        "pair_tokens": 80,
    }
    assert not consumer.reconstruct_source_guard(
        changed, requirement, actual, **kwargs
    )["supported"]


@pytest.mark.parametrize("change", ["unknown", "missing_contract", "old_policy"])
def test_new_interpretation_cannot_be_forged_downgraded_or_stripped(change):
    selection, requirement, actual, kwargs = replay_selection(quoted())
    profile = selection["evidence_profile"]
    if change == "unknown":
        profile["procedure_scope_profile"] = "unknown"
    elif change == "missing_contract":
        del profile["procedure_scope_contract"]
    else:
        profile.pop("procedure_scope_profile")
        profile.pop("procedure_scope_contract")
    with pytest.raises((SourceGuardError, ValueError)):
        consumer.reconstruct_source_guard(selection, requirement, actual, **kwargs)


def test_historical_policy_and_conditional_NI_are_not_upgraded():
    values = conditional()
    profile = json.loads(values[3].evidence_profile_json)
    assert "procedure_scope_profile" not in profile
    assert "procedure_scope_contract" not in profile
    assert recorded_evidence_policy(profile).record() == profile
    assert source_copy_version(reading_profile="contextual_source_v4").policy == (
        "ordinary_source_argument_copy_v1"
    )
    envelope = envelope_for(values)
    assert "with no separate assignment" in envelope["nli_obligations"][1]["hypothesis"]
    assert envelope["source_copy_policy"] == "ordinary_source_argument_copy_v1"
