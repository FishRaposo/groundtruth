"""UNITONLY retained NLI observations; no actual tokenizer/model execution."""

import ctypes
import json
import socket
import subprocess
import unittest
from dataclasses import replace
from unittest.mock import patch

from app.services import planning_declarations as d
from app.services import planning_support as p
from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS, NLI

from .fixtures_request import (
    ACTORS,
    ASSIGN,
    CAT,
    EXTERNAL,
    LABELS,
    NAME,
    UNKNOWN,
    capture,
    inputs,
    question,
    source,
)
from .fixtures_source import deny, parser


def metadata():
    return {
        "mode": "local_nli",
        "model": NLI.model,
        "revision": NLI.revision,
        "license": NLI.license,
        "minimum_entailment_margin": 2,
        "max_pair_tokens": MAX_PAIR_TOKENS,
        "batch_size": BATCH_SIZE,
        "device": "cpu",
        "score_semantics": "raw contradiction/entailment/neutral logits; uncalibrated",
        "readiness": "ready",
    }


def sql():
    return d.canonical(
        {
            "contract": "request-planning-publications-v1",
            "selection_mode": "all_authorized_publications_v1",
            "scope": {"fixture": "UNITONLY"},
            "authorized": True,
        }
    )


def case(rows=LABELS, groups=(NAME, CAT), extra=()):
    q, c = question(rows)
    m, s, w = inputs(groups, extra=extra)
    return {
        "question": q,
        "capture": c,
        "manifest": m,
        "snapshots": s,
        "source_captures": w,
        "support_metadata": metadata(),
        "sql_read_set_json": sql(),
    }


def assessment(kind="positive"):
    if kind == "negative":
        return {
            "label": "neutral",
            "logits": [-3.0, 0.0, 3.0],
            "entailment_margin": -3.0,
            "supported": False,
            "pair_tokens": 40,
        }
    if kind == "tie":
        return {
            "label": "contradiction",
            "logits": [1.0, 1.0, 0.0],
            "entailment_margin": 0.0,
            "supported": False,
            "pair_tokens": 40,
        }
    if kind == "boundary":
        return {
            "label": "entailment",
            "logits": [-1.0, 2.0, 0.0],
            "entailment_margin": 2.0,
            "supported": True,
            "pair_tokens": 40,
        }
    return {
        "label": "entailment",
        "logits": [-3.0, 3.0, 0.0],
        "entailment_margin": 3.0,
        "supported": True,
        "pair_tokens": 40,
    }


def retained(prepared, kind="positive"):
    obs = []
    executions = []
    for index, a in enumerate(prepared.assertions):
        identity = "UNITONLY-execution-" + str(index)
        body = d.canonical(assessment(kind))
        meta = prepared.support_metadata_json
        obs.append(p.NliObservation(a.id, identity, a.pair, meta, body))
        executions.append(
            p.NliExecution(identity, a.id, a.pair, meta, body, 40, "UNITONLY")
        )
    return tuple(obs), tuple(executions)


def run_case(args, kind="positive"):
    prepared = p.prepare_planning_assertions(**args)
    obs, execution = retained(prepared, kind)
    return (
        p.reconstruct_planning_support(
            **args, observations=obs, actual_executions=execution
        ),
        prepared,
        obs,
        execution,
    )


def mutate_assess(obs, execution, **fields):
    item = json.loads(obs.assessment_json)
    item.update(fields)
    raw = d.canonical(item)
    return replace(obs, assessment_json=raw), replace(execution, assessment_json=raw)


class Support(unittest.TestCase):
    def test_supported_positive_literal_name_and_catalogue_relations(self):
        result, prepared, obs, traces = run_case(case())
        self.assertTrue(result.accepted)
        self.assertEqual(len(prepared.assertions), 6)
        self.assertEqual(set(result.supported_obligation_ids), {"d1", "d2"})
        self.assertTrue(all(a.supported for a in result.assessments))
        self.assertEqual(result.capture_kinds, ("UNITONLY",))

    def test_pairs_are_exact_source_ranges_and_request_relations(self):
        args = case()
        prepared = p.prepare_planning_assertions(**args)
        self.assertTrue(prepared.assertions)
        for assertion in prepared.assertions:
            source = next(
                s for s in args["snapshots"] if s.identity == assertion.source_identity
            )
            self.assertEqual(
                assertion.pair.premise,
                source.body[assertion.source_range.start : assertion.source_range.end],
            )
            self.assertTrue(assertion.request_relation_json)
            self.assertIn("Cedar inspection", assertion.pair.hypothesis)

    def test_non_entailing_actual_observations_do_not_support(self):
        result, prepared, obs, traces = run_case(case(), "negative")
        self.assertFalse(result.accepted)
        self.assertTrue(result.assessments)
        self.assertTrue(all(not a.supported for a in result.assessments))

    def test_equal_logits_never_entail_even_at_zero_threshold(self):
        args = case()
        args["support_metadata"]["minimum_entailment_margin"] = 0
        result, _, _, _ = run_case(args, "tie")
        self.assertFalse(result.accepted)

    def test_exact_threshold_boundary_reuses_existing_numeric_decision(self):
        result, _, _, _ = run_case(case(), "boundary")
        self.assertTrue(result.accepted)

    def test_missing_actual_trace_cannot_be_replaced_by_observation(self):
        args = case()
        prep = p.prepare_planning_assertions(**args)
        obs, traces = retained(prep)
        with self.assertRaises(ValueError):
            p.reconstruct_planning_support(
                **args, observations=obs, actual_executions=()
            )

    def test_changed_observation_hypothesis_is_rejected(self):
        args = case()
        prep = p.prepare_planning_assertions(**args)
        obs, traces = retained(prep)
        self.assertTrue(obs)
        bad = (
            replace(
                obs[0], pair=replace(obs[0].pair, hypothesis="Different scope relation")
            ),
            *obs[1:],
        )
        with self.assertRaises(ValueError):
            p.reconstruct_planning_support(
                **args, observations=bad, actual_executions=traces
            )

    def test_coherently_changed_trace_and_observation_still_need_actual_assertion(self):
        args = case()
        prep = p.prepare_planning_assertions(**args)
        obs, traces = retained(prep)
        self.assertTrue(obs)
        pair = replace(obs[0].pair, premise="Forged premise")
        with self.assertRaises(ValueError):
            p.reconstruct_planning_support(
                **args,
                observations=(replace(obs[0], pair=pair), *obs[1:]),
                actual_executions=(replace(traces[0], pair=pair), *traces[1:]),
            )

    def test_changed_actual_output_cannot_match_old_observation(self):
        args = case()
        prep = p.prepare_planning_assertions(**args)
        obs, traces = retained(prep)
        self.assertTrue(obs)
        with self.assertRaises(ValueError):
            p.reconstruct_planning_support(
                **args,
                observations=obs,
                actual_executions=(
                    replace(
                        traces[0], assessment_json=d.canonical(assessment("negative"))
                    ),
                    *traces[1:],
                ),
            )

    def test_model_revision_and_threshold_metadata_are_pinned(self):
        args = case()
        prep = p.prepare_planning_assertions(**args)
        obs, traces = retained(prep)
        self.assertTrue(obs)
        for key, value in [
            ("revision", "UNITONLY-forged"),
            ("minimum_entailment_margin", 1),
        ]:
            meta = json.loads(obs[0].support_metadata_json)
            meta[key] = value
            raw = d.canonical(meta)
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    p.reconstruct_planning_support(
                        **args,
                        observations=(
                            replace(obs[0], support_metadata_json=raw),
                            *obs[1:],
                        ),
                        actual_executions=(
                            replace(traces[0], support_metadata_json=raw),
                            *traces[1:],
                        ),
                    )

    def test_pair_tokens_are_exact_positive_bounded_integers(self):
        args = case()
        prep = p.prepare_planning_assertions(**args)
        obs, traces = retained(prep)
        self.assertTrue(obs)
        for count in [0, 513, True, 1.5]:
            bad_o, bad_t = mutate_assess(obs[0], traces[0], pair_tokens=count)
            bad_t = replace(bad_t, pair_tokens=count)
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    p.reconstruct_planning_support(
                        **args,
                        observations=(bad_o, *obs[1:]),
                        actual_executions=(bad_t, *traces[1:]),
                    )

    def test_raw_logits_label_margin_and_supported_replay(self):
        args = case()
        prep = p.prepare_planning_assertions(**args)
        obs, traces = retained(prep)
        self.assertTrue(obs)
        for fields in [
            {"logits": [True, 3.0, 0.0]},
            {"label": "neutral"},
            {"entailment_margin": 4},
            {"supported": 1},
            {"logits": [0.0, 3.0]},
        ]:
            bad_o, bad_t = mutate_assess(obs[0], traces[0], **fields)
            with self.subTest(fields=fields):
                with self.assertRaises(ValueError):
                    p.reconstruct_planning_support(
                        **args,
                        observations=(bad_o, *obs[1:]),
                        actual_executions=(bad_t, *traces[1:]),
                    )

    def test_bare_success_boolean_is_not_an_assessment(self):
        args = case()
        prep = p.prepare_planning_assertions(**args)
        obs, traces = retained(prep)
        self.assertTrue(obs)
        bad = d.canonical({"supported": True})
        with self.assertRaises(ValueError):
            p.reconstruct_planning_support(
                **args,
                observations=(replace(obs[0], assessment_json=bad), *obs[1:]),
                actual_executions=(
                    replace(traces[0], assessment_json=bad),
                    *traces[1:],
                ),
            )

    def test_duplicate_or_selected_subset_observations_refuse(self):
        args = case()
        prep = p.prepare_planning_assertions(**args)
        obs, traces = retained(prep)
        self.assertTrue(obs)
        for bad in [obs[:-1], (obs[0], *obs)]:
            with self.assertRaises(ValueError):
                p.reconstruct_planning_support(
                    **args, observations=bad, actual_executions=traces
                )

    def test_missing_or_ambiguous_catalogues_cannot_support_by_rank(self):
        for args in [
            case(groups=(NAME,)),
            case(extra=(source([CAT], doc="UNITONLY-other"),)),
        ]:
            result, _, _, _ = run_case(args)
            self.assertFalse(result.accepted)
            self.assertTrue(result.assertion_set.pending)

    def test_authority_and_completeness_remain_separate_even_on_positive(self):
        result, _, _, _ = run_case(case())
        self.assertTrue(result.accepted)
        self.assertEqual(result.permissions, "NOT_ASSESSED")
        self.assertEqual(result.universe_completeness, "NOT_ESTABLISHED")
        self.assertIn(
            "source_authority_requires_separate_verification", result.remaining_gates
        )
        self.assertIn(
            "sql_authority_currentness_and_universe_requires_runtime_recheck",
            result.remaining_gates,
        )

    def test_source_metadata_read_set_and_sql_receipt_bind_replay(self):
        args = case()
        result, _, obs, traces = run_case(args)
        changed = dict(args)
        changed["sql_read_set_json"] = d.canonical(
            {
                "contract": "request-planning-publications-v1",
                "selection_mode": "all_authorized_publications_v1",
                "scope": {"fixture": "UNITONLY-changed"},
            }
        )
        self.assertFalse(
            p.validate_planning_support(
                result.record(), **changed, observations=obs, actual_executions=traces
            )
        )
        changed = dict(args)
        changed["snapshots"] = (
            replace(
                args["snapshots"][0],
                metadata_json=d.canonical({"fixture": "UNITONLY-changed"}),
            ),
        )
        self.assertFalse(
            p.validate_planning_support(
                result.record(), **changed, observations=obs, actual_executions=traces
            )
        )

    def test_source_capture_mismatch_refuses(self):
        args = case()
        args["source_captures"] = (replace(args["source_captures"][0], windows=()),)
        with self.assertRaises(ValueError):
            p.prepare_planning_assertions(**args)

    def test_external_target_even_present_unique_remains_unresolved(self):
        args = case(
            groups=(NAME, CAT, EXTERNAL),
            extra=(source([NAME], doc="UNITONLY-note", title="Note Amber"),),
        )
        result, _, _, _ = run_case(args)
        self.assertFalse(result.accepted)
        self.assertTrue(
            any("external" in item.reason for item in result.assertion_set.pending)
        )

    def test_unknown_source_grammar_cannot_be_nli_redeemed(self):
        result, prepared, _, _ = run_case(case(groups=(NAME, CAT, UNKNOWN)))
        self.assertFalse(result.accepted)
        self.assertTrue(prepared.pending)

    def test_negative_premise_is_not_inferred_from_no_observed_override(self):
        premise = [
            ("No", "DET", "no", "det", 1),
            ("override", "NOUN", "override", "nsubjpass", 3),
            ("was", "AUX", "be", "auxpass", 3),
            ("issued", "VERB", "issue", "ROOT", 3),
            (".", "PUNCT", ".", "punct", 3),
        ]
        args = case()
        q, c = capture([LABELS, premise])
        a = c["annotation"]
        a["tokens"][10]["tag"] = "VBN"
        args.update(question=q, capture=parser.make_capture(a))
        result, prepared, _, _ = run_case(args)
        self.assertFalse(result.accepted)
        self.assertTrue(
            any(v.kind == "verify_request_constraint" for v in prepared.pending)
        )

    def test_incumbent_relations_can_be_supported_without_granting_answer_facts(self):
        groups = [NAME, CAT]
        for role, actor in [
            ("coordinator", "Rowan"),
            ("observer", "Nova"),
            ("recorder", "Ash"),
        ]:
            groups.append(
                [
                    (role, pos, role, dep, head)
                    if text == "coordinator"
                    else (actor, pos, actor, dep, head)
                    if text == "Rowan"
                    else (text, pos, lemma, dep, head)
                    for text, pos, lemma, dep, head in ASSIGN
                ]
            )
        result, prepared, _, _ = run_case(case(ACTORS, tuple(groups)))
        self.assertTrue(result.accepted)
        self.assertEqual(
            len([a for a in prepared.assertions if a.kind == "actor_role_relation"]), 3
        )
        self.assertEqual(result.accepted_scope, "planning_source_relations_only")

    def test_result_tamper_or_acceptance_promotion_fails_independent_replay(self):
        args = case()
        result, _, obs, traces = run_case(args)
        self.assertTrue(
            p.validate_planning_support(
                result.record(), **args, observations=obs, actual_executions=traces
            )
        )
        for field, value in [
            ("permissions", "GRANTED"),
            ("supported_obligation_ids", []),
            ("remaining_gates", []),
        ]:
            rec = result.record()
            rec[field] = value
            self.assertFalse(
                p.validate_planning_support(
                    rec, **args, observations=obs, actual_executions=traces
                )
            )

    def test_invalid_or_nonfinite_threshold_and_nonapproved_model_refuse(self):
        for key, value in [
            ("minimum_entailment_margin", True),
            ("minimum_entailment_margin", 5),
            ("minimum_entailment_margin", float("nan")),
            ("model", "UNITONLY-other"),
        ]:
            args = case()
            args["support_metadata"][key] = value
            with self.subTest(key=key, value=str(value)):
                with self.assertRaises(ValueError):
                    p.prepare_planning_assertions(**args)


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
