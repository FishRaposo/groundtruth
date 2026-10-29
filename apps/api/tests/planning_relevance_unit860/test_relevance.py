"""Bounded relevance contrast controls; no inference or SQL."""

import json
import unittest
from dataclasses import replace

from app.services import planning_declarations as d
from app.services import staged_role_evidence as role
from app.services.planning_relevance import (
    reconstruct_candidate_selection,
    validate_candidate_selection,
)
from app.services.staged_request import compile_request

from tests.staged_plan_unit837.fixtures_request import LABELS
from tests.staged_plan_unit837.fixtures_source import (
    ASSIGN,
    CAT,
    EXTERNAL,
    NAME,
    UNKNOWN,
    source,
)
from tests.staged_role_unit850.fixtures_role import role_receipts

from .fixtures import bridge, prepare, raw, retained_inputs, routine

EXAMPLES = {}


def selection(actual, record=None):
    return reconstruct_candidate_selection(
        compile_request(actual["question"], actual["capture"]),
        actual["manifest"],
        actual["snapshots"],
        actual["source_captures"],
        scope_bridge_record=bridge(actual) if record is None else record,
    )


class CandidateRelevance(unittest.TestCase):
    def test_default_conservative_and_explicit_bridge_are_distinct(self):
        actual = raw()
        conservative = prepare(actual, opt_in=False)
        self.assertTrue(conservative.pending)
        self.assertNotIn(
            "candidate_selection_json", json.loads(conservative.effective_plan_json)
        )
        selected = prepare(actual)
        self.assertFalse(selected.pending)
        self.assertTrue(selected.assertions)
        ledger = json.loads(
            json.loads(selected.effective_plan_json)["candidate_selection_json"]
        )
        original = d.declaration_inventory(
            actual["manifest"], actual["snapshots"], actual["source_captures"]
        )
        self.assertEqual(
            json.loads(selected.effective_plan_json)["inventory_json"],
            d.canonical(original.record()),
        )
        self.assertEqual(
            ledger["read_set_json"], d.canonical(original.read_set.record())
        )
        self.assertTrue(ledger["deferred_blockers"])
        self.assertEqual(
            {entry["source"]["document_id"] for entry in ledger["deferred_blockers"]},
            set(bridge(actual)["excluded"]),
        )
        EXAMPLES["explicit_candidate_only_UNITONLY"] = {
            "assertions": selected.record(),
            "ledger": ledger,
        }

    def test_no_actual_exclusions_preserves_completed_record_shape(self):
        actual = raw(extra=())
        self.assertEqual(bridge(actual)["excluded"], [])
        self.assertEqual(
            prepare(actual, opt_in=False).record(), prepare(actual).record()
        )

    def test_forged_exclusion_flags_and_missing_source_receipts_are_refused(self):
        actual = raw(extra=(routine("Cedar"),))
        forged = bridge(actual)
        self.assertEqual(forged["excluded"], [])
        forged["excluded"] = [actual["snapshots"][1].identity.document_id]
        forged["retained"] = [actual["snapshots"][0].identity.document_id]
        with self.assertRaises(ValueError):
            selection(actual, forged)
        actual = raw()
        proof = selection(actual).record()
        proof["active_blockers"] = []
        self.assertFalse(
            validate_candidate_selection(
                proof,
                compile_request(actual["question"], actual["capture"]),
                actual["manifest"],
                actual["snapshots"],
                actual["source_captures"],
                scope_bridge_record=bridge(actual),
            )
        )

    def test_same_reason_owned_by_retained_source_is_not_removed(self):
        actual = raw(extra=(routine(), source([UNKNOWN], doc="UNITONLY-global")))
        selected = selection(actual)
        self.assertTrue(selected.used)
        self.assertIn(
            "unknown_source_grammar",
            {entry.reason for entry in selected.deferred_blockers},
        )
        active = [
            entry
            for entry in selected.active_blockers
            if entry.reason == "unknown_source_grammar"
        ]
        self.assertTrue(active)
        self.assertEqual(
            {entry.source.document_id for entry in active},
            {actual["snapshots"][2].identity.document_id},
        )
        self.assertTrue(prepare(actual).pending)
        EXAMPLES["same_reason_retained_UNITONLY"] = selected.record()

    def test_same_namespace_and_qualified_other_namespace_remain_candidates(self):
        for extra in (routine("Cedar"), routine(qualified=True)):
            with self.subTest(body=extra[0].body):
                actual = raw(extra=(extra,))
                self.assertEqual(bridge(actual)["excluded"], [])
                self.assertTrue(prepare(actual).pending)

    def test_unavailable_publication_and_ranked_universe_never_disappear(self):
        actual = raw()
        missing = replace(
            actual["snapshots"][0].identity, document_id="UNITONLY-missing"
        )
        actual["manifest"] = replace(
            actual["manifest"], publications=(*actual["manifest"].publications, missing)
        )
        selected = selection(actual)
        self.assertTrue(selected.used)
        self.assertTrue(
            any(
                entry.reason == "uninspectable_selected_publication"
                for entry in selected.active_blockers
            )
        )
        self.assertTrue(prepare(actual).pending)
        self.assertEqual(
            len(json.loads(selected.read_set_json)["missing_publications"]), 1
        )
        ranked = raw()
        ranked["manifest"] = replace(ranked["manifest"], selection_mode="ranked_subset")
        self.assertFalse(selection(ranked).used)
        self.assertTrue(prepare(ranked).pending)

    def test_retained_external_reference_stays_unresolved_even_unique_target(self):
        target, cap = routine()
        target = replace(target, title="Note Amber")
        actual = raw(extra=((target, cap),), groups=(NAME, CAT, ASSIGN, EXTERNAL))
        ledger = selection(actual)
        references = [
            row
            for row in d.declaration_inventory(
                actual["manifest"], actual["snapshots"], actual["source_captures"]
            ).declarations
            if row.kind == "external_instruction_target"
        ]
        self.assertTrue(
            any(
                len(json.loads(row.payload_json)["candidate_document_ids"]) == 1
                for row in references
            )
        )
        self.assertTrue(
            any(
                row.reason == "external_instruction_targets_initially_unresolved"
                and row.source.document_id
                == actual["snapshots"][0].identity.document_id
                for row in ledger.active_blockers
            )
        )
        self.assertTrue(prepare(actual).pending)

    def test_original_condition_or_source_condition_cannot_get_exclusion(self):
        conditional = LABELS[:-1] + [
            ("if", "SCONJ", "if", "mark", 8),
            ("permit", "NOUN", "permit", "nsubj", 8),
            ("applies", "VERB", "apply", "advcl", 0),
            (".", "PUNCT", ".", "punct", 0),
        ]
        actual = raw(rows=conditional)
        self.assertEqual(bridge(actual)["excluded"], [])
        self.assertTrue(prepare(actual).pending)
        from tests.staged_plan_unit837.fixtures_source import COND

        actual = raw(groups=(NAME, CAT, COND))
        self.assertTrue(prepare(actual).pending)

    def test_full_actor_lineage_and_set_proof_keep_other_document(self):
        actual = raw()
        inputs, plan = retained_inputs(actual)
        self.assertTrue(plan.resolved_request)
        parent = next(row for row in plan.requirements if row.kind == "role_catalogue")
        prepared = role.prepare_role_evidence(**inputs, requirement_id=parent.id)
        observations, executions = role_receipts(prepared)
        evidence = role.reconstruct_role_evidence(
            **inputs,
            requirement_id=parent.id,
            proposal_id=prepared.proposals[0].proposal_id,
            observations=observations,
            actual_executions=executions,
        )
        self.assertTrue(evidence.supported)
        self.assertEqual(evidence.facts, ())
        self.assertIsNotNone(evidence.set_proof)
        self.assertEqual(
            len(json.loads(evidence.prepared.read_set_json)["snapshot_reads"]), 2
        )
        self.assertEqual(
            len(json.loads(evidence.prepared.planning_inputs_json)["snapshots"]), 2
        )

    def test_opposing_retained_assignment_still_blocks_role_proof(self):
        rival = [
            ("Juniper", pos, "Juniper", dep, head)
            if word == "Rowan"
            else (word, pos, lemma, dep, head)
            for word, pos, lemma, dep, head in ASSIGN
        ]
        actual = raw(extra=(routine(), source([rival], doc="UNITONLY-opposing")))
        inputs, plan = retained_inputs(actual)
        parent = next(row for row in plan.requirements if row.kind == "role_catalogue")
        with self.assertRaisesRegex(ValueError, "Ambiguous or opposing"):
            role.prepare_role_evidence(**inputs, requirement_id=parent.id)
