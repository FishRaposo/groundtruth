"""Derived pure replay of failed real-model852 evidence, not completed API proof."""

import json
from pathlib import Path

from app.services import staged_output


def test_staged_wrapper_keeps_selected_profile_for_actual_factual_guard():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/staged-factual-failure-v852.json").read_text(
            encoding="utf-8"
        )
    )
    assert "NOT observed completed API" in fixture["origin"]
    actual = staged_output.build_output(fixture["selection"], **fixture["context"])
    assert "7 minutes" in actual["answer"]
    assert actual["certificate"]["contract"] == "procedure-output-cover-v8"
    assert actual["certificate"]["reading_profile"] == "contextual_source_v3"
    selection = fixture["selection"]
    selection[staged_output.CERTIFICATE_FIELD] = actual["certificate"]
    assert staged_output.verify_output(
        selection,
        answer=actual["answer"],
        citations=actual["citations"],
        **fixture["context"],
    )
