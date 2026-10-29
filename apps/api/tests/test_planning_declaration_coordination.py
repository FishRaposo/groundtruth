"""UNITONLY syntax closure controls; no source truth or parser incidence."""

import ctypes
import json
import socket
import subprocess
import unittest
from unittest.mock import patch

from tests.test_planning_declarations import (
    ASSIGN,
    CAT,
    FIELD,
    deny,
    inventory,
    of_kind,
    parser,
)


def actor(extra):
    return ASSIGN[:-1] + extra + [(".", "PUNCT", ".", "punct", 6)]


def has_unknown(inv):
    return "unclosed_source_coordination" in inv.blockers


class Coordination(unittest.TestCase):
    def test_complete_two_actor_arguments_keep_both_without_closure_error(self):
        x = inventory(
            [
                actor(
                    [
                        ("and", "CCONJ", "and", "cc", 7),
                        ("Nova", "PROPN", "Nova", "conj", 7),
                    ]
                )
            ]
        )
        self.assertFalse(has_unknown(x))
        self.assertEqual(
            [
                v["text"]
                for v in json.loads(of_kind(x, "role_assignment")[0].payload_json)[
                    "values"
                ]
            ],
            ["Rowan", "Nova"],
        )

    def test_dangling_actor_keeps_explicit_source_and_argument_obligation(self):
        x = inventory([actor([("and", "CCONJ", "and", "cc", 7)])])
        self.assertTrue(has_unknown(x))
        row = of_kind(x, "role_assignment")[0]
        self.assertTrue(
            any(
                "unclosed_source_coordination" in a.unknowns
                for a in row.arguments
                if a.kind == "actor_value"
            )
        )

    def test_nested_complete_coordination_is_not_rejected_as_dangling(self):
        x = inventory(
            [
                actor(
                    [
                        ("and", "CCONJ", "and", "cc", 7),
                        ("Nova", "PROPN", "Nova", "conj", 7),
                        ("and", "CCONJ", "and", "cc", 9),
                        ("Cedar", "PROPN", "Cedar", "conj", 9),
                    ]
                )
            ]
        )
        self.assertFalse(has_unknown(x))
        self.assertEqual(
            [
                v["text"]
                for v in json.loads(of_kind(x, "role_assignment")[0].payload_json)[
                    "values"
                ]
            ],
            ["Rowan", "Nova", "Cedar"],
        )

    def test_nested_dangling_operator_does_not_borrow_an_earlier_conjunct(self):
        x = inventory(
            [
                actor(
                    [
                        ("and", "CCONJ", "and", "cc", 7),
                        ("Nova", "PROPN", "Nova", "conj", 7),
                        ("and", "CCONJ", "and", "cc", 9),
                    ]
                )
            ]
        )
        self.assertTrue(has_unknown(x))

    def test_repeated_operators_cannot_share_one_actual_conjunct(self):
        x = inventory(
            [
                actor(
                    [
                        ("and", "CCONJ", "and", "cc", 7),
                        ("and", "CCONJ", "and", "cc", 7),
                        ("Nova", "PROPN", "Nova", "conj", 7),
                    ]
                )
            ]
        )
        self.assertTrue(has_unknown(x))

    def test_leading_operator_has_no_previous_actual_argument(self):
        rows = ASSIGN[:7] + [
            ("and", "CCONJ", "and", "cc", 8),
            ("Rowan", "PROPN", "Rowan", "attr", 6),
            (".", "PUNCT", ".", "punct", 6),
        ]
        self.assertTrue(has_unknown(inventory([rows])))

    def test_conjunct_without_operator_or_list_separator_stays_unknown(self):
        self.assertTrue(
            has_unknown(inventory([actor([("Nova", "PROPN", "Nova", "conj", 7)])]))
        )

    def test_complete_serial_list_has_all_actual_arguments(self):
        x = inventory(
            [
                actor(
                    [
                        (",", "PUNCT", ",", "punct", 7),
                        ("Nova", "PROPN", "Nova", "conj", 7),
                        ("and", "CCONJ", "and", "cc", 7),
                        ("Cedar", "PROPN", "Cedar", "conj", 7),
                    ]
                )
            ]
        )
        self.assertFalse(has_unknown(x))
        self.assertEqual(
            len(json.loads(of_kind(x, "role_assignment")[0].payload_json)["values"]), 3
        )

    def test_operator_attached_to_following_conjunct_has_same_closure(self):
        x = inventory(
            [
                actor(
                    [
                        ("and", "CCONJ", "and", "cc", 9),
                        ("Nova", "PROPN", "Nova", "conj", 7),
                    ]
                )
            ]
        )
        self.assertFalse(has_unknown(x))

    def test_qualified_argument_nested_dangling_list_is_unresolved(self):
        x = inventory(
            [
                actor(
                    [
                        ("from", "ADP", "from", "prep", 7),
                        ("District", "PROPN", "District", "pobj", 8),
                        ("and", "CCONJ", "and", "cc", 9),
                    ]
                )
            ]
        )
        self.assertTrue(has_unknown(x))

    def test_complete_inner_qualifier_coordination_keeps_full_literal(self):
        x = inventory(
            [
                actor(
                    [
                        ("from", "ADP", "from", "prep", 7),
                        ("District", "PROPN", "District", "pobj", 8),
                        ("and", "CCONJ", "and", "cc", 9),
                        ("Region", "PROPN", "Region", "conj", 9),
                    ]
                )
            ]
        )
        self.assertFalse(has_unknown(x))
        self.assertEqual(
            json.loads(of_kind(x, "role_assignment")[0].payload_json)["value"]["text"],
            "Rowan from District and Region",
        )
        self.assertIn("argument_qualifier_meaning_unassessed", x.blockers)

    def test_dangling_scalar_and_catalogue_are_semantic_unknowns(self):
        for rows, head in [
            (FIELD, 6),
            (CAT[:6] + [(".", "PUNCT", ".", "punct", 4)], 5),
        ]:
            with self.subTest(head=head):
                x = inventory(
                    [rows[:-1] + [("and", "CCONJ", "and", "cc", head), rows[-1]]]
                )
                self.assertTrue(has_unknown(x))
                self.assertEqual(x.support_or_permissions, "NOT_ASSESSED")
                self.assertEqual(x.read_set.universe_completeness, "NOT_ESTABLISHED")


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
