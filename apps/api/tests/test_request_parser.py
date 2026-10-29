"""Optional parser contracts; hand graphs are UNITONLY, never model truth."""

import asyncio
import hashlib
import importlib.util
import json
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

_path = Path(__file__).parents[1] / "app/services/request_parser.py"
_spec = importlib.util.spec_from_file_location("pure_request_parser", _path)
runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(runtime)


def annotation():
    import hashlib

    question = "Who leads?"
    tokens = []
    for i, start, end, ws, pos, tag, dep, head, lemma in [
        (0, 0, 3, " ", "PRON", "WP", "nsubj", 1, "who"),
        (1, 4, 9, "", "VERB", "VBZ", "ROOT", 1, "lead"),
        (2, 9, 10, "", "PUNCT", ".", "punct", 1, "?"),
    ]:
        tokens.append(
            {
                "i": i,
                "start": start,
                "end": end,
                "text": question[start:end],
                "whitespace": ws,
                "pos": pos,
                "tag": tag,
                "dep": dep,
                "head": head,
                "lemma": lemma,
                "morph": "",
                "sentence_start": i == 0,
                "children": [0, 2] if i == 1 else [],
            }
        )
    return {
        "raw_text": question,
        "raw_sha256": hashlib.sha256(question.encode()).hexdigest(),
        "coordinate_system": "python-unicode-codepoints",
        "tokens": tokens,
        "sentences": [
            {"start": 0, "end": 10, "text": question, "token_start": 0, "token_end": 3}
        ],
        "lossless_input_cover": [
            {"start": 0, "end": 3, "kind": "raw-token", "text": "Who"},
            {"start": 3, "end": 4, "kind": "raw-gap", "text": " "},
            {"start": 4, "end": 9, "kind": "raw-token", "text": "leads"},
            {"start": 9, "end": 10, "kind": "raw-token", "text": "?"},
        ],
        "linguistic_proposals": [
            {
                "anchor_token": 1,
                "surface": "leads",
                "dep": "ROOT",
                "sentence_range": {"start": 0, "end": 10},
                "subtree_token_indices": [0, 1, 2],
                "status": "unresolved_linguistic_proposal",
                "note": (
                    "No relation, scope, completeness, truth or entitlement acceptance."
                ),
            }
        ],
        "protected_token_indices": [],
        "all_token_indices_retained": [0, 1, 2],
        "semantic_obligation_completeness": "NOT_ESTABLISHED",
        "support_or_permissions": "NOT_ASSESSED",
    }


class PureCaptureTests(unittest.TestCase):
    def test_valid_graph_reconstructs_defensive_annotation(self):
        raw = annotation()
        record = runtime.make_capture(raw)
        self.assertIsInstance(record, dict, "Pinned graph capture envelope is missing")
        self.assertEqual(record["contract"], "dependency-request-capture-v1")
        actual = runtime.validate_capture("Who leads?", record)
        self.assertEqual(actual, raw)
        actual["tokens"].clear()
        self.assertEqual(len(record["annotation"]["tokens"]), 3)

    def test_recomputed_hashes_cannot_hide_graph_or_schema_tampering(self):
        changes = [
            lambda a: a["tokens"][0].update(start=False),
            lambda a: a["tokens"][0].update(end=3.0),
            lambda a: a["tokens"][0].update(whitespace=""),
            lambda a: a["tokens"][0].update(head=2),
            lambda a: a["tokens"][1].update(head=0),
            lambda a: a["tokens"][1].update(children=[]),
            lambda a: a["tokens"][1].update(pos="UNKNOWN"),
            lambda a: a["tokens"][0].update(dep="UNKNOWN"),
            lambda a: a["tokens"][0].update(tag="UNKNOWN"),
            lambda a: a["sentences"][0].update(token_end=2),
            lambda a: a["tokens"][0].update(sentence_start=False),
            lambda a: a["linguistic_proposals"][0].update(subtree_token_indices=[1]),
            lambda a: a["linguistic_proposals"][0].update(
                sentence_range={"start": 0, "end": 9}
            ),
            lambda a: a.update(protected_token_indices=[0]),
            lambda a: a.update(all_token_indices_retained=[0, 1]),
            lambda a: a["lossless_input_cover"].pop(),
            lambda a: a.update(semantic_obligation_completeness="complete"),
            lambda a: a.update(support_or_permissions="supported"),
            lambda a: a.update(extra=True),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                record = runtime.make_capture(annotation())
                self.assertIsInstance(record, dict, "Capture construction is missing")
                change(record["annotation"])
                reseal(record)
                with self.assertRaises(runtime.InvalidCapture):
                    runtime.validate_capture("Who leads?", record)

    def test_actual_question_and_pinned_model_identity_are_required(self):
        record = runtime.make_capture(annotation())
        self.assertIsInstance(record, dict, "Capture construction is missing")
        with self.assertRaises(runtime.InvalidCapture):
            runtime.validate_capture("Who follows?", record)
        record["parser"]["model_version"] = "forged"
        reseal(record)
        with self.assertRaises(runtime.InvalidCapture):
            runtime.validate_capture("Who leads?", record)

    def test_missing_optional_assets_and_disabled_mode_fail_readiness(self):
        for config in [
            SimpleNamespace(REQUEST_PARSER_MODE="bounded"),
            SimpleNamespace(
                REQUEST_PARSER_MODE="local_dependency",
                REQUEST_PARSER_MODEL_PATH="missing-parser-assets",
            ),
        ]:
            with (
                self.subTest(config=config),
                self.assertRaises(runtime.RequestParserReadinessError),
            ):
                runtime.capture("Who leads?", config)

    def test_question_is_bounded_without_truncation(self):
        for question in ["", " ", None, "a" * 2049, "bad\ud800"]:
            with self.subTest(question=repr(question)), self.assertRaises(ValueError):
                runtime.capture(
                    question, SimpleNamespace(REQUEST_PARSER_MODE="local_dependency")
                )


def reseal(record):
    def digest(value):
        return hashlib.sha256(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode()
        ).hexdigest()

    record["annotation_sha256"] = digest(record["annotation"])
    record["capture_sha256"] = digest(
        {k: v for k, v in record.items() if k != "capture_sha256"}
    )


@unittest.skipUnless(
    os.environ.get("REQUEST_PARSER_TEST_MODEL_PATH"),
    "Explicit cached model path required",
)
class CachedCPUParserTests(unittest.TestCase):
    def test_invalid_module_origins_raise_explicit_readiness(self):
        from unittest.mock import patch

        for origin in (None, "", "  ", False, 1):
            with self.subTest(origin=origin):
                with (
                    patch.object(
                        runtime.importlib.util,
                        "find_spec",
                        return_value=SimpleNamespace(origin=origin),
                    ),
                    self.assertRaises(runtime.RequestParserReadinessError),
                ):
                    runtime.capture("Who leads?", self.config())

    def test_metadata_simple_path_is_normalized_without_pathlike_protocol(self):
        from unittest.mock import patch

        distribution = runtime.importlib.metadata.distribution("spacy")
        package = str(distribution.locate_file("spacy"))

        class SimpleLocation:
            def __str__(self):
                return package

        with patch.object(distribution, "locate_file", return_value=SimpleLocation()):
            with patch.object(
                runtime.importlib.metadata, "distribution", return_value=distribution
            ):
                record = runtime.capture("Who leads?", self.config())
        self.assertEqual(record["annotation"]["raw_text"], "Who leads?")

    def test_invalid_metadata_locations_raise_explicit_readiness(self):
        from unittest.mock import patch

        distribution = runtime.importlib.metadata.distribution("spacy")
        for location in (None, "", "  ", False, 1, Path("spacy")):
            with self.subTest(location=location):
                with patch.object(distribution, "locate_file", return_value=location):
                    with (
                        patch.object(
                            runtime.importlib.metadata,
                            "distribution",
                            return_value=distribution,
                        ),
                        self.assertRaises(runtime.RequestParserReadinessError),
                    ):
                        runtime.capture("Who leads?", self.config())

    def test_unapproved_plugin_is_refused_before_model_use(self):
        from unittest.mock import patch

        plugin = SimpleNamespace(
            metadata={"Name": "unapproved"},
            entry_points=[
                SimpleNamespace(
                    group="spacy_factories",
                    name="external_factory",
                    value="unapproved:execute",
                )
            ],
        )
        with (
            patch.object(
                runtime.importlib.metadata, "distributions", return_value=[plugin]
            ),
            self.assertRaises(runtime.RequestParserReadinessError),
        ):
            runtime.capture("Who leads?", self.config())

    def config(self):
        return SimpleNamespace(
            REQUEST_PARSER_MODE="local_dependency",
            REQUEST_PARSER_MODEL_PATH=os.environ["REQUEST_PARSER_TEST_MODEL_PATH"],
            REQUEST_PARSER_MODEL_REVISION="en_core_web_sm-3.8.0",
            REQUEST_PARSER_MAX_CHARS=2048,
        )

    def test_actual_cached_cpu_capture_is_stable_and_detached(self):
        question = (
            "Who leads the Copper review, and why may the deputy "
            "act only after approval? 🌘\r\n"
        )
        first = runtime.capture(question, self.config())
        self.assertIsInstance(first, dict, "Actual cached CPU capture is missing")
        self.assertEqual(first, runtime.capture(question, self.config()))
        self.assertEqual(
            runtime.validate_capture(question, first)["raw_text"], question
        )
        first["annotation"]["tokens"].clear()
        self.assertTrue(
            runtime.capture(question, self.config())["annotation"]["tokens"]
        )

    def test_concurrent_async_requests_have_no_shared_doc_or_capture(self):
        questions = [
            "Who leads?",
            "Where is the Copper station?",
            "Name 1.50000000000000000001 tokens. 🪶",
        ]

        async def run():
            return await asyncio.gather(
                *(runtime.capture_async(q, self.config()) for q in questions)
            )

        records = asyncio.run(run())
        self.assertTrue(
            all(type(r) is dict for r in records), "Async CPU captures missing"
        )
        for q, r in zip(questions, records, strict=True):
            self.assertEqual(runtime.validate_capture(q, r)["raw_text"], q)
        records[0]["annotation"]["tokens"].clear()
        self.assertTrue(records[1]["annotation"]["tokens"])

    def test_explicit_local_wheel_setup_and_corruption_readiness(self):
        import uuid

        from app.request_parser_setup import cache_model, verify_assets

        parent = Path(os.environ["REQUEST_PARSER_TEST_WORKDIR"])
        destination = parent / ("asset-cache-" + uuid.uuid4().hex)
        model = Path(os.environ["REQUEST_PARSER_TEST_MODEL_PATH"])
        prototype = model.parents[4]
        wheel = prototype / "wheelhouse/en_core_web_sm-3.8.0-py3-none-any.whl"
        actual = cache_model(destination, wheel=wheel)
        self.assertIsInstance(
            actual, Path, "Explicit pinned model cache setup is missing"
        )
        self.assertTrue((actual / "LICENSE").is_file())
        self.assertTrue(verify_assets(actual))
        config = self.config()
        config.REQUEST_PARSER_MODEL_PATH = str(actual)
        self.assertEqual(
            runtime.capture("Who leads?", config)["annotation"]["raw_text"],
            "Who leads?",
        )
        (actual / "config.cfg").write_text(
            "arbitrary untrusted configuration", encoding="utf-8"
        )
        with self.assertRaises(runtime.RequestParserReadinessError):
            runtime.capture("Who leads?", config)


if __name__ == "__main__":
    unittest.main()
