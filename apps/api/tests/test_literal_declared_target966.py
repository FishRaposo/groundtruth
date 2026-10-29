"""Actual header graphs; optional literal interval is never NI acceptance."""

import json
from copy import deepcopy

import pytest
from app.services import contextual_source_proof as proof
from app.services.contextual_procedures import (
    _envelope_declaration,
    _envelope_named_subject,
)

from tests.test_captured_copy_ownership966 import selected


def header(logical_id):
    snapshot, captures, _units = selected(logical_id)
    declaration = _envelope_declaration(snapshot.body)
    first, last = _envelope_named_subject(declaration["subject"])
    windows = [
        {"start": w.start, "end": w.end, "capture": json.loads(w.capture_json)}
        for w in captures.windows
    ]
    return (
        snapshot.body,
        declaration,
        windows,
        declaration["subject"][first:last],
        {"relation": "routine"},
    )


@pytest.mark.parametrize(
    "logical_id",
    [
        "d526-13-routine",
        "d526-14-routine",
        "d526-10-routine",
        "d526-03-routine",
        "d526-07-routine",
        "d526-04-routine",
    ],
)
def test_actual_statistical_header_variation_keeps_exact_selected_literal_target(
    logical_id,
):
    # Existing default rejects these actual graphs; selected COPY must retain
    # its declared target without pretending to repair the statistical parse.
    args = header(logical_id)
    with pytest.raises(proof.SourceGuardRefusal):
        proof._declared_relation(*args)
    before = deepcopy(args[2])
    result = proof._declared_relation(*args, literal_declared_target=True)
    body, declaration, _windows, _subject, _requirement = args
    assert result["target"] == proof._literal(
        body, declaration.start("subject"), declaration.end("subject")
    )
    assert result["proposition"] == proof._literal(body, *declaration.span())
    assert result["statistical_target_attachment"] == "NOT_ASSERTED"
    assert result["captured_tokens"]
    assert args[2] == before
    assert "supported" not in result


@pytest.mark.parametrize("change", ["scope", "method", "nonbool"])
def test_optional_target_does_not_waive_requested_scope_method_or_mode_type(change):
    args = list(header("d526-13-routine"))
    mode = True
    if change == "scope":
        args[3] += " different variant"
    elif change == "method":
        args[4] = {"relation": "unrecognized-method"}
    else:
        mode = "true"
    with pytest.raises(proof.SourceGuardError):
        proof._declared_relation(*args, literal_declared_target=mode)


def test_selected_mode_keeps_strict_existing_legacy_declaration_format():
    from dataclasses import asdict

    from tests.test_contextual_source_proof import fixture

    raw, _identity, windows, plan, _snapshot = fixture()
    requirement = next(r for r in plan.requirements if r.kind == "procedure")
    args = (
        raw,
        _envelope_declaration(raw),
        windows,
        requirement.topic,
        asdict(requirement),
    )
    expected = proof._declared_relation(*args)
    assert proof._declared_relation(*args, literal_declared_target=True) == expected
