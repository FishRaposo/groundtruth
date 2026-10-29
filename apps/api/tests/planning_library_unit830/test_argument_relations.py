"""UNITONLY owned-argument contrasts; no model inference or lexical blacklist."""

import ctypes
import socket
import subprocess
import unittest
from unittest.mock import patch

from .test_support import (
    ACTORS,
    ASSIGN,
    CAT,
    LABELS,
    NAME,
    case,
    deny,
    parser,
    run_case,
)


def insert(rows, at, text, pos, lemma, dep, head):
    shifted = [
        (word, part, base, edge, parent + 1 if parent >= at else parent)
        for word, part, base, edge, parent in rows
    ]
    shifted.insert(at, (text, pos, lemma, dep, head + 1 if head >= at else head))
    return shifted


def scoped_case(prefix):
    return case(
        insert(LABELS, 4, prefix, "PROPN", prefix, "compound", 5),
        (
            insert(NAME, 4, prefix, "PROPN", prefix, "compound", 5),
            insert(CAT, 2, prefix, "PROPN", prefix, "compound", 3),
        ),
    )


class ArgumentRelations(unittest.TestCase):
    def test_nonlexical_catalogue_adjective_requires_relation_support(self):
        result, prepared, _, _ = run_case(
            case(insert(LABELS, 1, "temporary", "ADJ", "temporary", "amod", 2))
        )
        self.assertFalse(result.accepted)
        self.assertTrue(
            any(
                item.reason == "unsupported_owned_request_argument"
                for item in prepared.pending
            )
        )
        self.assertTrue(getattr(prepared, "argument_closures", ()))

    def test_extra_nominal_compound_on_requested_set_is_not_silently_dropped(self):
        result, prepared, _, _ = run_case(
            case(insert(LABELS, 1, "audit", "NOUN", "audit", "compound", 2))
        )
        self.assertFalse(result.accepted)
        self.assertTrue(
            any(
                item.reason == "unsupported_owned_request_argument"
                for item in prepared.pending
            )
        )

    def test_material_quantity_and_determiner_are_explicit_unresolved(self):
        for word, pos, dep in [("Some", "DET", "det"), ("Two", "NUM", "nummod")]:
            with self.subTest(word=word):
                result, prepared, _, _ = run_case(
                    case(insert(LABELS, 1, word, pos, word.casefold(), dep, 2))
                )
                self.assertFalse(result.accepted)
                self.assertTrue(
                    any(
                        item.reason == "unsupported_owned_request_argument"
                        for item in prepared.pending
                    )
                )

    def test_full_compound_activity_name_is_preserved_and_supported(self):
        result, prepared, _, _ = run_case(scoped_case("Archive"))
        self.assertTrue(result.accepted)
        self.assertEqual(len(prepared.assertions), 6)
        self.assertTrue(
            all(
                "Archive Cedar inspection" in a.pair.hypothesis
                for a in prepared.assertions
            )
        )
        self.assertTrue(getattr(prepared, "argument_closures", ()))
        self.assertTrue(
            all(
                row.status == "EXACT_INITIAL_RELATION"
                for row in prepared.argument_closures
            )
        )

    def test_same_surface_word_inside_literal_activity_name_is_not_blacklisted(self):
        result, prepared, _, _ = run_case(scoped_case("former"))
        self.assertTrue(result.accepted)
        self.assertTrue(
            all(
                "former Cedar inspection" in a.pair.hypothesis
                for a in prepared.assertions
            )
        )

    def test_scope_subtree_cannot_be_replaced_by_a_shorter_nominal_projection(self):
        rows = LABELS[:-1] + [
            ("near", "ADP", "near", "prep", 5),
            ("Dock", "PROPN", "Dock", "pobj", 6),
            (".", "PUNCT", ".", "punct", 0),
        ]
        result, prepared, _, _ = run_case(case(rows))
        self.assertFalse(result.accepted)
        self.assertTrue(
            any(
                item.reason == "unsupported_owned_request_argument"
                for item in prepared.pending
            )
        )

    def test_qualified_actor_request_cannot_use_unqualified_actor_relation(self):
        groups = [NAME, CAT]
        for role, actor in [
            ("coordinator", "Rowan"),
            ("observer", "Nova"),
            ("recorder", "Ash"),
        ]:
            groups.append(
                [
                    (role, pos, role, dep, head)
                    if text == "coordinator"
                    else (actor, pos, actor, dep, head)
                    if text == "Rowan"
                    else (text, pos, lemma, dep, head)
                    for text, pos, lemma, dep, head in ASSIGN
                ]
            )
        result, prepared, _, _ = run_case(
            case(
                insert(ACTORS, 1, "interim", "ADJ", "interim", "amod", 2), tuple(groups)
            )
        )
        self.assertFalse(result.accepted)
        self.assertFalse(
            any(a.kind == "actor_role_relation" for a in prepared.assertions)
        )

    def test_request_operator_modifier_stays_owned_and_unresolved(self):
        result, prepared, _, _ = run_case(
            case(insert(LABELS, 1, "only", "ADV", "only", "advmod", 0))
        )
        self.assertFalse(result.accepted)
        self.assertTrue(
            any(
                item.reason == "unsupported_owned_request_argument"
                for item in prepared.pending
            )
        )

    def test_syntax_carrier_cannot_consume_a_material_attached_subtree(self):
        rows = insert(LABELS, 0, "Do", "AUX", "do", "aux", 0)
        rows = insert(rows, 1, "only", "ADV", "only", "advmod", 0)
        result, prepared, _, _ = run_case(case(rows))
        self.assertFalse(result.accepted)
        self.assertTrue(
            any(
                item.reason == "unsupported_owned_request_argument"
                for item in prepared.pending
            )
        )


if __name__ == "__main__":
    with (
        patch.object(subprocess, "Popen", deny),
        patch.object(subprocess, "run", deny),
        patch.object(socket, "socket", deny),
        patch.object(socket, "create_connection", deny),
        patch.object(ctypes, "WinDLL", deny),
        patch.object(parser, "capture", deny),
        patch.object(parser, "_load_pipeline", deny),
    ):
        unittest.main(verbosity=2)
