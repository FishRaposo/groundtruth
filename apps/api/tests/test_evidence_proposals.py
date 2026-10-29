"""Discovery lineage cannot relabel a null reader prediction as QA evidence."""

from dataclasses import FrozenInstanceError

import pytest
from app.services.answer_reader import ReaderSelection
from app.services.evidence_proposals import QAObservation, make_proposal
from app.services.procedure_evidence import single_chunk_source

from tests.test_composite_procedures import chunk


def selection():
    from app.evidence_policy import PATTERN_REGISTRY_CONTRACT, EvidencePolicy
    from app.services.requirement_answers import source_identity
    from app.services.source_pattern_proposals import ROLE_PATTERN

    member = chunk("The archivist leads Alder review.")
    proposal = make_proposal(
        "r1",
        single_chunk_source(member),
        member,
        4,
        13,
        origin="source_pattern",
        pattern_id=ROLE_PATTERN,
        grammar_version=PATTERN_REGISTRY_CONTRACT,
    ).record()
    return {
        "evidence_profile": EvidencePolicy(
            "qa_plus_source_patterns_v1", "literal_v1"
        ).record(),
        "proposals": [proposal],
        "qa_observations": [],
        "inspected_sources": [source_identity(member)],
        "requirements": [
            {
                "id": "r1",
                "status": "supported",
                "witnesses": [
                    {
                        **source_identity(member),
                        "proposals": [proposal],
                        "span": {
                            "start": 0,
                            "end": len(member.content),
                            "text": member.content,
                        },
                        "document_range": {"start": 0, "end": len(member.content)},
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "origin",
        "null_margin",
        "pattern_id",
        "content_hash",
        "range",
        "profile",
        "missing",
    ],
)
def test_new_profile_rejects_forged_or_missing_lineage(mutation):
    from app.services.requirement_contract import validate_discovery_lineage

    value = selection()
    assert validate_discovery_lineage(value)["valid"] is True
    proposal = value["proposals"][0]
    if mutation == "range":
        proposal["chunk_range"]["end"] += 1
    elif mutation == "profile":
        value["evidence_profile"]["proposal_profile"] = "unknown"
    elif mutation == "missing":
        value["proposals"] = []
    else:
        proposal[mutation] = "forged"
    assert validate_discovery_lineage(value)["valid"] is False


def test_old_history_stays_explicitly_unrecorded():
    from app.services.requirement_contract import validate_discovery_lineage

    assert validate_discovery_lineage({"contract": "requirement-evidence-v2"}) == {
        "status": "legacy_unrecorded",
        "valid": None,
    }


@pytest.mark.parametrize("mutation", ["same_length_text", "document_offset"])
def test_lineage_must_map_back_to_recorded_literal_witness(mutation):
    from app.services.requirement_contract import validate_discovery_lineage

    value = selection()
    proposal = value["proposals"][0]
    if mutation == "same_length_text":
        proposal["text"] = "x" * len(proposal["text"])
    else:
        proposal["document_range"] = {"start": 9, "end": 18}
    assert validate_discovery_lineage(value)["valid"] is False


# Defect: a forged QA adapter currently accepts an actual null observation.
def test_qa_origin_requires_real_accepted_observation():
    member = chunk("The archivist leads Alder review.")
    observation = QAObservation.capture(
        "r1", member, ReaderSelection(None, {"decision": "no_answer"})
    )
    with pytest.raises(ValueError, match="qa_lineage"):
        make_proposal(
            "r1",
            single_chunk_source(member),
            member,
            4,
            13,
            origin="qa_reader",
            observation=observation,
        )


def test_observation_is_detached_from_later_diagnostic_mutation():
    member = chunk("The archivist leads Alder review.")
    diagnostics = {"decision": "no_answer", "raw_candidates": []}
    observation = QAObservation.capture(
        "r1", member, ReaderSelection(None, diagnostics)
    )
    diagnostics["raw_candidates"].append({"start": 4, "end": 13})
    assert observation.record()["diagnostics"]["raw_candidates"] == []
    with pytest.raises(FrozenInstanceError):
        observation.chunk_id = "another-chunk"


def test_origin_chunk_metadata_cannot_impersonate_snapshot_member():
    from app.evidence_policy import PATTERN_REGISTRY_CONTRACT
    from app.services.source_pattern_proposals import ROLE_PATTERN

    member = chunk("The archivist leads Alder review.")
    forged = member.model_copy(
        update={"metadata": {**member.metadata, "content_hash": "0" * 64}}
    )
    with pytest.raises(ValueError, match="origin_mapping"):
        make_proposal(
            "r1",
            single_chunk_source(member),
            forged,
            4,
            13,
            origin="source_pattern",
            pattern_id=ROLE_PATTERN,
            grammar_version=PATTERN_REGISTRY_CONTRACT,
        )
