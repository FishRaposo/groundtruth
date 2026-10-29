"""Bounded UNITONLY semantics/transport checks; no parser/model inference."""

import json
import unittest
from dataclasses import asdict

from app.services import linguistic_requirements as old
from app.services import planning_support as p
from app.services import staged_plan_binding as b
from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS, NLI

from .fixtures_request import ACTORS, DEPENDENT, FIELD, LABELS
from .fixtures_source import (
    CAT,
    COND,
    EXTERNAL,
    NAME,
    UNKNOWN,
    capture,
    source,
    universe,
)

EXAMPLES = {}


def insert(rows, at, word, pos, lemma, dep, head):
    out = [(w, x, base, d, h + 1 if h >= at else h) for w, x, base, d, h in rows]
    out.insert(at, (word, pos, lemma, dep, head + 1 if head >= at else head))
    return out


def args(rows=LABELS, groups=(NAME, CAT), extra=(), negative=False, multi=None):
    question, cap = capture(multi if multi is not None else [rows])
    pairs = [source(list(groups), doc="UNITONLY-main"), *extra]
    snapshots = tuple(s for s, _ in pairs)
    captures = tuple(c for _, c in pairs)
    result = {
        "question": question,
        "capture": cap,
        "manifest": universe(snapshots),
        "snapshots": snapshots,
        "source_captures": captures,
        "support_metadata": {
            "mode": "local_nli",
            "model": NLI.model,
            "revision": NLI.revision,
            "license": NLI.license,
            "minimum_entailment_margin": 2,
            "max_pair_tokens": MAX_PAIR_TOKENS,
            "batch_size": BATCH_SIZE,
            "device": "cpu",
            "score_semantics": (
                "raw contradiction/entailment/neutral logits; uncalibrated"
            ),
            "readiness": "ready",
        },
        "sql_read_set_json": b.canonical(
            {
                "contract": "request-planning-publications-v1",
                "selection_mode": "all_authorized_publications_v1",
                "fixture": "UNITONLY",
            }
        ),
    }
    prepared = p.prepare_planning_assertions(**result)
    body = b.canonical(
        {
            "label": "neutral" if negative else "entailment",
            "logits": [-3, 0, 3] if negative else [-3, 3, 0],
            "entailment_margin": -3 if negative else 3,
            "supported": not negative,
            "pair_tokens": 40,
        }
    )
    result["observations"] = tuple(
        p.NliObservation(
            a.id, "UNITONLY-" + str(i), a.pair, prepared.support_metadata_json, body
        )
        for i, a in enumerate(prepared.assertions)
    )
    result["actual_executions"] = tuple(
        p.NliExecution(
            "UNITONLY-" + str(i),
            a.id,
            a.pair,
            prepared.support_metadata_json,
            body,
            40,
            "UNITONLY",
        )
        for i, a in enumerate(prepared.assertions)
    )
    return result


def run(name=None, **kw):
    actual = args(**kw)
    plan = b.reconstruct_staged_plan(**actual)
    if name:
        EXAMPLES[name] = {
            "plan": plan.record(),
            "inputs": {
                k: asdict(v)
                if hasattr(v, "__dataclass_fields__")
                else [asdict(x) for x in v]
                if isinstance(v, tuple) and v and hasattr(v[0], "__dataclass_fields__")
                else v
                for k, v in actual.items()
            },
        }
    return plan, actual


class Binding(unittest.TestCase):
    def test_known_field_is_genuinely_resolved_original_v2_component(self):
        plan, a = run("known_field", rows=FIELD)
        self.assertTrue(plan.resolved_request)
        legacy = old.plan_request(a["question"], a["capture"])
        self.assertTrue(legacy.resolved_request)
        self.assertEqual(plan.requirements, legacy.requirements)
        self.assertEqual(plan.uses[0].original, legacy.uses[0].original)
        self.assertEqual(json.loads(plan.legacy_component_json), legacy.record())
        self.assertTrue(b.validate_staged_plan(plan.record(), **a))

    def test_supported_closed_catalogue_resolves_every_literal_child(self):
        plan, a = run("closed_catalogue")
        self.assertTrue(plan.resolved_request)
        self.assertFalse(old.plan_request(a["question"], a["capture"]).resolved_request)
        self.assertEqual(
            [r.attribute for r in plan.requirements if r.kind == "role_label"],
            ["coordinator", "observer", "recorder"],
        )
        self.assertEqual(len(plan.requirements), 4)
        self.assertTrue(
            all(u.source_uses_json != "[]" for u in plan.uses if u.parent_id)
        )
        self.assertTrue(b.validate_staged_plan(plan.record(), **a))

    def test_resolved_semantics_does_not_assess_facts_authority_or_output(self):
        plan, _ = run()
        for name in [
            "factual_witnesses",
            "answer_fact_nli",
            "source_authority",
            "sql_authorization_currentness",
            "catalogue_completeness_policy",
            "output_history",
            "support_or_permissions",
        ]:
            self.assertEqual(getattr(plan, name), "NOT_ASSESSED")

    def test_incumbent_slots_are_typed_execution_dependencies_without_values(self):
        plan, _ = run("incumbent_slots", rows=ACTORS)
        self.assertTrue(plan.resolved_request)
        slots = json.loads(plan.value_slots_json)
        self.assertEqual(len(slots), 3)
        self.assertTrue(all(s["status"] == "UNBOUND_ACTOR_VALUE" for s in slots))
        self.assertTrue(all(u.value_slot_id for u in plan.uses if u.parent_id))
        self.assertFalse(json.loads(plan.planning_support_json)["accepted"])

    def test_mixed_known_field_and_catalogue_preserve_both_original_requests(self):
        plan, a = run("mixed", multi=[FIELD, LABELS])
        self.assertTrue(plan.resolved_request)
        self.assertEqual(sum(r.kind == "quantity" for r in plan.requirements), 1)
        self.assertEqual(sum(r.kind == "role_label" for r in plan.requirements), 3)
        self.assertEqual(len({u.node_id for u in plan.uses}), 2)
        self.assertEqual(len(json.loads(plan.partial_json)["nodes"]), 2)
        self.assertTrue(b.validate_staged_plan(plan.record(), **a))

    def test_qualified_requested_set_remains_unresolved(self):
        plan, _ = run(rows=insert(LABELS, 1, "retired", "ADJ", "retired", "amod", 2))
        self.assertFalse(plan.resolved_request)
        self.assertIn("retired", plan.partial_json)

    def test_quantity_on_requested_set_remains_explicit(self):
        plan, _ = run(rows=insert(LABELS, 1, "two", "NUM", "two", "nummod", 2))
        self.assertFalse(plan.resolved_request)
        self.assertIn("two", plan.partial_json)

    def test_conditioned_request_cannot_become_unconditional_catalogue(self):
        rows = LABELS[:-1] + [
            ("unless", "SCONJ", "unless", "mark", 8),
            ("permit", "NOUN", "permit", "nsubj", 8),
            ("applies", "VERB", "apply", "advcl", 0),
            (".", "PUNCT", ".", "punct", 0),
        ]
        plan, _ = run("conditioned_request", rows=rows)
        self.assertFalse(plan.resolved_request)
        self.assertIn("unless", plan.partial_json)
        self.assertTrue(
            any(u.conditions or "unless" in u.features_json for u in plan.uses)
        )

    def test_conditioned_source_catalogue_cannot_discharge_membership(self):
        plan, _ = run(groups=(NAME, COND))
        self.assertFalse(plan.resolved_request)

    def test_ambiguous_source_catalogues_remain_blockers(self):
        plan, _ = run(extra=(source([CAT], doc="UNITONLY-rival"),))
        self.assertFalse(plan.resolved_request)

    def test_negative_planning_assessment_cannot_resolve_catalogue(self):
        plan, _ = run(negative=True)
        self.assertFalse(plan.resolved_request)

    def test_unknown_source_content_cannot_certify_closed_catalogue(self):
        plan, _ = run(groups=(NAME, CAT, UNKNOWN))
        self.assertFalse(plan.resolved_request)

    def test_external_instruction_reference_remains_explicitly_unresolved(self):
        plan, _ = run(groups=(NAME, CAT, EXTERNAL))
        self.assertFalse(plan.resolved_request)
        self.assertIn("external", plan.effective_candidate_json)

    def test_actor_dependencies_retain_edges_and_unbound_execution_slots(self):
        plan, _ = run("dependent", rows=DEPENDENT)
        edges = json.loads(plan.edges_json)
        self.assertEqual(sum(e["kind"] == "actor_value_dependency" for e in edges), 3)
        self.assertEqual(len(json.loads(plan.value_slots_json)), 3)
        self.assertTrue(
            all(
                e["value_slot_id"]
                for e in edges
                if e["kind"] == "actor_value_dependency"
            )
        )
        self.assertTrue(plan.resolved_request)
        self.assertTrue(
            all(
                slot["status"] == "UNBOUND_ACTOR_VALUE"
                for slot in json.loads(plan.value_slots_json)
            )
        )
        self.assertEqual(plan.factual_witnesses, "NOT_ASSESSED")
        self.assertEqual(plan.support_or_permissions, "NOT_ASSESSED")
        self.assertFalse(json.loads(plan.planning_support_json)["accepted"])

    def test_record_cannot_delete_child_or_promote_an_external_gate(self):
        plan, a = run()
        record = plan.record()
        record["requirements"].pop()
        self.assertFalse(b.validate_staged_plan(record, **a))
        record = plan.record()
        record["sql_authorization_currentness"] = "AUTHORIZED"
        self.assertFalse(b.validate_staged_plan(record, **a))

    def test_graph_range_features_or_obligation_mutation_refuses(self):
        plan, a = run()
        for field in [
            "graph_json",
            "partial_json",
            "read_set_json",
            "effective_candidate_json",
        ]:
            with self.subTest(field=field):
                record = plan.record()
                record[field] = "{}"
                self.assertFalse(b.validate_staged_plan(record, **a))
        record = plan.record()
        record["uses"][0]["original"]["start"] += 1
        self.assertFalse(b.validate_staged_plan(record, **a))
        record = plan.record()
        record["discharges"] = []
        self.assertFalse(b.validate_staged_plan(record, **a))

    def test_whole_scope_bridge_and_noncited_sources_bind_reconstruction(self):
        plan, a = run()
        bridge = json.loads(plan.scope_bridge_json)
        self.assertTrue(
            b.validate_staged_plan(plan.record(), **a, scope_bridge_record=bridge)
        )
        bridge["excluded"] = ["UNITONLY-main"]
        with self.assertRaises(ValueError):
            b.reconstruct_staged_plan(**a, scope_bridge_record=bridge)

    def test_old_observations_cannot_replay_against_changed_immutable_source(self):
        plan, a = run()
        changed = args(groups=(NAME, CAT, CAT))
        changed["observations"] = a["observations"]
        changed["actual_executions"] = a["actual_executions"]
        with self.assertRaises(ValueError):
            b.reconstruct_staged_plan(**changed)

    def test_budget_is_exact_and_never_truncates(self):
        a = args()
        for limit in [True, 0, 65]:
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    b.reconstruct_staged_plan(**a, max_requirements=limit)
        with self.assertRaises(ValueError):
            b.reconstruct_staged_plan(**a, max_requirements=3)

    def test_plan_is_detached_and_not_an_old_v2_record(self):
        plan, a = run()
        record = plan.record()
        record["uses"][0]["features_json"] = "{}"
        self.assertNotEqual(record, plan.record())
        self.assertFalse(
            old.validate_request_plan(
                plan.record(), question=a["question"], capture=a["capture"]
            )
        )

    def test_callbacks_and_subset_traces_do_not_replace_observations(self):
        a = args()
        a["observations"] = (lambda: True,)
        with self.assertRaises(ValueError):
            b.reconstruct_staged_plan(**a)

    def test_original_condition_and_unit_fields_equal_recomputed_known_components(self):
        rows = FIELD[:-1] + [
            ("in", "ADP", "in", "prep", 1),
            ("units", "NOUN", "unit", "pobj", 5),
            (".", "PUNCT", ".", "punct", 0),
        ]
        plan, a = run(rows=rows)
        legacy = old.plan_request(a["question"], a["capture"])
        self.assertEqual(json.loads(plan.legacy_component_json), legacy.record())
        self.assertIn("units", plan.partial_json)

    def test_known_full_procedure_has_original_extent_and_common_use_fields(self):
        rows = [
            ("Give", "VERB", "give", "ROOT", 0),
            ("full", "ADJ", "full", "amod", 2),
            ("routine", "NOUN", "routine", "dobj", 0),
            ("for", "ADP", "for", "prep", 2),
            ("Cedar", "PROPN", "Cedar", "compound", 5),
            ("inspection", "NOUN", "inspection", "pobj", 3),
            (".", "PUNCT", ".", "punct", 0),
        ]
        plan, a = run("known_full_procedure", rows=rows)
        self.assertTrue(plan.resolved_request)
        self.assertEqual(plan.requirements[0].kind, "procedure")
        self.assertEqual(plan.uses[0].extent, "whole_requested")
        self.assertEqual(json.loads(plan.graph_json), a["capture"]["annotation"])
        self.assertEqual(
            plan.uses[0].conditions,
            old.plan_request(a["question"], a["capture"]).uses[0].conditions,
        )

    def test_request_negative_premise_is_not_assumed_true(self):
        rows = LABELS[:-1] + [
            ("if", "SCONJ", "if", "mark", 10),
            ("no", "DET", "no", "det", 8),
            ("override", "NOUN", "override", "nsubjpass", 10),
            ("was", "AUX", "be", "auxpass", 10),
            ("issued", "VERB", "issue", "advcl", 0),
            (".", "PUNCT", ".", "punct", 0),
        ]
        plan, _ = run("negative_premise", rows=rows)
        self.assertFalse(plan.resolved_request)
        self.assertIn("no override", plan.question)
        self.assertEqual(plan.factual_witnesses, "NOT_ASSESSED")

    def test_ambiguous_temporal_attribute_remains_semantically_unresolved(self):
        rows = [
            ("time", pos, "time", dep, head)
            if text == "quantity"
            else (text, pos, lemma, dep, head)
            for text, pos, lemma, dep, head in FIELD
        ]
        plan, _ = run("ambiguous_time", rows=rows)
        self.assertFalse(plan.resolved_request)
        self.assertTrue(plan.unresolved)
