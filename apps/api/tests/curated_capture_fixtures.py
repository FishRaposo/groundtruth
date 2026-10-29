"""Explicit offline parser boundary: replay retained actual V695 source syntax."""

import json
from copy import deepcopy
from pathlib import Path

import pytest


def actual_source_windows(body):
    data = json.loads(
        (
            Path(__file__).parent / "fixtures/curated_source_captures_v695.json"
        ).read_text()
    )
    matches = [row for row in data["captures"] if row["body"] == body]
    if len(matches) != 1:
        raise ValueError("No retained actual parser source capture for test body")
    return deepcopy(matches[0]["source_windows"])


@pytest.fixture(autouse=True)
def curated_capture_runtime(monkeypatch):
    """No model runs during protocol tests, including old copied review tests."""
    from app.services import linguistic_conflicts

    async def captured(body, config, cache):
        return actual_source_windows(body)

    monkeypatch.setattr(linguistic_conflicts, "capture_fact_source_windows", captured)
