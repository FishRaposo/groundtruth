"""Actual full SQLite universe; UNITONLY syntax/NLI backend fixtures."""

import json

from app.services import required_copy_source as source
from app.services.staged_answer_planning import prepare_context

from tests.staged_role_unit850.test_role_evidence import Backend, backend_context
from tests.typed_role_unit870.fixtures import required_case

pytest_plugins = ["tests.test_connected_contract"]


async def test_nonrequired_declared_sources_retain_complete_scope_proof_ledgers(
    connected_db, monkeypatch
):
    db, config, principal, request, _, root, _ = await required_case(
        connected_db, monkeypatch
    )
    with backend_context(Backend()):
        ctx = await prepare_context(db, principal, request, config)
    plan = ctx.record()
    snapshot = ctx.snapshots()[str(root.id)]
    observed, analyses, snapshots, windows, dispositions = source._observations(
        {
            k: snapshot[k]
            for k in (
                "document_id",
                "document_version",
                "content_hash",
                "workspace_id",
                "snapshot_id",
            )
        },
        plan=plan,
        requirement=plan["requirements"][0],
        use=plan["uses"][0],
        planning_inputs=ctx.inputs(),
        authoritative_snapshots=ctx.snapshots(),
    )
    inventory = json.loads(
        json.loads(plan["effective_candidate_json"])["inventory_json"]
    )
    print(
        json.dumps(
            {
                "dispositions": dispositions,
                "units": [
                    {
                        "text": u["raw"]["text"],
                        "grammar": u["grammar"],
                        "unknowns": u["unknowns"],
                    }
                    for u in inventory["units"]
                ],
                "declarations": [
                    {"kind": d["kind"], "literal": d["literal"], "scope": d["scope"]}
                    for d in inventory["declarations"]
                ],
            },
            indent=2,
        )
    )
    assert all(
        d["status"] != "UNRESOLVED_POTENTIALLY_GOVERNING" for d in dispositions
    ), (
        dispositions,
        [(u["raw"]["text"], u["grammar"], u["unknowns"]) for u in inventory["units"]],
        [
            (d["kind"], d["literal"]["text"], d["scope"])
            for d in inventory["declarations"]
        ],
    )
