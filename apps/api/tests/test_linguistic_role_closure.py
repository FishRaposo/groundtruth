"""Actual retained parser syntax; QA/NLI fixtures are explicitly UNITONLY."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.evidence_policy import EvidencePolicy
from app.services.linguistic_role_closure import CONTRACT
from app.services.role_scope_inspection import (
    RoleScopeManifest,
    RoleScopeSource,
    capture_role_contexts,
    inspect_role_contexts,
)
from app.services.role_scope_policy import plan_activity_role

from tests.test_contextual_mixed_output import mirror, produce
from tests.test_linguistic_role_consumer import (
    add_source,
    install_role_records,
    role_data,
)


def captures():
    data = json.loads(
        (Path(__file__).parent / "fixtures/role_source_captures_v702.json").read_text()
    )
    return {row["body"]: row["source_windows"] for row in data["sources"]}


def with_source(body):
    data = role_data()
    requirement = data["request_reconstructor"](data["question"], {}).requirements[0]
    identifier = add_source(data, body, 2)
    snapshot = data["source_snapshots"][identifier]
    data["selection"]["inspected_sources"].append(
        {
            "chunk_id": snapshot["chunks"][0]["id"],
            **{
                k: snapshot[k]
                for k in ("document_id", "document_version", "content_hash")
            },
        }
    )
    install_role_records(data, requirement)
    return data


@pytest.mark.parametrize(
    "body",
    [
        "The clerk is available from 09:00 to 11:00.",
        "The clerk is available from 09:00 to 11:00 and from 13:00 to 15:00.",
    ],
)
def test_closed_availability_owns_the_whole_clause_before_role_exclusion(body):
    data = with_source(body)
    actual = produce(data)
    finding = actual["certificate"]["role_scope"]["findings"][0]
    assert finding["inspection_method"] == CONTRACT
    row = finding["source_closures"][1]["units"][0]
    assert row["source_range"] == {"start": 0, "end": len(body)}
    assert row["text"] == body
    closure = row["availability"]["dependency_closure"]
    assert closure["complete"] is True
    assert not closure["residual_token_indices"] and not closure["residual_edges"]
    assert "The archivist" in actual["answer"]


@pytest.mark.parametrize(
    "body",
    [
        "The clerk is present from 09:00 to 11:00.",
        (
            "The clerk is available from 09:00 to 11:00 "
            "and the archivist is available from 13:00 to 15:00."
        ),
        "The clerk is not available from 09:00 to 11:00.",
        "The clerk may be available from 09:00 to 11:00.",
        "If appointed, the clerk is available from 09:00 to 11:00.",
        (
            "The clerk is available from 09:00 to 11:00 "
            "unless the reviewer appoints the deputy."
        ),
        "The Alder review leading clerk is available from 09:00 to 11:00.",
        "The clerk who leads Alder review is available from 09:00 to 11:00.",
        "The clerk is available from 09:00 to 11:00 and leads Alder review.",
        "The clerk is available from 09:00 to 11:00 only.",
        "By appointment, the clerk is available from 09:00 to 11:00.",
        "Consult the appointment appendix.",
        "The clerk is available from 09:00 to 11:00. Follow the appointment appendix.",
        "The clerk is available from 09:00 to 11:00 for Alder review.",
        "The clerk is available from 09:00 to 11:00; the reviewer appoints the deputy.",
        '"The clerk is available from 09:00 to 11:00."',
    ],
)
def test_modifiers_authority_scope_and_unknown_suffixes_are_not_erased(body):
    data = with_source(body)
    assert data["selection"]["role_scope_findings"][0]["complete"] is False
    with pytest.raises(ValueError):
        produce(data)


@pytest.mark.parametrize(
    "mutation", ["method", "missing", "identity", "range", "graph", "closure"]
)
def test_captured_role_closure_replays_instead_of_trusting_recorded_flags(mutation):
    data = with_source("The clerk is available from 09:00 to 11:00.")
    selection = data["selection"]
    finding = selection["role_scope_findings"][0]
    if mutation == "method":
        finding.pop("inspection_method")
        finding.pop("source_closures")
    elif mutation == "missing":
        finding["source_closures"].pop()
    elif mutation == "identity":
        finding["source_closures"][1]["source_capture"]["source_identity"][
            "content_hash"
        ] = "f" * 64
    elif mutation == "range":
        finding["source_closures"][1]["source_capture"]["source_windows"][0]["end"] -= 1
    elif mutation == "graph":
        finding["source_closures"][1]["source_capture"]["source_windows"][0]["capture"][
            "annotation"
        ]["tokens"][0]["head"] = True
    else:
        finding["source_closures"][1]["units"][0]["availability"]["dependency_closure"][
            "consumed_token_indices"
        ].pop()
    selection["requirements"][0]["role_scope_inspection"] = deepcopy(finding)
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_captured_role_history_rechecks_sources_and_actual_rendered_output():
    from app.services import contextual_mixed_output as output

    data = with_source("The clerk is available from 09:00 to 11:00.")
    actual = produce(data)
    data["selection"][output.CERTIFICATE_FIELD] = actual["certificate"]
    context = {
        k: v for k, v in data.items() if k not in {"selection", "answer", "citations"}
    }
    assert output.verify_output(
        data["selection"],
        answer=actual["answer"],
        citations=actual["citations"],
        **context,
    )
    assert not output.verify_output(
        data["selection"],
        answer=actual["answer"] + " altered",
        citations=actual["citations"],
        **context,
    )


def test_existing_695_other_temporal_field_requires_the_same_whole_nominal_closure():
    actual = produce(with_source("The inspection lasts 8 minutes."))
    unit = actual["certificate"]["role_scope"]["findings"][0]["source_closures"][1][
        "units"
    ][0]
    assert unit["other_temporal"]["kind"] == "duration"
    assert unit["other_temporal"]["dependency_closure"]["complete"] is True
    for body in (
        "The inspection that determines the Alder lead lasts 8 minutes.",
        "The inspection lasts 8 minutes. Refer to the assignment register.",
    ):
        data = with_source(body)
        assert data["selection"]["role_scope_findings"][0]["complete"] is False
        with pytest.raises(ValueError):
            produce(data)


def test_legacy_default_inspection_does_not_infer_availability_exclusion():
    data = with_source("The clerk is available from 09:00 to 11:00.")
    original = data["request_reconstructor"](data["question"], {}).requirements[0]
    role = plan_activity_role(
        original,
        EvidencePolicy("qa_plus_source_patterns_v1", "ordinary_session_activity_v1"),
    )
    record = data["selection"]["role_scope_read_set"]
    sources = tuple(
        RoleScopeSource(s["body"], json.dumps(identity), json.dumps(s["metadata"]))
        for s, identity in zip(
            data["source_snapshots"].values(), record["documents"], strict=True
        )
    )
    legacy = inspect_role_contexts(RoleScopeManifest(sources, record), role)
    assert legacy["complete"] is False and "inspection_method" not in legacy


def test_unavailable_capture_cannot_become_an_exclusion_receipt():
    data = role_data()
    original = data["request_reconstructor"](data["question"], {}).requirements[0]
    role = plan_activity_role(
        original,
        EvidencePolicy("qa_plus_source_patterns_v1", "ordinary_session_activity_v1"),
    )
    assert role is not None
    record = data["selection"]["role_scope_read_set"]
    snapshot = next(iter(data["source_snapshots"].values()))
    source = RoleScopeSource(snapshot["body"], json.dumps(record["documents"][0]), "{}")
    finding = inspect_role_contexts(
        RoleScopeManifest((source,), record),
        role,
        source_windows={snapshot["document_id"]: None},
    )
    assert finding["complete"] is False
    assert finding["source_closures"][0]["reason"] == "role_source_capture_unavailable"


def test_connected_role_lineage_gate_accepts_the_current_captured_manifest():
    from app.services.requirement_contract import validate_role_scope_evidence

    from tests.test_linguistic_role_consumer import session_data

    assert (
        validate_role_scope_evidence(session_data(dependent=True)["selection"])["valid"]
        is True
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "legacy_manifest",
        "v1_manifest",
        "unknown",
        "method",
        "captures",
        "profile",
        "outer",
    ],
)
def test_connected_v2_role_lineage_rejects_contract_downgrades_and_mismatches(mutation):
    from app.evidence_policy import reading_version
    from app.services.requirement_contract import validate_role_scope_evidence
    from app.services.role_scope_inspection import ROLE_READ_SET_CONTRACT

    selection = role_data()["selection"]
    if mutation == "legacy_manifest":
        selection["role_scope_read_set"]["contract"] = ROLE_READ_SET_CONTRACT
    elif mutation == "v1_manifest":
        selection["role_scope_read_set"]["contract"] = reading_version(
            "contextual_source_v1"
        ).role_manifest
    elif mutation == "unknown":
        selection["role_scope_read_set"]["contract"] = "unknown-role-manifest"
    elif mutation == "method":
        selection["role_scope_findings"][0].pop("inspection_method")
    elif mutation == "captures":
        selection["role_scope_findings"][0]["source_closures"] = []
    elif mutation == "profile":
        selection["evidence_profile"]["evidence_reading_profile"] = (
            "contextual_source_v1"
        )
    else:
        selection["contract"] = reading_version("contextual_source_v1").requirement
    assert validate_role_scope_evidence(selection)["valid"] is False


@pytest.mark.parametrize("declared_manifest", [False, True])
def test_v3_role_lineage_keeps_legacy_and_explicit_v1_manifest_semantics(
    declared_manifest,
):
    from app.evidence_policy import reading_version
    from app.services.requirement_contract import validate_role_scope_evidence
    from app.services.role_scope_inspection import ROLE_READ_SET_CONTRACT

    selection = role_data()["selection"]
    version = reading_version("contextual_source_v1")
    selection["contract"] = version.requirement
    selection["evidence_profile"]["evidence_reading_profile"] = version.profile
    selection["role_scope_read_set"]["contract"] = (
        version.role_manifest if declared_manifest else ROLE_READ_SET_CONTRACT
    )
    selection["role_scope_read_set"]["limits"]["documents"] = version.scope_documents
    for finding in selection["role_scope_findings"]:
        finding.pop("inspection_method")
        finding.pop("source_closures")
    selection["requirements"][0]["role_scope_inspection"] = deepcopy(
        selection["role_scope_findings"][0]
    )
    assert validate_role_scope_evidence(selection) == {
        "status": "recorded",
        "valid": True,
    }
    # This is a lineage check, not an independently reconstructed output certificate.
    assert "contextual_output_certificate" not in selection


def test_runtime_capture_uses_the_existing_request_local_window_cache(monkeypatch):
    from app.services import request_parser

    body = "The clerk is available from 09:00 to 11:00."
    windows = captures()[body]
    calls = []

    async def captured(text, config):
        calls.append(text)
        return deepcopy(windows[0]["capture"])

    monkeypatch.setattr(request_parser, "capture_async", captured)
    sources = tuple(
        RoleScopeSource(body, json.dumps({"document_id": str(n)}), "{}") for n in (1, 2)
    )
    operation = capture_role_contexts(
        RoleScopeManifest(sources, {}), SimpleNamespace(REQUEST_PARSER_MAX_CHARS=2048)
    )
    with pytest.raises(StopIteration) as result:
        operation.send(None)
    assert calls == [
        body
    ]  # Same literal body is parsed once, independently copied twice.
    assert result.value.value == {"1": windows, "2": windows}
    result.value.value["1"][0]["end"] = 0
    assert result.value.value["2"][0]["end"] == len(body)


def test_runtime_asset_error_propagates_but_window_budget_stays_unavailable(
    monkeypatch,
):
    from app.services import request_parser

    async def failed(text, config):
        raise request_parser.RequestParserReadinessError(
            "UNITONLY missing parser asset"
        )

    monkeypatch.setattr(request_parser, "capture_async", failed)
    source = RoleScopeSource(
        "The clerk is available from 09:00 to 11:00.", '{"document_id":"1"}', "{}"
    )
    operation = capture_role_contexts(
        RoleScopeManifest((source,), {}), SimpleNamespace(REQUEST_PARSER_MAX_CHARS=2048)
    )
    with pytest.raises(request_parser.RequestParserReadinessError):
        operation.send(None)
    operation = capture_role_contexts(
        RoleScopeManifest((source,), {}), SimpleNamespace(REQUEST_PARSER_MAX_CHARS=10)
    )
    with pytest.raises(StopIteration) as result:
        operation.send(None)
    assert result.value.value == {"1": None}


def test_actual_ordinary_session_request_replays_dependency_without_a_planner_double():
    from app.services.linguistic_dependencies import resolve_linguistic_requirement
    from app.services.linguistic_requirements import plan_request

    from tests.test_linguistic_role_consumer import rebuild_rows, session_data

    record = json.loads(
        (Path(__file__).parent / "fixtures/role_request_capture_v702.json").read_text()
    )
    question, capture = record["question"], record["capture"]
    plan = plan_request(question, capture)
    assert plan.resolved_request and [r.kind for r in plan.requirements] == [
        "owner",
        "availability",
    ]
    data = session_data(dependent=True)
    data["question"] = question
    data["request_reconstructor"] = lambda actual, context: plan
    selection = data["selection"]
    selection.update(request_plan=plan.record(), request_capture=capture)
    profile = selection["evidence_profile"]
    policy = EvidencePolicy(
        profile["proposal_profile"],
        profile["role_scope_policy"],
        profile["procedure_verification_profile"],
        profile["source_context_policy"],
        "contextual_source_v2",
    )
    original = plan.requirements[0]
    role = plan_activity_role(original, policy)
    assert role is not None
    bound, binding = resolve_linguistic_requirement(
        plan.requirements[1], plan, {"r1": "The clerk"}
    )
    effective = {"r1": (role.prepared("session"), {}), "r2": (bound, binding)}
    rebuild_rows(
        data,
        effective,
        {
            "r1": ("00000000-0000-0000-0000-000000000002", "The clerk"),
            "r2": ("00000000-0000-0000-0000-000000000003", "09:00 to 11:00"),
        },
    )
    install_role_records(data, original)
    data["request_reconstructor"] = None
    actual = produce(data)
    dependent = actual["certificate"]["effective_requirements"][1]
    assert dependent["dependency_binding"]["bindings"][0]["source_value"] == "The clerk"
    assert "The clerk" in dependent["requirement"]["question"]
    assert len(actual["citations"]) == 2


def _inject_given_disclosure(selection, given):
    # Mirror the producer: activity-scope records append the given disclosure;
    # session-scope records replace a missing base with it.
    for record in selection["role_scope_interpretations"]:
        record["given_context"] = given
        if record["effective_scope"] == "activity":
            record["disclosure"] = record["disclosure"] + " " + given["disclosure"]
        else:
            record["disclosure"] = given["disclosure"]
    for req in selection["requirements"]:
        record = req.get("role_scope_interpretation")
        if record is None:
            continue
        record["given_context"] = given
        if record["effective_scope"] == "activity":
            record["disclosure"] = record["disclosure"] + " " + given["disclosure"]
        else:
            record["disclosure"] = given["disclosure"]


@pytest.mark.parametrize("builder", ["role_data", "session_data"])
def test_given_context_interpretation_disclosure_passes_the_lineage_gate(builder):
    # Break: the validator reconstructed only the base disclosure, so captured
    # given-context records raised a RuntimeError instead of validating.
    from app.services.requirement_contract import validate_role_scope_evidence

    from tests.test_linguistic_role_consumer import role_data, session_data

    selection = (role_data() if builder == "role_data" else session_data())["selection"]
    _inject_given_disclosure(
        selection,
        {
            "assignment_absence": "NOT_ESTABLISHED",
            "disclosure": "Given context (unverified): no bespoke staffing note.",
        },
    )
    assert validate_role_scope_evidence(selection)["valid"] is True


def test_given_context_interpretation_rejects_a_forged_disclosure():
    from app.services.requirement_contract import validate_role_scope_evidence

    from tests.test_linguistic_role_consumer import role_data

    selection = role_data()["selection"]
    _inject_given_disclosure(
        selection,
        {
            "assignment_absence": "NOT_ESTABLISHED",
            "disclosure": "Given context (unverified): no bespoke staffing note.",
        },
    )
    for record in selection["role_scope_interpretations"]:
        if record["effective_scope"] == "activity":
            record["disclosure"] = "forged " + record["disclosure"]
    assert validate_role_scope_evidence(selection)["valid"] is False
