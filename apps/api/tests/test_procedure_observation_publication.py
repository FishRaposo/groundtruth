"""Real SQLite/ASGI; retained parser/QA/NLI inputs are UNITONLY boundaries.

The fixture comes from failed real trial712. These tests neither execute models
nor relabel that trial as a successful application observation.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from app.config import get_settings
from app.models.query import AnswerSpan
from app.services import connected_query, request_parser
from app.services.answer_reader import ReaderSelection, reader_service
from app.services.answer_support import SupportAssessment, support_service

from tests.test_connected_contract import upload
from tests.test_linguistic_reading_profile import CONTROLS

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize("streaming", [False, True], ids=["normal", "sse"])
@pytest.mark.parametrize("count_profile", ["legacy_v1", "literal_source_count_v1"])
async def test_complete_procedure_publishes_only_canonical_pattern_observations(
    real_client, monkeypatch, streaming, count_profile
):
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/procedure_model_inputs_v712.json").read_text(
            encoding="utf-8"
        )
    )
    client, _, _ = real_client
    document = await upload(client, fixture["body"])
    config = get_settings().model_copy(
        deep=True,
        update={
            **CONTROLS,
            "REQUEST_PARSER_MODE": "local_dependency",
            "READER_NULL_THRESHOLD": 4,
            "SUPPORT_ENTAILMENT_MARGIN": 2,
            "QUANTITY_VERIFICATION_PROFILE": count_profile,
        },
    )
    monkeypatch.setattr(connected_query, "settings", config)
    failures = []
    prepare = connected_query.prepare_answer

    async def observed_prepare(*args, **kwargs):
        try:
            return await prepare(*args, **kwargs)
        except Exception as exc:
            failures.append(f"{type(exc).__name__}: {exc}")
            raise

    monkeypatch.setattr(connected_query, "prepare_answer", observed_prepare)

    async def capture(text, settings):
        if text == fixture["question"]:
            return deepcopy(fixture["request_capture"])
        assert len(fixture["source_windows"]) == 1
        source_capture = fixture["source_windows"][0]["capture"]
        assert text == source_capture["annotation"]["raw_text"]
        return deepcopy(source_capture)

    async def qa(question, contents, config):
        if not contents:
            # Readiness asks for no predictions before the atomic requirement.
            assert question == fixture["question"]
            return []
        actual = fixture["qa"]
        assert question == actual["question"] and contents == [fixture["body"]]
        span = AnswerSpan(**actual["span"]) if actual["span"] else None
        return [ReaderSelection(span, deepcopy(actual["diagnostics"]))]

    assessed = []

    async def assess(pairs, config):
        decisions = []
        for pair in pairs:
            exact = [
                row
                for row in fixture["nli"]
                if pair.premise == row["premise"]
                and pair.hypothesis == row["hypothesis"]
            ]
            assert exact, "A new model proposition requires a real new observation"
            assert all(row["assessment"] == exact[0]["assessment"] for row in exact)
            assessed.append((pair.premise, pair.hypothesis))
            decisions.append(SupportAssessment(**deepcopy(exact[0]["assessment"])))
        return decisions

    monkeypatch.setattr(request_parser, "capture_async", capture)
    monkeypatch.setattr(reader_service, "select_atomic", qa)
    monkeypatch.setattr(
        reader_service,
        "metadata",
        lambda config=None: deepcopy(fixture["qa"]["reader"]),
    )
    monkeypatch.setattr(support_service, "assess", assess)
    monkeypatch.setattr(
        support_service,
        "metadata",
        lambda config=None: deepcopy(fixture["support_metadata"]),
    )
    response = await client.post(
        "/api/queries/stream" if streaming else "/api/queries",
        json={
            "question": fixture["question"],
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, (response.text, failures)
    if streaming:
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert not any(event.get("type") in {"error", "refused"} for event in events), (
            failures
        )
        done = [event for event in events if event.get("type") == "done"]
        assert len(done) == 1
        value = {key: item for key, item in done[0].items() if key != "type"}
    else:
        value = response.json()
    assert value["outcome"] == "completed" and value["refused"] is False
    assert value["evidence_access"] == "available"
    assert fixture["body"] in value["answer"]
    assert "Ordinary action arguments are copied literally" in value["answer"]
    selection = value["provenance"]["answer_selection"]
    assert selection["pattern_observations"] == []
    assert any(
        row.get("origin") == "source_pattern" and row.get("decision") == "supported"
        for row in selection["candidates"]
    )
    assert len(selection["selected_proposal_ids"]) == 4
    assert selection["contextual_mixed_output_certificate"]["contract"] == (
        "procedure-output-cover-v7"
        if count_profile == "literal_source_count_v1"
        else "procedure-output-cover-v6"
    )
    assert len(assessed) == 2
    historical = await client.get(f"/api/queries/{value['id']}")
    assert historical.status_code == 200 and historical.json() == value
