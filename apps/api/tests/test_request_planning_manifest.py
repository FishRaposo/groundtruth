"""Real SQLite planning membership; no parser/model assertions."""

from copy import deepcopy

import pytest
from app.models.query import QueryRequest
from app.services.request_planning_manifest import (
    check_planning_read_set,
    inspect_planning_manifest,
)

from tests.test_contextual_scope_sql import PRINCIPAL, publish

pytest_plugins = ["tests.test_connected_contract"]


async def test_planning_inspects_all_authorized_publications_before_name_resolution(
    connected_db,
):
    db, _ = connected_db
    target = await publish(db, 11001, "The records steward leads Meridian review.")
    other = await publish(db, 11002, "The page steward leads Zinc review.")
    await publish(
        db, 11003, "The records steward leads Meridian review.", owner="other"
    )
    await publish(db, 11004, "The page steward leads Zinc review.", workspace="ops-b")
    await db.commit()
    manifest = await inspect_planning_manifest(
        db, PRINCIPAL, QueryRequest(question="Who leads Meridian review?")
    )
    assert manifest.complete
    assert {s.identity["document_id"] for s in manifest.sources} == {
        str(target.id),
        str(other.id),
    }


async def test_planning_filters_narrow_and_new_governing_sources_invalidate(
    connected_db,
):
    db, _ = connected_db
    target = await publish(db, 11101, "The records steward leads Meridian review.")
    await publish(db, 11102, "The page steward leads Zinc review.")
    await db.commit()
    request = QueryRequest(question="List the review roles.", document_ids=[target.id])
    captured = await inspect_planning_manifest(db, PRINCIPAL, request)
    assert captured.complete and len(captured.sources) == 1
    assert (await check_planning_read_set(db, PRINCIPAL, request, captured.record()))[
        "consistent"
    ]
    unfiltered = QueryRequest(question=request.question)
    all_sources = await inspect_planning_manifest(db, PRINCIPAL, unfiltered)
    await publish(db, 11103, "The session coordinator is the records steward.")
    await db.commit()
    assert not (
        await check_planning_read_set(db, PRINCIPAL, unfiltered, all_sources.record())
    )["consistent"]
    # A new publication outside an explicit filter does not expand that scope.
    assert (await check_planning_read_set(db, PRINCIPAL, request, captured.record()))[
        "consistent"
    ]
    target.owner_id = "different-owner"
    await db.commit()
    assert not (
        await check_planning_read_set(db, PRINCIPAL, request, captured.record())
    )["consistent"]


async def test_planning_overflow_is_incomplete_even_for_an_unmatched_question(
    connected_db,
):
    db, _ = connected_db
    # Denied rows sort first; authority must be inside SQL before its limit.
    for n in range(1, 131):
        await publish(db, 12000 + n, "The private steward leads review.", owner="other")
    for n in range(128):
        await publish(db, 13000 + n, "The records steward leads review.")
    await db.commit()
    request = QueryRequest(question="List activity roles for an unknown activity.")
    captured = await inspect_planning_manifest(db, PRINCIPAL, request)
    assert captured.complete and len(captured.sources) == 128
    await publish(db, 14000, "The page steward leads review.")
    await db.commit()
    overflow = await inspect_planning_manifest(db, PRINCIPAL, request)
    assert not overflow.complete
    assert overflow.reason == "role_scope_document_budget_exceeded"


@pytest.mark.parametrize(
    "mutation", ["boolean_version", "missing_source", "legacy_contract"]
)
async def test_planning_recheck_rejects_forged_receipts(connected_db, mutation):
    db, _ = connected_db
    await publish(db, 15000, "The records steward leads review.")
    await db.commit()
    request = QueryRequest(question="List all review roles.")
    receipt = deepcopy(
        (await inspect_planning_manifest(db, PRINCIPAL, request)).record()
    )
    if mutation == "boolean_version":
        receipt["documents"][0]["document_version"] = True
    elif mutation == "missing_source":
        receipt["documents"] = []
    else:
        receipt["contract"] = "role-scope-inspection-read-set-v1"
    assert not (await check_planning_read_set(db, PRINCIPAL, request, receipt))[
        "consistent"
    ]
