"""Actual SQL-authorized publications for source-dependent request planning.

This boundary establishes membership and immutable snapshots, never semantic
support. Reading declarations cannot grant permissions or certify an answer.
"""

from dataclasses import replace

from app.services.role_scope_inspection import (
    _typed_read_set_equal,
    inspect_role_manifest,
)

CONTRACT = "request-planning-publications-v1"


async def inspect_planning_manifest(db, principal, request):
    manifest = await inspect_role_manifest(
        db,
        principal,
        request,
        reading_profile="contextual_source_v2",
        all_authorized_publications=True,
    )
    # A new receipt cannot be mistaken for the old role-candidate contract.
    return replace(manifest, read_set={**manifest.read_set, "contract": CONTRACT})


async def check_planning_read_set(db, principal, request, expected):
    """Recheck the entire permitted universe, including previously unseen rows."""
    if (
        type(expected) is not dict
        or expected.get("contract") != CONTRACT
        or expected.get("complete") is not True
        or expected.get("selection_mode") != "all_authorized_publications_v1"
    ):
        return {"consistent": False, "reason": "planning_read_set_invalid"}
    actual = await inspect_planning_manifest(db, principal, request)
    consistent = actual.complete and _typed_read_set_equal(actual.read_set, expected)
    return {
        "consistent": bool(consistent),
        "reason": None if consistent else "planning_publications_changed",
    }
