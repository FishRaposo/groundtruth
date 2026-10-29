"""UNITONLY curated closure: unparsed instructions cannot disappear before NLI."""

from copy import deepcopy
from typing import Any, cast

import pytest

from tests.curated_capture_fixtures import (
    curated_capture_runtime as curated_capture_runtime,
)
from tests.test_contextual_mixed_output import output, produce
from tests.test_curated_consumer_proof import factual_group_fixture


@pytest.mark.parametrize(
    "body",
    [
        "Delegate the Alder review decision to the caretaker.",
        "If the archivist is absent, designate the caretaker for Alder review.",
        "Refer to the current assignment register for Alder review.",
        "Follow the caretaker's determination for Alder review.",
        "The inspection lasts 8 minutes. Refer to the assignment register.",
        "The inspection lasts 8 minutes, then designate the caretaker.",
        "The inspection that determines the Alder lead lasts 8 minutes.",
        "The inspection lasts 8 minutes unless the caretaker is appointed.",
        "The caretaker leads Birch review. Refer to the Alder assignment register.",
    ],
)
def test_unknown_directive_or_referral_cannot_certify_nonconflict(body):
    # Break: an imperative/known other-field signal excluded the whole source.
    data = factual_group_fixture(foreign_body=body)
    with pytest.raises(ValueError):
        produce(data)


@pytest.mark.parametrize(
    "body",
    [
        "The inspection lasts 8 minutes.",
        "The inspection takes 8 minutes.",
        "The Alder review session starts at 09:00.",
        "The inspection starts on Tuesday.",
        "The caretaker leads Birch review.",
        "Retest: use the temporary sheet.",
    ],
)
def test_complete_explicit_unrelated_fact_still_publishes_and_replays(body):
    data = factual_group_fixture(foreign_body=body)
    actual = produce(data)
    proof = actual["certificate"]["curated_inspections"][0]
    assert proof["subject_scope_excluded_documents"] == [
        "00000000-0000-0000-0000-000000000099"
    ]
    assert len(proof["comparisons"]) == 1
    data["selection"][output.CERTIFICATE_FIELD] = deepcopy(actual["certificate"])
    context = {k: v for k, v in data.items() if k != "selection"}
    context.update(answer=actual["answer"], citations=actual["citations"])
    assert output.verify_output(data["selection"], **context)


def test_positive_other_relation_proof_is_independently_reconstructed():
    data = factual_group_fixture(foreign_body="The inspection lasts 8 minutes.")
    actual = produce(data)
    proof = actual["certificate"]["curated_inspections"][0]
    assert (
        proof["source_scope_decisions"][1]["scope_cover"][0]["other_relation_proof"][
            "kind"
        ]
        == "duration"
    )
    data["selection"][output.CERTIFICATE_FIELD] = deepcopy(actual["certificate"])
    certificate = data["selection"][output.CERTIFICATE_FIELD]
    certificate["curated_inspections"][0]["source_scope_decisions"][1]["scope_cover"][
        0
    ]["other_relation_proof"] = {"kind": "duration", "subject": "forged"}
    context = {k: v for k, v in data.items() if k != "selection"}
    context.update(answer=actual["answer"], citations=actual["citations"])
    assert not output.verify_output(data["selection"], **context)


@pytest.mark.parametrize("condition", ["the archivist is absent", "pending approval"])
def test_unknown_declared_condition_is_not_positive_disjointness(condition):
    # Break: disjoint words in metadata were mistaken for exclusive conditions.
    from app.services.curated_conflict_proof import fact_inputs

    data = factual_group_fixture(
        foreign_body="Delegate the Alder review decision to the caretaker."
    )
    snapshot = data["source_snapshots"]["00000000-0000-0000-0000-000000000099"]
    snapshot["metadata"]["condition"] = condition
    record = data["selection"]["conflicts"][0]
    req = data["request_reconstructor"](data["question"], {}).requirements[0]
    scopes, _, pairs = fact_inputs(
        req,
        data["source_snapshots"],
        record["inspection_sources"],
        record["witness_claims"],
    )
    assert scopes[1]["included"] is True
    assert any(row["premise"] == snapshot["body"] for row in pairs)


@pytest.mark.parametrize(
    ("body", "excluded"),
    [
        ("Delegate the Alder review decision to the caretaker.", False),
        (
            "If the archivist is absent, designate the caretaker for Alder review.",
            False,
        ),
        ("Refer to the current assignment register for Alder review.", False),
        ("The inspection lasts 8 minutes.", True),
    ],
)
async def test_actual_producer_compares_unknown_opponent_despite_qa_abstention(
    monkeypatch, body, excluded
):
    # Break: controller certified complete nonconflict without opponent NLI.
    from app.models.chunk import ChunkWithScore
    from app.models.query import AnswerSpan, QueryRequest
    from app.services import procedure_evidence
    from app.services import requirement_answers as controller
    from app.services.answer_support import SupportAssessment

    from tests.test_contextual_mixed_output import mirror
    from tests.test_linguistic_runtime_dispatch import config

    data = factual_group_fixture(foreign_body=body)
    req = data["request_reconstructor"](data["question"], {}).requirements[0]
    members = [
        ChunkWithScore(
            id=s["chunks"][0]["id"],
            document_id=s["document_id"],
            content=s["body"],
            chunk_index=0,
            relevance_score=1.0,
            metadata={
                **s["metadata"],
                **{
                    k: s[k]
                    for k in ("document_version", "content_hash", "workspace_id")
                },
            },
        )
        for s in data["source_snapshots"].values()
    ]
    sources = {m.id: procedure_evidence.single_chunk_source(m) for m in members}
    resolved, compared = [], []

    async def resolve(db, principal, request, member, inspected):
        resolved.append(str(member.id))
        return sources[member.id]

    async def retrieve(*args, **kwargs):
        return members, False

    async def current(member):
        return True

    async def assess(pairs, **kwargs):
        compared.extend(p.premise for p in pairs)
        return [
            SupportAssessment("entailment", (-1.0, 5.0, 0.0), 5.0, True, 80)
            if p.premise == members[0].content
            else SupportAssessment("neutral", (-1.0, 0.0, 5.0), -5.0, False, 80)
            for p in pairs
        ]

    monkeypatch.setattr(procedure_evidence, "resolve_version", resolve)
    monkeypatch.setattr(controller, "inspect_curated_group", retrieve)
    monkeypatch.setattr(controller.support_service, "assess", assess)
    raw = data["selection"]["requirements"][0]["witnesses"][0]
    witness = controller.Witness(
        req.id,
        members[0],
        AnswerSpan(**raw["span"]),
        raw["value"],
        data["selection"]["candidates"][0]["hypothesis"],
        5.0,
        -3.0,
    )
    records, relevant = await controller._inspect_conflicts(
        cast(Any, None),
        QueryRequest(question=data["question"]),
        {},
        {members[0].id: members[0]},
        (req,),
        {req.id: req},
        {req.id: [witness]},
        config(),
        current,
        [],
    )
    assert set(resolved) == {str(m.id) for m in members}
    assert (body in compared) is (not excluded)
    assert records[0]["inspection_complete"] is True
    assert relevant is (not excluded)
    data["selection"]["conflicts"] = records
    mirror(data)
    if excluded:
        actual = produce(data)
        assert "archivist" in actual["answer"]
    else:
        assert records[0]["outcome"] == "comparison_unconfirmed"
        with pytest.raises(ValueError):
            produce(data)
