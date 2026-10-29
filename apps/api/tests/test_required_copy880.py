"""Actual parser-bound complete required copies; UNITONLY NLI boundary."""

import copy
import json
from dataclasses import asdict, replace

import pytest
from app.services import contextual_source_proof as body_proof
from app.services import planning_declarations as d
from app.services import (
    required_copy_source,
    staged_plan_binding,
    staged_plan_replay,
    staged_source_proof,
)
from app.services.contextual_source_proof import SourceGuardRefusal
from app.services.staged_answer_planning import StagedAnswerContext

from tests.required_copy_fixtures880 import (
    arguments,
    context,
    envelope_args,
    extra_context,
)


def test_actual_unambiguous_reference_reaches_versioned_full_two_source_inventory():
    ctx = context()
    envelope = staged_source_proof.build_envelope(**envelope_args(ctx))
    required = envelope["required_copy"]
    assert required["contract"] == "parser-bound-required-copy-v1"
    assert required["ordered_document_ids"] == list(ctx.snapshots())
    assert [row["body"] for row in required["documents"]] == [
        row["body"] for row in ctx.snapshots().values()
    ]
    assert required["edges"][0]["target_literal"]["text"] == "Appendix Alpha"
    assert {row["name"].split(":")[0] for row in envelope["nli_obligations"]} >= {
        "namespace",
        "applicability",
        "incorporation",
    }
    assert all(
        row["verification_method"] == "exact_source_structure"
        for row in required["structural_obligations"]
    )
    assert all(
        row["verification_method"] == "exact_source_copy"
        for row in required["copy_obligations"]
    )
    assert not any(
        row["name"].startswith("target_declaration")
        for row in envelope["nli_obligations"]
    )


def test_original_wait_keeps_ordinary_envelope_and_ambiguous_a_remains_refused():
    ordinary = staged_source_proof.build_envelope(
        **envelope_args(context("control", None))
    )
    assert "required_copy" not in ordinary
    with pytest.raises(SourceGuardRefusal):
        staged_source_proof.build_envelope(
            **envelope_args(context("ambiguous_a", "ambiguous_target_a"))
        )


def test_missing_and_duplicate_declarations_never_bind_by_title_or_rank():
    with pytest.raises(SourceGuardRefusal, match="absent or ambiguous"):
        staged_source_proof.build_envelope(**envelope_args(context("root", None)))
    args, actual = arguments()
    original = args["snapshots"][1]
    identity = replace(
        original.identity,
        document_id="00000000-0000-0000-0000-000000000003",
        snapshot_id="00000000-0000-0000-0000-000000000103",
    )
    duplicate = replace(
        original,
        identity=identity,
        chunks=(
            replace(
                original.chunks[0], chunk_id="00000000-0000-0000-0000-000000000203"
            ),
        ),
    )
    args["snapshots"] += (duplicate,)
    args["source_captures"] += (replace(args["source_captures"][1], identity=identity),)
    args["manifest"] = replace(
        args["manifest"], publications=args["manifest"].publications + (identity,)
    )
    actual[identity.document_id] = {
        **copy.deepcopy(actual[original.identity.document_id]),
        **asdict(identity),
        "chunks": [
            {
                "id": duplicate.chunks[0].chunk_id,
                "index": 0,
                "content": duplicate.body,
                "metadata": {},
            }
        ],
    }
    ctx = StagedAnswerContext(
        staged_plan_binding.reconstruct_staged_plan(**args),
        d.canonical(staged_plan_replay.capture_inputs(**args)),
        d.canonical(actual),
    )
    with pytest.raises(SourceGuardRefusal, match="absent or ambiguous"):
        staged_source_proof.build_envelope(**envelope_args(ctx))


@pytest.mark.parametrize("mutation", ["body", "title", "metadata", "chunk", "capture"])
def test_presented_targets_cannot_replace_independent_snapshot(mutation):
    args = envelope_args(context())
    inputs = copy.deepcopy(args["planning_inputs"])
    if mutation == "capture":
        inputs["source_captures"][1]["windows"][0]["capture_json"] = "{}"
    elif mutation == "chunk":
        inputs["snapshots"][1]["chunks"][0]["literal"]["text"] += " extra"
    elif mutation == "metadata":
        inputs["snapshots"][1]["metadata_json"] = '{"authority":true}'
    else:
        inputs["snapshots"][1][mutation] += " extra"
    args["planning_inputs"] = inputs
    args["retained_inputs"] = json.loads(json.dumps(inputs))
    with pytest.raises(ValueError):
        staged_source_proof.build_envelope(**args)


@pytest.mark.parametrize("name", ["ambiguous_a", "ambiguous_target_a"])
def test_unknown_same_namespace_and_global_sources_remain_mandatory(name):
    ctx = extra_context(name)
    assert len(ctx.snapshots()) == len(ctx.inputs()["source_captures"]) == 3
    with pytest.raises(SourceGuardRefusal, match="mandatory"):
        staged_source_proof.build_envelope(**envelope_args(ctx))


def test_activity_entity_name_is_not_an_immutable_document_name_declaration():
    from tests.staged_plan_unit837.fixtures_source import NAME, capture

    raw, cap = capture([NAME])
    g = body_proof._Graph(raw, 0, cap["annotation"], 0, len(raw))
    with pytest.raises(SourceGuardRefusal, match="document"):
        required_copy_source._named(g, {"start": 0, "end": len(raw), "text": raw})


def test_generic_inspection_scope_is_not_a_proven_other_namespace(monkeypatch):
    from tests.required_copy_fixtures880 import CAPTURES
    from tests.staged_plan_unit837.fixtures_source import CAT, capture

    generic = [
        (word, pos, lemma, dep, head - 1 if head > 2 else head)
        for index, (word, pos, lemma, dep, head) in enumerate(CAT)
        if index != 2
    ]
    _, captured = capture([generic])
    monkeypatch.setitem(CAPTURES, "UNITONLY_generic_scope", captured)
    ctx = extra_context("UNITONLY_generic_scope")
    with pytest.raises(SourceGuardRefusal, match="mandatory"):
        staged_source_proof.build_envelope(**envelope_args(ctx))


def test_same_namespace_closed_catalogue_defers_copy_only(monkeypatch):
    from tests.required_copy_fixtures880 import CAPTURES
    from tests.staged_plan_unit837.fixtures_source import CAT, capture

    rows = [
        ("Moss", pos, "Moss", dep, head)
        if word == "Cedar"
        else (word, pos, lemma, dep, head)
        for word, pos, lemma, dep, head in CAT
    ]
    _, captured = capture([rows])
    monkeypatch.setitem(CAPTURES, "UNITONLY_same_scope_catalogue", captured)
    ctx = extra_context("UNITONLY_same_scope_catalogue")
    envelope = staged_source_proof.build_envelope(**envelope_args(ctx))
    assert (
        len(ctx.snapshots())
        == len(envelope["required_copy"]["structural_closure"]["source_inventory"])
        == 3
    )
    assert len(envelope["required_copy"]["documents"]) == 2
    assert ctx.record()["answer_fact_nli"] == "NOT_ASSESSED"
    assert envelope["required_copy"]["permissions_currentness"] == "REQUIRED_SEPARATELY"
    curated = extra_context(
        "UNITONLY_same_scope_catalogue",
        {"conflict_group": "UNITONLY-curated-opposition"},
    )
    with pytest.raises(SourceGuardRefusal, match="mandatory"):
        staged_source_proof.build_envelope(**envelope_args(curated))
