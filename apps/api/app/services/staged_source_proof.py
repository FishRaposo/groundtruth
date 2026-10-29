"""Version-specific whole-request ingress for shared exact body mechanics.

A staged request is never projected into a resolved legacy request plan. Source
identity and actual retained inputs must independently reconstruct first.
"""

import json
from copy import deepcopy

from app.evidence_policy import (
    reading_version,
    recorded_evidence_policy,
    source_copy_version,
)
from app.services import contextual_source_proof as body_proof
from app.services.staged_plan_replay import reconstruct_request

PROFILE = "contextual_source_v3"
METHOD = body_proof.METHOD


def _bound(
    inputs,
    retained_inputs,
    snapshots,
    question,
    requirement_id,
    *,
    require_runtime,
    reading_profile=PROFILE,
):
    if reading_profile not in {PROFILE, "contextual_source_v4"}:
        raise body_proof.SourceGuardError("Explicit staged source profile required")
    reconstruct = reconstruct_request
    if reading_version(reading_profile).request_inputs:
        from app.services.captured_plan_binding import (
            reconstruct_request as reconstruct,
        )

    plan = reconstruct(
        inputs,
        question=question,
        authoritative_snapshots=snapshots,
        retained_inputs=retained_inputs,
        require_runtime=require_runtime,
    )
    if not plan.resolved_request:
        raise body_proof.SourceGuardRefusal("Whole staged request remains unresolved")
    record = plan.record()
    requirements = [r for r in record["requirements"] if r["id"] == requirement_id]
    uses = [u for u in record["uses"] if u["requirement_id"] == requirement_id]
    if len(requirements) != 1 or len(uses) != 1:
        raise body_proof.SourceGuardError("One actual staged requirement/use required")
    requirement, use = requirements[0], uses[0]
    applicability = _check_pending_applicability(record, use, reading_profile)
    if requirement["kind"] != "procedure" or requirement["depends_on"]:
        raise body_proof.SourceGuardRefusal(
            "An independently bound whole procedure is required"
        )
    if (
        use["extent"] != "whole_requested"
        or use["conditions"]
        and applicability is None
    ):
        raise body_proof.SourceGuardRefusal(
            "Whole source extent and resolved applicability required"
        )
    return record, requirement, use


def _check_pending_applicability(record, use, reading_profile):
    requirement = next(
        r for r in record["requirements"] if r["id"] == use["requirement_id"]
    )
    return body_proof._request_source_applicability(
        record, requirement, use, reading_profile
    )


def build_envelope(
    body,
    identity,
    requested_subject,
    source_windows,
    *,
    question,
    requirement_id,
    planning_inputs,
    retained_inputs,
    authoritative_snapshots,
    require_runtime=True,
    reading_profile=PROFILE,
):
    """Replay the new contract before invoking the shared body-copy machinery."""
    plan, requirement, use = _bound(
        planning_inputs,
        retained_inputs,
        authoritative_snapshots,
        question,
        requirement_id,
        require_runtime=require_runtime,
        reading_profile=reading_profile,
    )
    actual = authoritative_snapshots[identity["document_id"]]
    expected_identity = body_proof._snapshot_identity(actual)
    body_proof._same(identity, expected_identity)
    body_proof._same(body, actual["body"])
    body_proof._same(requested_subject, requirement["topic"])
    if reading_profile == "contextual_source_v4":
        profile = json.loads(plan["evidence_profile_json"])
        policy = recorded_evidence_policy(profile)
        body_proof._same(profile, policy.record())
        if policy.source_governance_profile == "requirement_bound_v1":
            ledger = json.loads(plan["source_productions_json"])
            sources = [row for row in ledger["sources"] if row["identity"] == identity]
            captures = [
                row
                for row in ledger["original_inputs"]["source_captures"]
                if row["identity"] == identity
            ]
            if len(sources) != 1 or len(captures) != 1:
                raise body_proof.SourceGuardError(
                    "One independently replayed source owner required"
                )
            body_proof._same(
                source_windows,
                [
                    {
                        "start": row["start"],
                        "end": row["end"],
                        "capture": json.loads(row["capture_json"]),
                    }
                    for row in captures[0]["windows"]
                ],
            )
            ownership = _selected_copy_ownership(ledger, identity, profile)
            # Unknown/global/curated/required-reference material cannot fall
            # through to a weaker historical COPY admission path in this mode.
            return body_proof._build_from_bound_request(
                body,
                identity,
                requested_subject,
                plan,
                requirement,
                use,
                source_windows,
                source_copy_version(
                    reading_profile=reading_profile,
                    procedure_scope=policy.procedure_scope_profile,
                ),
                reading_profile=reading_profile,
                source_ownership=ownership,
            )
    try:
        return body_proof._build_from_bound_request(
            body,
            identity,
            requested_subject,
            plan,
            requirement,
            use,
            source_windows,
            source_copy_version(reading_profile=reading_profile),
            reading_profile=reading_profile,
        )
    except body_proof.SourceGuardRefusal:
        from app.services import required_copy_source

        required = required_copy_source.prepare(
            identity,
            plan=plan,
            requirement=requirement,
            use=use,
            planning_inputs=planning_inputs,
            authoritative_snapshots=authoritative_snapshots,
        )
        body_proof._same(source_windows, required["documents"][0]["source_windows"])
        return required_copy_source.envelope(
            required, plan=plan, requirement=requirement, use=use
        )


def _selected_copy_ownership(ledger, identity, profile):
    """Rebuild opt-in COPY evidence without changing the old raw source ledger."""
    from app.services import captured_source_productions, planning_declarations
    from app.services.request_parser import validate_capture
    from app.services.staged_plan_replay import _captures, _snapshot

    original = ledger["original_inputs"]
    snapshots = [row for row in original["snapshots"] if row["identity"] == identity]
    captures = [
        row for row in original["source_captures"] if row["identity"] == identity
    ]
    if len(snapshots) != 1 or len(captures) != 1:
        raise body_proof.SourceGuardError("One independently retained source required")
    snapshot, captured = _snapshot(snapshots[0]), _captures(captures[0])
    units = []
    for window in captured.windows:
        raw = json.loads(window.capture_json)
        annotation = validate_capture(snapshot.body[window.start : window.end], raw)
        rows, _, _ = planning_declarations._window_inventory(
            snapshot, snapshot.identity, window, raw, annotation
        )
        units.extend(rows)
    return captured_source_productions._instruction_domain(
        snapshot, captured, tuple(units), evidence_profile=profile
    )


def reconstruct_source_guard(
    selection,
    requirement,
    snapshot,
    *,
    question,
    planning_inputs,
    retained_inputs,
    authoritative_snapshots,
    require_runtime=True,
    retained_records=None,
    reading_profile=PROFILE,
):
    """Rebuild every assessed source envelope before choosing one witness."""
    version = reading_version(reading_profile)
    body_proof._same(selection["contract"], version.requirement)
    policy = recorded_evidence_policy(selection["evidence_profile"])
    body_proof._same(selection["evidence_profile"], policy.record())
    if not policy.staged_request or policy.evidence_reading_profile != reading_profile:
        raise body_proof.SourceGuardError("Actual staged reading profile required")
    identifier = requirement["id"] if isinstance(requirement, dict) else requirement.id
    plan, expected_requirement, _use = _bound(
        planning_inputs,
        retained_inputs,
        authoritative_snapshots,
        question,
        identifier,
        require_runtime=require_runtime,
        reading_profile=reading_profile,
    )
    provided = (
        requirement
        if isinstance(requirement, dict)
        else {key: getattr(requirement, key) for key in expected_requirement}
    )
    body_proof._same(provided, expected_requirement)
    _bind_governance_profile(selection, policy, plan, reading_profile)
    support = body_proof._support(selection)
    selected_identity = body_proof._snapshot_identity(snapshot)
    actual_selected = authoritative_snapshots[selected_identity["document_id"]]
    body_proof._same(selected_identity, body_proof._snapshot_identity(actual_selected))
    body_proof._same(snapshot["body"], actual_selected["body"])
    records = selection["source_guard_records"]
    if type(records) is not list:
        raise body_proof.SourceGuardError(
            "Actual assessed staged source inventory required"
        )
    retained, seen, selected = [], set(), []
    for row in records:
        required_copy = type(row) is dict and "required_copy" in row.get(
            "envelope_inventory", {}
        )
        expected_fields = body_proof._RECORD_FIELDS | (
            {"required_copy_execution"} if required_copy else set()
        )
        if type(row) is not dict or set(row) != expected_fields:
            raise body_proof.SourceGuardError("Staged assessed source schema differs")
        identity = row["source_identity"]
        source = authoritative_snapshots[identity["document_id"]]
        envelope = build_envelope(
            source["body"],
            identity,
            row["requested_subject"],
            row["source_windows"],
            question=question,
            requirement_id=row["requirement_id"],
            planning_inputs=planning_inputs,
            retained_inputs=retained_inputs,
            authoritative_snapshots=authoritative_snapshots,
            require_runtime=require_runtime,
            reading_profile=reading_profile,
        )
        body_proof._same(row["envelope_inventory"], envelope)
        assessments = _replay_assessments(
            row, envelope, support, retained_records, require_runtime
        )
        key = (row["requirement_id"], body_proof._json(identity))
        if key in seen:
            raise body_proof.SourceGuardError(
                "Duplicate staged assessed source identity"
            )
        seen.add(key)
        retained.append(
            {
                "requirement_id": row["requirement_id"],
                "source_identity": deepcopy(identity),
                "record_sha256": body_proof._digest(row),
            }
        )
        if row["requirement_id"] == identifier and body_proof._json(
            identity
        ) == body_proof._json(selected_identity):
            body_proof._same(source["body"], snapshot["body"])
            selected.append((envelope, assessments))
    if len(selected) != 1:
        raise body_proof.SourceGuardError(
            "One independently assessed staged source required"
        )
    envelope, assessments = selected[0]
    supported = all(row["assessment"]["supported"] for row in assessments)
    result = {
        "contract": version.procedure,
        "status": "discharged",
        "method": METHOD,
        "source_identity": body_proof._snapshot_identity(snapshot),
        "requirement_id": identifier,
        "request_plan_sha256": body_proof._digest(plan),
        "envelope_inventory": envelope,
        "literal_scope": envelope["literal_scope"],
        "nli_assessments": assessments,
        "retained_record_inventory": retained,
        "retained_record_authority": "each_identity_independently_replayed",
        "supported": supported,
        "entailment_margin": min(
            row["assessment"]["entailment_margin"] for row in assessments
        ),
        "minimum_entailment_margin": support["minimum_entailment_margin"],
        "support_settings": support,
        "governing_material": "covered_verbatim_without_action_semantics",
        "reference_closure": "disclosed_ordinary_argument_bounded_reference_inventory"
        if supported
        else "not_supported",
        "independent_factual_role_output_access_history": "required_separately",
    }
    if "required_copy" in envelope:
        from app.services.required_copy_source import METHOD as REQUIRED_METHOD

        result.update(
            method=REQUIRED_METHOD,
            required_copy=envelope["required_copy"],
            reference_closure="independently_replayed_required_copy"
            if supported
            else "not_supported",
        )
    result.update(_selected_scope_result(policy, envelope))
    return result


def _selected_scope_result(policy, envelope):
    if policy.source_governance_profile != "requirement_bound_v1":
        return {}
    result = {
        "source_governance_profile": "requirement_bound_v1",
        "selected_source_scope": deepcopy(envelope["selected_source_scope"]),
        "pending_external_checks": deepcopy(envelope["pending_external_checks"]),
        "supported_meaning": "selected_source_namespace_and_applicability_only",
    }
    if "request_applicability" in envelope:
        result["request_applicability"] = deepcopy(envelope["request_applicability"])
        if policy.procedure_scope_profile in {"activity_quote_v1", "activity_quote_v2"}:
            result["supported_meaning"] = (
                "source_activity_quote_only_session_not_certified"
            )
    return result


def _bind_governance_profile(selection, policy, plan, reading_profile):
    if reading_profile != "contextual_source_v4":
        return
    profile = json.loads(plan["evidence_profile_json"])
    actual = recorded_evidence_policy(profile)
    if "requirement_bound_v1" in {
        policy.source_governance_profile,
        actual.source_governance_profile,
    }:
        body_proof._same(selection["evidence_profile"], profile)


def _replay_assessments(row, envelope, support, retained_records, require_runtime):
    if "required_copy" not in envelope:
        return body_proof._assessments(row, envelope, support)
    from app.services.required_copy_runtime import replay_execution

    if type(retained_records) is not list:
        raise body_proof.SourceGuardError(
            "Independently retained required-copy records required"
        )
    matches = [
        r
        for r in retained_records
        if r.get("requirement_id") == row["requirement_id"]
        and r.get("source_identity") == row["source_identity"]
    ]
    if len(matches) != 1:
        raise body_proof.SourceGuardError(
            "One retained required-copy execution required"
        )
    return replay_execution(
        row, matches[0], envelope, support, require_runtime=require_runtime
    )
