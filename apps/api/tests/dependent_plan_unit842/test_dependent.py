"""Captured request structure only; no actor values or fact approval invented."""

import json
import unittest
from copy import deepcopy
from dataclasses import asdict

from app.services import planning_declarations as d
from app.services import planning_support as p
from app.services import request_relation
from app.services import staged_plan_binding as b
from app.services.request_parser import make_capture

from tests.staged_plan_unit837.fixtures_request import DEPENDENT
from tests.staged_plan_unit837.fixtures_source import capture
from tests.staged_plan_unit837.test_binding import args, insert
from tests.test_contextual_source_proof import fixture, governor_plan

EXAMPLES = {}


def observe(name, actual, plan):
    EXAMPLES[name] = {
        "plan": plan.record(),
        "inputs": {
            key: asdict(value)
            if hasattr(value, "__dataclass_fields__")
            else [asdict(row) for row in value]
            if isinstance(value, tuple)
            and value
            and hasattr(value[0], "__dataclass_fields__")
            else value
            for key, value in actual.items()
        },
    }


def fresh_receipts(actual):
    prepared = p.prepare_planning_assertions(
        **{
            key: value
            for key, value in actual.items()
            if key not in {"observations", "actual_executions"}
        }
    )
    assessment = b.canonical(
        {
            "label": "entailment",
            "logits": [-3, 3, 0],
            "entailment_margin": 3,
            "supported": True,
            "pair_tokens": 40,
        }
    )
    actual["observations"] = tuple(
        p.NliObservation(
            row.id,
            "UNITONLY842-" + str(index),
            row.pair,
            prepared.support_metadata_json,
            assessment,
        )
        for index, row in enumerate(prepared.assertions)
    )
    actual["actual_executions"] = tuple(
        p.NliExecution(
            "UNITONLY842-" + str(index),
            row.id,
            row.pair,
            prepared.support_metadata_json,
            assessment,
            40,
            "UNITONLY",
        )
        for index, row in enumerate(prepared.assertions)
    )
    return actual


def onyx_inputs():
    body, identity, windows, original, _ = fixture()
    capture = make_capture(json.loads(original.graph_json))
    assert capture["capture_sha256"] == original.capture_sha256
    source_id = d.SourceIdentity(**identity, snapshot_id="UNITONLY842-Onyx-snapshot")
    snapshot = d.SourceSnapshot(
        source_id,
        "UNITONLY Onyx body",
        body,
        "{}",
        (d.SourceChunk("UNITONLY842-Onyx-chunk", 0, d.RawRange(0, len(body), body)),),
    )
    source_captures = d.SourceCaptures(
        source_id,
        tuple(
            d.CaptureWindow(
                window["start"], window["end"], d.canonical(window["capture"])
            )
            for window in windows
        ),
    )
    actual = args()
    actual.update(
        question=original.question,
        capture=capture,
        manifest=d.PlanningUniverse("{}", (source_id,), "bounded_authorized_scan"),
        snapshots=(snapshot,),
        source_captures=(source_captures,),
    )
    return fresh_receipts(actual)


class DependentSemantics(unittest.TestCase):
    def test_captured_dependent_request_resolves_without_inventing_actor_values(self):
        actual = args(rows=DEPENDENT)
        plan = b.reconstruct_staged_plan(**actual)
        self.assertTrue(plan.resolved_request)
        slots = json.loads(plan.value_slots_json)
        self.assertEqual(len(slots), 3)
        self.assertTrue(all(slot["status"] == "UNBOUND_ACTOR_VALUE" for slot in slots))
        self.assertTrue(all(not slot["candidate_uses"] for slot in slots))
        self.assertEqual(
            sum(
                edge["kind"] == "actor_value_dependency"
                for edge in json.loads(plan.edges_json)
            ),
            3,
        )
        self.assertTrue(
            all(
                use.execution_dependencies
                for use in plan.uses
                if use.operation == "request_field_value" and use.parent_id
            )
        )
        self.assertEqual(plan.factual_witnesses, "NOT_ASSESSED")
        self.assertEqual(plan.source_authority, "NOT_ASSESSED")
        self.assertTrue(b.validate_staged_plan(plan.record(), **actual))
        observe("dependent_unbound", actual, plan)

    def test_retained_full_procedure_copy_governor_is_semantically_retained(self):
        actual = onyx_inputs()
        plan = b.reconstruct_staged_plan(**actual)
        self.assertTrue(plan.resolved_request)
        self.assertTrue(plan.uses[0].governors)
        self.assertEqual(plan.uses[0].extent, "whole_requested")
        partial = json.loads(plan.partial_json)
        self.assertTrue(
            any(
                slot["kind"] == "procedure_facet_reference"
                for slot in partial["deferred"]
            )
        )
        self.assertEqual(plan.output_history, "NOT_ASSESSED")
        self.assertEqual(plan.factual_witnesses, "NOT_ASSESSED")
        self.assertTrue(b.validate_staged_plan(plan.record(), **actual))
        self.assertTrue(
            any(
                row.production == "whole_source_copy_requires_output_inventory"
                for row in plan.discharges
            )
        )
        observe("retained_actual_governor", actual, plan)

    def test_unrepresented_or_qualified_child_cannot_be_delegated(self):
        variants = [
            insert(DEPENDENT, 8, "scheduled", "ADJ", "scheduled", "amod", 8),
            insert(DEPENDENT, 8, "two", "NUM", "two", "nummod", 8),
            [
                ("whereabouts", pos, "whereabouts", dep, head)
                if text == "availability"
                else (text, pos, lemma, dep, head)
                for text, pos, lemma, dep, head in DEPENDENT
            ],
        ]
        for index, rows in enumerate(variants):
            with self.subTest(index=index):
                actual = args(rows=rows)
                plan = b.reconstruct_staged_plan(**actual)
                self.assertFalse(plan.resolved_request)
                self.assertEqual(
                    json.loads(plan.graph_json), actual["capture"]["annotation"]
                )
                observe("qualified_child_" + str(index), actual, plan)

    def test_unknown_antecedent_and_competing_actual_catalogues_do_not_bind(self):
        unknown = [
            ("our", pos, "our", dep, head)
            if text == "their"
            else (text, pos, lemma, dep, head)
            for text, pos, lemma, dep, head in DEPENDENT
        ]
        competing = [
            ("List", "VERB", "list", "ROOT", 0),
            ("role", "NOUN", "role", "compound", 2),
            ("incumbents", "NOUN", "incumbent", "dobj", 0),
            ("for", "ADP", "for", "prep", 2),
            ("Cedar", "PROPN", "Cedar", "compound", 5),
            ("inspection", "NOUN", "inspection", "pobj", 3),
            ("and", "CCONJ", "and", "cc", 2),
            ("role", "NOUN", "role", "compound", 8),
            ("incumbents", "NOUN", "incumbent", "conj", 2),
            ("for", "ADP", "for", "prep", 8),
            ("Larch", "PROPN", "Larch", "compound", 11),
            ("inspection", "NOUN", "inspection", "pobj", 9),
            ("and", "CCONJ", "and", "cc", 8),
            ("their", "PRON", "their", "poss", 14),
            ("availability", "NOUN", "availability", "conj", 8),
            (".", "PUNCT", ".", "punct", 0),
        ]
        for index, rows in enumerate((unknown, competing)):
            with self.subTest(index=index):
                actual = args(rows=rows)
                plan = b.reconstruct_staged_plan(**actual)
                self.assertFalse(plan.resolved_request)
                self.assertFalse(
                    any(
                        edge["kind"] == "catalogue_member_value"
                        for edge in json.loads(plan.partial_json)["edges"]
                    )
                )
                observe("unknown_antecedent_" + str(index), actual, plan)

    def test_foreign_child_ids_and_subset_nodes_cannot_certify_delegation(self):
        actual = args(rows=DEPENDENT)
        partial = json.loads(b.reconstruct_staged_plan(**actual).partial_json)
        nodes = deepcopy(partial["nodes"])
        nodes[0]["id"] = "foreign-child"
        closure = request_relation.request_relation_closures(
            actual["question"], actual["capture"], nodes
        )
        self.assertTrue(all(row.status == "UNRESOLVED" for row in closure))
        parent = [node for node in partial["nodes"] if node["kind"] == "role_catalogue"]
        closure = request_relation.request_relation_closures(
            actual["question"], actual["capture"], parent
        )
        self.assertEqual(closure[0].status, "UNRESOLVED")

    def test_per_member_slot_edges_and_execution_dependencies_are_replayed(self):
        actual = args(rows=DEPENDENT)
        plan = b.reconstruct_staged_plan(**actual)
        for field in ("value_slots_json", "edges_json", "uses"):
            with self.subTest(field=field):
                record = plan.record()
                if field == "value_slots_json":
                    values = json.loads(record[field])
                    values[0]["member_binding_id"] = values[1]["member_binding_id"]
                    record[field] = b.canonical(values)
                elif field == "edges_json":
                    edges = json.loads(record[field])
                    edge = next(
                        row for row in edges if row["kind"] == "actor_value_dependency"
                    )
                    edge["value_slot_id"] = "foreign-slot"
                    record[field] = b.canonical(edges)
                else:
                    child = next(
                        row for row in record[field] if row["execution_dependencies"]
                    )
                    child["execution_dependencies"] = []
                self.assertFalse(b.validate_staged_plan(record, **actual))

    def test_unknown_extra_governor_modifier_remains_unresolved(self):
        actual = onyx_inputs()
        rows = [
            (token["text"], token["pos"], token["lemma"], token["dep"], token["head"])
            for token in actual["capture"]["annotation"]["tokens"]
        ]
        head = next(index for index, row in enumerate(rows) if row[2] == "condition")
        rows = insert(rows, head, "imaginary", "ADJ", "imaginary", "amod", head)
        question, changed = capture([rows])
        actual.update(question=question, capture=changed)
        actual = fresh_receipts(actual)
        plan = b.reconstruct_staged_plan(**actual)
        self.assertFalse(plan.resolved_request)
        self.assertIn("imaginary", plan.partial_json)
        observe("unknown_governor_modifier", actual, plan)

    def test_factual_governor_or_units_do_not_resolve_by_whole_copy(self):
        variants = [
            (
                "with emergency overrides",
                [
                    ("with", "ADP", "prep", 3, "with"),
                    ("emergency", "NOUN", "compound", 9, "emergency"),
                    ("overrides", "NOUN", "pobj", 7, "override"),
                ],
            ),
            (
                "with measurements in seconds",
                [
                    ("with", "ADP", "prep", 3, "with"),
                    ("measurements", "NOUN", "pobj", 7, "measurement"),
                    ("in", "ADP", "prep", 8, "in"),
                    ("seconds", "NOUN", "pobj", 9, "second"),
                ],
            ),
        ]
        for index, (tail, spec) in enumerate(variants):
            with self.subTest(index=index):
                old = governor_plan(tail, spec)
                actual = onyx_inputs()
                actual.update(
                    question=old.question,
                    capture=make_capture(json.loads(old.graph_json)),
                )
                actual = fresh_receipts(actual)
                plan = b.reconstruct_staged_plan(**actual)
                self.assertFalse(plan.resolved_request)
                self.assertEqual(json.loads(plan.legacy_component_json), old.record())
                self.assertEqual(plan.factual_witnesses, "NOT_ASSESSED")
                observe("factual_governor_" + str(index), actual, plan)
