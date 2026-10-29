"""UNITONLY handcrafted syntax/source fixtures; no observed parser/model behavior."""

import ctypes
import hashlib
import json
import socket
import subprocess
import unittest
from dataclasses import replace
from unittest.mock import patch

from app.services import planning_declarations as d
from app.services import request_parser as parser


def deny(*args, **kwargs):
    raise AssertionError("No actual process/socket/native/model action")


def capture(groups):
    """UNITONLY graph constructor; it creates no actual linguistic observation."""
    flat = []
    sentences = []
    cursor = 0
    for group in groups:
        base = len(flat)
        left = cursor
        for i, (text, pos, lemma, dep, head) in enumerate(group):
            ws = (
                "" if i == len(group) - 1 or group[i + 1][0] in {",", ".", ";"} else " "
            )
            if i == len(group) - 1 and group is not groups[-1]:
                ws = " "
            flat.append(
                {
                    "i": base + i,
                    "start": cursor,
                    "end": cursor + len(text),
                    "text": text,
                    "whitespace": ws,
                    "pos": pos,
                    "tag": "MD"
                    if text in {"may", "must", "should"}
                    else "NN"
                    if pos not in {"VERB", "AUX", "PUNCT"}
                    else "VB"
                    if pos in {"VERB", "AUX"}
                    else ".",
                    "dep": dep,
                    "head": base + head,
                    "lemma": lemma,
                    "morph": "",
                    "sentence_start": i == 0,
                    "children": [],
                }
            )
            cursor += len(text) + len(ws)
        sentences.append(
            {
                "start": left,
                "end": flat[-1]["end"],
                "text": "",
                "token_start": base,
                "token_end": len(flat),
            }
        )
    raw = "".join(t["text"] + t["whitespace"] for t in flat)
    for s in sentences:
        s["text"] = raw[s["start"] : s["end"]]
    for t in flat:
        t["children"] = [
            x["i"] for x in flat if x["head"] == t["i"] and x["i"] != t["i"]
        ]
    annotation = {
        "raw_text": raw,
        "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "coordinate_system": "python-unicode-codepoints",
        "tokens": flat,
        "sentences": sentences,
        "lossless_input_cover": parser._cover(raw, flat),
        "linguistic_proposals": parser._proposals(flat, sentences),
        "protected_token_indices": [
            t["i"] for t in flat if t["dep"] in parser._PROTECTED or t["tag"] == "MD"
        ],
        "all_token_indices_retained": list(range(len(flat))),
        "semantic_obligation_completeness": "NOT_ESTABLISHED",
        "support_or_permissions": "NOT_ASSESSED",
    }
    return raw, parser.make_capture(annotation)


CAT = [
    ("Roles", "NOUN", "role", "nsubj", 4),
    ("for", "ADP", "for", "prep", 0),
    ("Cedar", "PROPN", "Cedar", "compound", 3),
    ("inspection", "NOUN", "inspection", "pobj", 1),
    ("are", "AUX", "be", "ROOT", 4),
    ("coordinator", "NOUN", "coordinator", "attr", 4),
    (",", "PUNCT", ",", "punct", 5),
    ("observer", "NOUN", "observer", "conj", 5),
    ("and", "CCONJ", "and", "cc", 5),
    ("recorder", "NOUN", "recorder", "conj", 5),
    (".", "PUNCT", ".", "punct", 4),
]
NAME = [
    ("The", "DET", "the", "det", 1),
    ("activity", "NOUN", "activity", "nsubjpass", 3),
    ("is", "AUX", "be", "auxpass", 3),
    ("called", "VERB", "call", "ROOT", 3),
    ("Cedar", "PROPN", "Cedar", "compound", 5),
    ("inspection", "NOUN", "inspection", "oprd", 3),
    (".", "PUNCT", ".", "punct", 3),
]
ASSIGN = [
    ("The", "DET", "the", "det", 2),
    ("coordinator", "NOUN", "coordinator", "compound", 2),
    ("role", "NOUN", "role", "nsubj", 6),
    ("for", "ADP", "for", "prep", 2),
    ("Cedar", "PROPN", "Cedar", "compound", 5),
    ("inspection", "NOUN", "inspection", "pobj", 3),
    ("is", "AUX", "be", "ROOT", 6),
    ("Rowan", "PROPN", "Rowan", "attr", 6),
    (".", "PUNCT", ".", "punct", 6),
]
FIELD = [
    ("Inspection", "NOUN", "inspection", "compound", 1),
    ("time", "NOUN", "time", "nsubj", 5),
    ("for", "ADP", "for", "prep", 1),
    ("Cedar", "PROPN", "Cedar", "compound", 4),
    ("inspection", "NOUN", "inspection", "pobj", 2),
    ("is", "AUX", "be", "ROOT", 5),
    ("09:00", "NUM", "09:00", "attr", 5),
    (".", "PUNCT", ".", "punct", 5),
]
COND = [
    ("Roles", "NOUN", "role", "nsubj", 6),
    ("for", "ADP", "for", "prep", 0),
    ("Cedar", "PROPN", "Cedar", "compound", 3),
    ("inspection", "NOUN", "inspection", "pobj", 1),
    ("may", "AUX", "may", "aux", 6),
    ("not", "PART", "not", "neg", 6),
    ("be", "AUX", "be", "ROOT", 6),
    ("coordinator", "NOUN", "coordinator", "attr", 6),
    ("and", "CCONJ", "and", "cc", 7),
    ("observer", "NOUN", "observer", "conj", 7),
    ("unless", "SCONJ", "unless", "mark", 12),
    ("permit", "NOUN", "permit", "nsubj", 12),
    ("applies", "VERB", "apply", "advcl", 6),
    (".", "PUNCT", ".", "punct", 6),
]
EXTERNAL = [
    ("Follow", "VERB", "follow", "ROOT", 0),
    ("Note", "NOUN", "note", "dobj", 0),
    ("Amber", "PROPN", "Amber", "appos", 1),
    (".", "PUNCT", ".", "punct", 0),
]
UNKNOWN = [
    ("Perhaps", "ADV", "perhaps", "advmod", 1),
    ("something", "NOUN", "something", "ROOT", 1),
    (".", "PUNCT", ".", "punct", 1),
]


def source(groups, doc="UNITONLY-doc", title="UNITONLY source"):
    body, cap = capture(groups)
    ident = d.SourceIdentity(
        doc, 1, d.body_hash(body), "UNITONLY-workspace", doc + "-snapshot"
    )
    snap = d.SourceSnapshot(
        ident,
        title,
        body,
        d.canonical({"fixture": "UNITONLY"}),
        (d.SourceChunk(doc + "-chunk", 0, d.RawRange(0, len(body), body)),),
    )
    caps = d.SourceCaptures(ident, (d.CaptureWindow(0, len(body), d.canonical(cap)),))
    return snap, caps


def universe(snaps, mode="bounded_authorized_scan"):
    return d.PlanningUniverse(
        d.canonical(
            {
                "fixture": "UNITONLY",
                "workspace": "UNITONLY-workspace",
                "selector": "caller-applied filters; authorization NOT_ASSESSED",
            }
        ),
        tuple(s.identity for s in snaps),
        mode,
    )


def inventory(groups):
    s, c = source(groups)
    return d.declaration_inventory(universe([s]), (s,), (c,))


def of_kind(inv, kind):
    return [x for x in inv.declarations if x.kind == kind]


class Declarations(unittest.TestCase):
    # Defect: a fixed owner/deputy or top-two catalogue loses arbitrary members.
    def test_arbitrary_role_catalogue_preserves_three_literal_members(self):
        inv = inventory([CAT])
        rows = of_kind(inv, "role_catalogue")
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            [x.text for x in rows[0].members], ["coordinator", "observer", "recorder"]
        )
        self.assertEqual([x.text for x in rows[0].scope], ["Cedar inspection"])
        self.assertEqual(inv.support_or_permissions, "NOT_ASSESSED")
        self.assertEqual(rows[0].status, "UNASSESSED_PROPOSAL")

    def test_new_fourth_member_changes_inventory_without_truncation(self):
        group = CAT[:-1] + [
            ("and", "CCONJ", "and", "cc", 5),
            ("arbiter", "NOUN", "arbiter", "conj", 5),
            (".", "PUNCT", ".", "punct", 4),
        ]
        inv = inventory([group])
        rows = of_kind(inv, "role_catalogue")
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            [x.text for x in rows[0].members],
            ["coordinator", "observer", "recorder", "arbiter"],
        )

    # Membership must not become actor-value support or rewrite the operation.
    def test_labels_only_and_incumbents_are_separate_proposals(self):
        inv = inventory([CAT])
        labels = d.catalogue_candidates(
            inv, operation="labels_only", scope_literal="Cedar inspection"
        )
        actors = d.catalogue_candidates(
            inv, operation="incumbents", scope_literal="Cedar inspection"
        )
        self.assertEqual(len(labels.catalogues), 1)
        self.assertFalse(labels.actor_values_required)
        self.assertTrue(actors.actor_values_required)
        self.assertEqual(labels.support_or_permissions, "NOT_ASSESSED")
        self.assertIn("independent_membership_evidence_required", labels.blockers)
        self.assertIn("independent_actor_value_evidence_required", actors.blockers)

    def test_unsupported_request_operation_never_inferred_from_question_template(self):
        with self.assertRaises(ValueError):
            d.catalogue_candidates(
                inventory([CAT]),
                operation="who ever...",
                scope_literal="Cedar inspection",
            )

    def test_literal_declared_name_has_exact_original_range(self):
        inv = inventory([NAME])
        rows = of_kind(inv, "literal_name")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].literal.text, "Cedar inspection")
        self.assertEqual(rows[0].raw.text, "The activity is called Cedar inspection.")
        self.assertEqual(rows[0].literal.start, 23)
        self.assertEqual(rows[0].literal.end, 39)

    def test_title_is_not_a_body_declaration_or_scope_proof(self):
        s, c = source([UNKNOWN], title="Cedar inspection")
        inv = d.declaration_inventory(universe([s]), (s,), (c,))
        self.assertEqual(of_kind(inv, "literal_name"), [])
        self.assertEqual(len(inv.units), 1)
        self.assertIn("unknown_source_grammar", inv.units[0].unknowns)

    def test_assignment_retains_label_and_value_but_does_not_establish_truth(self):
        inv = inventory([ASSIGN])
        rows = of_kind(inv, "role_assignment")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].literal.text, "coordinator")
        self.assertEqual(json.loads(rows[0].payload_json)["value"]["text"], "Rowan")
        self.assertEqual(rows[0].status, "UNASSESSED_PROPOSAL")

    # Defect: temporal name lookup invents relation/type or converts requested units.
    def test_literal_field_does_not_invent_temporal_relation(self):
        inv = inventory([FIELD])
        rows = of_kind(inv, "literal_field")
        self.assertEqual(len(rows), 1)
        payload = json.loads(rows[0].payload_json)
        self.assertEqual(rows[0].literal.text, "Inspection time")
        self.assertEqual(payload["value"]["text"], "09:00")
        self.assertEqual(payload["temporal_meaning"], "NOT_ASSESSED")

    def test_conditions_negation_modals_and_governors_are_retained(self):
        inv = inventory([COND])
        rows = of_kind(inv, "role_catalogue")
        self.assertEqual(len(rows), 1)
        features = json.loads(rows[0].features_json)
        self.assertEqual(
            [x["text"] for x in features["conditions"]], ["unless permit applies"]
        )
        self.assertEqual([x["text"] for x in features["negation"]], ["not"])
        self.assertEqual([x["text"] for x in features["modality"]], ["may"])
        self.assertTrue(features["governors"])
        self.assertIn("conditioned_or_qualified_declaration", inv.blockers)

    def test_unknown_units_and_opposing_catalogues_not_ranked_away(self):
        s1, c1 = source([CAT, UNKNOWN], doc="UNITONLY-a")
        changed = [
            ("auditor", "NOUN", "auditor", dep, head)
            if text == "coordinator"
            else (text, pos, lemma, dep, head)
            for text, pos, lemma, dep, head in CAT
        ]
        s2, c2 = source([changed], doc="UNITONLY-b")
        inv = d.declaration_inventory(universe([s1, s2]), (s1, s2), (c1, c2))
        self.assertEqual(len(inv.units), 4)
        self.assertEqual(len(of_kind(inv, "role_catalogue")), 2)
        self.assertEqual(
            [u.raw.text for u in inv.units if u.grammar == "raw_gap"], [" "]
        )
        p = d.catalogue_candidates(
            inv, operation="labels_only", scope_literal="Cedar inspection"
        )
        self.assertEqual(len(p.catalogues), 2)
        self.assertIn("multiple_catalogue_declarations", p.blockers)

    def test_present_unique_external_instruction_target_stays_unresolved(self):
        s1, c1 = source([EXTERNAL], doc="UNITONLY-caller")
        s2, c2 = source([NAME], doc="UNITONLY-target", title="Note Amber")
        inv = d.declaration_inventory(universe([s1, s2]), (s1, s2), (c1, c2))
        rows = of_kind(inv, "external_instruction_target")
        self.assertEqual(len(rows), 1)
        payload = json.loads(rows[0].payload_json)
        self.assertEqual(payload["candidate_document_ids"], ["UNITONLY-target"])
        self.assertEqual(rows[0].status, "UNRESOLVED_EXTERNAL_TARGET")
        self.assertIn("external_instruction_targets_initially_unresolved", inv.blockers)

    def test_missing_or_ambiguous_external_targets_always_unresolved(self):
        for count in [0, 2]:
            with self.subTest(count=count):
                pairs = [source([EXTERNAL], doc="UNITONLY-caller")] + [
                    source([NAME], doc=f"UNITONLY-target-{i}", title="Note Amber")
                    for i in range(count)
                ]
                snaps = tuple(x[0] for x in pairs)
                caps = tuple(x[1] for x in pairs)
                inv = d.declaration_inventory(universe(snaps), snaps, caps)
                rows = of_kind(inv, "external_instruction_target")
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0].status, "UNRESOLVED_EXTERNAL_TARGET")
                self.assertEqual(
                    len(json.loads(rows[0].payload_json)["candidate_document_ids"]),
                    count,
                )

    # Defect: a producer flag or top-K inventory masquerades as complete authorization.
    def test_ranked_subset_has_no_universe_completeness_or_absence_proof(self):
        s, c = source([CAT])
        inv = d.declaration_inventory(universe([s], "ranked_subset"), (s,), (c,))
        self.assertEqual(inv.read_set.universe_completeness, "NOT_ESTABLISHED")
        self.assertIn(
            "planning_universe_requires_independent_authorization_and_currentness",
            inv.blockers,
        )
        self.assertIn(
            "ranked_or_unknown_universe_cannot_establish_closure", inv.blockers
        )

    def test_missing_declared_publication_retained_in_read_set(self):
        s1, c1 = source([CAT])
        s2, c2 = source([UNKNOWN], doc="UNITONLY-missing")
        inv = d.declaration_inventory(universe([s1, s2]), (s1,), (c1,))
        self.assertEqual(inv.read_set.missing_publications, (s2.identity,))
        self.assertIn("uninspectable_selected_publication", inv.blockers)

    def test_source_body_hash_mismatch_fails(self):
        s, c = source([CAT])
        s = replace(s, body=s.body + " foreign")
        with self.assertRaises(ValueError):
            d.declaration_inventory(universe([s]), (s,), (c,))

    def test_capture_body_swap_and_bool_indices_fail(self):
        s, c = source([CAT])
        s2, c2 = source([NAME])
        for bad in [
            replace(c, windows=c2.windows),
            replace(c, windows=(replace(c.windows[0], start=False),)),
        ]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    d.declaration_inventory(universe([s]), (s,), (bad,))

    def test_full_capture_body_coverage_required(self):
        s, c = source([CAT])
        bad = replace(c, windows=(replace(c.windows[0], end=len(s.body) - 1),))
        with self.assertRaises(ValueError):
            d.declaration_inventory(universe([s]), (s,), (bad,))

    def test_chunk_membership_literal_and_ordinals_are_exact(self):
        s, c = source([CAT])
        for chunk in [
            replace(s.chunks[0], ordinal=False),
            replace(s.chunks[0], literal=d.RawRange(0, 5, "wrong")),
        ]:
            bad = replace(s, chunks=(chunk,))
            with self.subTest(chunk=chunk):
                with self.assertRaises(ValueError):
                    d.declaration_inventory(universe([bad]), (bad,), (c,))

    def test_read_set_binds_metadata_membership_and_actual_capture(self):
        s, c = source([CAT])
        m = universe([s])
        record = d.planning_read_set(m, (s,), (c,)).record()
        self.assertTrue(
            d.validate_planning_read_set(
                record, manifest=m, snapshots=(s,), captures=(c,)
            )
        )
        changed = replace(s, metadata_json=d.canonical({"changed": "UNITONLY"}))
        self.assertFalse(
            d.validate_planning_read_set(
                record, manifest=m, snapshots=(changed,), captures=(c,)
            )
        )
        changed = replace(s, chunks=(replace(s.chunks[0], chunk_id="UNITONLY-new"),))
        self.assertFalse(
            d.validate_planning_read_set(
                record, manifest=m, snapshots=(changed,), captures=(c,)
            )
        )

    def test_reconstruction_rejects_deleted_member_or_condition_even_with_new_digest(
        self,
    ):
        s, c = source([COND])
        m = universe([s])
        inv = d.declaration_inventory(m, (s,), (c,))
        record = inv.record()
        self.assertTrue(
            d.validate_declaration_inventory(
                record, manifest=m, snapshots=(s,), captures=(c,)
            )
        )
        self.assertTrue(record["declarations"])
        record["declarations"][0]["members"] = []
        record["declarations"][0]["id"] = d.digest(record["declarations"][0])
        self.assertFalse(
            d.validate_declaration_inventory(
                record, manifest=m, snapshots=(s,), captures=(c,)
            )
        )

    def test_unknown_addition_changes_inventory_and_read_set(self):
        s1, c1 = source([CAT])
        m1 = universe([s1])
        old = d.declaration_inventory(m1, (s1,), (c1,))
        s2, c2 = source([UNKNOWN], doc="UNITONLY-added")
        m2 = universe([s1, s2])
        self.assertFalse(
            d.validate_declaration_inventory(
                old.record(), manifest=m2, snapshots=(s1, s2), captures=(c1, c2)
            )
        )
        self.assertFalse(
            d.validate_planning_read_set(
                old.read_set.record(),
                manifest=m2,
                snapshots=(s1, s2),
                captures=(c1, c2),
            )
        )

    def test_unknown_grammar_does_not_prove_no_override_or_governing_absence(self):
        inv = inventory([UNKNOWN])
        self.assertEqual(len(inv.units), 1)
        self.assertIn("unknown_source_grammar", inv.blockers)
        self.assertIn("source_authority_and_evidence_not_assessed", inv.blockers)

    def test_duplicate_sources_or_unlisted_source_fail(self):
        s, c = source([CAT])
        for manifest, snaps, caps in [
            (universe([s]), (s, s), (c, c)),
            (universe([]), (s,), (c,)),
            (replace(universe([s]), publications=(s.identity, s.identity)), (s,), (c,)),
        ]:
            with self.assertRaises(ValueError):
                d.declaration_inventory(manifest, snaps, caps)

    def test_document_budget_overflow_fails_without_truncation(self):
        s, c = source([CAT])
        pubs = tuple(
            replace(s.identity, document_id=f"UNITONLY-{i}") for i in range(129)
        )
        with self.assertRaises(ValueError):
            d.declaration_inventory(
                replace(universe([s]), publications=pubs), (s,), (c,)
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
