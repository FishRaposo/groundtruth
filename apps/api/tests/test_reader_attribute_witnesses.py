"""Prefer an explicitly requested activity without turning overlap into truth."""

import pytest
from app.config import Settings
from app.services.answer_reader import LocalReader, ReaderSelection, passage_span
from app.services.reader_attributes import attribute_features
from app.services.reader_witnesses import select_witness_cover


def predictions(monkeypatch, question, sources, raw, margins, *, accepted=(True, True)):
    local = LocalReader()

    def selected(part, context, config):
        index = sources.index(context)
        start = context.index(raw[index])
        end = start + len(raw[index])
        return ReaderSelection(
            passage_span(context, start, end) if accepted[index] else None,
            {
                "decision": "answer",
                "null_margin": margins[index],
                "raw_span": {"start": start, "end": end},
            },
        )

    monkeypatch.setattr(local, "_context", selected)
    return local._parts(question, sources, Settings())


@pytest.mark.parametrize(
    ("question", "sources", "raw"),
    [
        (
            "For Aurora, What is the responsible review role?",
            [
                "The Aurora review is owned by the seal reviewer.",
                "The reservations scheduler accepts reservations for Aurora.",
            ],
            ["seal reviewer", "reservations scheduler"],
        ),
        (
            "For Aurora, give the explicit access restriction.",
            [
                "The Aurora access rule requires a badge.",
                "The Aurora folding rule forbids folding the coat.",
            ],
            ["a badge", "folding the coat"],
        ),
        (
            "What is the normal inspection workload for Aurora?",
            [
                "The Aurora inspection covers four seals.",
                "The Aurora reservation deadline is four days before the appointment.",
            ],
            ["four seals", "four days"],
        ),
        (
            "For Aurora, give the explicit access restriction.",
            [
                "The Aurora access rule requires a badge.",
                "The Aurora access office opens at 10:00. "
                "Its folding rule forbids folding the coat.",
            ],
            ["a badge", "folding the coat"],
        ),
    ],
)
def test_explicit_requested_attribute_ranks_accepted_selected_clause(
    monkeypatch, question, sources, raw
):
    selections = predictions(monkeypatch, question, sources, raw, [-7, -10])
    assert all(selection.span is not None for selection in selections)
    assert select_witness_cover(selections).indices == (0,)


def test_paraphrase_without_literal_activity_keeps_accepted_margin_fallback(
    monkeypatch,
):
    selections = predictions(
        monkeypatch,
        "For Aurora, What is the responsible inspection role?",
        [
            "The Aurora check is owned by the seal reviewer.",
            "The reservations scheduler accepts bookings for Aurora.",
        ],
        ["seal reviewer", "reservations scheduler"],
        [-10, -5],
    )
    assert all(selection.span is not None for selection in selections)
    assert select_witness_cover(selections).indices == (0,)


def test_matching_attribute_never_promotes_a_null_model_prediction(monkeypatch):
    selections = predictions(
        monkeypatch,
        "For Aurora, What is the responsible review role?",
        [
            "The Aurora review is owned by the seal reviewer.",
            "The reservations scheduler accepts reservations for Aurora.",
        ],
        ["seal reviewer", "reservations scheduler"],
        [5, -10],
        accepted=(False, True),
    )
    assert selections[0].span is None
    assert select_witness_cover(selections).indices == (1,)


def test_genitive_role_owner_is_not_interpreted_as_an_activity_object():
    source = "The Aurora review is owned by the seal reviewer."
    raw = "seal reviewer"
    start = source.index(raw)
    feature = attribute_features(
        "What is the responsible review role OF the Aurora coordinator?",
        source,
        {"start": start, "end": start + len(raw)},
    )
    assert not feature["requested"]


@pytest.mark.parametrize("raw", [{"start": True, "end": 8}, {"start": 10, "end": 11}])
def test_invalid_or_punctuation_offsets_cannot_borrow_a_whole_chunk(raw):
    source = "Aurora note. The review is owned by the reviewer."
    if raw["start"] == 10:
        raw = {"start": source.index("."), "end": source.index(".") + 1}
    assert not attribute_features(
        "What is the responsible review role for Aurora?", source, raw
    )["selected_clause_matches"]


@pytest.mark.parametrize("contract", [None, "custom-future"])
def test_mixed_or_unknown_attribute_diagnostics_keep_legacy_margin_fallback(contract):
    source = "The Aurora review is owned by the reviewer."
    start = source.index("reviewer")
    known = attribute_features(
        "What is the responsible review role for Aurora?",
        source,
        {"start": start, "end": start + 8},
    )
    candidates = []
    for index, margin in enumerate([-4, -10]):
        part = {"index": 0, "null_margin": margin}
        if index == 0 or contract is not None:
            part["attribute_evidence"] = {
                **known,
                "selected_clause_matches": index == 0,
                **({"contract": contract} if contract is not None else {}),
            }
        candidates.append(
            ReaderSelection(
                passage_span(source, start, start + 8),
                {"part_count": 1, "covered_parts": [0], "parts": [part]},
            )
        )
    assert select_witness_cover(candidates).indices == (1,)


def test_attribute_words_do_not_leak_across_explicit_coordinated_clauses(monkeypatch):
    selections = predictions(
        monkeypatch,
        "For Aurora, What is the responsible review role?",
        [
            "The Aurora inspection is owned by the seal reviewer.",
            "The Aurora review covers four seals, "
            "but the reservations are handled by the scheduler.",
        ],
        ["seal reviewer", "scheduler"],
        [-10, -4],
    )
    assert all(selection.span is not None for selection in selections)
    assert select_witness_cover(selections).indices == (0,)


def test_joined_people_in_one_predicate_retain_their_selected_clause():
    source = "The Aurora review is owned by the seal reviewer and the scheduler."
    start = source.index("scheduler")
    assert attribute_features(
        "What is the responsible review role for Aurora?",
        source,
        {"start": start, "end": start + 9},
    )["selected_clause_matches"]
