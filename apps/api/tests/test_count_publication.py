"""Authenticated SQLite/ASGI; recorded parser/QA, UNITONLY classifier boundary."""

import json
import uuid
from copy import deepcopy

import pytest
from app.config import get_settings
from app.models.query import AnswerSpan, Query
from app.services import connected_query, request_parser
from app.services.answer_reader import ReaderSelection, reader_service
from app.services.answer_support import SupportAssessment, support_service

from tests.test_connected_contract import upload
from tests.test_linguistic_reading_profile import CONTROLS
from tests.test_source_bound_counts import fixture, requirement

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize("streaming", [False, True], ids=["normal", "sse"])
async def test_source_bound_count_publishes_and_history_reconstructs(
    real_client, monkeypatch, streaming
):
    data = fixture()
    req = requirement(data)
    client, factory, _ = real_client
    bodies = [
        "There are 4 tokens assigned to Copper alignment.",
        data["actual_bad_candidate"]["whole_source_support"]["premise"],
    ]
    documents = [await upload(client, body) for body in bodies]
    config = get_settings().model_copy(
        deep=True,
        update={
            **CONTROLS,
            "REQUEST_PARSER_MODE": "local_dependency",
            "QUANTITY_VERIFICATION_PROFILE": "literal_source_count_v1",
            "READER_NULL_THRESHOLD": 4,
            "SUPPORT_MIN_MARGIN": 2,
        },
    )
    monkeypatch.setattr(connected_query, "settings", config)

    async def capture(text, settings):
        assert text in data["captures"]
        return deepcopy(data["captures"][text])

    by_body = {o["span"]["text"]: o for o in data["qa_observations"]}

    async def qa(question, contents, config):
        assert question == req.question
        return [
            ReaderSelection(
                AnswerSpan(**by_body[body]["span"]),
                deepcopy(by_body[body]["diagnostics"]),
            )
            for body in contents
        ]

    calls = []

    async def assess(pairs, config):
        calls.extend(pairs)
        return [
            SupportAssessment("entailment", (-5.0, 5.0, -5.0), 10.0, True, 32)
            for pair in pairs
        ]

    monkeypatch.setattr(request_parser, "capture_async", capture)
    monkeypatch.setattr(reader_service, "select_atomic", qa)
    monkeypatch.setattr(
        reader_service,
        "metadata",
        lambda config=None: deepcopy(data["reader_metadata"]),
    )
    monkeypatch.setattr(support_service, "assess", assess)
    monkeypatch.setattr(
        support_service,
        "metadata",
        lambda config=None: deepcopy(data["support_metadata"]),
    )
    errors = []
    prepare = connected_query.prepare_answer

    async def observed(*args, **kwargs):
        try:
            return await prepare(*args, **kwargs)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            raise

    monkeypatch.setattr(connected_query, "prepare_answer", observed)
    response = await client.post(
        "/api/queries/stream" if streaming else "/api/queries",
        json={
            "question": req.question,
            "document_ids": [d["id"] for d in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, (response.text, errors)
    if streaming:
        events = [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert not any(e.get("type") == "error" for e in events), (events, errors)
        result = {
            k: v
            for k, v in next(e for e in events if e.get("type") == "done").items()
            if k != "type"
        }
    else:
        result = response.json()
    assert not result["refused"], (result, errors)
    assert bodies[0] in result["answer"] and "7 minutes" not in result["answer"]
    selection = result["provenance"]["answer_selection"]
    assert selection["evidence_profile"]["contract"] == "evidence-profile-v7"
    assert (
        selection["contextual_mixed_output_certificate"]["contract"]
        == "procedure-output-cover-v7"
    )
    assert len(result["sources"]) == 1
    assert calls and all("7 minutes" not in p.hypothesis for p in calls)
    history = await client.get(f"/api/queries/{result['id']}")
    assert history.status_code == 200, history.text
    assert history.json()["answer"] == result["answer"]
    # Coherently change both saved presentation and its retained input copy.
    # A matching self-reported record is still insufficient: source replay wins.
    async with factory() as db:
        row = await db.get(Query, uuid.UUID(result["id"]))
        provenance = deepcopy(row.provenance)
        trace = deepcopy(row.retrieval_trace)
        for saved in (
            provenance["answer_selection"],
            trace["provenance"]["answer_selection"],
        ):
            for candidate in saved["candidates"]:
                if "quantity_binding" in candidate:
                    candidate["quantity_binding"]["binding"]["canonical_value"][
                        "number"
                    ] = "7"
        row.provenance, row.retrieval_trace = provenance, trace
        await db.commit()
    corrupt = await client.get(f"/api/queries/{result['id']}")
    assert corrupt.status_code == 200
    assert corrupt.json()["answer"] is None
    assert corrupt.json()["sources"] == []
    assert corrupt.json()["evidence_access"] == "unknown"
    assert (
        "integrity"
        in corrupt.json()["provenance"]["answer_selection"][
            "presentation_verification"
        ]["reason"]
    )
