"""Actual SQLite/capture wiring; UNITONLY syntax, no model-support claim."""

import pytest
from app.config import get_settings
from app.models.query import QueryRequest
from app.services import planning_runtime, request_parser

from tests.test_contextual_scope_sql import PRINCIPAL, publish
from tests.test_planning_declarations import CAT, capture

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize(
    "change", ["none", "new_source", "revoke", "title_change", "invalid_capture"]
)
async def test_actual_planning_capture_binds_sql_snapshot_and_rechecks_membership(
    connected_db, monkeypatch, change
):
    db, _ = connected_db
    body, observed = capture([CAT])
    doc = await publish(db, 16001, body)
    await publish(db, 16002, "Private source", owner="other")
    await db.commit()
    calls = []

    async def recorded_capture(text, config):
        assert text == body
        calls.append(text)
        if change == "new_source":
            await publish(db, 16003, "A new governing source appeared.")
            await db.commit()
        elif change == "revoke":
            doc.owner_id = "other"
            await db.commit()
        elif change == "title_change":
            doc.title = "A different instruction reference target"
            await db.commit()
        return {} if change == "invalid_capture" else observed

    monkeypatch.setattr(request_parser, "capture_async", recorded_capture)
    request = QueryRequest(question="List the activity roles.")
    if change != "none":
        with pytest.raises(ValueError):
            await planning_runtime.inspect_planning_declarations(
                db, PRINCIPAL, request, get_settings()
            )
        return
    result = await planning_runtime.inspect_planning_declarations(
        db, PRINCIPAL, request, get_settings()
    )
    assert calls == [body]
    assert len(result.snapshots) == 1 and result.snapshots[0].body == body
    assert result.snapshots[0].identity.document_id == str(doc.id)
    assert result.inventory.support_or_permissions == "NOT_ASSESSED"
    catalogues = [
        d for d in result.inventory.declarations if d.kind == "role_catalogue"
    ]
    assert len(catalogues) == 1
    assert [member.text for member in catalogues[0].members] == [
        "coordinator",
        "observer",
        "recorder",
    ]
