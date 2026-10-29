"""Compact presentation cannot discard stronger accepted part witnesses."""

from app.config import get_settings
from app.models.query import AnswerSpan
from app.services.answer_reader import ReaderSelection, reader_service
from app.services.reader_witnesses import select_witness_cover

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


def candidate(parts, scores, count=2, accepted=True):
    return ReaderSelection(
        AnswerSpan(start=0, end=4, text="text") if accepted else None,
        {
            "part_count": count,
            "covered_parts": parts,
            "parts": [
                {"index": part, "null_margin": score} for part, score in scores.items()
            ],
        },
    )


def test_single_source_and_deterministic_ties_remain_compact():
    result = select_witness_cover(
        [candidate([0, 1], {0: -9, 1: -8}), candidate([0, 1], {0: -9, 1: -8})]
    )
    assert result.indices == (0,)


def test_missing_legacy_scores_preserve_coverage_without_invented_ranking():
    result = select_witness_cover([candidate([0], {}), candidate([1], {})])
    assert result.indices == (0, 1)
    assert all(
        row["null_margin"] is None and row["score_status"] == "unknown"
        for row in result.diagnostics["witnesses"]
    )


def test_null_predictions_cannot_replace_accepted_witnesses():
    result = select_witness_cover(
        [
            candidate([0, 1], {0: -9, 1: -8}),
            candidate([0, 1], {0: -100, 1: -100}, accepted=False),
        ]
    )
    assert result.indices == (0,)


def test_four_stronger_sources_cannot_be_silently_replaced_to_fit_cap():
    result = select_witness_cover(
        [candidate([0, 1, 2, 3], dict.fromkeys(range(4), -1), count=4)]
        + [candidate([part], {part: -10}, count=4) for part in range(4)]
    )
    assert result.indices == ()
    assert result.diagnostics["decision"] == "no_cover_within_citation_limit"


async def test_compact_cover_preserves_stronger_complementary_source(
    real_client, monkeypatch
):
    client, _, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    owner_text = "Nova maintenance is owned by Imani. Place the tools on the mat."
    schedule_text = "Nova maintenance is scheduled on Thursday at 14:20."
    owner = await upload(client, owner_text)
    schedule = await upload(client, schedule_text)

    async def accepted_predictions(question, contexts, config=None):
        result = []
        for text in contexts:
            owns = "Imani" in text
            result.append(
                ReaderSelection(
                    AnswerSpan(start=0, end=len(text), text=text),
                    {
                        "part_count": 2,
                        "covered_parts": [0, 1] if owns else [1],
                        "parts": [
                            {
                                "index": 0,
                                "decision": "answer" if owns else "no_answer",
                                "null_margin": -9 if owns else 3,
                            },
                            {
                                "index": 1,
                                "decision": "answer",
                                "null_margin": -1 if owns else -12,
                            },
                        ],
                    },
                )
            )
        return result

    monkeypatch.setattr(reader_service, "select", accepted_predictions)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who owns Nova maintenance, and when is it scheduled?",
            "document_ids": [owner["id"], schedule["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["outcome"] == "completed"
    assert {source["document_id"] for source in row["sources"]} == {
        owner["id"],
        schedule["id"],
    }
    assert "Thursday at 14:20" in row["answer"]
