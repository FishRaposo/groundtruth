"""Actual parser999 native assumptions; no new parser/model or authority claim."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from app.services import captured_plan_binding as binding
from app.services import contextual_source_proof as source
from app.services.captured_plan_requirements import _rows, closed_original_frames
from app.services.planning_declarations import digest


def actual():
    return json.loads(
        (Path(__file__).parent / "fixtures/native-given-context1002.json").read_text(
            encoding="utf-8"
        )
    )


def boundary():
    data = actual()
    question, capture = data["request"]["question"], data["capture"]
    structure = binding.prepare_structure(
        question, capture, reading_profile="contextual_source_v4"
    )
    frames, _ = closed_original_frames(
        question, capture, structure["historical_partial"]
    )
    requirements, uses = [], []
    for node in structure["nodes"]:
        frame = frames[node["id"]][1]
        identifier = "r-" + digest({"node": node, "question": question})
        requirement, use = _rows(question, node, identifier, node["kind"], frame=frame)
        requirements.append(requirement)
        uses.append(use)
    record = {
        "contract": "staged-request-plan-v2",
        "question": question,
        "evidence_profile_json": json.dumps(data["profile"]),
        "structure_json": json.dumps(structure),
        "graph_json": json.dumps(capture["annotation"]),
        "requirements": [asdict(r) for r in requirements],
        "uses": [asdict(u) for u in uses],
        "remaining_external_governing_json": json.dumps(
            structure["pending_source_applicability"]
        ),
    }
    return json.loads(json.dumps(record)), requirements, uses


def test_actual_native_condition_reaches_semantic_guard_without_false_integrity_error():
    record, _, _ = boundary()
    requirement = next(r for r in record["requirements"] if r["kind"] == "procedure")
    use = next(u for u in record["uses"] if u["requirement_id"] == requirement["id"])
    from app.services.role_scope_policy import replay_native_request_use

    frame = replay_native_request_use(record, requirement, use)
    assert json.loads(json.dumps(frame["condition_ast"])) == use["condition_ast"]
    # Phase1 original source-call expectation/log are preserved in Q1002.
    # The unchanged PP-only helper still refuses this distinct native premise.
    with pytest.raises(source.SourceGuardRefusal, match="Unknown requested condition"):
        source._ordinary_assignment_condition(
            source._Graph(
                record["question"],
                0,
                json.loads(record["graph_json"]),
                0,
                len(record["question"]),
            ),
            use,
        )


def test_actual_given_premise_is_preserved_unverified_under_quote_policy():
    record, _, _ = boundary()
    requirement = next(r for r in record["requirements"] if r["kind"] == "procedure")
    use = next(u for u in record["uses"] if u["requirement_id"] == requirement["id"])
    result = source._request_source_applicability(
        record, requirement, use, "contextual_source_v4"
    )
    assert result is not None
    assert result["given_context"]["status"] == "UNVERIFIED_GIVEN_CONTEXT"
    assert result["given_context"]["premise"] == use["conditions"][0]
    assert use["conditions"][0]["text"] in result["disclosure"]
    assert result["assignment_absence"] == "NOT_ESTABLISHED"
    assert result["session_applicability"] == "NOT_CERTIFIED"


def test_shared_native_role_authority_preserves_both_original_roles_and_disclosures():
    from app.evidence_policy import recorded_evidence_policy
    from app.services.role_scope_policy import (
        _original_activity_interpretation,
        plan_activity_role,
    )

    record, requirements, uses = boundary()
    policy = recorded_evidence_policy(actual()["profile"])

    class Context:
        def __init__(self, raw, requirements, uses):
            self.raw = raw
            self.question = raw["question"]
            self.requirements = requirements
            self.uses = uses

        def record(self):
            return self.raw

    context = Context(record, requirements, uses)
    for requirement in requirements:
        if requirement.kind not in {"owner", "deputy"}:
            continue
        assert plan_activity_role(requirement, policy) is None
        role = plan_activity_role(requirement, policy, request_plan=context)
        assert role is not None
        proof = role.record("activity")
        given = json.loads(role.given_context_json)
        assert proof["given_context"] == given
        assert given["status"] == "UNVERIFIED_GIVEN_CONTEXT"
        assert isinstance(proof["disclosure"], str)
        assert given["premise"]["text"] in proof["disclosure"]
        assert "not a verified absence fact" in proof["disclosure"]
        assert role.prepared("activity").kind == requirement.kind
        assert role.prepared("activity").original_text == requirement.original_text
        assert (
            _original_activity_interpretation(
                role.prepared("activity"), policy, context
            )
            == role
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "local_ast",
        "frame_ast",
        "use_ast",
        "tokens",
        "modality",
        "negation",
        "reference",
        "premise",
        "missing_requirement",
    ],
)
def test_native_context_integrity_mutations_refuse(mutation):
    from app.evidence_policy import recorded_evidence_policy
    from app.services.role_scope_policy import native_given_context

    record, _, _ = boundary()
    requirement = next(r for r in record["requirements"] if r["kind"] == "procedure")
    use = next(u for u in record["uses"] if u["requirement_id"] == requirement["id"])
    policy = recorded_evidence_policy(actual()["profile"])
    if mutation == "local_ast":
        structure = json.loads(record["structure_json"])
        node = next(
            n
            for n in structure["historical_partial"]["nodes"]
            if n["id"] == use["node_id"]
        )
        features = json.loads(node["feature_json"])
        features["condition_ast"] = deepcopy(use["condition_ast"])
        node["feature_json"] = json.dumps(features)
        record["structure_json"] = json.dumps(structure)
    elif mutation == "frame_ast":
        use["condition_ast"][0]["complements"] = []
    elif mutation == "use_ast":
        use["conditions"] = []
    elif mutation == "tokens":
        use["consumed_token_indices"].pop(0)
    elif mutation == "modality":
        use["modality"] = []
    elif mutation == "negation":
        use["negation"] = []
    elif mutation == "reference":
        use["references"] = [{"start": 90, "end": 93, "text": "its"}]
    elif mutation == "premise":
        record["question"] = record["question"].replace("no bespoke", "a bespoke")
    else:
        requirement["original_text"] = ""
    with pytest.raises(ValueError):
        native_given_context(record, requirement, use, policy)


def test_old_scope_policy_cannot_interpret_native_assumption():
    from app.evidence_policy import recorded_evidence_policy

    record, _, _ = boundary()
    requirement = next(r for r in record["requirements"] if r["kind"] == "procedure")
    use = next(u for u in record["uses"] if u["requirement_id"] == requirement["id"])
    policy = replace(
        recorded_evidence_policy(actual()["profile"]),
        procedure_scope_profile="requested_scope_v1",
    )
    record["evidence_profile_json"] = json.dumps(policy.record())
    with pytest.raises(source.SourceGuardError):
        source._request_source_applicability(
            record, requirement, use, "contextual_source_v4"
        )


def test_legacy_role_asdict_and_record_do_not_gain_context_fields():
    from app.evidence_policy import recorded_evidence_policy
    from app.services.role_scope_policy import plan_activity_role

    record, requirements, _ = boundary()
    policy = replace(
        recorded_evidence_policy(actual()["profile"]),
        procedure_scope_profile="requested_scope_v1",
    )
    requirement = next(r for r in requirements if r.kind == "deputy")
    role = plan_activity_role(requirement, policy)
    assert role is not None
    assert set(asdict(role)) == {
        "requirement",
        "requested_scope",
        "session_scope",
        "activity_scope",
        "prepared_relation",
    }
    assert "given_context" not in role.record("activity")
    assert "unverified" not in role.disclosure()
