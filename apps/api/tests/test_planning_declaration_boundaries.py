"""UNITONLY stricter source/read-set regressions; no actual parser incidence."""

import ctypes
import json
import socket
import subprocess
import unittest
from dataclasses import replace
from unittest.mock import patch

from tests.test_planning_declarations import (
    CAT,
    COND,
    FIELD,
    d,
    deny,
    inventory,
    of_kind,
    parser,
    source,
    universe,
)


class Boundaries(unittest.TestCase):
    # Defect: serialized untyped source/read lists hide structural obligations.
    def test_read_set_contains_typed_frozen_snapshot_and_capture_rows(self):
        s, c = source([CAT])
        read = d.planning_read_set(universe([s]), (s,), (c,))
        self.assertIsInstance(getattr(read, "snapshot_reads", None), tuple)
        self.assertIsInstance(getattr(read, "capture_reads", None), tuple)
        self.assertEqual(read.snapshot_reads[0].identity, s.identity)
        self.assertEqual(read.capture_reads[0].identity, s.identity)
        self.assertEqual(read.snapshot_reads[0].chunks, s.chunks)

    # Defect: source-declared literal labels lose an actual determiner by normalization.
    def test_declared_name_keeps_source_determiner_in_literal(self):
        group = [
            ("The", "DET", "the", "det", 1),
            ("activity", "NOUN", "activity", "nsubjpass", 3),
            ("is", "AUX", "be", "auxpass", 3),
            ("called", "VERB", "call", "ROOT", 3),
            ("The", "DET", "the", "det", 5),
            ("Lantern", "PROPN", "Lantern", "oprd", 3),
            (".", "PUNCT", ".", "punct", 3),
        ]
        rows = of_kind(inventory([group]), "literal_name")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].literal.text, "The Lantern")

    # Retain dangling condition markers even on a recognized catalogue.
    def test_unattached_conditional_marker_remains_unknown(self):
        group = CAT[:-1] + [
            ("unless", "SCONJ", "unless", "mark", 4),
            (".", "PUNCT", ".", "punct", 4),
        ]
        inv = inventory([group])
        self.assertTrue(of_kind(inv, "role_catalogue"))
        self.assertIn("unbound_source_condition_marker", inv.blockers)
        features = json.loads(inv.units[0].features_json)
        self.assertEqual(features["unbound_condition_markers"][0]["text"], "unless")

    def test_model_identity_and_capture_body_binding_cannot_be_resealed(self):
        s, c = source([CAT])
        cap = json.loads(c.windows[0].capture_json)
        cap["parser"]["model"] = "UNITONLY-forged"
        cap["capture_sha256"] = d.digest(
            {k: v for k, v in cap.items() if k != "capture_sha256"}
        )
        bad = replace(
            c, windows=(replace(c.windows[0], capture_json=d.canonical(cap)),)
        )
        with self.assertRaises(ValueError):
            d.declaration_inventory(universe([s]), (s,), (bad,))

    def test_empty_catalogue_is_retained_and_blocks_membership(self):
        group = CAT[:5] + [
            ("none", "NOUN", "none", "attr", 4),
            (".", "PUNCT", ".", "punct", 4),
        ]
        inv = inventory([group])
        rows = of_kind(inv, "role_catalogue")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].members, ())
        proposal = d.catalogue_candidates(
            inv, operation="labels_only", scope_literal="Cedar inspection"
        )
        self.assertIn("empty_catalogue_not_supported", proposal.blockers)

    def test_no_literal_scope_match_never_selects_nearest_or_unique_catalogue(self):
        proposal = d.catalogue_candidates(
            inventory([CAT]), operation="incumbents", scope_literal="Cedar"
        )
        self.assertEqual(proposal.catalogues, ())
        self.assertIn("missing_literal_catalogue_declaration", proposal.blockers)

    def test_conditions_deleted_from_coherent_record_rejected(self):
        s, c = source([COND])
        m = universe([s])
        record = d.declaration_inventory(m, (s,), (c,)).record()
        row = record["declarations"][0]
        features = json.loads(row["features_json"])
        features["conditions"] = []
        row["features_json"] = d.canonical(features)
        row["id"] = d.digest(row)
        self.assertFalse(
            d.validate_declaration_inventory(
                record, manifest=m, snapshots=(s,), captures=(c,)
            )
        )

    def test_read_set_never_claims_currentness_or_permissions_from_self_description(
        self,
    ):
        s, c = source([CAT])
        m = replace(
            universe([s]),
            scope_json=d.canonical(
                {"complete": True, "authorized": True, "no_override_issued": True}
            ),
        )
        inv = d.declaration_inventory(m, (s,), (c,))
        self.assertEqual(inv.read_set.universe_completeness, "NOT_ESTABLISHED")
        self.assertEqual(inv.read_set.support_or_permissions, "NOT_ASSESSED")
        self.assertIn(
            "planning_universe_requires_independent_authorization_and_currentness",
            inv.blockers,
        )

    def test_canonical_json_rejects_duplicate_fields_nonfinite_and_extra_capture_key(
        self,
    ):
        s, c = source([CAT])
        m = universe([s])
        for raw in ['{"x":1,"x":2}', '{"x":NaN}']:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    d.declaration_inventory(replace(m, scope_json=raw), (s,), (c,))
        cap = json.loads(c.windows[0].capture_json)
        cap["accepted"] = True
        bad = replace(
            c, windows=(replace(c.windows[0], capture_json=d.canonical(cap)),)
        )
        with self.assertRaises(ValueError):
            d.declaration_inventory(m, (s,), (bad,))

    def test_snapshot_version_workspace_and_current_universe_change_invalidate_read_set(
        self,
    ):
        s, c = source([CAT])
        m = universe([s])
        record = d.planning_read_set(m, (s,), (c,)).record()
        for identity in [
            replace(s.identity, document_version=2),
            replace(s.identity, workspace_id="UNITONLY-other"),
            replace(s.identity, snapshot_id="UNITONLY-other"),
        ]:
            s2 = replace(s, identity=identity)
            c2 = replace(c, identity=identity)
            m2 = replace(m, publications=(identity,))
            self.assertFalse(
                d.validate_planning_read_set(
                    record, manifest=m2, snapshots=(s2,), captures=(c2,)
                )
            )

    def test_scalar_fields_remain_separate_without_temporal_selection(self):
        g = [
            (
                text if text != "09:00" else "12",
                pos,
                lemma if text != "09:00" else "12",
                dep,
                head,
            )
            for text, pos, lemma, dep, head in FIELD
        ]
        inv = inventory([FIELD, g])
        rows = of_kind(inv, "literal_field")
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            [json.loads(x.payload_json)["value"]["text"] for x in rows], ["09:00", "12"]
        )
        self.assertTrue(
            all(
                json.loads(x.payload_json)["temporal_meaning"] == "NOT_ASSESSED"
                for x in rows
            )
        )

    def test_replay_rejects_permission_and_completeness_marker_promotion(self):
        s, c = source([CAT])
        m = universe([s])
        inv = d.declaration_inventory(m, (s,), (c,))
        for key, value in [("support_or_permissions", "ACCEPTED"), ("blockers", [])]:
            rec = inv.record()
            rec[key] = value
            self.assertFalse(
                d.validate_declaration_inventory(
                    rec, manifest=m, snapshots=(s,), captures=(c,)
                )
            )
        read = inv.read_set.record()
        read["universe_completeness"] = "COMPLETE"
        self.assertFalse(
            d.validate_planning_read_set(
                read, manifest=m, snapshots=(s,), captures=(c,)
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
