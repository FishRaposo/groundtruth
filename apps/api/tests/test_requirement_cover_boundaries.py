"""Independent controller probes. No external models, services, or source edits."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from app.config import Settings
from app.models.chunk import ChunkWithScore
from app.models.query import AnswerSpan, QueryRequest
from app.services import requirement_answers as module
from app.services.answer_support import SupportAssessment


def chunk(content, index, group=None):
    return ChunkWithScore(
        id=uuid.UUID(int=index),
        document_id=uuid.UUID(int=1000 + index),
        content=content,
        chunk_index=0,
        relevance_score=1.0,
        metadata={
            "document_version": 1,
            "content_hash": "a" * 64,
            "workspace_id": "w",
            "conflict_group": group,
        },
    )


def requirement(identifier, question, depends=()):
    return SimpleNamespace(
        id=identifier,
        question=question,
        original_text=question,
        input_start=0,
        input_end=len(question),
        kind="role" if not depends else "hours",
        depends_on=depends,
        source_workspace=None,
    )


def witness(req, source, value, hypothesis, margin=10):
    start = source.content.index(value)
    return module.Witness(
        req.id,
        source,
        AnswerSpan(start=start, end=start + len(value), text=value),
        value,
        hypothesis,
        margin,
        -10,
    )


async def valid(source):
    return True


@pytest.mark.parametrize("rank", [1, 4])
async def test_truncated_group_never_certifies_a_complete_inspection(rank):
    root = module.plan_requirements("Who leads Quartz review?")[0]
    selected = chunk("Alice leads Quartz review.", 1, "curated-review")
    # These are the first 64 scoped SQL rows in a larger curated group. A later
    # row can contain an actual opponent, so the lookup reports truncation.
    capped = [
        chunk(f"The unrelated inventory item is {i}.", 10 + i, "curated-review")
        for i in range(64)
    ]

    outsiders = [
        chunk(f"Owner {index} leads Quartz review.", 80 + index)
        for index in range(rank - 1)
    ]

    async def found(
        req,
        scope,
        config,
        candidates,
        *,
        policy=None,
        resolve_source=None,
        pattern_observations=None,
        request_plan=None,
    ):
        return [
            witness(
                root,
                source,
                f"Owner {index}",
                f"Owner {index} leads Quartz review.",
                20,
            )
            for index, source in enumerate(outsiders)
        ] + [witness(root, selected, "Alice", "Alice leads Quartz review.")]

    async def inspect(*args, **kwargs):
        return capped, True

    async def neutral(pairs, config=None):
        return [
            SupportAssessment("neutral", (-5.0, -5.0, 5.0), -10.0, False) for _ in pairs
        ]

    with (
        patch.object(module, "plan_requirements", return_value=(root,)),
        patch.object(
            module, "resolve_requirement", side_effect=lambda req, values: req
        ),
        patch.object(module, "_find_witnesses", side_effect=found),
        patch.object(module, "inspect_curated_group", side_effect=inspect),
        patch.object(module.support_service, "assess", side_effect=neutral),
    ):
        result = await module.select_requirement_answer(
            None,
            QueryRequest(question=root.question),
            {"id": "user", "workspace_id": "w"},
            [*outsiders, selected],
            Settings(),
            validate_current=valid,
        )
    assert result.reason is not None
    assert any(row["outcome"] == "comparison_unconfirmed" for row in result.conflicts)
    assert str(selected.id) in {row["chunk_id"] for row in result.inspected_sources}


async def test_dependency_cover_retains_the_resolved_owner():
    root = requirement("r1", "Who leads Quartz review?")
    dependent = requirement("r2", "During which hours is that role present?", ("r1",))
    alice = chunk("Alice leads Quartz review.", 1)
    combined = chunk(
        "Bob leads Quartz review. Alice is present from 09:00 to 17:00.", 2
    )
    prepared = []

    def resolve(req, values):
        if req.id == "r1":
            return req
        prepared.append(values["r1"])
        return requirement(
            "r2", f"During which hours is {values['r1']} present?", ("r1",)
        )

    async def found(
        req,
        scope,
        config,
        candidates,
        *,
        policy=None,
        resolve_source=None,
        pattern_observations=None,
        request_plan=None,
    ):
        if req.id == "r1":
            return [
                witness(req, alice, "Alice", "Alice leads Quartz review.", 20),
                witness(req, combined, "Bob", "Bob leads Quartz review.", 10),
            ]
        return [
            witness(
                req, combined, "09:00 to 17:00", "Alice is present from 09:00 to 17:00."
            )
        ]

    with (
        patch.object(module, "plan_requirements", return_value=(root, dependent)),
        patch.object(module, "resolve_requirement", side_effect=resolve),
        patch.object(module, "_find_witnesses", side_effect=found),
    ):
        result = await module.select_requirement_answer(
            None,
            QueryRequest(
                question=(
                    "Who leads Quartz review, and during which hours "
                    "is that role present?"
                )
            ),
            {"id": "user", "workspace_id": "w"},
            [alice, combined],
            Settings(),
            validate_current=valid,
        )
    assert prepared == ["Alice"]
    assert result.reason is None
    assert alice.id in result.spans
    assert result.spans[alice.id].text == "Alice"
