"""947 real HTTP503 reproduction narrowed to the actual proposal registry."""

from copy import deepcopy

from app.evidence_policy import resolve_evidence_policy
from app.services.requirement_contract import validate_discovery_lineage

from tests.captured_roles_unit943.fixtures import labels_selection
from tests.test_captured_policy928 import configured


def selection():
    _, inputs, selected, _ = labels_selection()
    selected.update(
        contract="requirement-evidence-v5",
        evidence_profile=inputs["planning_inputs"]["evidence_profile"],
        requirements=[],
        inspected_sources=[
            {
                key: proposal[key]
                for key in (
                    "chunk_id",
                    "document_id",
                    "document_version",
                    "content_hash",
                )
            }
            for proposal in selected["proposals"]
        ],
        selected_proposal_ids=[row["proposal_id"] for row in selected["proposals"]],
    )
    return selected


def test_new_registered_captured_proposals_keep_discovery_lineage():
    actual = selection()
    assert {row["pattern_id"] for row in actual["proposals"]} == {
        "captured-role-declaration-v1"
    }
    assert validate_discovery_lineage(actual) == {"status": "recorded", "valid": True}


def test_unknown_or_cross_profile_proposal_is_not_admitted():
    original = selection()
    for damage in ("unknown", "old_profile"):
        actual = deepcopy(original)
        if damage == "unknown":
            actual["proposals"][0]["pattern_id"] = "unrecognized-pattern"
        else:
            actual["evidence_profile"] = resolve_evidence_policy(
                configured("contextual_source_v3")
            ).record()
        assert validate_discovery_lineage(actual)["valid"] is False
