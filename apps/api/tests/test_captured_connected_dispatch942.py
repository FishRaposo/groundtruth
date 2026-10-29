"""Unit dispatch only; no successful API or model response is simulated."""

import pytest
from app.evidence_policy import resolve_evidence_policy
from app.models.query import QueryRequest
from app.services import captured_answer_planning, staged_answer_planning
from app.services.requirement_answers import select_requirement_answer

from tests.test_captured_policy928 import configured


class AdapterReached(RuntimeError):
    pass


@pytest.mark.parametrize("profile", ["contextual_source_v3", "contextual_source_v4"])
async def test_connected_selection_dispatches_to_its_recorded_planning_contract(
    monkeypatch, profile
):
    expected = (
        captured_answer_planning
        if profile == "contextual_source_v4"
        else staged_answer_planning
    )
    other = (
        staged_answer_planning
        if expected is captured_answer_planning
        else captured_answer_planning
    )
    config = configured(profile)
    principal = {"id": "UNITONLY", "workspace_id": "ops-a", "is_admin": False}
    request = QueryRequest(question="List role labels for Cedar inspection.")
    calls = []

    async def reached(db, actual_principal, actual_request, actual_config):
        calls.append((db, actual_principal, actual_request, actual_config))
        raise AdapterReached(profile)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Connected request dispatched to a different contract")

    monkeypatch.setattr(expected, "prepare_context", reached)
    monkeypatch.setattr(other, "prepare_context", forbidden)
    with pytest.raises(AdapterReached, match=profile):
        await select_requirement_answer(
            None,
            request,
            principal,
            [],
            config,
            validate_current=forbidden,
            policy=resolve_evidence_policy(config),
        )
    assert calls == [(None, principal, request, config)]
