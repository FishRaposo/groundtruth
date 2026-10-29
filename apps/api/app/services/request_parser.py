"""Optional CPU linguistic proposals, never truth, completeness or permissions.

No optional library is imported until an explicitly configured capture. Each
request receives detached JSON; the cached pipeline is serialized by a lock.
Pure replay binds recorded graphs, not actual model execution or semantics.
"""

import asyncio
import hashlib
import importlib
import importlib.metadata
import importlib.util
import json
import math
import threading
from copy import deepcopy
from pathlib import Path

from app.request_parser_catalog import (
    APPROVED_ENTRY_POINTS,
    CONTRACT,
    MAX_QUESTION_CHARS,
    MODEL_REVISION,
)
from app.request_parser_catalog import (
    parser_identity as parser_identity,
)

_LOCK = threading.Lock()
_PIPELINES = {}
_VERIFIED_LIBRARY = None
_NOTE = "No relation, scope, completeness, truth or entitlement acceptance."
_ANCHORS = frozenset({"ROOT", "conj", "advcl", "ccomp", "xcomp", "relcl"})
_PROTECTED = frozenset({"neg", "cc", "conj", "mark", "aux", "auxpass", "nummod"})
_POS = frozenset(
    (
        "ADJ ADP ADV AUX CCONJ DET INTJ NOUN NUM PART PRON PROPN "
        "PUNCT SCONJ SYM VERB X SPACE"
    ).split()
)
_TAGS = frozenset(parser_identity()["tag_labels"])
_DEPS = frozenset(parser_identity()["dependency_labels"])


class RequestParserReadinessError(RuntimeError):
    """Explicitly configured optional parser is unavailable or untrusted."""


class InvalidCapture(ValueError):
    """Retained graph does not reconstruct the actual question."""


def metadata(config):
    """Safe declared runtime identity; readiness requires actual cached loading."""
    mode = getattr(config, "REQUEST_PARSER_MODE", "bounded")
    result = {"mode": mode, "support_or_permissions": "NOT_ASSESSED"}
    if mode == "local_dependency":
        identity = parser_identity()
        result.update(
            contract=CONTRACT,
            model=identity["model"],
            revision=MODEL_REVISION,
            library=identity["library"],
            library_version=identity["library_version"],
            character_limit=config.REQUEST_PARSER_MAX_CHARS,
            device="cpu",
            annotation_semantics=(
                "Syntax proposals; source support requires separate verification."
            ),
        )
    return result


def make_capture(annotation):
    """Seal validated JSON proposals, also usable for explicit UNITONLY fixtures."""
    try:
        validated = _validate_annotation(annotation["raw_text"], annotation)
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise InvalidCapture("Invalid request annotation") from exc
    record = {
        "contract": CONTRACT,
        "parser": parser_identity(),
        "annotation": validated,
        "annotation_sha256": _digest(validated),
    }
    record["capture_sha256"] = _digest(record)
    return record


def validate_capture(question, capture):
    """Strict model-free graph replay against the actual original question."""
    try:
        _native(capture)
        if type(capture) is not dict or set(capture) != {
            "contract",
            "parser",
            "annotation",
            "annotation_sha256",
            "capture_sha256",
        }:
            raise ValueError("Capture schema mismatch")
        _same(capture["contract"], CONTRACT)
        _same(capture["parser"], parser_identity())
        _same(capture["annotation_sha256"], _digest(capture["annotation"]))
        _same(
            capture["capture_sha256"],
            _digest({k: v for k, v in capture.items() if k != "capture_sha256"}),
        )
        return _validate_annotation(question, capture["annotation"])
    except (KeyError, TypeError, ValueError, RecursionError) as exc:
        raise InvalidCapture(
            "Request capture does not reconstruct the actual question/graph"
        ) from exc


def capture(question, config):
    """Parse original text using only explicitly cached, pinned local assets."""
    limit = getattr(config, "REQUEST_PARSER_MAX_CHARS", MAX_QUESTION_CHARS)
    if type(limit) is not int or not 1 <= limit <= MAX_QUESTION_CHARS:
        raise ValueError("Invalid request parser character budget")
    _question(question, limit)
    if getattr(config, "REQUEST_PARSER_MODE", "bounded") != "local_dependency":
        raise RequestParserReadinessError(
            "Optional local dependency parser is disabled"
        )
    if (
        getattr(config, "REQUEST_PARSER_MODEL_REVISION", MODEL_REVISION)
        != MODEL_REVISION
    ):
        raise RequestParserReadinessError("Unapproved request parser model revision")
    configured = getattr(config, "REQUEST_PARSER_MODEL_PATH", None)
    if not isinstance(configured, (str, Path)) or not str(configured).strip():
        raise RequestParserReadinessError(
            "Explicit cached request parser model path required"
        )
    from app.request_parser_setup import verify_assets

    with _LOCK:
        try:
            model_path = Path(configured)
            verify_assets(model_path)
            nlp = _load_pipeline(model_path.resolve())
            doc = nlp(question)
            if (
                doc.text != question
                or not doc.has_annotation("DEP")
                or not doc.has_annotation("POS")
            ):
                raise ValueError("Incomplete local parser annotations")
            annotation = _annotation(question, doc)
            return make_capture(annotation)
        except (OSError, ImportError, ValueError, RuntimeError) as exc:
            raise RequestParserReadinessError(
                "Pinned optional parser unavailable; invalid assets/annotations"
            ) from exc


async def capture_async(question, config):
    """Run CPU parsing off the event loop; synchronization lives in capture."""
    return await asyncio.to_thread(capture, question, config)


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _same(actual, expected):
    if _digest(actual) != _digest(expected):
        raise ValueError("Canonical JSON mismatch")


def _native(value, depth=0):
    if depth > 32:
        raise ValueError("Capture nesting budget exceeded")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise TypeError("JSON keys must be strings")
            _native(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _native(child, depth + 1)
    elif value is not None and type(value) not in (str, int, float, bool):
        raise TypeError("Native JSON required")
    elif type(value) is float and not math.isfinite(value):
        raise ValueError("Finite JSON values required")


def _question(question, limit=MAX_QUESTION_CHARS):
    if type(question) is not str or not question.strip() or len(question) > limit:
        raise ValueError(
            "Original nonempty question exceeds parser character budget or type"
        )
    try:
        question.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("Question is not valid Unicode") from exc


def _validate_annotation(question, a):
    _question(question)
    _native(a)
    fields = {
        "raw_text",
        "raw_sha256",
        "coordinate_system",
        "tokens",
        "sentences",
        "lossless_input_cover",
        "linguistic_proposals",
        "protected_token_indices",
        "all_token_indices_retained",
        "semantic_obligation_completeness",
        "support_or_permissions",
    }
    if type(a) is not dict or set(a) != fields:
        raise ValueError("Annotation schema mismatch")
    for key, expected in {
        "raw_text": question,
        "raw_sha256": hashlib.sha256(question.encode()).hexdigest(),
        "coordinate_system": "python-unicode-codepoints",
        "semantic_obligation_completeness": "NOT_ESTABLISHED",
        "support_or_permissions": "NOT_ASSESSED",
    }.items():
        _same(a[key], expected)
    tokens = a["tokens"]
    if type(tokens) is not list or not 0 < len(tokens) <= len(question):
        raise ValueError("Token inventory missing or oversized")
    _validate_tokens(question, tokens)
    sentences = _validate_sentences(question, a["sentences"], tokens)
    _same(a["lossless_input_cover"], _cover(question, tokens))
    _same(a["all_token_indices_retained"], list(range(len(tokens))))
    _same(
        a["protected_token_indices"],
        [t["i"] for t in tokens if t["dep"] in _PROTECTED or t["tag"] == "MD"],
    )
    _same(a["linguistic_proposals"], _proposals(tokens, sentences))
    return deepcopy(a)


def _validate_tokens(raw, tokens):
    cursor = 0
    keys = {
        "i",
        "start",
        "end",
        "text",
        "whitespace",
        "pos",
        "tag",
        "dep",
        "head",
        "lemma",
        "morph",
        "sentence_start",
        "children",
    }
    for i, token in enumerate(tokens):
        cursor = _validate_token(raw, token, i, cursor, len(tokens), keys)
    if cursor != len(raw):
        raise ValueError("Tokens/whitespace do not cover original input")
    for i, token in enumerate(tokens):
        expected_children = [
            j for j, t in enumerate(tokens) if j != i and t["head"] == i
        ]
        _same(token["children"], expected_children)
        seen = set()
        head = i
        while tokens[head]["head"] != head:
            if head in seen:
                raise ValueError("Cyclic dependency graph")
            seen.add(head)
            head = tokens[head]["head"]


def _validate_sentences(raw, sentences, tokens):
    if type(sentences) is not list or not sentences:
        raise ValueError("Sentence inventory missing")
    cursor = 0
    for s in sentences:
        if (
            type(s) is not dict
            or set(s) != {"start", "end", "text", "token_start", "token_end"}
            or any(
                type(s[k]) is not int
                for k in ("start", "end", "token_start", "token_end")
            )
        ):
            raise ValueError("Sentence schema/types invalid")
        left, right = s["token_start"], s["token_end"]
        if left != cursor or not left < right <= len(tokens):
            raise ValueError("Sentences do not partition token inventory")
        _same(
            {k: s[k] for k in ("start", "end", "text")},
            {
                "start": tokens[left]["start"],
                "end": tokens[right - 1]["end"],
                "text": raw[tokens[left]["start"] : tokens[right - 1]["end"]],
            },
        )
        _sentence_graph(tokens, left, right)
        cursor = right
    if cursor != len(tokens):
        raise ValueError("Missing sentence tokens")
    return sentences


def _validate_token(raw, token, i, cursor, count, keys):
    if type(token) is not dict or set(token) != keys:
        raise ValueError("Token schema mismatch")
    if any(type(token[k]) is not int for k in ("i", "start", "end", "head")):
        raise ValueError("Token integer fields invalid")
    if (
        token["i"] != i
        or token["start"] != cursor
        or not cursor < token["end"] <= len(raw)
        or not 0 <= token["head"] < count
    ):
        raise ValueError("Token coordinates/heads invalid")
    if (
        any(
            type(token[k]) is not str
            for k in ("text", "whitespace", "pos", "tag", "dep", "lemma", "morph")
        )
        or type(token["sentence_start"]) is not bool
    ):
        raise ValueError("Token annotation types invalid")
    if (
        token["pos"] not in _POS
        or token["tag"] not in _TAGS
        or token["dep"] not in _DEPS
    ):
        raise ValueError("Token labels missing or unknown")
    if raw[token["start"] : token["end"]] != token["text"] or (
        token["whitespace"] and not token["whitespace"].isspace()
    ):
        raise ValueError("Original token literal mismatch")
    cursor = token["end"] + len(token["whitespace"])
    if raw[token["end"] : cursor] != token["whitespace"]:
        raise ValueError("Original whitespace mismatch")
    return cursor


def _sentence_graph(tokens, left, right):
    roots = []
    for i in range(left, right):
        t = tokens[i]
        if not left <= t["head"] < right or t["sentence_start"] is not (i == left):
            raise ValueError("Sentence/head/start mismatch")
        if t["head"] == i:
            roots.append(i)
        if (t["dep"] == "ROOT") != (t["head"] == i):
            raise ValueError("Root/head mismatch")
    if len(roots) != 1:
        raise ValueError("Sentence requires one graph root")


def _cover(raw, tokens):
    result = []
    cursor = 0
    for t in tokens:
        if t["start"] > cursor:
            result.append(
                {
                    "start": cursor,
                    "end": t["start"],
                    "kind": "raw-gap",
                    "text": raw[cursor : t["start"]],
                }
            )
        result.append(
            {
                "start": t["start"],
                "end": t["end"],
                "kind": "raw-token",
                "text": t["text"],
            }
        )
        cursor = t["end"]
    if cursor < len(raw):
        result.append(
            {"start": cursor, "end": len(raw), "kind": "raw-gap", "text": raw[cursor:]}
        )
    return result


def _proposals(tokens, sentences):
    result = []
    for t in tokens:
        if t["pos"] not in {"VERB", "AUX"} and t["dep"] not in _ANCHORS:
            continue
        descendants = set()
        pending = [t["i"]]
        while pending:
            i = pending.pop()
            descendants.add(i)
            pending.extend(tokens[i]["children"])
        s = next(s for s in sentences if s["token_start"] <= t["i"] < s["token_end"])
        result.append(
            {
                "anchor_token": t["i"],
                "surface": t["text"],
                "dep": t["dep"],
                "sentence_range": {"start": s["start"], "end": s["end"]},
                "subtree_token_indices": sorted(descendants),
                "status": "unresolved_linguistic_proposal",
                "note": _NOTE,
            }
        )
    return result


def _annotation(raw, doc):
    tokens = [
        {
            "i": t.i,
            "start": t.idx,
            "end": t.idx + len(t.text),
            "text": t.text,
            "whitespace": t.whitespace_,
            "pos": t.pos_,
            "tag": t.tag_,
            "dep": t.dep_,
            "head": t.head.i,
            "lemma": t.lemma_,
            "morph": str(t.morph),
            "sentence_start": t.is_sent_start,
            "children": [c.i for c in t.children],
        }
        for t in doc
    ]
    sentences = [
        {
            "start": s.start_char,
            "end": s.end_char,
            "text": raw[s.start_char : s.end_char],
            "token_start": s.start,
            "token_end": s.end,
        }
        for s in doc.sents
    ]
    return {
        "raw_text": raw,
        "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "coordinate_system": "python-unicode-codepoints",
        "tokens": tokens,
        "sentences": sentences,
        "lossless_input_cover": _cover(raw, tokens),
        "linguistic_proposals": _proposals(tokens, sentences),
        "protected_token_indices": [
            t["i"] for t in tokens if t["dep"] in _PROTECTED or t["tag"] == "MD"
        ],
        "all_token_indices_retained": list(range(len(tokens))),
        "semantic_obligation_completeness": "NOT_ESTABLISHED",
        "support_or_permissions": "NOT_ASSESSED",
    }


def _verify_library(identity):
    distribution = importlib.metadata.distribution("spacy")
    if distribution.version != identity["library_version"]:
        raise ValueError("Unapproved optional parser library version")
    try:
        location = str(distribution.locate_file("spacy"))
    except (TypeError, ValueError) as exc:
        raise ValueError("Optional parser library location is invalid") from exc
    if not location.strip() or "\x00" in location:
        raise ValueError("Optional parser library location is empty or invalid")
    package = Path(location)
    if not package.is_absolute() or not package.is_dir():
        raise ValueError(
            "Optional parser library location must be an absolute directory"
        )
    global _VERIFIED_LIBRARY
    if package != _VERIFIED_LIBRARY:
        files = {
            "spacy/" + p.relative_to(package).as_posix(): hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
            for p in package.rglob("*")
            if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts
        }
        if (
            _digest(files) != identity["library_file_manifest_sha256"]
            or len(files) != identity["library_file_count"]
        ):
            raise ValueError("Optional parser library file hash mismatch")
        _VERIFIED_LIBRARY = package
    return package


def _load_pipeline(path):
    _validate_plugins()
    identity = parser_identity()
    package = _verify_library(identity)
    module = importlib.util.find_spec("spacy")
    origin = None if module is None else module.origin
    if (
        not isinstance(origin, str)
        or not origin.strip()
        or "\x00" in origin
        or not Path(origin).is_absolute()
        or Path(origin).resolve() != (package / "__init__.py").resolve()
    ):
        raise ValueError("Optional parser library import origin mismatch")
    if path not in _PIPELINES:
        spacy = importlib.import_module("spacy")
        if spacy.require_cpu() is not True:
            raise ValueError("CPU parser unavailable")
        nlp = spacy.load(path, exclude=identity["excluded_components"])
        if (
            nlp.pipe_names != identity["pipeline"]
            or nlp.meta["version"] != identity["model_version"]
            or any(
                component.model.ops.device_type != "cpu"
                for _, component in nlp.pipeline
                if getattr(component, "model", None) is not None
            )
        ):
            raise ValueError("Unexpected pipeline/model/device")
        _PIPELINES[path] = nlp
    return _PIPELINES[path]


def _validate_plugins():
    approved = frozenset(APPROVED_ENTRY_POINTS)
    for distribution in importlib.metadata.distributions():
        for entry in distribution.entry_points:
            if (
                entry.group.startswith("spacy")
                and (
                    distribution.metadata["Name"],
                    entry.group,
                    entry.name,
                    entry.value,
                )
                not in approved
            ):
                raise ValueError("Unapproved optional parser plugin entry point")
