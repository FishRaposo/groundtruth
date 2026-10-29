"""R640 composition regressions: retained actual and explicit UNITONLY graphs."""

import json
from pathlib import Path

import pytest
from app.services.linguistic_requirements import plan_request, validate_request_plan
from app.services.request_parser import make_capture

F = Path(__file__).parent / "fixtures"
ENGINEERING = json.loads((F / "dependency_graphs_v642.json").read_text())


def planned_case(name):
    rows = json.loads((F / "dependency_adversarial_v642.json").read_text())["cases"]
    row = next(r for r in rows if r["name"] == name)
    return plan_request(row["question"], row["capture"])


def test_dependent_nominal_normalizes_after_binding_with_all_qualifiers():
    p = planned_case("UNITONLY-conditional-dependency")
    assert p.resolved_request
    r, use = p.requirements[1], p.uses[1]
    assert r.question.startswith("What is ")
    assert "that role's availability" in r.question
    for group in [use.conditions, use.modality, use.units, use.governors]:
        assert all(s.text in r.question for s in group)
    assert "unless the deputy is absent" in r.question
    assert r.depends_on == ("r1",)


def test_actual_dependent_nominal_has_prepared_interrogative():
    rows = json.loads((F / "dependency_graphs_v628.json").read_text())["captures"]
    row = next(r for r in rows if r["id"] == "e628-explicit-data-reference")
    cap = row.get("capture") or make_capture(row["annotation"])
    q = cap["annotation"]["raw_text"]
    p = plan_request(q, cap)
    assert p.resolved_request
    assert p.requirements[1].question == "What is that role's availability?"
    assert validate_request_plan(p.record(), question=q, capture=cap)


def test_passive_owns_only_its_predicate_and_retains_condition_ast():
    p = planned_case("UNITONLY-passive-extra-WH")
    assert p.resolved_request
    assert [r.kind for r in p.requirements] == [
        "quantity",
        "duration",
        "location",
        "deputy",
    ]
    assert "deputy" not in p.requirements[0].question
    conditional = planned_case("UNITONLY-passive-conditional")
    assert conditional.resolved_request
    assert all(u.condition_ast for u in conditional.uses)
    assert all("unless" in r.question for r in conditional.requirements)


def test_standalone_procedure_uses_common_workspace_processing():
    row = json.loads((F / "dependency_adversarial_v642.json").read_text())["workspace"]
    p = plan_request(row["question"], row["capture"])
    assert p.resolved_request
    assert all(
        r.source_workspace == row["expected_source_workspace"] for r in p.requirements
    )


@pytest.mark.parametrize("row", ENGINEERING["captures"], ids=lambda r: r["id"])
def test_actual_prefrozen_question_grammar(row):
    expected = ENGINEERING["expected"][row["id"]]
    cap = row["capture"]
    q = cap["annotation"]["raw_text"]
    p = plan_request(q, cap)
    if expected["kinds"] is not None:
        assert [r.kind for r in p.requirements] == expected["kinds"]
    assert p.resolved_request is expected["resolved"]
    assert validate_request_plan(p.record(), question=q, capture=cap)
    assert "".join(c.evidence.text for c in p.consumption) == "".join(
        t["text"] for t in cap["annotation"]["tokens"]
    )
    if row["id"] == "e642-context-assumption":
        assert all(u.condition_ast for u in p.uses)
        assert all("no separate staffing note" in r.question for r in p.requirements)
    if row["id"] == "e642-qualified-replication":
        assert p.requirements[0].topic == "ops-b replication of Nickel review"
        assert p.requirements[0].source_workspace is None
    if row["id"] == "e642-entity-anaphora":
        assert p.requirements[1].topic == "Nickel review"
        assert p.requirements[1].depends_on == ()
    if row["id"] == "e642-how-must-complete":
        assert [s.text for s in p.uses[0].modality] == ["must"]
        assert "must" in p.requirements[0].question
    if row["id"] == "e642-unknown-and-governor":
        assert "rotation angle" in " ".join(r.question for r in p.requirements)
