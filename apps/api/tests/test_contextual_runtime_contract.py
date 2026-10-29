"""Runtime/profile and real SQLite error-history regressions; no inference doubles."""

from app.api import health
from app.config import Settings
from app.evidence_policy import resolve_evidence_policy
from app.models.query import Query
from app.services import connected_query

pytest_plugins = ["tests.test_connected_contract"]


def configuration():
    return Settings(
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        GENERATION_MODE="extractive",
        ANSWER_PROPOSAL_PROFILE="qa_plus_source_patterns_v1",
        ROLE_SCOPE_POLICY="ordinary_session_activity_v1",
        PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1",
        SOURCE_CONTEXT_POLICY="scoped_note_context_v2",
        EVIDENCE_READING_PROFILE="contextual_source_v1",
    )


def test_safe_health_captures_the_configured_requirement_contract(monkeypatch):
    config = configuration()
    monkeypatch.setattr(health, "get_settings", lambda: config)
    metadata = health.runtime_metadata()
    assert metadata["answer_selection"]["contract"] == "requirement-evidence-v3"
    assert (
        metadata["evidence_profile"]["evidence_reading_profile"]
        == "contextual_source_v1"
    )


async def test_failed_contextual_execution_retains_error_without_claiming_revocation(
    connected_db, monkeypatch
):
    db, _ = connected_db
    config = configuration()
    monkeypatch.setattr(connected_query, "settings", config)
    row = Query(
        question="How long is the Copper check?",
        owner_id="writer",
        workspace_id="ops-a",
        outcome="processing",
        sources=[],
    )
    db.add(row)
    await db.commit()
    row._request_evidence_policy = resolve_evidence_policy(config)
    await connected_query.fail_query(db, row)
    assert row.provenance["answer_selection"]["contract"] == "requirement-evidence-v3"
    result = await connected_query.present_query(
        db, row, {"id": "writer", "workspace_id": "ops-a", "is_admin": False}
    )
    assert result.outcome == "error"
    assert result.answer is None and not result.sources
    assert result.evidence_access != "restricted"
    assert "execution failed" in result.refusal_reason.lower()
