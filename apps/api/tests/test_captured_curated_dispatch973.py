"""Recorded961 failure: new reader selected a legacy opponent-extent inspector."""

from types import SimpleNamespace

import pytest
from app.services import linguistic_conflicts, requirement_answers

from tests.test_captured_policy928 import configured


class SelectedReaderInspection(Exception):
    pass


async def test_source_bound_reader_uses_complete_source_scope_inspection(monkeypatch):
    async def selected(*args, **kwargs):
        raise SelectedReaderInspection

    monkeypatch.setattr(linguistic_conflicts, "inspect_group", selected)
    config = configured().model_copy(
        update={"SOURCE_GOVERNANCE_PROFILE": "requirement_bound_v1"}
    )
    with pytest.raises(SelectedReaderInspection):
        await requirement_answers._inspect_procedure_group(
            None,
            None,
            None,
            SimpleNamespace(id="route-control"),
            config,
            [],
            False,
            [],
            {},
            [],
        )


async def test_historical_profile9_keeps_recorded_inspection_contract(monkeypatch):
    async def selected(*args, **kwargs):
        raise SelectedReaderInspection

    monkeypatch.setattr(linguistic_conflicts, "inspect_group", selected)
    result = await requirement_answers._inspect_procedure_group(
        None,
        None,
        None,
        SimpleNamespace(id="route-control"),
        configured(),
        [],
        False,
        [],
        {},
        [],
    )
    assert result["inspection_method"] == "complete-immutable-procedure-v3"
