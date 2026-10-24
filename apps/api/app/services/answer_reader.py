"""Local CPU QA logits, explicit null decision, and exact source-span extraction.

Scores are raw start/end logits and null margins, never calibrated probabilities.
The model/tokenizer are shared read-only behind a thread lock; all request
features, scores, and selected passages are local. Cancellation abandons results,
while the lock keeps an in-flight CPU call from overlapping subsequent calls.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import math
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.models.query import AnswerSpan
from app.reader_catalog import get_reader_spec
from app.services.reader_questions import mismatch_reason, question_parts, scope_matches
from app.services.reader_support import procedure_features


@dataclass(frozen=True)
class ReaderSelection:
    span: AnswerSpan | None
    diagnostics: dict[str, Any]


def support_rejection(passage: str, start: int, end: int) -> str | None:
    """Reject missing-information language in the selected occurrence's clause.

    This is a bounded surface check, never entity/attribute entailment. Other
    clauses, repeated text, quantities, and ambiguous intent are left to the
    reader's declared null decision rather than guessed by lexical rules.
    """
    absence = (
        r"\b(?:do|does|did)\s+not\s+(?:\w+ly\s+)?"
        r"(?:specify|provide|define|state|describe|document)\b"
        r"|\b(?:is|are|was|were)\s+not\s+(?:\w+ly\s+)?"
        r"(?:specified|provided|defined|stated|described|documented)\b"
    )
    for clause in re.finditer(r"[^.!?;\n]+", passage):
        if not (clause.start() <= start < end <= clause.end()):
            continue
        text = clause.group()
        if re.match(r"\s*do\s+not\b", text, re.I):
            continue
        if re.search(absence, text, re.I):
            return "selected_clause_explicitly_absent"
    return None


def passage_span(context: str, start: int, end: int) -> AnswerSpan:
    """Copy a complete sentence or contiguous numbered procedure, never rewrite."""
    paragraph_left = max(
        (match.end() for match in re.finditer(r"\n\s*\n", context[:start])),
        default=0,
    )
    paragraph_break = re.search(r"\n\s*\n", context[end:])
    paragraph_right = end + paragraph_break.start() if paragraph_break else len(context)
    left = max(
        (
            match.end()
            for match in re.finditer(r"[.!?](?:\s+)|\n\s*\n", context[:start])
        ),
        default=0,
    )
    following = re.search(r"[.!?](?=\s|$)|\n\s*\n", context[end:])
    right = (
        end
        if end > 0 and context[end - 1] in ".!?"
        else end + following.end()
        if following
        else len(context)
    )
    # Periods are intrinsically ambiguous without a language-aware segmenter
    # (abbreviations, initials, decimals). Preserve the entire source paragraph
    # rather than discard a preceding negation or following qualifier. No list
    # of question-specific or abbreviation-specific aliases is used.
    if "." in context[paragraph_left:paragraph_right]:
        left, right = paragraph_left, paragraph_right
    # A numbered procedure is a unit: preserve ordered prerequisites and steps.
    if re.search(r"(?:^|\n)\s*(?:\d+[.)]|[-*])\s", context):
        left, right = 0, len(context)
    while left < right and context[left].isspace():
        left += 1
    while right > left and context[right - 1].isspace():
        right -= 1
    return AnswerSpan(start=left, end=right, text=context[left:right])


def reader_question(question: str) -> str:
    """Map a procedural imperative to QA form without dropping its subject."""
    match = re.fullmatch(
        r"\s*(?:(?:please|can you|could you|would you)\s+)?"
        r"walk\s+me\s+through\s+(?:(?:the\s+)?steps\s+for|how\s+to)\s+(.+?)\s*",
        question,
        re.I | re.S,
    )
    if match:
        subject = match.group(1).strip().rstrip(".?!")
        return f"What are the steps for {subject}?"
    ordered = re.fullmatch(
        r"\s*(?:(?:please|can you|could you|would you)\s+)?"
        r"(?:walk|take)\s+me\s+through\s+(.+?)\s+in\s+(?:order|sequence)[.?!]*\s*",
        question,
        re.I | re.S,
    )
    if ordered and not re.match(
        r"(?:why|whether|how\s+(?:long|much)|the\s+duration)\b",
        ordered.group(1),
        re.I,
    ):
        return f"What are the steps for {ordered.group(1).strip()}?"
    order_question = re.fullmatch(
        r"\s*in\s+what\s+order\s+do\s+(?:we|I)\s+(.+?)\s*[.?!]*\s*",
        question,
        re.I | re.S,
    )
    if order_question:
        return f"What are the steps to {order_question.group(1).strip()}?"
    return question


class LocalReader:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._identity: tuple[str, str] | None = None
        self._tokenizer: Any = None
        self._model: Any = None
        self._error = False

    def metadata(self, config: Settings | None = None) -> dict[str, Any]:
        config = config or get_settings()
        mode = config.ANSWER_SELECTION_MODE
        try:
            spec = get_reader_spec(config.READER_MODEL_REVISION)
        except ValueError:
            spec = None
        return {
            "mode": mode,
            "contract": "reader-parts-v5"
            if mode == "reader"
            else "extractive-coverage-v1.1",
            "model": spec.model if mode == "reader" and spec else None,
            "revision": config.READER_MODEL_REVISION if mode == "reader" else None,
            "threshold": config.READER_NULL_THRESHOLD if mode == "reader" else None,
            "readiness": "disabled"
            if mode == "lexical"
            else "error"
            if self._error or spec is None
            else "ready"
            if self._identity
            == (config.READER_MODEL_PATH, config.READER_MODEL_REVISION)
            else "not_loaded",
            "score_semantics": "raw null-minus-best-span logits; uncalibrated"
            if mode == "reader"
            else "lexical coverage",
            "coverage_semantics": (
                "non-null QA selections with bounded mismatch checks; "
                "not general factual entailment"
            )
            if mode == "reader"
            else "lexical coverage",
        }

    def _load(self, config: Settings) -> None:
        identity = (config.READER_MODEL_PATH, config.READER_MODEL_REVISION)
        if self._identity == identity:
            return
        if not config.READER_MODEL_PATH:
            raise RuntimeError(
                "Configure the pinned local reader; no fallback was used."
            )
        spec = get_reader_spec(config.READER_MODEL_REVISION)
        root = Path(config.READER_MODEL_PATH).resolve()
        manifest = json.loads(
            (root / "groundtruth-reader.json").read_text(encoding="utf-8")
        )
        if (
            manifest.get("model") != spec.model
            or manifest.get("revision") != spec.revision
            or set(manifest.get("files", {})) != set(spec.files)
        ):
            raise RuntimeError("Reader manifest does not match the pinned assets.")
        # Transformers can prefer tokenizer.json/added_tokens.json or sharded
        # model indexes over the files listed in our manifest. A dedicated cache
        # directory must not silently introduce another unverified model input.
        allowed = set(spec.files) | {
            "groundtruth-reader.json",
            "download-manifest.json",
            "README.md",
            "LICENSE",
            "LICENSE.txt",
        }
        if any(path.is_file() and path.name not in allowed for path in root.iterdir()):
            raise RuntimeError(
                "Reader directory contains unverified files; "
                "use a clean setup directory."
            )
        for filename in spec.files:
            path = (root / filename).resolve()
            if (
                not path.is_relative_to(root)
                or hashlib.sha256(path.read_bytes()).hexdigest()
                != manifest["files"][filename]
            ):
                raise RuntimeError("Reader asset integrity check failed.")
        module = importlib.import_module("transformers")
        tokenizer = module.AutoTokenizer.from_pretrained(
            str(root), local_files_only=True, trust_remote_code=False, use_fast=True
        )
        if not tokenizer.is_fast:
            raise RuntimeError(
                "Reader requires a fast tokenizer with canonical offsets."
            )
        model = module.AutoModelForQuestionAnswering.from_pretrained(
            str(root),
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
        )
        model.to("cpu")
        model.eval()
        self._tokenizer, self._model, self._identity = tokenizer, model, identity

    def _read(
        self, question: str, contexts: list[str], config: Settings
    ) -> list[ReaderSelection]:
        with self._lock:
            try:
                self._load(config)
                self._error = False
                return self._parts(question, contexts, config)
            except Exception as exc:
                self._error = True
                raise RuntimeError(
                    "Configured local reader is unavailable. Check "
                    "READER_MODEL_PATH and the reader extra; no fallback was used."
                ) from exc

    def _parts(
        self, question: str, contexts: list[str], config: Settings
    ) -> list[ReaderSelection]:
        parts = question_parts(question)
        matrix: list[list[ReaderSelection]] = []
        for part in parts:
            row = []
            for context in contexts:
                if not scope_matches(part, context):
                    row.append(
                        ReaderSelection(None, {"decision": "entity_scope_mismatch"})
                    )
                    continue
                prediction = self._context(part.question, context, config)
                raw = prediction.diagnostics.get("raw_span")
                rejection = None
                if prediction.span is not None and isinstance(raw, dict):
                    rejection = mismatch_reason(
                        part.question, context, raw["start"], raw["end"]
                    )
                row.append(
                    ReaderSelection(
                        None if rejection else prediction.span,
                        {
                            **prediction.diagnostics,
                            "evidence_rejection": rejection,
                            "procedure_evidence": procedure_features(
                                reader_question(part.question),
                                context,
                                start=raw.get("start")
                                if isinstance(raw, dict)
                                else None,
                                end=raw.get("end") if isinstance(raw, dict) else None,
                                anchors=part.anchors,
                            ),
                        },
                    )
                )
            matrix.append(row)
        missing = [i for i, row in enumerate(matrix) if not any(p.span for p in row)]
        results = []
        for index, context in enumerate(contexts):
            predictions = [row[index] for row in matrix]
            covered = [i for i, prediction in enumerate(predictions) if prediction.span]
            spans = [prediction.span for prediction in predictions if prediction.span]
            span = None
            if spans and not missing:
                start, end = min(s.start for s in spans), max(s.end for s in spans)
                span = AnswerSpan(start=start, end=end, text=context[start:end])
            results.append(
                ReaderSelection(
                    span,
                    {
                        **(predictions[0].diagnostics if len(parts) == 1 else {}),
                        "decision": "answer" if span else "no_answer",
                        "question_parts": [p.question for p in parts],
                        "part_count": len(parts),
                        "covered_parts": covered,
                        "missing_parts": missing,
                        "parts": [
                            {"index": i, **p.diagnostics}
                            for i, p in enumerate(predictions)
                        ],
                    },
                )
            )
        return results

    async def select(
        self, question: str, contexts: list[str], config: Settings | None = None
    ) -> list[ReaderSelection]:
        # Snapshot all settings so concurrent environment changes cannot alter a call.
        config = (config or get_settings()).model_copy(deep=True)
        return await asyncio.to_thread(self._read, question, contexts, config)

    def _context(
        self, question: str, context: str, config: Settings
    ) -> ReaderSelection:
        torch = importlib.import_module("torch")
        normalized_question = reader_question(question)
        encoded = self._tokenizer(
            normalized_question,
            context,
            truncation="only_second",
            max_length=config.READER_MAX_LENGTH,
            stride=config.READER_STRIDE,
            return_overflowing_tokens=True,
            return_offsets_mapping=True,
            padding=True,
            return_tensors="pt",
        )
        offsets = encoded.pop("offset_mapping").tolist()
        encoded.pop("overflow_to_sample_mapping", None)
        with torch.inference_mode():
            output = self._model(**encoded)
        starts, ends = output.start_logits.tolist(), output.end_logits.tolist()
        best: tuple[float, int, int] | None = None
        null_score = math.inf
        for window, (start_logits, end_logits) in enumerate(
            zip(starts, ends, strict=True)
        ):
            ids = encoded["input_ids"][window].tolist()
            cls = ids.index(self._tokenizer.cls_token_id)
            null_score = min(null_score, float(start_logits[cls] + end_logits[cls]))
            sequences = encoded.sequence_ids(window)
            valid = [
                i
                for i, pair in enumerate(offsets[window])
                if sequences[i] == 1 and pair[1] > pair[0]
            ]
            start_indices = sorted(valid, key=lambda i: start_logits[i], reverse=True)[
                : config.READER_N_BEST
            ]
            end_indices = sorted(valid, key=lambda i: end_logits[i], reverse=True)[
                : config.READER_N_BEST
            ]
            for left in start_indices:
                for right in end_indices:
                    if right < left or right - left + 1 > config.READER_MAX_SPAN_TOKENS:
                        continue
                    start, end = offsets[window][left][0], offsets[window][right][1]
                    score = float(start_logits[left] + end_logits[right])
                    if 0 <= start < end <= len(context) and (
                        best is None or score > best[0]
                    ):
                        best = score, start, end
        if (
            not math.isfinite(null_score)
            or best is not None
            and not math.isfinite(best[0])
        ):
            raise RuntimeError("Reader produced non-finite logits.")
        margin = null_score - best[0] if best else None
        accepted = (
            best is not None
            and margin is not None
            and margin <= config.READER_NULL_THRESHOLD
        )
        span = passage_span(context, best[1], best[2]) if accepted and best else None
        rejection = (
            support_rejection(span.text, best[1] - span.start, best[2] - span.start)
            if span is not None and best
            else None
        )
        if rejection:
            accepted = False
            span = None
        return ReaderSelection(
            span,
            {
                "decision": "answer" if accepted else "no_answer",
                "support_rejection": rejection,
                "question_normalization": "explicit-procedure-qa-v2"
                if normalized_question != question
                else "none",
                "null_score": null_score,
                "best_span_score": best[0] if best else None,
                "null_margin": margin,
                "raw_span": {
                    "start": best[1],
                    "end": best[2],
                    "text": context[best[1] : best[2]],
                }
                if best
                else None,
                "windows": len(starts),
            },
        )


reader_service = LocalReader()
