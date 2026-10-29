"""Role pattern and actual support-service UNITONLY backend integration."""

import asyncio
import json
import unittest
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from app.config import Settings
from app.services import answer_support
from app.services import staged_role_evidence as role
from app.services.staged_planning_runtime import RuntimeLimits
from app.support_catalog import NLI

from tests.staged_plan_unit837.fixtures_request import ACTORS
from tests.staged_plan_unit837.fixtures_source import ASSIGN, CAT, NAME, source
from tests.staged_plan_unit837.test_binding import insert

from .fixtures_role import (
    actor_inputs,
    role_inputs,
    role_receipts,
    select,
    split_source,
)

EXAMPLES = {}


def checked(actual, **kwargs):
    prepared = role.prepare_role_evidence(**actual)
    observations, executions = role_receipts(prepared, **kwargs)
    replay = {
        **actual,
        "proposal_id": prepared.proposals[0].proposal_id,
        "observations": observations,
        "actual_executions": executions,
    }
    return role.reconstruct_role_evidence(**replay), replay


def config():
    return Settings(
        _env_file=None,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        ANSWER_SUPPORT_MODE="local_nli",
        SUPPORT_MODEL_REVISION=NLI.revision,
        SUPPORT_MODEL_PATH="UNITONLY850-no-assets",
        SUPPORT_MIN_MARGIN=2,
    )


class Backend:
    def __init__(self, *, whole=None, tokens=40):
        self.whole, self.tokens = whole, tokens
        self.token_calls, self.logit_calls = [], []

    def token_lengths(self, pairs):
        self.token_calls.append(tuple(pairs))
        return [self.tokens] * len(pairs)

    def logits(self, pairs):
        self.logit_calls.append(tuple(pairs))
        return [
            [-3.0, 0.0, 3.0] if pair.premise == self.whole else [-3.0, 3.0, 0.0]
            for pair in pairs
        ]


def backend_context(backend):
    stack = ExitStack()
    service = answer_support.support_service
    for name in ("_backend", "_identity", "_error_identity"):
        stack.enter_context(patch.object(service, name, None))
    stack.enter_context(
        patch.object(answer_support, "validate_assets", side_effect=lambda path: path)
    )
    stack.enter_context(
        patch.object(answer_support, "_load_backend", return_value=backend)
    )
    return stack


class RolePreparation(unittest.TestCase):
    def test_declared_set_parent_is_typed_and_not_a_scalar(self):
        inputs, plan = role_inputs()
        prepared = role.prepare_role_evidence(**select(inputs, plan, "role_catalogue"))
        self.assertIsNotNone(prepared)
        self.assertEqual(prepared.bound_requirement.kind, "role_catalogue")
        self.assertEqual(
            [member.literal.text for member in prepared.members],
            ["coordinator", "observer", "recorder"],
        )
        self.assertIsNone(prepared.candidate_value)
        self.assertTrue(prepared.proposals)
        self.assertTrue(prepared.checks)

    def test_set_replay_returns_set_proof_and_no_scalar_fact(self):
        inputs, plan = role_inputs()
        evidence, replay = checked(select(inputs, plan, "role_catalogue"))
        self.assertTrue(evidence.supported)
        self.assertEqual(evidence.facts, ())
        self.assertIsNotNone(evidence.set_proof)
        self.assertEqual(evidence.set_proof.completeness, "SOURCE_DECLARATION_ONLY")
        self.assertEqual(len(evidence.set_proof.child_requirement_ids), 3)
        self.assertTrue(role.validate_role_evidence(evidence.record(), **replay))
        EXAMPLES["declared_set"] = evidence.record()

    def test_label_child_preserves_kind_source_range_and_normal_proposal(self):
        inputs, plan = role_inputs()
        evidence, replay = checked(select(inputs, plan, "role_label"))
        fact = evidence.facts[0]
        self.assertEqual(fact.kind, "role_label")
        self.assertEqual(fact.value, "coordinator")
        self.assertIsNone(fact.value_slot_id)
        body = inputs["authoritative_snapshots"][fact.source_identity.document_id][
            "body"
        ]
        self.assertEqual(
            body[fact.value_range.start : fact.value_range.end], fact.value
        )
        self.assertEqual(evidence.proposals[0].document_start, fact.value_range.start)
        self.assertEqual(evidence.proposals[0].origin, "source_pattern")
        self.assertTrue(role.validate_role_evidence(evidence.record(), **replay))
        EXAMPLES["literal_label"] = evidence.record()

    def test_actor_hypotheses_reuse805_and_all_checks_have_whole_pair(self):
        actual = actor_inputs()
        evidence, replay = checked(actual)
        fact = evidence.facts[0]
        self.assertEqual(fact.kind, "role_assignment")
        self.assertEqual(fact.value, "Rowan")
        self.assertEqual(fact.role_label.text, "coordinator")
        for check in evidence.prepared.checks:
            lineage = json.loads(check.request_relation_json)["source_assertion"]
            self.assertEqual(check.pair.hypothesis, lineage["pair"]["hypothesis"])
            if check.kind == "staged_role_whole_body":
                self.assertEqual(
                    check.pair.premise,
                    actual["authoritative_snapshots"][
                        check.source_identity.document_id
                    ]["body"],
                )
        self.assertEqual(
            sum(row.kind == "staged_role_local" for row in evidence.prepared.checks),
            sum(
                row.kind == "staged_role_whole_body" for row in evidence.prepared.checks
            ),
        )
        self.assertTrue(role.validate_role_evidence(evidence.record(), **replay))
        EXAMPLES["supported_actor_UNITONLY"] = evidence.record()

    def test_arbitrary_role_label_and_full_actor_compound_are_not_projected(self):
        catalogue = [
            ("adjudicator", pos, "adjudicator", dep, head)
            if text == "coordinator"
            else (text, pos, lemma, dep, head)
            for text, pos, lemma, dep, head in CAT
        ]
        assignment = [
            ("adjudicator", pos, "adjudicator", dep, head)
            if text == "coordinator"
            else ("Meadow", pos, "Meadow", dep, head)
            if text == "Rowan"
            else (text, pos, lemma, dep, head)
            for text, pos, lemma, dep, head in ASSIGN
        ]
        assignment = insert(assignment, 7, "Rowan", "PROPN", "Rowan", "compound", 7)
        inputs, plan = role_inputs(rows=ACTORS, groups=(NAME, catalogue, assignment))
        evidence, _ = checked(select(inputs, plan, "role_assignment"))
        self.assertEqual(evidence.facts[0].value, "Rowan Meadow")
        self.assertEqual(evidence.facts[0].role_label.text, "adjudicator")
        self.assertEqual(evidence.bound_requirement.kind, "role_assignment")

    def test_missing_actor_does_not_guess_a_value(self):
        inputs, plan = role_inputs(rows=ACTORS, groups=(NAME, CAT))
        self.assertTrue(plan.resolved_request)
        with self.assertRaisesRegex(ValueError, "One actual source actor"):
            role.prepare_role_evidence(**select(inputs, plan, "role_assignment"))

    def test_opposing_assignment_is_retained_and_refused(self):
        rival = [
            ("Juniper", pos, "Juniper", dep, head)
            if text == "Rowan"
            else (text, pos, lemma, dep, head)
            for text, pos, lemma, dep, head in ASSIGN
        ]
        inputs, plan = role_inputs(
            rows=ACTORS, extra=(source([rival], doc="UNITONLY-opponent"),)
        )
        with self.assertRaisesRegex(ValueError, "Ambiguous or opposing"):
            role.prepare_role_evidence(**select(inputs, plan, "role_assignment"))

    def test_unlisted_relevant_assignment_cannot_be_pruned_for_set_proof(self):
        outsider = [
            ("auditor", pos, "auditor", dep, head)
            if text == "coordinator"
            else (text, pos, lemma, dep, head)
            for text, pos, lemma, dep, head in ASSIGN
        ]
        inputs, plan = role_inputs(groups=(NAME, CAT, outsider))
        with self.assertRaisesRegex(ValueError, "unlisted relevant"):
            role.prepare_role_evidence(**select(inputs, plan, "role_catalogue"))

    def test_unknown_actor_qualification_remains_blocked(self):
        qualified = insert(ASSIGN, 7, "former", "ADJ", "former", "amod", 7)
        inputs, plan = role_inputs(rows=ACTORS, groups=(NAME, CAT, qualified))
        identifier = actor_inputs()["requirement_id"]
        self.assertFalse(plan.resolved_request)
        with self.assertRaises(ValueError):
            role.prepare_role_evidence(**{**inputs, "requirement_id": identifier})

    def test_cross_chunk_local_unit_refuses_instead_of_truncating(self):
        actual = actor_inputs()
        doc = next(iter(actual["authoritative_snapshots"]))
        body = actual["authoritative_snapshots"][doc]["body"]
        changed = split_source(actual, body.rindex("coordinator") + 2)
        with self.assertRaisesRegex(ValueError, "cross-chunk"):
            role.prepare_role_evidence(**changed)


class RoleReplayTampering(unittest.TestCase):
    def test_local_entailment_without_whole_support_binds_no_actor(self):
        evidence, _ = checked(actor_inputs(), neutral_whole=True)
        self.assertFalse(evidence.supported)
        self.assertEqual(evidence.facts, ())
        self.assertIsNone(evidence.set_proof)

    def test_missing_whole_execution_or_duplicate_local_is_not_a_receipt(self):
        evidence, actual = checked(actor_inputs())
        local = tuple(
            row
            for row in actual["actual_executions"]
            if next(
                check.kind
                for check in evidence.prepared.checks
                if check.id == row.assertion_id
            )
            == "staged_role_local"
        )
        with self.assertRaisesRegex(ValueError, "inventory"):
            role.reconstruct_role_evidence(**{**actual, "actual_executions": local})
        traces = actual["actual_executions"]
        with self.assertRaises(ValueError):
            role.reconstruct_role_evidence(
                **{**actual, "actual_executions": (traces[0], *traces[:-1])}
            )

    def test_coherent_hypothesis_rewrite_cannot_change_role_semantics(self):
        _, actual = checked(actor_inputs())
        trace = actual["actual_executions"][0]
        observed = actual["observations"][0]
        pair = replace(trace.pair, hypothesis="Rowan is an owner without any scope.")
        with self.assertRaises(ValueError):
            role.reconstruct_role_evidence(
                **{
                    **actual,
                    "actual_executions": (
                        replace(trace, pair=pair),
                        *actual["actual_executions"][1:],
                    ),
                    "observations": (
                        replace(observed, pair=pair),
                        *actual["observations"][1:],
                    ),
                }
            )

    def test_model_or_token_receipts_cannot_override_existing_validator(self):
        _, actual = checked(actor_inputs())
        trace, observed = actual["actual_executions"][0], actual["observations"][0]
        metadata = json.loads(trace.support_metadata_json)
        metadata["revision"] = "foreign-revision"
        raw = role.canonical(metadata)
        with self.assertRaises(ValueError):
            role.reconstruct_role_evidence(
                **{
                    **actual,
                    "actual_executions": (
                        replace(trace, support_metadata_json=raw),
                        *actual["actual_executions"][1:],
                    ),
                    "observations": (
                        replace(observed, support_metadata_json=raw),
                        *actual["observations"][1:],
                    ),
                }
            )
        with self.assertRaisesRegex(ValueError, "token"):
            role.reconstruct_role_evidence(
                **{
                    **actual,
                    "actual_executions": (
                        replace(trace, pair_tokens=41),
                        *actual["actual_executions"][1:],
                    ),
                }
            )

    def test_value_slot_proposal_offsets_or_source_body_mutation_cannot_replay(self):
        evidence, actual = checked(actor_inputs())
        for field in ("value", "value_slot_id", "source_offset"):
            with self.subTest(field=field):
                record = evidence.record()
                if field == "source_offset":
                    record["prepared"]["proposals"][0]["document_start"] += 1
                else:
                    record["facts"][0][field] = "foreign"
                self.assertFalse(role.validate_role_evidence(record, **actual))
        changed = deepcopy(actual)
        doc = next(iter(changed["authoritative_snapshots"]))
        changed["authoritative_snapshots"][doc]["body"] += " changed"
        with self.assertRaises(ValueError):
            role.reconstruct_role_evidence(**changed)


class RoleRuntime(unittest.IsolatedAsyncioTestCase):
    async def test_actual_service_catalogue_remains_a_typed_set(self):
        inputs, plan = role_inputs()
        backend = Backend()
        with backend_context(backend):
            evidence = await role.assess_role_evidence(
                config(),
                **select(inputs, plan, "role_catalogue"),
                execution_capture_kind="UNITONLY",
            )
        self.assertTrue(evidence.supported)
        self.assertIsNotNone(evidence.set_proof)
        self.assertEqual(evidence.facts, ())
        self.assertEqual(len(evidence.actual_executions), 10)
        self.assertEqual(sum(len(batch) for batch in backend.logit_calls), 10)
        EXAMPLES["runtime_declared_set_UNITONLY"] = evidence.record()

    async def test_actual_returned_inventory_mismatch_is_not_evidence(self):
        actual = actor_inputs()
        metadata = {
            **json.loads(role.prepare_role_evidence(**actual).support_metadata_json),
            "readiness": "ready",
        }

        async def short(pairs, selected):
            return [
                answer_support.SupportAssessment(
                    "entailment", (-3.0, 3.0, 0.0), 3.0, True, 40
                )
            ]

        with (
            patch.object(
                answer_support.support_service, "metadata", return_value=metadata
            ),
            patch.object(answer_support.support_service, "assess", short),
        ):
            with self.assertRaises(ValueError) as caught:
                await role.assess_role_evidence(
                    config(), **actual, execution_capture_kind="UNITONLY"
                )
        receipt = json.loads(caught.exception.role_evidence_json)
        self.assertEqual(receipt["stage"], "assess")
        self.assertEqual(receipt["returned_decision_count"], 1)
        self.assertEqual(receipt["actual_executions"], [])

    async def test_actual_service_binds_actor_only_after_local_and_whole_body(self):
        class Backend:
            def token_lengths(self, pairs):
                return [40] * len(pairs)

            def logits(self, pairs):
                return [[-3.0, 3.0, 0.0] for _ in pairs]

        service = answer_support.support_service
        config = Settings(
            _env_file=None,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            ANSWER_SUPPORT_MODE="local_nli",
            SUPPORT_MODEL_REVISION=NLI.revision,
            SUPPORT_MODEL_PATH="UNITONLY850-no-assets",
            SUPPORT_MIN_MARGIN=2,
        )
        with (
            patch.object(service, "_backend", None),
            patch.object(service, "_identity", None),
            patch.object(service, "_error_identity", None),
            patch.object(
                answer_support, "validate_assets", side_effect=lambda path: path
            ),
            patch.object(answer_support, "_load_backend", return_value=Backend()),
        ):
            evidence = await role.assess_role_evidence(
                config, **actor_inputs(), execution_capture_kind="UNITONLY"
            )
        self.assertIsNotNone(evidence)
        self.assertTrue(evidence.supported)
        self.assertEqual(evidence.bound_requirement.kind, "role_assignment")
        self.assertEqual(evidence.facts[0].value, "Rowan")
        self.assertTrue(evidence.facts[0].value_slot_id)
        self.assertTrue(evidence.actual_executions)
        self.assertTrue(
            all(row.capture_kind == "UNITONLY" for row in evidence.actual_executions)
        )

    async def test_whole_body_neutral_returns_no_supported_actor(self):
        actual = actor_inputs()
        body = next(iter(actual["authoritative_snapshots"].values()))["body"]
        with backend_context(Backend(whole=body)):
            evidence = await role.assess_role_evidence(
                config(), **actual, execution_capture_kind="UNITONLY"
            )
        self.assertFalse(evidence.supported)
        self.assertEqual(evidence.facts, ())
        self.assertTrue(evidence.actual_executions)
        EXAMPLES["runtime_whole_rejected"] = evidence.record()

    async def test_real_service_missing_assets_is_an_error_without_fallback(self):
        service = answer_support.support_service
        with (
            patch.object(service, "_backend", None),
            patch.object(service, "_identity", None),
            patch.object(service, "_error_identity", None),
            patch.object(
                answer_support,
                "_load_backend",
                side_effect=AssertionError("No model load expected"),
            ),
        ):
            with self.assertRaises(answer_support.SupportUnavailableError) as caught:
                await role.assess_role_evidence(
                    config(), **actor_inputs(), execution_capture_kind="UNITONLY"
                )
        receipt = json.loads(caught.exception.role_evidence_json)
        self.assertEqual(receipt["stage"], "assess")
        self.assertEqual(receipt["actual_executions"], [])

    async def test_adapter_budget_and_existing_token_budget_propagate(self):
        with patch.object(
            answer_support.support_service,
            "assess",
            side_effect=AssertionError("Must not infer"),
        ):
            with self.assertRaisesRegex(ValueError, "budget"):
                await role.assess_role_evidence(
                    config(),
                    **actor_inputs(),
                    limits=RuntimeLimits(max_pairs=1),
                    execution_capture_kind="UNITONLY",
                )
        backend = Backend(tokens=513)
        with backend_context(backend):
            with self.assertRaises(answer_support.SupportInputBudgetExceeded):
                await role.assess_role_evidence(
                    config(), **actor_inputs(), execution_capture_kind="UNITONLY"
                )
        self.assertEqual(backend.logit_calls, [])

    async def test_cancel_and_timeout_preserve_failure_stage(self):
        async def cancel(*args):
            raise asyncio.CancelledError()

        async def hang(*args):
            await asyncio.Future()

        for function, error in ((cancel, asyncio.CancelledError), (hang, TimeoutError)):
            with self.subTest(error=error.__name__):
                with (
                    patch.object(
                        answer_support.support_service,
                        "metadata",
                        return_value={
                            **json.loads(
                                role.prepare_role_evidence(
                                    **actor_inputs()
                                ).support_metadata_json
                            ),
                            "readiness": "ready",
                        },
                    ),
                    patch.object(answer_support.support_service, "assess", function),
                ):
                    with self.assertRaises(error) as caught:
                        await role.assess_role_evidence(
                            config(),
                            **actor_inputs(),
                            limits=RuntimeLimits(inference_timeout_seconds=0.01),
                            execution_capture_kind="UNITONLY",
                        )
                self.assertEqual(
                    json.loads(caught.exception.role_evidence_json)["stage"], "assess"
                )

    async def test_actual_inventory_or_metadata_mismatch_does_not_bind_value(self):
        actual = actor_inputs()
        original_metadata = answer_support.support_service.metadata
        counter = 0

        def metadata(selected):
            nonlocal counter
            counter += 1
            value = original_metadata(selected)
            if counter > 1:
                value["minimum_entailment_margin"] = 1.0
            return value

        with (
            backend_context(Backend()),
            patch.object(answer_support.support_service, "metadata", metadata),
        ):
            with self.assertRaisesRegex(ValueError, "settings") as caught:
                await role.assess_role_evidence(
                    config(), **actual, execution_capture_kind="UNITONLY"
                )
        receipt = json.loads(caught.exception.role_evidence_json)
        self.assertEqual(receipt["stage"], "reconstruct")
        self.assertTrue(receipt["actual_executions"])

    async def test_original_inputs_and_config_do_not_mutate_selected_receipt(self):
        actual = actor_inputs()
        selected = config()

        async def mutate(pairs, config):
            selected.SUPPORT_MIN_MARGIN = 0
            actual["authoritative_snapshots"][
                next(iter(actual["authoritative_snapshots"]))
            ]["body"] = "forged"
            return [
                answer_support.SupportAssessment(
                    "entailment", (-3.0, 3.0, 0.0), 3.0, True, 40
                )
                for _ in pairs
            ]

        metadata = {
            **json.loads(role.prepare_role_evidence(**actual).support_metadata_json),
            "readiness": "ready",
        }
        with (
            patch.object(
                answer_support.support_service, "metadata", return_value=metadata
            ),
            patch.object(answer_support.support_service, "assess", mutate),
        ):
            evidence = await role.assess_role_evidence(
                selected, **actual, execution_capture_kind="UNITONLY"
            )
        self.assertTrue(evidence.supported)
        self.assertEqual(evidence.facts[0].value, "Rowan")
        self.assertEqual(
            json.loads(evidence.actual_executions[0].support_metadata_json)[
                "minimum_entailment_margin"
            ],
            2.0,
        )
        self.assertNotIn(
            '"body":"forged"', evidence.prepared.authoritative_snapshots_json
        )
