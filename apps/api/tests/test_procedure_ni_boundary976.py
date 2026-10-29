"""Exact COPY completeness is separate from conditional NI; no model execution."""

from dataclasses import asdict

from app.services import contextual_source_proof as proof
from app.services.planning_declarations import canonical

from tests.test_procedure_applicability962 import conditional, envelope_for


def test_actual_conditional_NI_retains_scope_and_governance_without_copy_completeness():
    values = conditional()
    snapshot, _windows, requirement, plan, _kwargs = values
    result = envelope_for(values)
    gates = {row["name"]: row for row in result["nli_obligations"]}
    assert gates["namespace"]["hypothesis"] == (
        "The source-declared standard Citrine fragment desk routine is a procedure "
        "for Citrine fragment desk."
    )
    assert gates["applicability"]["hypothesis"] == (
        "For an ordinary Citrine fragment desk session with no separate assignment, "
        "the source-declared standard Citrine fragment desk routine is the governed "
        "procedure."
    )
    assert all(row["premise"] == snapshot.body[:132] for row in gates.values())
    assert requirement.attribute == "the complete governed procedure"
    assert canonical(
        result["request_applicability"]["original_requirement"]
    ) == canonical(asdict(requirement))
    assert canonical(result["request_applicability"]["original_use"]) == canonical(
        asdict(next(u for u in plan.uses if u.requirement_id == requirement.id))
    )
    assert result["source_body"] == snapshot.body
    assert result["envelope_range"] == {"start": 0, "end": len(snapshot.body)}
    assert result["closure"] == {"kind": "immutable_eof", "offset": len(snapshot.body)}
    assert result["request_applicability"]["assignment_absence"] == "NOT_ESTABLISHED"
    assert result["pending_external_checks"]["ordinary_session_assignments"] == (
        "required_separately"
    )


def test_legacy_shared_proposition_is_unchanged():
    text = "This complete routine applies to the activity."
    result = proof._requested_NI_obligations(
        text, {"proposition": {"text": text}}, {"start": 0, "end": len(text)}, None
    )
    assert [row["hypothesis"] for row in result] == [text, text]


def test_other_approved_attribute_words_are_not_removed():
    applicability = {
        "original_requirement": {
            "attribute": "the entire governed procedure",
            "relation": "procedure",
        },
        "original_use": {"scopes": [{"text": "an ordinary activity session"}]},
        "activity_scope": "activity",
        "condition": {"text": "with no separate assignment"},
    }
    text = "The source header."
    result = proof._requested_NI_obligations(
        text,
        {
            "proposition": {"text": text},
            "declared_subject": {"text": "standard activity routine"},
        },
        {"start": 0, "end": len(text)},
        applicability,
    )
    assert result[1]["hypothesis"].endswith("is the entire governed procedure.")
