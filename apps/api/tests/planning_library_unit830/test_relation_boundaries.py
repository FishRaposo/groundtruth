"""UNITONLY relation-strength and actual-trace boundary controls."""

import ctypes
import socket
import subprocess
import unittest
from dataclasses import replace
from unittest.mock import patch

from .test_support import LABELS, case, d, deny, p, parser, retained, run_case


class Boundaries(unittest.TestCase):
    def test_conditioned_request_cannot_get_a_weaker_unconditional_assertion(self):
        rows = LABELS[:-1] + [
            ("unless", "SCONJ", "unless", "mark", 8),
            ("permit", "NOUN", "permit", "nsubj", 8),
            ("applies", "VERB", "apply", "advcl", 0),
            (".", "PUNCT", ".", "punct", 0),
        ]
        result, prepared, _, _ = run_case(case(rows))
        self.assertFalse(result.accepted)
        self.assertEqual(prepared.assertions, ())
        self.assertTrue(
            any(
                item.reason == "request_relation_qualifiers_require_supported_assertion"
                for item in prepared.pending
            )
        )
        self.assertIn("unless", prepared.effective_plan_json)

    def test_actual_token_length_must_match_assessment_count(self):
        args = case()
        prepared = p.prepare_planning_assertions(**args)
        obs, traces = retained(prepared)
        self.assertTrue(obs)
        with self.assertRaises(ValueError):
            p.reconstruct_planning_support(
                **args,
                observations=obs,
                actual_executions=(replace(traces[0], pair_tokens=41), *traces[1:]),
            )

    def test_failed_actual_metadata_cannot_claim_ready_support(self):
        args = case()
        prepared = p.prepare_planning_assertions(**args)
        obs, traces = retained(prepared)
        self.assertTrue(obs)
        metadata = {
            "mode": "local_nli",
            "model": p.NLI.model,
            "revision": p.NLI.revision,
            "license": p.NLI.license,
            "minimum_entailment_margin": 2,
            "max_pair_tokens": 512,
            "batch_size": 8,
            "device": "cpu",
            "score_semantics": (
                "raw contradiction/entailment/neutral logits; uncalibrated"
            ),
            "readiness": "error",
        }
        raw = d.canonical(metadata)
        with self.assertRaises(ValueError):
            p.reconstruct_planning_support(
                **args,
                observations=(replace(obs[0], support_metadata_json=raw), *obs[1:]),
                actual_executions=(
                    replace(traces[0], support_metadata_json=raw),
                    *traces[1:],
                ),
            )

    def test_execution_id_cannot_be_shared_between_two_assertions(self):
        args = case()
        prepared = p.prepare_planning_assertions(**args)
        obs, traces = retained(prepared)
        self.assertGreater(len(obs), 1)
        with self.assertRaises(ValueError):
            p.reconstruct_planning_support(
                **args,
                observations=(
                    obs[0],
                    replace(obs[1], execution_id=obs[0].execution_id),
                    *obs[2:],
                ),
                actual_executions=(
                    traces[0],
                    replace(traces[1], execution_id=traces[0].execution_id),
                    *traces[2:],
                ),
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
