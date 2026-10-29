"""Explicit new discovery contract; declarations are proposals, not support."""

from app.evidence_policy import reading_version, resolve_evidence_policy
from app.services.answer_requirements import Requirement
from app.services.source_pattern_proposals import collect_source_proposals

from tests.test_linguistic_runtime_dispatch import config
from tests.test_source_pattern_grammar import source

BODY = (
    "The following instructions govern the standard Copper check routine only, "
    "including references that omit the activity name. "
    "First, inspect the counter. Do not reset it until all readings are stored. "
    "Retain the physical attachments."
)
QUESTION = "Give the complete Copper check routine."
REQ = Requirement(
    "r1", QUESTION, 0, len(QUESTION), QUESTION, "procedure", "Copper check", ("copper",)
)


def test_new_discovery_version_is_captured_without_rewriting_old_registry():
    assert (
        resolve_evidence_policy(config()).record()["pattern_registry_contract"]
        == "typed-source-patterns-v2"
    )
    assert (
        reading_version("contextual_source_v2").procedure
        == "complete-immutable-procedure-v5"
    )


def test_whole_declared_source_has_a_bound_unassessed_seed_even_if_qa_abstains():
    batch = collect_source_proposals(
        REQ, [source(BODY)], reading_profile="contextual_source_v2"
    )
    assert batch.complete and len(batch.proposals) == 1
    proposal = batch.proposals[0].record()
    assert proposal["pattern_id"] == "source-declared-envelope-v2"
    assert proposal["grammar_version"] == "typed-source-patterns-v2"
    assert proposal["text"] == BODY[: BODY.index(". ") + 1]
    assert proposal["document_range"] == proposal["chunk_range"]
    assert "supported" not in proposal and proposal["qa_observation_id"] is None


def test_default_registry_does_not_gain_the_new_admission_rule():
    batch = collect_source_proposals(REQ, [source(BODY)])
    assert not any(
        p.pattern_id == "source-declared-envelope-v2" for p in batch.proposals
    )


def test_unknown_reading_profile_cannot_choose_the_new_grammar():
    import pytest

    with pytest.raises(ValueError):
        collect_source_proposals(REQ, [source(BODY)], reading_profile="forged")


def test_declared_envelope_discovery_keeps_the_positive_named_subject_bound():
    other = BODY.replace("Copper check", "Graphite check")
    batch = collect_source_proposals(
        REQ, [source(other)], reading_profile="contextual_source_v2"
    )
    assert not any(
        p.pattern_id == "source-declared-envelope-v2" for p in batch.proposals
    )
