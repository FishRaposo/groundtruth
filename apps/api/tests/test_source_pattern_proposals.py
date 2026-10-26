"""Closed source grammar controls and failure paths on invented sources only."""

from app.services import requirement_answers
from app.services.answer_requirements import plan_requirements
from app.services.procedure_evidence import single_chunk_source
from app.services.requirement_binding import role_discovery_candidates
from app.services.source_pattern_proposals import collect_source_proposals

from tests.test_composite_procedures import chunk, config, doubles


def test_source_overflow_is_visible_whole_requirement_refusal():
    member = chunk(
        " ".join(
            f"The {actor} leads Alder review."
            for actor in (
                "archivist",
                "records clerk",
                "desk steward",
                "dispatch clerk",
            )
        )
    )
    batch = collect_source_proposals(
        plan_requirements("Who leads Alder review?")[0], [single_chunk_source(member)]
    )
    assert not batch.complete and not batch.proposals
    assert batch.observations[0]["decision"] == "pattern_source_budget_exceeded"
    assert batch.observations[0]["truncated"] is True


def test_unknown_roles_and_other_fact_kinds_are_outside_registry():
    member = chunk(
        "The owner for Alder review is the archivist. Alder review lasts 12 minutes."
    )
    batch = collect_source_proposals(
        plan_requirements("Who owns Alder review?")[0], [single_chunk_source(member)]
    )
    assert batch.complete and not batch.proposals


def test_role_inspection_enumerates_multiple_assignments_with_exact_ranges():
    text = "The archivist leads Alder review. The deputy clerk leads Alder review."
    found = role_discovery_candidates(
        plan_requirements("Who leads Alder review?")[0], text
    )
    assert len(found) == 2
    assert [item["value"] for item in found] == ["The archivist", "The deputy clerk"]
    for item in found:
        assert (
            text[item["value_range"]["start"] : item["value_range"]["end"]]
            == item["value"]
        )
        assert (
            "Alder review"
            in text[item["target_range"]["start"] : item["target_range"]["end"]]
        )


# Defect: source-pattern discovery currently bypasses the request workspace restriction.
async def test_pattern_cannot_bypass_workspace_binding(monkeypatch):
    from dataclasses import replace

    member = chunk("The archivist leads Alder review.")
    calls = doubles(monkeypatch, member)
    requirement = replace(
        plan_requirements("Who leads Alder review?")[0], source_workspace="ops-b"
    )
    found = await requirement_answers._find_witnesses(
        requirement, [member], config(), []
    )
    assert not found and not calls


def test_total_pattern_overflow_refuses_instead_of_truncating():
    sources = [
        single_chunk_source(chunk(f"The clerk leads Alder review. Record {i}."))
        for i in range(17)
    ]
    batch = collect_source_proposals(
        plan_requirements("Who leads Alder review?")[0], sources
    )
    assert not batch.complete and not batch.proposals
    assert batch.observations[-1]["decision"] == "pattern_requirement_budget_exceeded"


def test_snapshot_hash_and_both_source_endpoints_are_mandatory():
    from dataclasses import replace

    from app.services.procedure_evidence import LocatedChunk

    member = chunk("The archivist leads Alder review.")
    source = single_chunk_source(member)
    requirement = plan_requirements("Who leads Alder review?")[0]
    for broken in (
        replace(source, identity={**source.identity, "content_hash": "0" * 64}),
        replace(source, chunks=(LocatedChunk(member, 1, len(member.content)),)),
    ):
        batch = collect_source_proposals(requirement, [broken])
        assert not batch.complete and not batch.proposals


async def test_pattern_condition_and_support_rejection_produce_no_answer(monkeypatch):
    for text, reject in (
        ("For special Larch review, the archivist leads Larch review.", False),
        ("The archivist leads Larch review.", True),
    ):
        member = chunk(text)
        doubles(monkeypatch, member, reject=reject)
        found = await requirement_answers._find_witnesses(
            plan_requirements("Who leads ordinary Larch review?")[0],
            [member],
            config(),
            [],
        )
        assert not found


def test_exact_source_limit_preserves_all_three_candidates():
    member = chunk(
        "The archivist leads Alder review. The records clerk leads Alder review. "
        "The desk steward leads Alder review."
    )
    batch = collect_source_proposals(
        plan_requirements("Who leads Alder review?")[0], [single_chunk_source(member)]
    )
    assert batch.complete and len(batch.proposals) == 3
