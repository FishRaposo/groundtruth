"""Strict support can inspect bounded non-null alternatives, never question tokens."""

import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from app.config import Settings
from app.services.answer_reader import LocalReader

from tests.test_answer_reader import _Encoding, _Tensor


@pytest.mark.parametrize("null_logit", [2.0, 20.0])
def test_only_threshold_accepted_source_spans_are_available(monkeypatch, null_logit):
    context = "Iris Rowan"

    class Tokenizer:
        cls_token_id = 101

        def __call__(self, question, text, **options):
            return _Encoding(
                input_ids=_Tensor([[101, 9, 102, 1, 2, 3, 102]]),
                offset_mapping=_Tensor(
                    [[(0, 0), (0, 4), (0, 0), (0, 4), (5, 10), (0, 0), (0, 0)]]
                ),
                overflow_to_sample_mapping=_Tensor([0]),
            )

    def model(**options):
        logits = _Tensor([[null_logit, 100.0, 0.0, 5.0, 4.0, -10.0, 0.0]])
        return SimpleNamespace(start_logits=logits, end_logits=logits)

    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(inference_mode=nullcontext)
    )
    reader = LocalReader()
    reader._tokenizer, reader._model = Tokenizer(), model
    result = reader._context("Which role?", context, Settings(READER_NULL_THRESHOLD=0))
    choices = result.diagnostics.get("raw_candidates", [])
    if null_logit == 20:
        assert result.span is None and choices == []
    else:
        assert {"Iris", "Rowan"}.issubset({choice["text"] for choice in choices})
        assert 1 <= len(choices) <= 3
        assert all(choice["null_margin"] <= 0 for choice in choices)
        assert all(
            context[choice["start"] : choice["end"]] == choice["text"]
            for choice in choices
        )
        assert all(choice["score"] <= 10 for choice in choices)
