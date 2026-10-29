"""UNITONLY parser/NLI boundary fixtures; real SQLite and application SQL inspection."""

import asyncio
import hashlib
import json
import unittest
import uuid
from dataclasses import FrozenInstanceError, asdict
from unittest.mock import patch

from app.config import Settings
from app.db.session import Base
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus, DocumentVersion, SourceType
from app.models.query import QueryRequest
from app.services import answer_support as support
from app.services import request_parser
from app.services import staged_planning_runtime as runtime
from app.support_catalog import NLI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.staged_planning_fixtures834 import LABELS, question
from tests.test_planning_declarations import CAT, NAME, capture

PRINCIPAL = {"id": "owner-a", "workspace_id": "ops-a", "is_admin": False}


async def publish(db, number, body, *, owner="owner-a"):
    ident = uuid.UUID(int=number)
    digest = hashlib.sha256(body.encode()).hexdigest()
    document = Document(
        id=ident,
        title="UNITONLY declaration snapshot",
        owner_id=owner,
        workspace_id="ops-a",
        source_type=SourceType.TEXT,
        status=DocumentStatus.READY,
        version_number=1,
        content_hash=digest,
        chunk_count=1,
        metadata_={},
    )
    chunk = Chunk(
        id=uuid.UUID(int=number + 1000),
        document_id=ident,
        content=body,
        chunk_index=0,
        metadata_={
            "document_version": 1,
            "content_hash": digest,
            "workspace_id": "ops-a",
        },
    )
    db.add_all(
        [
            document,
            chunk,
            DocumentVersion(
                document_id=ident,
                workspace_id="ops-a",
                version_number=1,
                content_hash=digest,
                normalized_content=body,
                chunks=[
                    {
                        "id": str(chunk.id),
                        "index": 0,
                        "content": body,
                        "metadata": chunk.metadata_,
                    }
                ],
            ),
        ]
    )
    await db.commit()
    return document


class RuntimeIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.db = self.factory()
        self.q, self.qcapture = question()
        self.body, self.bodycapture = capture([NAME, CAT])
        self.doc = await publish(self.db, 812, self.body)
        self.config = Settings(
            _env_file=None,
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            ANSWER_SUPPORT_MODE="local_nli",
            SUPPORT_MODEL_REVISION=NLI.revision,
            SUPPORT_MODEL_PATH="UNITONLY-not-an-asset-directory",
            SUPPORT_MIN_MARGIN=2,
        )
        self.request = QueryRequest(question=self.q)
        self.parsed = []
        self.calls = []
        self.returned = None
        self.on_assess = None
        self.kind = "positive"

        async def parse(raw, config):
            self.parsed.append(raw)
            if raw == self.q:
                return json.loads(json.dumps(self.qcapture))
            if raw == self.body:
                return json.loads(json.dumps(self.bodycapture))
            raise AssertionError("UNITONLY: unknown capture input")

        self.patches = [
            patch.object(request_parser, "capture_async", parse),
            patch.object(
                support.support_service, "assess", self._unit_assessment_boundary
            ),
            patch.object(
                support, "_load_backend", side_effect=AssertionError("No real model")
            ),
        ]
        for item in self.patches:
            item.start()

    async def _unit_assessment_boundary(self, pairs, config):
        self.calls.append((tuple(pairs), config.model_copy(deep=True)))
        if self.on_assess:
            await self.on_assess()
        if self.kind == "short":
            return []
        await self._unit_assessment_fault()
        return self._unit_decisions(pairs)

    async def _unit_assessment_fault(self):
        if self.kind == "unavailable":
            raise support.SupportUnavailableError("UNITONLY missing assets")
        if self.kind == "budget":
            raise support.SupportInputBudgetExceeded("UNITONLY pair budget", (513,))
        if self.kind == "cancel":
            raise asyncio.CancelledError()
        if self.kind == "timeout":
            await asyncio.Future()

    def _unit_decisions(self, pairs):
        label, logits, margin, passed = ("entailment", (-3.0, 3.0, 0.0), 3.0, True)
        if self.kind == "neutral":
            label, logits, margin, passed = "neutral", (-3.0, 0.0, 3.0), -3.0, False
        if self.kind == "lying":
            label, logits, margin, passed = (
                "entailment",
                (-3.0, 0.0, 3.0),
                3.0,
                True,
            )
        self.returned = [
            support.SupportAssessment(
                label,
                logits,
                margin,
                passed,
                513
                if self.kind == "long"
                else None
                if self.kind == "no_tokens"
                else 40,
            )
            for _ in pairs
        ]
        if self.kind == "extra":
            self.returned.append(self.returned[0])
        return self.returned

    async def test_missing_or_bool_tokens_preserve_boundary_without_malformed_receipt(
        self,
    ):
        for token_count in (None, True):
            with self.subTest(token_count=token_count):

                async def malformed(pairs, config, *, tokens=token_count):
                    return [
                        support.SupportAssessment(
                            "entailment", (-3.0, 3.0, 0.0), 3.0, True, tokens
                        )
                        for _ in pairs
                    ]

                with patch.object(support.support_service, "assess", malformed):
                    with self.assertRaisesRegex(ValueError, "token") as caught:
                        await self.run_prepare()
                receipt = json.loads(caught.exception.planning_evidence_json)
                self.assertEqual(receipt["stage"], "assess")
                self.assertEqual(receipt["returned_decision_count"], 6)
                assessments = json.loads(receipt["boundary_assessments_json"])
                self.assertEqual(len(assessments), 6)
                self.assertTrue(
                    all(row["pair_tokens"] is token_count for row in assessments)
                )
                self.assertEqual(receipt["executions"], [])
                self.assertEqual(receipt["observations"], [])

    async def asyncTearDown(self):
        for item in reversed(self.patches):
            item.stop()
        await self.db.close()
        await self.engine.dispose()

    async def run_prepare(self, **kwargs):
        return await runtime.prepare_staged_planning(
            self.db,
            PRINCIPAL,
            self.request,
            self.config,
            execution_capture_kind="UNITONLY",
            **kwargs,
        )

    async def test_positive_records_exact_pairs_settings_and_actual_sql(self):
        result = await self.run_prepare()
        self.assertTrue(result.support.accepted)
        self.assertEqual(
            result.support.accepted_scope, "planning_source_relations_only"
        )
        self.assertEqual(result.support.capture_kinds, ("UNITONLY",))
        self.assertEqual(self.parsed, [self.q, self.body])
        self.assertEqual(len(self.calls), 1)
        prepared = result.support.assertion_set
        self.assertEqual(len(prepared.assertions), 6)
        self.assertEqual(
            [asdict(a.pair) for a in prepared.assertions],
            [asdict(p) for p in self.calls[0][0]],
        )
        self.assertEqual(self.calls[0][1].SUPPORT_MIN_MARGIN, 2)
        self.assertEqual(self.calls[0][1].SUPPORT_MODEL_REVISION, NLI.revision)
        self.assertEqual(
            self.calls[0][1].SUPPORT_MODEL_PATH, self.config.SUPPORT_MODEL_PATH
        )
        self.assertTrue(json.loads(result.sql_recheck_json)["consistent"])
        sql = json.loads(result.inspection.sql_read_set_json)
        self.assertEqual(sql["contract"], "request-planning-publications-v1")
        self.assertEqual(sql["selection_mode"], "all_authorized_publications_v1")
        self.assertEqual(len(result.inspection.snapshots), 1)
        self.assertEqual(result.inspection.snapshots[0].body, self.body)
        self.assertIn(
            "source_authority_requires_separate_verification",
            result.support.remaining_gates,
        )
        self.assertEqual(result.support.permissions, "NOT_ASSESSED")
        self.assertEqual(result.support.universe_completeness, "NOT_ESTABLISHED")
        self.assertEqual(json.loads(json.dumps(result.record())), result.record())
        for actual, observed in zip(
            result.executions, result.observations, strict=True
        ):
            self.assertIsNot(actual, observed)
            self.assertEqual(actual.assessment_json, observed.assessment_json)
            self.assertEqual(actual.pair_tokens, 40)
            with self.assertRaises(FrozenInstanceError):
                actual.pair_tokens = 3
        self.returned.clear()
        self.qcapture.clear()
        self.assertEqual(len(result.executions), 6)
        self.assertTrue(json.loads(result.request_capture_json)["annotation"])

    async def test_actual_support_service_with_UNITONLY_token_logit_boundary(self):
        class UnitOnlyBackend:
            def __init__(self):
                self.token_inputs = []
                self.logit_inputs = []

            def token_lengths(self, pairs):
                self.token_inputs.append(tuple(pairs))
                return [42 for _ in pairs]

            def logits(self, pairs):
                self.logit_inputs.append(tuple(pairs))
                return [[-3.0, 3.0, 0.0] for _ in pairs]

        backend = UnitOnlyBackend()
        service = support.support_service
        actual_assess = support.LocalSupportVerifier.assess.__get__(service)
        with (
            patch.object(service, "assess", actual_assess),
            patch.object(service, "_backend", None),
            patch.object(service, "_identity", None),
            patch.object(service, "_error_identity", None),
            patch.object(support, "validate_assets", side_effect=lambda path: path),
            patch.object(support, "_load_backend", return_value=backend),
        ):
            result = await self.run_prepare()
        self.assertTrue(result.support.accepted)
        self.assertEqual(len(backend.token_inputs), 1)
        self.assertEqual(backend.token_inputs, backend.logit_inputs)
        self.assertEqual(
            [asdict(p) for p in backend.token_inputs[0]],
            [asdict(a.pair) for a in result.support.assertion_set.assertions],
        )
        self.assertEqual([row.pair_tokens for row in result.executions], [42] * 6)
        self.assertEqual(result.support.capture_kinds, ("UNITONLY",))
        self.assertEqual(
            json.loads(result.actual_support_metadata_json)["readiness"], "ready"
        )

    async def test_missing_or_extra_nli_decisions_never_zip_truncate(self):
        self.kind = "short"
        with self.assertRaisesRegex(ValueError, "inventory"):
            await self.run_prepare()

    async def test_extra_nli_decision_rejected(self):
        self.kind = "extra"
        with self.assertRaisesRegex(ValueError, "inventory"):
            await self.run_prepare()

    async def test_pair_token_count_is_mandatory(self):
        self.kind = "no_tokens"
        with self.assertRaises(ValueError):
            await self.run_prepare()

    async def test_unavailable_assets_propagate_without_fallback(self):
        self.kind = "unavailable"
        with self.assertRaises(support.SupportUnavailableError) as caught:
            await self.run_prepare()
        self.assertIn('"stage":"assess"', caught.exception.planning_evidence_json)

    async def test_token_budget_error_propagates_without_truncation(self):
        self.kind = "budget"
        with self.assertRaises(support.SupportInputBudgetExceeded):
            await self.run_prepare()

    async def test_returned_pair_tokens_above_existing_budget_rejected(self):
        self.kind = "long"
        with self.assertRaises(ValueError):
            await self.run_prepare()

    async def test_numeric_supported_flag_cannot_override_logits(self):
        self.kind = "lying"
        with self.assertRaises(ValueError):
            await self.run_prepare()

    async def test_non_entailment_retains_recorded_evidence_without_acceptance(self):
        self.kind = "neutral"
        result = await self.run_prepare()
        self.assertFalse(result.support.accepted)
        self.assertEqual(len(result.executions), 6)
        self.assertTrue(all(not a.supported for a in result.support.assessments))

    async def test_cancel_does_not_return_supported_receipt(self):
        self.kind = "cancel"
        with self.assertRaises(asyncio.CancelledError) as caught:
            await self.run_prepare()
        self.assertIn('"stage":"assess"', caught.exception.planning_evidence_json)

    async def test_finite_timeout_cancels_assessment(self):
        self.kind = "timeout"
        with self.assertRaises(TimeoutError):
            await self.run_prepare(
                limits=runtime.RuntimeLimits(inference_timeout_seconds=0.02)
            )

    async def test_actual_sql_recheck_rejects_revocation_after_inference(self):
        async def revoke():
            async with self.factory() as writer:
                row = await writer.get(Document, self.doc.id)
                row.owner_id = "someone-else"
                await writer.commit()

        self.on_assess = revoke
        with self.assertRaisesRegex(
            ValueError, "planning_publications_changed"
        ) as caught:
            await self.run_prepare()
        receipt = json.loads(caught.exception.planning_evidence_json)
        self.assertEqual(len(receipt["executions"]), 6)
        self.assertEqual(receipt["stage"], "sql_recheck")

    async def test_actual_sql_recheck_rejects_new_publication_after_inference(self):
        async def add():
            async with self.factory() as writer:
                await publish(writer, 813, self.body)

        self.on_assess = add
        with self.assertRaisesRegex(ValueError, "planning_publications_changed"):
            await self.run_prepare()

    async def test_request_owned_modifier_remains_pending_with_no_weakened_pairs(self):
        rows = list(LABELS)
        rows.insert(1, ("former", "ADJ", "former", "amod", 3))
        rows = [
            (t, p, lemma, d, (h + 1 if h >= 1 and i != 1 else h))
            for i, (t, p, lemma, d, h) in enumerate(rows)
        ]
        # Literal graph explicitly matches former->labels; indexes shifted once.
        rows[1] = ("former", "ADJ", "former", "amod", 3)
        self.q, self.qcapture = question(rows)
        self.request = QueryRequest(question=self.q)
        result = await self.run_prepare()
        self.assertFalse(result.support.accepted)
        self.assertTrue(result.support.assertion_set.pending)
        self.assertFalse(self.calls)
        self.assertTrue(json.loads(result.sql_recheck_json)["consistent"])

    async def test_denied_sql_rows_never_reach_parser(self):
        await publish(
            self.db, 814, "UNITONLY private unrelated body", owner="not-owner-a"
        )
        result = await self.run_prepare()
        self.assertTrue(result.support.accepted)
        self.assertEqual(self.parsed, [self.q, self.body])

    async def test_adapter_pair_limit_stops_before_inference(self):
        with self.assertRaisesRegex(ValueError, "adapter_pair_limit"):
            await self.run_prepare(limits=runtime.RuntimeLimits(max_pairs=1))
        self.assertFalse(self.calls)

    async def test_metadata_mutation_after_assess_rejected(self):
        original = support.support_service.metadata
        calls = 0

        def changed(config):
            nonlocal calls
            calls += 1
            meta = original(config)
            if calls > 1:
                meta["minimum_entailment_margin"] = 1
            return meta

        with (
            patch.object(support.support_service, "metadata", changed),
            self.assertRaisesRegex(ValueError, "settings"),
        ):
            await self.run_prepare()

    async def test_parser_absence_never_uses_lexical_fallback(self):
        async def missing(*args):
            raise RuntimeError("UNITONLY missing parser assets")

        with (
            patch.object(request_parser, "capture_async", missing),
            self.assertRaisesRegex(RuntimeError, "missing parser assets"),
        ):
            await self.run_prepare()
        self.assertFalse(self.calls)

    async def test_original_mutable_settings_do_not_change_service_snapshot(self):
        async def mutate():
            self.config.SUPPORT_MIN_MARGIN = 0

        self.on_assess = mutate
        result = await self.run_prepare()
        self.assertTrue(result.support.accepted)
        self.assertEqual(
            json.loads(result.executions[0].support_metadata_json)[
                "minimum_entailment_margin"
            ],
            2,
        )


class AdapterBounds(unittest.TestCase):
    def test_bounds_are_finite_exact_types(self):
        for kwargs in (
            {"max_pairs": True},
            {"max_pairs": 0},
            {"max_pairs": 129},
            {"inference_timeout_seconds": float("nan")},
            {"inference_timeout_seconds": float("inf")},
            {"inference_timeout_seconds": True},
            {"inference_timeout_seconds": 0},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                runtime.RuntimeLimits(**kwargs)
