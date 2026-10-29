"""Profile identity is discovery metadata, never itself an answer certificate."""

from app.evidence_policy import EvidencePolicy
from app.services.requirement_contract import validate_discovery_lineage


def empty_record(policy, contract="requirement-evidence-v3"):
    return {
        "contract": contract,
        "evidence_profile": policy.record(),
        "proposals": [],
        "qa_observations": [],
        "inspected_sources": [],
        "requirements": [],
        "selected_proposal_ids": [],
    }


def contextual_policy(**overrides):
    fields = {
        "proposal_profile": "qa_plus_source_patterns_v1",
        "role_scope_policy": "ordinary_session_activity_v1",
        "procedure_verification_profile": "source_declared_procedure_copy_v1",
        "source_context_policy": "scoped_note_context_v2",
        "evidence_reading_profile": "contextual_source_v1",
    }
    return EvidencePolicy(**{**fields, **overrides})


def test_contextual_discovery_record_has_distinct_required_contract():
    record = empty_record(contextual_policy())
    assert validate_discovery_lineage(record)["valid"] is True
    record["contract"] = "requirement-evidence-v2"
    assert validate_discovery_lineage(record)["valid"] is False


def test_unchecked_dataclass_cannot_bypass_mandatory_contextual_controls():
    record = empty_record(contextual_policy(role_scope_policy="literal_v1"))
    assert validate_discovery_lineage(record)["valid"] is False


def test_new_profile_metadata_preserves_integer_types():
    record = empty_record(contextual_policy())
    record["evidence_profile"]["pattern_limits"]["per_source_requirement"] = 3.0
    assert validate_discovery_lineage(record)["valid"] is False


def test_legacy_discovery_defaults_stay_readable_without_new_fields():
    record = empty_record(
        EvidencePolicy("qa_only_v1", "literal_v1"), "requirement-evidence-v2"
    )
    assert validate_discovery_lineage(record)["valid"] is True
