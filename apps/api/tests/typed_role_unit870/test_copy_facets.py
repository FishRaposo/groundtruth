"""Generic UNITONLY captured copy selectors; source/fact authority unassessed."""

import json
from copy import deepcopy
from dataclasses import asdict

import pytest
from app.services import staged_plan_binding as binding
from app.services.staged_copy_facets import reconstruct_copy_facets
from app.services.staged_plan_replay import capture_inputs
from app.services.staged_source_proof import build_envelope

from tests.dependent_plan_unit842.test_dependent import fresh_receipts, onyx_inputs
from tests.staged_plan_unit837.fixtures_source import capture
from tests.test_contextual_source_proof import unit_capture

FACETS = [
    ("Give", "VERB", "give", "ROOT", 0),
    ("the", "DET", "the", "det", 5),
    ("entire", "ADJ", "entire", "amod", 5),
    ("Onyx", "PROPN", "Onyx", "compound", 4),
    ("calibration", "NOUN", "calibration", "compound", 5),
    ("routine", "NOUN", "routine", "dobj", 0),
    (",", "PUNCT", ",", "punct", 0),
    ("including", "VERB", "include", "prep", 0),
    ("its", "PRON", "its", "poss", 10),
    ("entry", "NOUN", "entry", "compound", 10),
    ("condition", "NOUN", "condition", "pobj", 7),
    (",", "PUNCT", ",", "punct", 10),
    ("prohibition", "NOUN", "prohibition", "conj", 10),
    ("and", "CCONJ", "and", "cc", 12),
    ("overlapping", "ADJ", "overlapping", "amod", 16),
    ("-", "PUNCT", "-", "punct", 16),
    ("fragment", "NOUN", "fragment", "compound", 17),
    ("contingency", "NOUN", "contingency", "conj", 12),
    (".", "PUNCT", ".", "punct", 0),
]


def inputs(rows=FACETS):
    actual = onyx_inputs()
    question, observed = capture([rows])
    question = question.replace("overlapping - fragment", "overlapping-fragment")
    observed = unit_capture(
        question,
        [(word, pos, dep, head, lemma) for word, pos, lemma, dep, head in rows],
    )
    actual.update(question=question, capture=observed)
    return fresh_receipts(actual)


def test_modified_literal_content_selectors_and_local_reference_keep_source_gate():
    actual = inputs()
    plan = binding.reconstruct_staged_plan(**actual)
    assert plan.resolved_request
    requirement, use = plan.requirements[0], plan.uses[0]
    assert use.governors and [ref.text for ref in use.references] == ["its"]
    snapshot = actual["snapshots"][0]
    authority = {
        snapshot.identity.document_id: {
            **asdict(snapshot.identity),
            "title": snapshot.title,
            "body": snapshot.body,
            "metadata": json.loads(snapshot.metadata_json),
            "chunks": [
                {
                    "id": chunk.chunk_id,
                    "index": chunk.ordinal,
                    "content": chunk.literal.text,
                    "metadata": json.loads(chunk.metadata_json),
                }
                for chunk in snapshot.chunks
            ],
        }
    }
    windows = [
        {
            "start": window.start,
            "end": window.end,
            "capture": json.loads(window.capture_json),
        }
        for window in actual["source_captures"][0].windows
    ]
    recorded = capture_inputs(**actual)
    envelope = build_envelope(
        snapshot.body,
        asdict(snapshot.identity),
        requirement.topic,
        windows,
        question=actual["question"],
        requirement_id=requirement.id,
        planning_inputs=recorded,
        retained_inputs=deepcopy(recorded),
        authoritative_snapshots=authority,
        require_runtime=False,
    )
    rows = envelope["request_obligation_inventory"]
    assert [row["request_range"] for row in rows] == [
        asdict(span) for span in use.governors
    ]
    assert all(
        row["source_range"] == {"start": 0, "end": len(snapshot.body)} for row in rows
    )
    assert rows[0]["copy_facet_ownership"]["facet_existence"] == "NOT_ASSERTED"
    assert rows[0]["copy_facet_ownership"]["reference_bindings"]
    assert envelope["nli_obligations"]


@pytest.mark.parametrize(
    "replacement",
    ["their", "availability"],
    ids=["unknown_antecedent", "factual_facet"],
)
def test_unbound_antecedent_and_factual_facet_remain_unresolved(replacement):
    rows = list(FACETS)
    if replacement == "their":
        word, pos, _, dep, head = rows[8]
        rows[8] = (replacement, pos, replacement, dep, head)
    else:
        word, pos, _, dep, head = rows[17]
        rows[17] = (replacement, pos, replacement, dep, head)
    actual = inputs(rows)
    plan = binding.reconstruct_staged_plan(**actual)
    assert not plan.resolved_request
    assert plan.unresolved


def test_cleared_reference_record_cannot_replace_actual_captured_binding():
    actual = inputs()
    plan = binding.reconstruct_staged_plan(**actual)
    use = asdict(plan.uses[0])
    use["references"] = []
    with pytest.raises(ValueError):
        reconstruct_copy_facets(plan.record(), asdict(plan.requirements[0]), use, None)
