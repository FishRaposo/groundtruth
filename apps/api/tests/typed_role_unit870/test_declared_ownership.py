"""COPY-domain ownership only; complete factual/alias/NLI gates remain."""

from dataclasses import replace

import pytest
from app.services import planning_declarations as source
from app.services.staged_production_obligations import declared_copy_ownership
from app.services.staged_request import compile_request

from tests.required_copy_fixtures880 import CAPTURES
from tests.staged_plan_unit837.fixtures_source import (
    ASSIGN,
    CAT,
    COND,
    EXTERNAL,
    FIELD,
    NAME,
    UNKNOWN,
)
from tests.staged_plan_unit837.fixtures_source import (
    source as make_source,
)
from tests.staged_plan_unit837.test_binding import args


def moss(rows, *, generic=False):
    return [
        (
            "inspection" if generic else "Moss",
            "NOUN" if generic else pos,
            "inspection" if generic else "Moss",
            dep,
            head,
        )
        if word == "Cedar"
        else (word, pos, lemma, dep, head)
        for word, pos, lemma, dep, head in rows
    ]


def inspect(groups, *, extra=(), curated=False):
    actual = args(groups=groups, extra=extra)
    snapshots = actual["snapshots"]
    if curated:
        snapshots = (
            replace(
                snapshots[0], metadata_json='{"conflict_group":"UNITONLY870-group"}'
            ),
            *snapshots[1:],
        )
    observed = CAPTURES["question"]
    partial = compile_request(observed["annotation"]["raw_text"], observed)
    record = declared_copy_ownership(
        partial, actual["manifest"], snapshots, actual["source_captures"]
    )
    return record, actual, partial


def test_same_namespace_closed_facts_catalogue_and_names_own_copy_only():
    record, actual, _ = inspect(
        tuple(moss(rows) for rows in (NAME, CAT, ASSIGN, FIELD))
    )
    assert record["sources"][0]["copy_ownership_complete"]
    assert (
        record["read_set"]
        == source.declaration_inventory(
            actual["manifest"], actual["snapshots"], actual["source_captures"]
        ).read_set.record()
    )
    assert record["full_world_procedure_completeness"] == "NOT_ASSERTED"
    assert record["target_alias_inspection"] == "REQUIRED_SEPARATELY"
    assert all(
        unit["factual_authority"] == "NOT_ASSESSED"
        for unit in record["sources"][0]["units"]
    )


@pytest.mark.parametrize(
    "kind", ["generic", "conditional", "reference", "unknown", "curated", "opposing"]
)
def test_unclosed_or_opposing_source_keeps_copy_obligations_mandatory(kind):
    groups = tuple(
        moss(rows, generic=kind == "generic") for rows in (NAME, CAT, ASSIGN)
    )
    extra = ()
    if kind in {"conditional", "reference", "unknown"}:
        groups += (
            moss(
                {"conditional": COND, "reference": EXTERNAL, "unknown": UNKNOWN}[kind]
            ),
        )
    if kind == "opposing":
        opposite = [
            ("Birch", pos, "Birch", dep, head)
            if word == "Rowan"
            else (word, pos, lemma, dep, head)
            for word, pos, lemma, dep, head in moss(ASSIGN)
        ]
        extra = (make_source([opposite], doc="UNITONLY870-opponent"),)
    record, _, _ = inspect(groups, extra=extra, curated=kind == "curated")
    assert not record["sources"][0]["copy_ownership_complete"]
    assert any(
        unit["disposition"] == "mandatory" for unit in record["sources"][0]["units"]
    )
