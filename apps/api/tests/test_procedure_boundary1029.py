"""Actual1023 boundary regression, pure captured AST; no model/HTTP claim."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from app.evidence_policy import recorded_evidence_policy, source_copy_version
from app.services import contextual_source_proof as body_proof


def actual():
    return json.loads(
        (Path(__file__).parent / "fixtures/procedure-boundary1029.json").read_text()
    )


def envelope(scope="activity_quote_v2", *, data=None):
    data = actual() if data is None else data
    plan = deepcopy(data["plan"])
    policy = replace(
        recorded_evidence_policy(json.loads(plan["evidence_profile_json"])),
        procedure_scope_profile=scope,
    )
    plan["evidence_profile_json"] = json.dumps(policy.record(), sort_keys=True)
    return body_proof._build_from_bound_request(
        data["body"],
        data["identity"],
        data["requirement"]["topic"],
        plan,
        data["requirement"],
        data["use"],
        data["windows"],
        source_copy_version(
            reading_profile="contextual_source_v4", procedure_scope=scope
        ),
        reading_profile="contextual_source_v4",
        source_ownership=data["ownership"],
    )


def test_actual001_v2_quotes_instructions_through_full_overlap_contingency():
    result = envelope()
    assert result["envelope_range"] == {"start": 0, "end": 656}
    assert (
        result["source_body"] == actual()["body"]
    )  # Full immutable authority survives.
    assert result["ordered_ranges"][-1]["end"] == 656
    assert result["source_body"][:656].endswith("for the fragment steward.")
    assert result["reference_inventory"]["entries"][-1]["clause"]["end"] == 950
    assert result["selected_source_scope"]["source_range"] == {"start": 0, "end": 656}
    assert [r["name"] for r in result["nli_obligations"]] == [
        "namespace",
        "applicability",
    ]
    assert all(
        r["premise"] == actual()["body"][:132] for r in result["nli_obligations"]
    )
    assert result["instruction_boundary"]["authority_scope"] == {"start": 0, "end": 950}


def test_v1_and_default_retain_old_full_body_and_serialized_contract():
    data = actual()
    result = envelope("activity_quote_v1")
    assert result["envelope_range"] == data["old_inventory"]["envelope_range"]
    assert result["closure"] == data["old_inventory"]["closure"]
    assert "instruction_boundary" not in result
    assert (
        source_copy_version(reading_profile="contextual_source_v4").policy
        == "ordinary_source_argument_copy_v1"
    )
    assert (
        source_copy_version(
            reading_profile="contextual_source_v4", procedure_scope="activity_quote_v1"
        ).policy
        == "ordinary_activity_quote_v1"
    )


def test_v2_requires_exact_canonical_version_and_governance():
    profile = replace(
        recorded_evidence_policy(json.loads(actual()["plan"]["evidence_profile_json"])),
        procedure_scope_profile="activity_quote_v2",
    ).record()
    assert profile["procedure_scope_contract"] == "activity-procedure-quote-v2"
    assert recorded_evidence_policy(profile).record() == profile
    for damage in ("missing", "v1_contract", "unknown", "old_governance"):
        changed = deepcopy(profile)
        if damage == "missing":
            del changed["procedure_scope_contract"]
        elif damage == "v1_contract":
            changed["procedure_scope_contract"] = "activity-procedure-quote-v1"
        elif damage == "unknown":
            changed["procedure_scope_profile"] = "activity_quote_v999"
        else:
            changed["source_governance_profile"] = "all_sources_v1"
        with pytest.raises(ValueError):
            recorded_evidence_policy(changed)


@pytest.mark.parametrize(
    "damage", ["negative", "separate", "antecedent", "conditional_tail"]
)
def test_ambiguous_trailing_scope_is_not_silently_omitted(damage):
    data = actual()
    group = data["ownership"]["units"][-1]["captured_clauses"][0]
    if damage == "negative":
        group["clauses"][-1]["negation"] = []
    elif damage == "separate":
        next(t for t in group["tokens"] if t["lemma"] == "separate")["dep"] = "dep"
    elif damage == "antecedent":
        subjects = [
            a for a in group["clauses"][-1]["arguments"] if a["attachment"] == "nsubj"
        ]
        for token in group["tokens"]:
            if subjects[0]["start"] <= token["source_start"] < subjects[0]["end"]:
                token["lemma"] = "unresolved"
    else:
        data["ownership"]["units"][-3]["captured_clauses"][0]["clauses"][0][
            "clause_marker"
        ] = "unless"
    with pytest.raises(body_proof.SourceGuardRefusal):
        envelope(data=data)


def test_explicit_foreign_instruction_inside_requested_interval_refuses():
    data = actual()
    foreign = deepcopy(data["ownership"]["units"][-1])
    foreign["raw"] = {"start": 300, "end": 349, "text": data["body"][300:349]}
    # UNITONLY boundary-policy input; not a valid independent capture/replay.
    data["ownership"]["units"][6] = foreign
    with pytest.raises(body_proof.SourceGuardRefusal):
        body_proof._instruction_quote_boundary(data["body"], data["ownership"], 132)


def test_v2_proof_fragments_and_existing_renderer_emit_only_instruction_interval():
    from types import SimpleNamespace

    from app.services import contextual_mixed_output as output
    from app.services.answer_requirements import Requirement
    from app.services.procedure_output import render_extractive

    data = actual()
    identity = data["identity"]
    chunk = SimpleNamespace(
        id="10000000-0000-0000-0000-000000001029",
        document_id=identity["document_id"],
        content=data["body"],
        metadata=identity,
    )
    source = SimpleNamespace(
        body=data["body"],
        identity=identity,
        chunks=(SimpleNamespace(chunk=chunk, start=0, end=950),),
    )
    proposal = {
        "document_id": identity["document_id"],
        "document_range": {"start": 0, "end": 132},
        "text": data["body"][:132],
        "proposal_id": "UNITONLY-actual-body",
        "origin": "source_pattern",
        "chunk_id": chunk.id,
        "chunk_range": {"start": 0, "end": 132},
    }
    proof = output.procedure_obligations(
        Requirement(**data["requirement"]),
        source,
        proposal,
        method="consumer_envelope",
        consumer_inventory=envelope(),
        reading_profile="contextual_source_v4",
    )
    assert proof["source_body"] == data["body"] and proof["body_length"] == 950
    assert proof["extent"] == {"start": 0, "end": 656}
    assert proof["fragments"] == [
        {
            "chunk_id": chunk.id,
            "chunk_start": 0,
            "chunk_end": 656,
            "document_start": 0,
            "document_end": 656,
        }
    ]
    fragments, groups = output._procedure_emissions(
        "r-unit", proof, {chunk.id: {"identity": {**identity, "chunk_id": chunk.id}}}
    )
    assert groups[0]["text"] == data["body"][:656]
    assert fragments[0]["text"] == data["body"][:656]
    rendered, _ = render_extractive(
        [
            {
                "chunk_id": chunk.id,
                "citation_index": 1,
                "quoted_text": data["body"][:656],
                "answer_spans": [{"start": 0, "end": 656, "text": data["body"][:656]}],
            }
        ],
        groups,
    )
    assert data["body"][:656] in rendered and "batch contains" not in rendered


def test_v2_independent_source_replay_rejects_omission_or_scope_forgery():
    from dataclasses import asdict

    from app.services import staged_source_proof as consumer
    from app.services.captured_plan_inputs import capture_inputs_v2, decode_inputs_v2

    from tests.test_contextual_source_proof import settings
    from tests.test_declared_copy_consumer958 import prepared

    snapshot, windows, req, plan, kwargs = prepared()
    decoded = decode_inputs_v2(
        kwargs["planning_inputs"],
        question=kwargs["question"],
        authoritative_snapshots=kwargs["authoritative_snapshots"],
        retained_inputs=kwargs["retained_inputs"],
    )
    policy = replace(
        recorded_evidence_policy(json.loads(plan.evidence_profile_json)),
        procedure_scope_profile="activity_quote_v2",
    )
    inputs = capture_inputs_v2(**decoded.arguments, evidence_profile=policy.record())
    kwargs.update(planning_inputs=inputs, retained_inputs=inputs)
    inv = consumer.build_envelope(
        snapshot.body, asdict(snapshot.identity), req.topic, windows, **kwargs
    )
    selection = {
        "contract": "requirement-evidence-v5",
        "evidence_profile": policy.record(),
        "evidence_support": settings(),
        "source_guard_records": [
            {
                "requirement_id": req.id,
                "source_identity": asdict(snapshot.identity),
                "requested_subject": req.topic,
                "source_windows": windows,
                "envelope_inventory": inv,
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
                    for g in inv["nli_obligations"]
                ],
            }
        ],
    }
    guard_kwargs = {k: v for k, v in kwargs.items() if k != "requirement_id"}
    actual_snapshot = kwargs["authoritative_snapshots"][snapshot.identity.document_id]
    result = consumer.reconstruct_source_guard(
        selection, req, actual_snapshot, **guard_kwargs
    )
    assert result["supported"]  # Explicit UNITONLY model boundary, not actual NI.
    assert result["envelope_inventory"]["envelope_range"] == {"start": 0, "end": 656}
    # Actual _groups -> _selected transport, not a hand-built consumer value.
    from types import SimpleNamespace

    from app.services import captured_plan_binding as binding
    from app.services import contextual_mixed_output as output

    rebound = binding.reconstruct_request(
        inputs,
        question=kwargs["question"],
        authoritative_snapshots=kwargs["authoritative_snapshots"],
        retained_inputs=inputs,
        require_runtime=False,
    )
    identity = asdict(snapshot.identity)
    raw_chunk = actual_snapshot["chunks"][0]
    assert raw_chunk["content"] == snapshot.body
    chunk = SimpleNamespace(
        id=raw_chunk["id"],
        document_id=identity["document_id"],
        content=snapshot.body,
        metadata=identity,
    )
    source = SimpleNamespace(
        body=snapshot.body,
        identity=identity,
        chunks=(SimpleNamespace(chunk=chunk, start=0, end=len(snapshot.body)),),
    )
    proposal = {
        "proposal_id": "UNITONLY-group-transport",
        "requirement_id": req.id,
        "origin": "source_pattern",
        "chunk_id": chunk.id,
        "document_id": identity["document_id"],
        "text": snapshot.body[:132],
        "chunk_range": {"start": 0, "end": 132},
        "document_range": {"start": 0, "end": 132},
    }
    proof = output.procedure_obligations(
        req,
        source,
        proposal,
        method="consumer_envelope",
        consumer_inventory=inv,
        reading_profile="contextual_source_v4",
    )
    member = {**identity, "chunk_id": chunk.id}
    candidate = {
        **member,
        "requirement_id": req.id,
        "proposal": proposal,
        "raw_span": proposal["chunk_range"],
        "null_margin": 1.0,
        "decision": "supported",
        "procedure_completeness": proof,
    }
    selection["candidates"] = [candidate]

    def reconstruct_guard(actual_selection, current, authoritative, _plan):
        return consumer.reconstruct_source_guard(
            actual_selection, current, authoritative, **guard_kwargs
        )

    groups, owners = output._groups(
        selection,
        [req],
        {proposal["proposal_id"]: proposal},
        {proposal["proposal_id"]: 1.0},
        {chunk.id: {"identity": member, "source": source, "chunk": chunk}},
        kwargs["authoritative_snapshots"],
        rebound,
        reconstruct_guard,
        {"support": settings(), "evidence_profile": policy.record()},
    )
    witness = {
        **groups[0]["descriptor"],
        "proposals": [proposal],
        "value": snapshot.body[:656],
        "entailment_margin": 5.0,
    }
    selection["selected_proposal_ids"] = [proposal["proposal_id"]]
    selection["requirements"] = [
        {
            "id": req.id,
            "kind": req.kind,
            "original_text": req.original_text,
            "input_range": {"start": req.input_start, "end": req.input_end},
            "prepared_question": req.question,
            "source_workspace": req.source_workspace,
            "depends_on": list(req.depends_on),
            "status": "supported",
            "witnesses": [witness],
            "procedure_completeness": proof,
        }
    ]
    assert output._selected(selection, [req], groups, owners) == groups
    assert groups[0]["descriptor"]["value"] == snapshot.body[:656]
    assert (
        groups[0]["descriptor"]["procedure_completeness"]["source_body"]
        == snapshot.body
    )
    for damage in (
        "omit_contingency",
        "include_foreign_tail",
        "remove_reference",
        "v1_policy",
    ):
        changed = deepcopy(selection)
        record = changed["source_guard_records"][0]["envelope_inventory"]
        if damage == "omit_contingency":
            record["envelope_range"]["end"] = 561
        elif damage == "include_foreign_tail":
            record["envelope_range"]["end"] = 950
        elif damage == "remove_reference":
            record["reference_inventory"]["entries"].pop()
        else:
            record["source_copy_policy"] = "ordinary_activity_quote_v1"
        with pytest.raises(body_proof.SourceGuardError):
            consumer.reconstruct_source_guard(
                changed, req, actual_snapshot, **guard_kwargs
            )


def test_v2_configuration_runtime_comparison_and_policy_roundtrip():
    from app.evidence_policy import resolve_evidence_policy
    from app.portfolio.comparison import evidence_profile_matches

    from tests.test_captured_policy928 import configured

    config = configured(
        SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1",
        PROCEDURE_SCOPE_PROFILE="activity_quote_v2",
    )
    policy = resolve_evidence_policy(config)
    profile = policy.record()
    assert profile["procedure_scope_contract"] == "activity-procedure-quote-v2"
    assert recorded_evidence_policy(profile) == policy
    selection = {
        "contract": profile["requirement_contract"],
        "evidence_profile": profile,
    }
    controls = {
        "procedure_scope_profile": "activity_quote_v2",
        "procedure_verification_profile": "source_declared_procedure_copy_v1",
        "source_context_policy": "scoped_note_context_v2",
    }
    assert evidence_profile_matches(selection, controls)
    assert not evidence_profile_matches(
        selection, {**controls, "procedure_scope_profile": "activity_quote_v1"}
    )
