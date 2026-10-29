"""Contextual role scope must survive coordinator and publication rechecks."""

import pytest
from app.models.query import QueryRequest
from app.services import requirement_answers
from app.services.role_scope_inspection import (
    check_role_read_set,
    inspect_role_manifest,
)

from tests.test_contextual_runtime_contract import configuration
from tests.test_contextual_scope_sql import PRINCIPAL, publish

pytest_plugins = ["tests.test_connected_contract"]


async def test_v2_role_read_set_rechecks_its_recorded_contract(connected_db):
    db, _ = connected_db
    await publish(db, 1, "The records steward leads Meridian review.")
    await publish(db, 2, "The custodian leads Distant inspection.")
    await db.commit()
    request = QueryRequest(question="Who leads Meridian review?")
    manifest = await inspect_role_manifest(
        db, PRINCIPAL, request, reading_profile="contextual_source_v2"
    )
    assert manifest.complete
    assert manifest.record()["contract"] == "declared-context-role-manifest-v2"
    checked = await check_role_read_set(db, PRINCIPAL, request, manifest.record())
    assert checked == {"consistent": True, "reason": None}


async def test_public_coordinator_uses_contextual_candidate_scope(
    connected_db, monkeypatch
):
    db, _ = connected_db
    target = await publish(db, 1, "The records steward leads Meridian review.")
    await publish(db, 2, "The custodian leads Distant inspection.")
    await db.commit()
    captured = []
    original = inspect_role_manifest

    class Inspected(Exception):
        pass

    async def inspect(*args, **kwargs):
        result = await original(*args, **kwargs)
        captured.append(result)
        raise Inspected

    monkeypatch.setattr(
        "app.services.role_scope_inspection.inspect_role_manifest", inspect
    )

    async def current(_):
        return True

    with pytest.raises(Inspected):
        await requirement_answers.select_requirement_answer(
            db,
            QueryRequest(question="Who leads the ordinary Meridian review session?"),
            PRINCIPAL,
            [],
            configuration(),
            validate_current=current,
        )
    manifest = captured[0]
    assert manifest.record()["contract"] == "declared-context-role-manifest-v1"
    assert {s.identity["document_id"] for s in manifest.sources} == {str(target.id)}
