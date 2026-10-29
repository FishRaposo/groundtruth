"""Actual captured engineering syntax, never model or quality acceptance."""

import json
from pathlib import Path

from app.services.captured_plan_binding import prepare_structure


def captured(name):
    rows = json.loads((Path(__file__).parent / "data/questions929.json").read_text())
    return next(row for row in rows if row["id"] == name)


def test_actual_nominal_operator_derives_new_node_without_retagging():
    # Defect: historical generic node survives despite fully owned nominal frame.
    row = captured("labels")
    result = prepare_structure(
        row["text"], row["capture"], reading_profile="contextual_source_v4"
    )
    assert result["nodes"][0]["kind"] == "role_catalogue"
    assert result["unresolved"] == []
    assert result["historical_partial"]["nodes"][0]["kind"] == "generic"
    assert row["capture"]["annotation"]["tokens"][0]["pos"] == "NOUN"


def test_actual_dependent_capture_retains_set_reference_and_original_features():
    row = captured("actors-dependent")
    result = prepare_structure(
        row["text"], row["capture"], reading_profile="contextual_source_v4"
    )
    assert [n["kind"] for n in result["nodes"]] == ["role_catalogue", "availability"]
    assert result["unresolved"] == []
    assert result["edges"][0]["kind"] == "catalogue_member_value"
    assert result["edges"][0]["evidence"][0]["text"] == "their"
    assert result["original_capture"] == row["capture"]


def test_actual_two_sentence_composite_owns_each_production():
    row = captured("same-activity-full")
    result = prepare_structure(
        row["text"], row["capture"], reading_profile="contextual_source_v4"
    )
    assert [n["kind"] for n in result["nodes"]] == ["role_catalogue", "procedure"]
    assert result["unresolved"] == []
    assert len(result["production_resolutions"]) == 2


def test_actual_qualified_copy_and_legacy_defaults_remain_blocked():
    import pytest

    row = captured("unsupported")
    result = prepare_structure(
        row["text"], row["capture"], reading_profile="contextual_source_v4"
    )
    assert result["unresolved"][0]["owner_id"] == "p2"
    for profile in (None, "contextual_source_v3"):
        with pytest.raises(ValueError):
            prepare_structure(row["text"], row["capture"], reading_profile=profile)


def test_actual_complete_copy_facet_keeps_conditions_prohibitions_and_quantifiers():
    row = captured("required-copy")
    result = prepare_structure(
        row["text"], row["capture"], reading_profile="contextual_source_v4"
    )
    assert not result["unresolved"]
    assert result["nodes"][0]["kind"] == "procedure"
    features = json.loads(result["nodes"][0]["feature_json"])
    assert (
        features["governors"][0]["text"] == "including all conditions and prohibitions"
    )
    assert [r["text"] for r in features["quantifiers"]] == ["full", "all"]
    assert result["deferred"] == result["historical_partial"]["deferred"]
    assert (
        "".join(t["token"]["text"] + t["whitespace"] for t in result["consumption"])
        == row["text"]
    )


def test_existing_verb_operator_owned_relation_remains_available_in_new_profile():
    from tests.planning_library_unit830.fixtures_request import question

    text, observed = question()
    result = prepare_structure(text, observed, reading_profile="contextual_source_v4")
    assert result["nodes"][0]["kind"] == "role_catalogue"
    assert result["unresolved"] == []


def test_65_owned_nodes_are_refused_without_truncating_original_input():
    import pytest

    from tests.captured_productions_unit931.test_request import BASE
    from tests.staged_plan_unit837.fixtures_source import capture

    short = list(BASE)
    short[4] = ("H", "NOUN", "h", "compound", 5)
    short[5] = ("x", "NOUN", "x", "pobj", 3)
    question, observed = capture([list(short) for _ in range(65)])
    with pytest.raises(ValueError, match="limit exceeded; no truncation"):
        prepare_structure(question, observed, reading_profile="contextual_source_v4")
    assert len(observed["annotation"]["sentences"]) == 65
