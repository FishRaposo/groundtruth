"""Loss of requested nominal slots or compound obligations is a real failure.

Inputs are retained actual question graphs and prefrozen actual638 engineering
captures. Expected structure is question grammar, never source/answer truth.
"""

import json
from pathlib import Path

import pytest
from app.services.linguistic_requirements import plan_request, validate_request_plan

F = json.loads(
    (Path(__file__).parent / "fixtures/dependency_graphs_v662.json").read_text()
)


@pytest.mark.parametrize("row", F["captures"], ids=lambda r: r["id"])
def test_actual_nominal_and_compound_requests_keep_every_obligation(row):
    cap = row["capture"]
    question = cap["annotation"]["raw_text"]
    p = plan_request(question, cap)
    expected = F["expected"][row["id"]]
    if expected["kinds"] is not None:
        assert [r.kind for r in p.requirements] == expected["kinds"]
    assert p.resolved_request is expected["resolved"]
    assert validate_request_plan(p.record(), question=question, capture=cap)
    assert "".join(c.evidence.text for c in p.consumption) == "".join(
        t["text"] for t in cap["annotation"]["tokens"]
    )
    if row["id"] == "d526-08-facts":
        assert "checking duration" in p.requirements[1].attribute
        assert {r.topic for r in p.requirements} == {"Jade Path pointer transcription"}
    if row["id"] == "d526-06-combined":
        assert "all exception handling" in p.requirements[2].question
        assert p.uses[2].governors
    if row["id"] == "d526-12-combined":
        assert "every governing note" in p.requirements[2].question
    if row["id"] == "e662-qualified":
        assert all(u.condition_ast for u in p.uses)
        assert all(
            "unless the supervisor is absent" in r.question for r in p.requirements
        )
        units = {s.text for u in p.uses for s in u.units}
        assert {"1.50 mW", "seconds"} <= units
    if row["id"] == "e662-distinct":
        assert p.requirements[0].topic == p.requirements[1].topic == "Indigo audit"
        assert p.requirements[2].topic == "Copper review"
    if row["id"] == "e662-conditional-compound":
        assert all(u.condition_ast for u in p.uses)
        assert all(
            "unless the supervisor is absent" in r.question for r in p.requirements
        )
    if row["id"] in {"e662-why", "e662-action", "e662-extra-action"}:
        literal = {
            "e662-why": "why",
            "e662-action": "reduce",
            "e662-extra-action": "delete",
        }[row["id"]]
        assert literal in " ".join(r.question for r in p.requirements).casefold()
