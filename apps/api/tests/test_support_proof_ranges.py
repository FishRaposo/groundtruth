"""Source proof diagnostics must identify the actual occurrence, not the first."""

from types import SimpleNamespace

import pytest
from app.config import Settings
from app.models.query import AnswerSpan
from app.services import requirement_answers as module
from app.services.answer_reader import ReaderSelection
from app.services.answer_support import SupportAssessment

from tests.test_requirement_cover_boundaries import chunk

BODY = "Select profile C. Alice leads Quartz review. Select profile C."
CHECK = "Select profile C."


def proof_decision(diagnostics, decision):
    # QA observations are independently retained after the candidate diagnostics.
    matching = [row for row in diagnostics if row.get("decision") == decision]
    assert len(matching) == 1
    return matching[0]


async def run(
    monkeypatch, check_offsets, edge=None, *, raw_bounds=None, primary_bounds=None
):
    req = module.plan_requirements("Who leads Quartz review?")[0]
    start = BODY.index("Alice")
    check = SimpleNamespace(
        name="profile",
        premise=CHECK,
        hypothesis="Profile C is selected.",
        **check_offsets,
    )
    primary_start, primary_end = primary_bounds or (0, len(BODY))
    raw_start, raw_end = raw_bounds or (start, start + 5)
    claim = SimpleNamespace(
        rejection=None,
        hypothesis="Alice leads Quartz review.",
        premise=BODY[primary_start:primary_end],
        premise_start=primary_start,
        premise_end=primary_end,
        value="Alice",
        start=start,
        end=start + 5,
        support_start=0,
        support_end=len(BODY),
        checks=(check,),
        proof_edges=() if edge is None else (edge,),
    )

    async def predict(question, contexts, config=None):
        return [
            ReaderSelection(
                AnswerSpan(start=start, end=start + 5, text="Alice"),
                {"raw_span": {"start": raw_start, "end": raw_end}, "null_margin": -5},
            )
        ]

    async def entail(pairs, config=None):
        return [SupportAssessment("entailment", (-5, 5, -5), 10, True) for _ in pairs]

    monkeypatch.setattr(module.reader_service, "select_atomic", predict)
    monkeypatch.setattr(module.support_service, "assess", entail)
    monkeypatch.setattr(module, "support_claim", lambda *args: claim)
    diagnostics = []
    witnesses = await module._find_witnesses(
        req, [chunk(BODY, 1)], Settings(), diagnostics
    )
    return witnesses, diagnostics


async def test_narrowing_cannot_discard_the_accepted_raw_context(monkeypatch):
    left = BODY.index("Alice")
    right = BODY.index(". Select") + 1
    witnesses, diagnostics = await run(
        monkeypatch,
        {"start": 0, "end": len(CHECK)},
        raw_bounds=(0, len(BODY)),
        primary_bounds=(left, right),
    )
    assert witnesses == []
    assert (
        proof_decision(diagnostics, "raw_context_not_verified")["decision"]
        == "raw_context_not_verified"
    )


async def test_narrowing_with_the_entire_raw_in_a_mandatory_proof_is_allowed(
    monkeypatch,
):
    witnesses, diagnostics = await run(
        monkeypatch,
        {"start": 0, "end": len(CHECK)},
        raw_bounds=(0, len(BODY)),
    )
    assert witnesses
    supported = proof_decision(diagnostics, "supported")
    assert supported["raw_span"] == {"start": 0, "end": len(BODY)}
    assert supported["validated_answer_span"]["text"] == "Alice"


async def test_explicit_second_occurrence_is_the_recorded_proof(monkeypatch):
    start = BODY.rindex(CHECK)
    witnesses, diagnostics = await run(monkeypatch, {"start": start, "end": len(BODY)})
    assert witnesses
    assert proof_decision(diagnostics, "supported")["support_checks"][0][
        "source_range"
    ] == {
        "start": start,
        "end": len(BODY),
    }


@pytest.mark.parametrize(
    "offsets",
    [{}, {"start": 0, "end": 4}, {"start": False, "end": len(CHECK)}, {"start": 0}],
)
async def test_ambiguous_or_invalid_ranges_cannot_be_successful_proofs(
    monkeypatch, offsets
):
    witnesses, _ = await run(monkeypatch, offsets)
    assert witnesses == []


async def test_foreign_requirement_cannot_supply_an_edge(monkeypatch):
    edge = SimpleNamespace(
        name="worksheet_namespace_to_applicability",
        source_start=0,
        source_end=len(CHECK),
        target_start=BODY.index("Alice"),
        target_end=BODY.index("Alice") + 5,
        requirement_id="foreign",
        depends_on=(),
    )
    witnesses, _ = await run(
        monkeypatch,
        {"start": 0, "end": len(CHECK)},
        edge,
    )
    assert witnesses == []


async def test_real_atomic_proof_requires_every_recorded_model_check(monkeypatch):
    from tests.test_binding_additional_scope import METHOD, procedure_req

    req = procedure_req()
    selected = "Write depth zero in the left margin"
    start = METHOD.index(selected)

    async def predict(question, contexts, config=None):
        return [
            ReaderSelection(
                None,
                {
                    "raw_candidates": [
                        {
                            "start": start,
                            "end": start + len(selected),
                            "null_margin": -9,
                        }
                    ]
                },
            )
        ]

    model_pairs = []

    async def entail(pairs, config=None):
        model_pairs.extend(pairs)
        return [SupportAssessment("entailment", (-5, 5, -5), 10, True) for _ in pairs]

    monkeypatch.setattr(module.reader_service, "select_atomic", predict)
    monkeypatch.setattr(module.support_service, "assess", entail)
    witnesses = await module._find_witnesses(req, [chunk(METHOD, 1)], Settings(), [])
    assert witnesses
    assert len(model_pairs) == 4  # Instructions, namespace, applicability, prohibition.
    assert len(witnesses[0].proof_edges) == 3

    async def deny_one(pairs, config=None):
        return [
            SupportAssessment("neutral", (-5, -5, 5), -10, False)
            if index == 2
            else SupportAssessment("entailment", (-5, 5, -5), 10, True)
            for index, _ in enumerate(pairs)
        ]

    monkeypatch.setattr(module.support_service, "assess", deny_one)
    assert await module._find_witnesses(req, [chunk(METHOD, 1)], Settings(), []) == []
