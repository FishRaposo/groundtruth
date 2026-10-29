"""Actual cached-parser closure checks; expected request structure is not truth.

These catch silently inherited named subjects and omitted governor antecedents.
All captures are complete real CPU parses of prefrozen engineering questions.
"""

import json
from pathlib import Path

import pytest
from app.services.linguistic_requirements import plan_request, validate_request_plan

F = json.loads(
    (Path(__file__).parent / "fixtures/dependency_graphs_v671.json").read_text()
)


def _assert_scope_reference_controls(row, p):
    if row["id"] in {"named-ambiguous", "novel-named-ambiguous"}:
        expected_deputy = (
            "Copper review" if row["id"] == "named-ambiguous" else "Amber check"
        )
        assert p.requirements[1].topic == expected_deputy
        assert any("reference" in u.reason for u in p.unresolved)
    if row["id"] in {
        "governor-their",
        "novel-governor-their",
        "governor-its",
        "novel-governor-those",
        "governor-these",
    }:
        cue = (
            "these"
            if row["id"] == "governor-these"
            else "those"
            if row["id"].endswith("those")
            else "its"
            if row["id"] == "governor-its"
            else "their"
        )
        assert any(cue in s.text.split() for s in p.uses[-1].references)
        assert any("reference" in u.reason for u in p.unresolved)
        assert not p.requirements[-1].depends_on


@pytest.mark.parametrize("row", F["captures"], ids=lambda r: r["id"])
def test_actual_named_scopes_and_governor_references_are_closed(row):
    cap = row["capture"]
    question = cap["annotation"]["raw_text"]
    p = plan_request(question, cap)
    expected = F["expected"][row["id"]]
    assert p.resolved_request is expected["resolved"]
    if expected["topics"] is not None:
        if expected["resolved"]:
            assert [r.kind for r in p.requirements] == ["owner", "deputy", "procedure"]
        assert [r.topic for r in p.requirements] == expected["topics"]
    _assert_scope_reference_controls(row, p)
    if row["id"] in {"qualified-named", "qualified-governor-unit"}:
        assert all(u.condition_ast for u in p.uses)
        assert all(
            "unless the supervisor is absent" in r.question for r in p.requirements
        )
    if row["id"] == "qualified-governor-unit":
        assert "1.50 mW" in {s.text for s in p.uses[-1].units}
        assert "all 1.50 mW restrictions" in p.requirements[-1].question
    if row["id"] == "qualified-named":
        assert all(r.source_workspace == "ops-b" for r in p.requirements)
    if row["id"] == "qualified-inherited-deputy":
        assert "acting deputy" in p.requirements[1].attribute
    if row["id"] == "condition-it":
        assert all(u.condition_ast for u in p.uses)
        assert all(any(s.text == "it" for s in u.references) for u in p.uses)
    assert validate_request_plan(p.record(), question=question, capture=cap)
    assert len(p.consumption) == len(cap["annotation"]["tokens"])
    assert all(
        question[c.evidence.start : c.evidence.end] == c.evidence.text
        for c in p.consumption
    )
    for r, use in zip(p.requirements, p.uses, strict=True):
        for group in [
            use.conditions,
            use.modality,
            use.units,
            use.governors,
            use.references,
        ]:
            assert all(s.text in r.question for s in group)
