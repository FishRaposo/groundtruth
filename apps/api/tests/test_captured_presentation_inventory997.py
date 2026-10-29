"""UNITONLY shape controls for actual997's 46-authority/5-inspected split."""

import hashlib
import json
import uuid
from copy import deepcopy
from types import SimpleNamespace

import pytest
from app.evidence_policy import EvidencePolicy
from app.services import contextual_mixed_output as mixed


def inventory(reading="contextual_source_v4", governance="requirement_bound_v1"):
    snapshots, inspected = {}, []
    policy = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        reading,
        "literal_source_count_v1",
        governance,
    )
    for i in range(46):
        document, chunk = str(uuid.UUID(int=i + 1)), str(uuid.UUID(int=i + 1001))
        body = f"UNITONLY997 source unit {i}."
        identity = {
            "document_id": document,
            "document_version": 1,
            "content_hash": hashlib.sha256(body.encode()).hexdigest(),
        }
        snapshots[document] = {
            **identity,
            "body": body,
            "workspace_id": "UNITONLY997",
            "snapshot_id": str(uuid.UUID(int=i + 10001)),
            "metadata": {},
            "chunks": [{"id": chunk, "index": 0, "content": body}],
        }
        if i < 5:
            inspected.append({"chunk_id": chunk, **identity})
    return snapshots, {
        "contract": policy.requirement_contract,
        "evidence_profile": policy.record(),
        "inspected_sources": inspected,
    }


def structural_plan_seam(snapshots, profile):
    # UNITONLY private helper seam, never passed as a production request plan.
    identities = [
        {
            k: row[k]
            for k in (
                "document_id",
                "document_version",
                "content_hash",
                "workspace_id",
                "snapshot_id",
            )
        }
        for row in snapshots.values()
    ]
    return SimpleNamespace(
        evidence_profile_json=json.dumps(profile),
        source_productions_json=json.dumps(
            {
                "original_inputs": {
                    "manifest": {"publications": identities},
                    "snapshots": [{"identity": identity} for identity in identities],
                }
            }
        ),
    )


def test_captured_authority_stays_complete_while_model_replay_uses_inspected_view():
    snapshots, selection = inventory()
    chunks, complete_inventory, replay_sources = mixed._sources(
        snapshots,
        selection,
        reading_profile="contextual_source_v4",
        request_plan=structural_plan_seam(snapshots, selection["evidence_profile"]),
    )
    assert len(chunks) == len(complete_inventory) == len(snapshots) == 46
    assert all(
        entry["source"].metadata
        == snapshots[entry["identity"]["document_id"]]["metadata"]
        and entry["source"].identity["workspace_id"] == "UNITONLY997"
        and hasattr(entry["source"], "captured_scope")
        for entry in chunks.values()
    )
    assert len(replay_sources) == len(selection["inspected_sources"]) == 5
    assert {s.identity["document_id"] for s in replay_sources} == {
        row["document_id"] for row in selection["inspected_sources"]
    }
    assert len(snapshots) == 46  # No authoritative/planning member is removed.


@pytest.mark.parametrize(
    "reading,governance",
    [
        ("contextual_source_v2", "all_sources_v1"),
        ("contextual_source_v3", "all_sources_v1"),
        ("contextual_source_v4", "all_sources_v1"),
    ],
)
def test_historical_exact_inspection_inventory_is_unchanged(reading, governance):
    snapshots, selection = inventory(reading, governance)
    with pytest.raises(ValueError, match="snapshot document inventory"):
        mixed._sources(snapshots, selection, reading_profile=reading)


@pytest.mark.parametrize(
    "damage", ["version", "hash", "foreign", "uninspected_body", "extra_authority"]
)
def test_inspected_binding_and_uninspected_authority_bytes_still_fail_closed(damage):
    snapshots, selection = deepcopy(inventory())
    plan = structural_plan_seam(snapshots, selection["evidence_profile"])
    if damage == "version":
        selection["inspected_sources"][0]["document_version"] += 1
    elif damage == "hash":
        selection["inspected_sources"][0]["content_hash"] = "0" * 64
    elif damage == "foreign":
        selection["inspected_sources"][0]["chunk_id"] = str(uuid.UUID(int=9000))
    elif damage == "uninspected_body":
        snapshots[str(uuid.UUID(int=46))]["body"] += " changed"
    else:
        foreign = str(uuid.UUID(int=9000))
        snapshots[foreign] = {
            **deepcopy(next(iter(snapshots.values()))),
            "document_id": foreign,
        }
        snapshots[foreign]["snapshot_id"] = str(uuid.UUID(int=9002))
        for i, chunk in enumerate(snapshots[foreign]["chunks"]):
            chunk["id"] = str(uuid.UUID(int=9100 + i))
    with pytest.raises((ValueError, KeyError)):
        mixed._sources(
            snapshots,
            selection,
            reading_profile="contextual_source_v4",
            request_plan=plan,
        )


@pytest.fixture(scope="module")
def strict_ingress():
    from tests.test_declared_copy_consumer958 import prepared

    _snapshot, _windows, _requirement, plan, kwargs = prepared()
    snapshots = kwargs["authoritative_snapshots"]
    first = next(iter(snapshots.values()))
    selection = {
        "contract": "requirement-evidence-v5",
        "evidence_profile": json.loads(plan.evidence_profile_json),
        "staged_request_inputs": kwargs["planning_inputs"],
        "request_plan": plan.record(),
        "inspected_sources": [
            {
                "chunk_id": c["id"],
                **{
                    k: first[k]
                    for k in ("document_id", "document_version", "content_hash")
                },
            }
            for c in first["chunks"]
        ],
    }
    return selection, snapshots, kwargs["question"]


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "missing",
        "extra",
        "foreign_key",
        "version",
        "hash",
        "same_document_extra_chunk",
    ],
)
def test_real_staged_input_replay_then_view_preserves_complete_authority_checks(
    strict_ingress, damage
):
    from app.services.staged_output import _inputs

    selection, snapshots, question = deepcopy(strict_ingress)
    first = next(iter(snapshots))
    if damage == "missing":
        del snapshots[first]
    elif damage == "extra":
        foreign = str(uuid.UUID(int=9001))
        snapshots[foreign] = {**deepcopy(snapshots[first]), "document_id": foreign}
        snapshots[foreign]["snapshot_id"] = str(uuid.UUID(int=9002))
        for i, chunk in enumerate(snapshots[foreign]["chunks"]):
            chunk["id"] = str(uuid.UUID(int=9100 + i))
    elif damage == "foreign_key":
        snapshots[str(uuid.UUID(int=9001))] = snapshots.pop(first)
    elif damage == "version":
        snapshots[first]["document_version"] += 1
    elif damage == "hash":
        snapshots[first]["content_hash"] = "0" * 64
    elif damage == "same_document_extra_chunk":
        snapshots[first]["chunks"].append(
            {
                **deepcopy(snapshots[first]["chunks"][0]),
                "id": str(uuid.UUID(int=9001)),
                "index": 99,
            }
        )

    def replay():
        plan, _, _ = _inputs(
            selection,
            question,
            snapshots,
            {"provenance": {"answer_selection": deepcopy(selection)}},
            reading_profile="contextual_source_v4",
        )
        return mixed._sources(
            snapshots,
            selection,
            reading_profile="contextual_source_v4",
            request_plan=plan,
        )

    if damage is None:
        chunks, complete, sources = replay()
        assert len(complete) == len(snapshots) == 3
        assert len(sources) == 1
        assert len(chunks) >= len(selection["inspected_sources"])
    else:
        with pytest.raises((ValueError, KeyError)):
            replay()
