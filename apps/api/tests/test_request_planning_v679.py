"""Missing personal antecedents and adjective-as-subject errors must fail.

Every row is a complete actual cached CPU parse of a prefrozen question.
Expected request semantics are engineering assertions, not answer truth labels.
"""

import json
from pathlib import Path

import pytest
from app.services.linguistic_requirements import plan_request, validate_request_plan

F = json.loads(
    (Path(__file__).parent / "fixtures/dependency_graphs_v679.json").read_text()
)


def _assert_reference_inventory(expected, p):
    if expected["reference"] is not None:
        assert any(
            expected["reference"] in s.text.split()
            for u in p.uses
            for s in u.references
        )
        if not expected["resolved"]:
            assert any("reference" in u.reason for u in p.unresolved)
        assert not any(r.depends_on for r in p.requirements)


@pytest.mark.parametrize("row", F["captures"], ids=lambda r: r["id"])
def test_actual_reference_and_qualified_role_closure(row):
    cap = row["capture"]
    question = cap["annotation"]["raw_text"]
    p = plan_request(question, cap)
    expected = F["expected"][row["id"]]
    assert p.resolved_request is expected["resolved"]
    if expected["topics"] is not None:
        assert [r.topic for r in p.requirements] == expected["topics"]
    _assert_reference_inventory(expected, p)
    if row["id"] in {"local-including", "local-preserving"}:
        assert p.uses[0].grammar.endswith("_local_procedure_reference")
        assert p.uses[0].governors
    if row["id"].startswith("adjective-") and expected["resolved"]:
        assert "interim deputy" in p.requirements[1].attribute
    if row["id"].startswith("novel-adjective-"):
        assert "acting deputy" in p.requirements[1].attribute
    if row["id"] == "condition-modal":
        assert all(u.condition_ast for u in p.uses)
        assert all("may not attend" in r.question for r in p.requirements)
        assert all({"may", "not"} <= {s.text for s in u.modality} for u in p.uses)
    if row["id"] == "expletive-there":
        token = next(t for t in cap["annotation"]["tokens"] if t["text"] == "there")
        assert token["dep"] == "expl" and token["tag"] == "EX"
        assert all(u.condition_ast for u in p.uses)
        assert not any("there" in s.text.split() for u in p.uses for s in u.references)
    assert validate_request_plan(p.record(), question=question, capture=cap)
    assert len(p.consumption) == len(cap["annotation"]["tokens"])
    for r, use in zip(p.requirements, p.uses, strict=True):
        for group in [
            use.conditions,
            use.modality,
            use.units,
            use.governors,
            use.references,
        ]:
            assert all(s.text in r.question for s in group)
