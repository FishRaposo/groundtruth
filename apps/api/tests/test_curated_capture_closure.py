"""Actual cached syntax + UNITONLY NLI protocol; never model-quality evidence."""

from copy import deepcopy
from dataclasses import replace

import pytest

from tests.curated_capture_fixtures import actual_source_windows
from tests.test_contextual_mixed_output import mirror, output, produce
from tests.test_curated_consumer_proof import factual_group_fixture


def test_newline_contrast_reaches_consumer_with_actual_capture():
    body = "The inspection starts at 09:00\nAssign the caretaker to lead Alder review."
    data = factual_group_fixture(foreign_body=body)
    record = data["selection"]["conflicts"][0]
    assert record["source_scope_decisions"][1]["included"] is True
    assert any(row["premise"] == body for row in record["comparisons"])
    with pytest.raises(ValueError):
        produce(data)


@pytest.mark.parametrize(("workspace", "included"), [(None, True), ("other", False)])
def test_unknown_workspace_does_not_prove_a_foreign_source(workspace, included):
    from app.services.curated_conflict_proof import fact_scope

    data = factual_group_fixture(
        foreign_body="Assign the caretaker to lead Alder review."
    )
    req = data["request_reconstructor"](data["question"], {}).requirements[0]
    req = replace(req, source_workspace="requested")
    snapshot = data["source_snapshots"]["00000000-0000-0000-0000-000000000099"]
    snapshot["workspace_id"] = workspace
    assert fact_scope(req, snapshot)["included"] is included


@pytest.mark.parametrize(
    ("body", "included"),
    [
        ("The caretaker supervising Alder review starts at 09:00.", True),
        ("The ordinary Alder review starts at 09:00.", False),
        (
            "The caretaker leads Birch review, then nominate a replacement "
            "for Alder review.",
            True,
        ),
        (
            "Retest: use the temporary sheet, for ordinary Alder review "
            "consult the register.",
            True,
        ),
        ("The inspection starts at 09:00 and lasts 8 minutes.", True),
        ("The inspection with the caretaker starts at 09:00.", True),
    ],
)
def test_fresh_captured_nominal_and_scope_contrasts(body, included):
    data = factual_group_fixture(foreign_body=body)
    record = data["selection"]["conflicts"][0]
    assert record["source_scope_decisions"][1]["included"] is included
    if included:
        assert any(row["premise"] == body for row in record["comparisons"])
        with pytest.raises(ValueError):
            produce(data)
    else:
        assert "archivist" in produce(data)["answer"]


def test_actual_verbal_amod_cannot_be_consumed_as_an_adjectival_nominal():
    body = "The caretaker leading Alder review starts at 09:00."
    windows = actual_source_windows(body)
    token = next(
        t
        for t in windows[0]["capture"]["annotation"]["tokens"]
        if t["text"] == "leading"
    )
    assert (token["pos"], token["dep"]) == ("VERB", "amod")
    data = factual_group_fixture(foreign_body=body)
    scope = data["selection"]["conflicts"][0]["source_scope_decisions"][1]
    assert scope["scope_cover"][0]["other_relation_proof"] is None
    assert scope["included"] is True


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "source_identity",
        "foreign_graph",
        "missing_tail",
        "hash_only",
        "duplicate",
        "extra",
        "false_closed",
        "drop_source_unit",
        "old_v2",
    ],
)
def test_captured_source_inventory_and_derived_closure_cannot_be_forged(change):  # noqa: C901 - explicit protocol mutations
    data = factual_group_fixture()
    record = data["selection"]["conflicts"][0]
    scopes = record["source_scope_decisions"]
    source = scopes[1]["source_capture"]
    if change == "missing":
        scopes[1].pop("source_capture")
    elif change == "source_identity":
        source["source_identity"]["document_version"] += 1
    elif change == "foreign_graph":
        source["source_windows"] = actual_source_windows(
            "The archivist leads Alder review."
        )
    elif change == "missing_tail":
        source["source_windows"][0]["end"] -= 1
    elif change == "hash_only":
        source["source_windows"][0]["capture"].pop("annotation")
    elif change == "duplicate":
        scopes.append(deepcopy(scopes[1]))
    elif change == "extra":
        scopes.append(deepcopy(scopes[1]))
        scopes[-1]["source_capture"]["source_identity"]["document_id"] = "unbound"
    elif change == "false_closed":
        scopes[0]["scope_cover"][0]["dependency_closure"]["complete"] = True
        scopes[0]["included"] = False
    elif change == "drop_source_unit":
        scopes[1]["scope_cover"] = []
    else:
        record["inspection_method"] = "curated-full-source-fact-comparison-v2"
        for row in scopes:
            row.pop("source_capture")
    mirror(data)
    with pytest.raises(ValueError):
        produce(data)


def test_old_uncaptured_v2_is_retained_as_history_but_not_retrocertified():
    data = factual_group_fixture()
    actual = produce(data)
    data["selection"][output.CERTIFICATE_FIELD] = deepcopy(actual["certificate"])
    record = data["selection"]["conflicts"][0]
    record["inspection_method"] = "curated-full-source-fact-comparison-v2"
    for row in record["source_scope_decisions"]:
        row.pop("source_capture")
    mirror(data)
    context = {k: v for k, v in data.items() if k != "selection"}
    context.update(answer=actual["answer"], citations=actual["citations"])
    assert not output.verify_output(data["selection"], **context)
