"""824v2 controls; UNITONLY graphs, no source artifact writes."""

import json
import unittest
from dataclasses import asdict, replace

from app.services import planning_declarations as d
from app.services.planning_scope_bridge import (
    reconstruct_scope_bridge,
    validate_scope_bridge,
)
from app.services.staged_request import compile_request

from tests.planning_scope_fixtures834 import (
    REQUEST,
    inputs,
    request_modifier,
    retain_evidence,
)
from tests.test_planning_declarations import capture


class ScopeBridgeTests(unittest.TestCase):
    def test_global_and_opposing_matching_source_retained(self):
        data = inputs(
            "All sessions require a card.",
            "This note applies to Cedar inspection. Do not move the card.",
        )
        result = reconstruct_scope_bridge(*data)
        self.assertEqual(result["excluded"], [])
        self.assertEqual(result["retained"], ["UNITONLY-0", "UNITONLY-1"])

    def test_title_metadata_cannot_prove_exclusion(self):
        partial, manifest, snapshots, caps = inputs("Unclassified governance applies.")
        snapshots = (
            replace(
                snapshots[0],
                title="Larch inspection",
                metadata_json='{"irrelevant":true,"rank":0}',
            ),
        )
        self.assertEqual(
            reconstruct_scope_bridge(partial, manifest, snapshots, caps)["excluded"], []
        )

    def test_missing_snapshot_retained_with_full_read_set(self):
        partial, manifest, _snapshots, _caps = inputs(
            "This note applies to Larch inspection. Move the card."
        )
        result = reconstruct_scope_bridge(partial, manifest, (), ())
        self.assertEqual(result["retained"], ["UNITONLY-0"])
        self.assertEqual(
            result["read_set"]["missing_publications"][0]["document_id"], "UNITONLY-0"
        )

    def test_changed_partial_scope_or_body_cannot_be_certified(self):
        partial, manifest, snapshots, caps = inputs(
            "This note applies to Larch inspection. Move the card."
        )
        node = partial.nodes[0]
        forged = replace(
            partial,
            nodes=(
                replace(
                    node, scopes=(replace(node.scopes[0], text="Larch inspection"),)
                ),
                *partial.nodes[1:],
            ),
        )
        with self.assertRaises(ValueError):
            reconstruct_scope_bridge(forged, manifest, snapshots, caps)
        with self.assertRaises(ValueError):
            reconstruct_scope_bridge(
                partial,
                manifest,
                (replace(snapshots[0], body=snapshots[0].body + " Extra."),),
                caps,
            )

    def test_record_tamper_rejected_by_reconstruction(self):
        from app.services.planning_scope_bridge import validate_scope_bridge

        data = inputs("This note applies to Cedar inspection. Move the card.")
        record = reconstruct_scope_bridge(*data)
        self.assertTrue(validate_scope_bridge(record, *data))
        record["excluded"] = ["UNITONLY-0"]
        record["retained"] = []
        self.assertFalse(validate_scope_bridge(record, *data))

    def test_existing_procedure_declaration_exact_name_ranges_and_ambiguity(self):
        body = (
            "The following routine applies to ordinary Cedar sessions. Move the card."
        )
        result = reconstruct_scope_bridge(*inputs(body, body))
        candidates = [
            c
            for c in result["name_candidates"]
            if c["origin"] == "recognized_declared_envelope"
        ]
        self.assertEqual(len(candidates), 2)
        self.assertTrue(
            all(
                c["literal"]["text"] == "Cedar"
                and c["resolution"] == "ambiguous_literal"
                for c in candidates
            )
        )
        self.assertTrue(
            all(
                body[c["literal"]["start"] : c["literal"]["end"]] == "Cedar"
                for c in candidates
            )
        )

    def test_unsupported_unscoped_request_never_excludes(self):
        _partial, manifest, snapshots, caps = inputs(
            "This note applies to Larch inspection. Move the card."
        )
        question, cap = capture(
            [
                [
                    ("Explain", "VERB", "explain", "ROOT", 0),
                    ("everything", "PRON", "everything", "dobj", 0),
                    (".", "PUNCT", ".", "punct", 0),
                ]
            ]
        )
        result = reconstruct_scope_bridge(
            compile_request(question, cap), manifest, snapshots, caps
        )
        self.assertEqual(result["excluded"], [])
        self.assertTrue(result["request_scope_blockers"])

    def test_request_condition_is_retained_and_cannot_prune_sources(self):
        partial, manifest, snapshots, caps = inputs(
            "This note applies to Larch inspection. Move the card."
        )
        conditional = REQUEST[:-1] + [
            ("if", "SCONJ", "if", "mark", 8),
            ("card", "NOUN", "card", "nsubj", 8),
            ("moves", "VERB", "move", "advcl", 0),
            (".", "PUNCT", ".", "punct", 0),
        ]
        question, cap = capture([conditional])
        partial = compile_request(question, cap)
        self.assertTrue(json.loads(partial.features_json)["condition_ast"])
        result = reconstruct_scope_bridge(partial, manifest, snapshots, caps)
        self.assertEqual(result["excluded"], [])
        self.assertEqual(result["partial_request"], partial.record())
        self.assertIn(
            "qualified_request_requires_resolution", result["request_scope_blockers"]
        )


class InitialMaterialBoundaries(unittest.TestCase):
    def test_owned_qualifier_does_not_enable_exclusion(self):
        _, universe, snapshots, caps = inputs(
            "This note applies to Larch inspection. Move the card."
        )
        partial = request_modifier("former", "ADJ", "amod")
        result = reconstruct_scope_bridge(partial, universe, snapshots, caps)
        retain_evidence("owned-qualifier", partial, result)
        self.assertEqual(result["excluded"], [])
        self.assertTrue(result["request_scope_blockers"])

    def test_open_quantity_does_not_enable_exclusion(self):
        _, universe, snapshots, caps = inputs(
            "This note applies to Larch inspection. Move the card."
        )
        partial = request_modifier("Some", "DET", "det", "some")
        result = reconstruct_scope_bridge(partial, universe, snapshots, caps)
        retain_evidence("open-quantity", partial, result)
        self.assertEqual(result["excluded"], [])
        self.assertTrue(result["request_scope_blockers"])

    def test_temporally_qualified_source_namespace_stays_retained(self):
        partial, *rest = inputs(
            "This note applies to Larch inspection before approval. Move the card."
        )
        result = reconstruct_scope_bridge(partial, *rest)
        retain_evidence("qualified-source", partial, result)
        self.assertEqual(result["excluded"], [])

    def test_ranked_subset_cannot_exclude(self):
        partial, universe, snapshots, caps = inputs(
            "This note applies to Larch inspection. Move the card."
        )
        result = reconstruct_scope_bridge(
            partial, replace(universe, selection_mode="ranked_subset"), snapshots, caps
        )
        self.assertEqual(result["excluded"], [])
        self.assertIn(
            "universe_selection_not_complete_scan", result["request_scope_blockers"]
        )
        self.assertEqual(
            result["read_set"],
            d.planning_read_set(
                replace(universe, selection_mode="ranked_subset"), snapshots, caps
            ).record(),
        )

    def test_uncovered_capture_cannot_exclude(self):
        partial, universe, snapshots, caps = inputs(
            "This note applies to Larch inspection. Move the card."
        )
        window = caps[0].windows[0]
        changed = (replace(caps[0], windows=(replace(window, end=window.end - 1),)),)
        with self.assertRaises(ValueError):
            reconstruct_scope_bridge(partial, universe, snapshots, changed)


class QualifiedSourceBoundary(unittest.TestCase):
    def test_temporally_qualified_source_namespace_stays_retained(self):
        partial, universe, snapshots, caps = inputs(
            "This note applies to Larch inspection before approval. Move the card."
        )
        text, actual_cap = capture(
            [
                [
                    ("This", "DET", "this", "det", 1),
                    ("note", "NOUN", "note", "nsubj", 2),
                    ("applies", "VERB", "apply", "ROOT", 2),
                    ("to", "ADP", "to", "prep", 2),
                    ("Larch", "PROPN", "Larch", "compound", 5),
                    ("inspection", "NOUN", "inspection", "pobj", 3),
                    ("before", "ADP", "before", "prep", 5),
                    ("approval", "NOUN", "approval", "pobj", 6),
                    (".", "PUNCT", ".", "punct", 2),
                ],
                [
                    ("Move", "VERB", "move", "ROOT", 0),
                    ("the", "DET", "the", "det", 2),
                    ("card", "NOUN", "card", "dobj", 0),
                    (".", "PUNCT", ".", "punct", 0),
                ],
            ]
        )
        self.assertEqual(text, snapshots[0].body)
        caps = (
            replace(
                caps[0],
                windows=(d.CaptureWindow(0, len(text), d.canonical(actual_cap)),),
            ),
        )
        result = reconstruct_scope_bridge(partial, universe, snapshots, caps)
        retain_evidence("qualified-source-actualcapture", partial, result)
        self.assertEqual(result["excluded"], [])


def attached_source(snapshot, caps, *, nominal_change=None):
    """Freeze one fully attached generic declaration in test-only fixture code."""
    name = snapshot.body.split(" to ", 1)[1].split(".", 1)[0].split()
    head = 3 + len(name)
    rows = [
        ("This", "DET", "this", "det", 1),
        ("note", "NOUN", "note", "nsubj", 2),
        ("applies", "VERB", "apply", "ROOT", 2),
        ("to", "ADP", "to", "prep", 2),
    ]
    for offset, word in enumerate(name):
        index = 4 + offset
        row = (
            word,
            "PROPN" if offset == 0 else "NOUN",
            word,
            "pobj" if index == head else "compound",
            3 if index == head else head,
        )
        if nominal_change and offset == nominal_change[0]:
            row = (word, nominal_change[1], word, nominal_change[2], head)
        rows.append(row)
    rows.append((".", "PUNCT", ".", "punct", 2))
    body, actual = capture(
        [
            rows,
            [
                ("Move", "VERB", "move", "ROOT", 0),
                ("the", "DET", "the", "det", 2),
                ("card", "NOUN", "card", "dobj", 0),
                (".", "PUNCT", ".", "punct", 0),
            ],
        ]
    )
    assert body == snapshot.body
    return replace(caps, windows=(d.CaptureWindow(0, len(body), d.canonical(actual)),))


def attached_inputs(*bodies):
    partial, universe, snapshots, caps = inputs(*bodies)
    return (
        partial,
        universe,
        snapshots,
        tuple(
            attached_source(snapshot, cap)
            for snapshot, cap in zip(snapshots, caps, strict=True)
        ),
    )


def compound_request(names):
    rows = REQUEST[:4]
    head = 3 + len(names)
    for offset, word in enumerate(names):
        index = 4 + offset
        rows.append(
            (
                word,
                "PROPN" if offset == 0 else "NOUN",
                word,
                "pobj" if index == head else "compound",
                3 if index == head else head,
            )
        )
    rows.append((".", "PUNCT", ".", "punct", 0))
    question, cap = capture([rows])
    return compile_request(question, cap)


class StructuralContrasts(unittest.TestCase):
    def test_attached_unqualified_positive_and_unknown_tail(self):
        partial, universe, snapshots, caps = inputs(
            "This note applies to Cedar inspection. Move the card.",
            "This note applies to Larch inspection. Move the card.",
            "This note applies to Birch inspection. Unknown governing exception.",
        )
        caps = (
            attached_source(snapshots[0], caps[0]),
            attached_source(snapshots[1], caps[1]),
            caps[2],
        )
        result = reconstruct_scope_bridge(partial, universe, snapshots, caps)
        self.assertEqual(result["retained"], ["UNITONLY-0", "UNITONLY-2"])
        self.assertEqual(result["excluded"], ["UNITONLY-1"])
        self.assertEqual(
            result["source_decisions"][1]["source_nominal_closures"][0]["status"],
            "EXACT_LITERAL_COMPOUND_SCOPE",
        )
        self.assertEqual(
            result["request_relation_closures"][0]["status"], "EXACT_INITIAL_RELATION"
        )
        self.assertEqual(
            result["read_set"], d.planning_read_set(universe, snapshots, caps).record()
        )

    def test_full_literal_compound_scope_preserved(self):
        _, universe, snapshots, caps = attached_inputs(
            "This note applies to Larch archive inspection. Move the card.",
            "This note applies to Cedar archive inspection. Move the card.",
        )
        partial = compound_request(["Cedar", "archive", "inspection"])
        result = reconstruct_scope_bridge(partial, universe, snapshots, caps)
        self.assertEqual(result["excluded"], ["UNITONLY-0"])
        self.assertEqual(result["retained"], ["UNITONLY-1"])
        self.assertEqual(
            result["request_scopes"][0]["text"], "Cedar archive inspection"
        )
        self.assertEqual(
            result["source_decisions"][0]["source_nominal_closures"][0]["literal"][
                "text"
            ],
            "Larch archive inspection",
        )

    def test_two_attached_scopes_compare_every_source(self):
        _, universe, snapshots, caps = attached_inputs(
            "This note applies to Larch inspection. Move the card.",
            "This note applies to Spruce inspection. Move the card.",
        )
        other = [
            row if index != 4 else ("Larch", "PROPN", "Larch", "compound", 5)
            for index, row in enumerate(REQUEST)
        ]
        question, actual = capture([REQUEST, other])
        result = reconstruct_scope_bridge(
            compile_request(question, actual), universe, snapshots, caps
        )
        self.assertEqual(result["retained"], ["UNITONLY-0"])
        self.assertEqual(result["excluded"], ["UNITONLY-1"])
        self.assertTrue(
            all(
                len(row["scope_comparisons"]) == 2 for row in result["source_decisions"]
            )
        )

    def test_identical_source_text_compound_amod_and_unknown_attachment(self):
        partial, universe, snapshots, caps = attached_inputs(
            "This note applies to Larch future inspection. Move the card."
        )
        closed = reconstruct_scope_bridge(partial, universe, snapshots, caps)
        self.assertEqual(closed["excluded"], ["UNITONLY-0"])
        for pos, dep in (("ADJ", "amod"), ("NOUN", "dep")):
            with self.subTest(pos=pos, dep=dep):
                changed = (
                    attached_source(
                        snapshots[0], caps[0], nominal_change=(1, pos, dep)
                    ),
                )
                result = reconstruct_scope_bridge(partial, universe, snapshots, changed)
                self.assertEqual(result["excluded"], [])
                self.assertEqual(result["retained"], ["UNITONLY-0"])
                self.assertEqual(result["snapshots"], closed["snapshots"])

    def test_owned_request_qualifier_and_quantity_with_closed_source(self):
        _, universe, snapshots, caps = attached_inputs(
            "This note applies to Larch inspection. Move the card."
        )
        for word, pos, dep in (("future", "ADJ", "amod"), ("Several", "DET", "det")):
            with self.subTest(word=word):
                partial = request_modifier(word, pos, dep)
                result = reconstruct_scope_bridge(partial, universe, snapshots, caps)
                self.assertEqual(result["excluded"], [])
                self.assertIn(
                    "actual_owned_request_argument_or_quantity_unresolved",
                    result["request_scope_blockers"],
                )
                self.assertEqual(
                    result["request_relation_closures"][0]["status"], "UNRESOLVED"
                )

    def test_full_replay_preserves_unknown_capture_and_rejects_closure_tamper(self):
        partial, universe, snapshots, opaque_caps = inputs(
            "This note applies to Larch inspection. Move the card."
        )
        unresolved = reconstruct_scope_bridge(partial, universe, snapshots, opaque_caps)
        self.assertEqual(unresolved["excluded"], [])
        self.assertEqual(
            unresolved["captures"],
            json.loads(d.canonical([asdict(row) for row in opaque_caps])),
        )
        self.assertTrue(
            validate_scope_bridge(unresolved, partial, universe, snapshots, opaque_caps)
        )
        unresolved["source_decisions"][0]["source_nominal_closures"][0]["status"] = (
            "EXACT_LITERAL_COMPOUND_SCOPE"
        )
        unresolved["excluded"] = ["UNITONLY-0"]
        unresolved["retained"] = []
        self.assertFalse(
            validate_scope_bridge(unresolved, partial, universe, snapshots, opaque_caps)
        )


class OpaqueRetentionCharacterization(unittest.TestCase):
    def test_opaque_other_namespace_stays_retained_under_v2(self):
        data = inputs(
            "This note applies to Cedar inspection. Move the card.",
            "This note applies to Larch inspection. Move the card.",
            "This note applies to Birch inspection. Unknown governing exception.",
        )
        record = reconstruct_scope_bridge(*data)
        self.assertEqual(record["excluded"], [])
        self.assertEqual(record["retained"], ["UNITONLY-0", "UNITONLY-1", "UNITONLY-2"])
        self.assertEqual(
            record["source_decisions"][1]["reason"],
            "actual_source_nominal_or_qualification_unresolved",
        )
        self.assertEqual(record["read_set"], d.planning_read_set(*data[1:]).record())

    def test_opaque_two_scope_universe_stays_retained_under_v2(self):
        _, universe, snapshots, caps = inputs(
            "This note applies to Larch inspection. Move the card.",
            "This note applies to Spruce inspection. Move the card.",
        )
        other = [
            row if i != 4 else ("Larch", "PROPN", "Larch", "compound", 5)
            for i, row in enumerate(REQUEST)
        ]
        question, cap = capture([REQUEST, other])
        partial = compile_request(question, cap)
        record = reconstruct_scope_bridge(partial, universe, snapshots, caps)
        self.assertEqual(record["excluded"], [])
        self.assertEqual(record["retained"], ["UNITONLY-0", "UNITONLY-1"])
        self.assertEqual(len(record["request_scopes"]), 2)
        self.assertTrue(
            all(
                len(row["scope_comparisons"]) == 2 for row in record["source_decisions"]
            )
        )
