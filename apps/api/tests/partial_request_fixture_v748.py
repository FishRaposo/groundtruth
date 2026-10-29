"""Retained actual graphs plus explicitly UNITONLY hand-specified syntax controls."""

import hashlib
import json
from pathlib import Path

from app.services.request_parser import _PROTECTED, _cover, _proposals, make_capture

P = Path(__file__).resolve().parent
DATA = json.loads(
    (P / "fixtures/request_partial_captures_v748.json").read_text(encoding="utf-8")
)
ACTUAL = DATA["rows"]
UNITONLY_734 = DATA["unitonly_734"]
UNITONLY_744 = DATA["unitonly_744"]


def actual(identifier):
    row = next(r for r in ACTUAL if r["id"] == identifier)
    return row.get("capture") or make_capture(row["annotation"])


def unitonly(words):
    """Rows: exact token text, lemma, POS, tag, dependency, final head index."""
    tokens = []
    raw = ""
    for i, (word, lemma, pos, tag, dep, head) in enumerate(words):
        whitespace = "" if i == len(words) - 1 else " "
        tokens.append(
            {
                "i": i,
                "text": word,
                "lemma": lemma,
                "pos": pos,
                "tag": tag,
                "dep": dep,
                "head": head,
                "morph": "",
                "start": len(raw),
                "end": len(raw) + len(word),
                "whitespace": whitespace,
                "sentence_start": i == 0,
                "children": [],
            }
        )
        raw += word + whitespace
    for t in tokens:
        t["children"] = [
            x["i"] for x in tokens if x["head"] == t["i"] and x["i"] != t["i"]
        ]
    sentences = [
        {
            "start": 0,
            "end": len(raw),
            "text": raw,
            "token_start": 0,
            "token_end": len(tokens),
        }
    ]
    a = {
        "raw_text": raw,
        "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "coordinate_system": "python-unicode-codepoints",
        "semantic_obligation_completeness": "NOT_ESTABLISHED",
        "support_or_permissions": "NOT_ASSESSED",
        "tokens": tokens,
        "sentences": sentences,
        "lossless_input_cover": _cover(raw, tokens),
        "linguistic_proposals": _proposals(tokens, sentences),
        "protected_token_indices": [
            t["i"] for t in tokens if t["dep"] in _PROTECTED or t["tag"] == "MD"
        ],
        "all_token_indices_retained": list(range(len(tokens))),
    }
    return make_capture(a)


LABELS = unitonly(
    [
        ("List", "list", "VERB", "VB", "ROOT", 0),
        ("the", "the", "DET", "DT", "det", 4),
        ("stated", "stated", "ADJ", "JJ", "amod", 4),
        ("role", "role", "NOUN", "NN", "compound", 4),
        ("labels", "label", "NOUN", "NNS", "dobj", 0),
        ("for", "for", "ADP", "IN", "prep", 4),
        ("Cedar", "Cedar", "PROPN", "NNP", "compound", 7),
        ("review", "review", "NOUN", "NN", "pobj", 5),
        (".", ".", "PUNCT", ".", "punct", 0),
    ]
)
INCUMBENTS = unitonly(
    [
        ("Who", "who", "PRON", "WP", "nsubj", 1),
        ("fills", "fill", "VERB", "VBZ", "ROOT", 1),
        ("each", "each", "DET", "DT", "det", 3),
        ("role", "role", "NOUN", "NN", "dobj", 1),
        ("for", "for", "ADP", "IN", "prep", 3),
        ("Cedar", "Cedar", "PROPN", "NNP", "compound", 6),
        ("review", "review", "NOUN", "NN", "pobj", 4),
        ("?", "?", "PUNCT", ".", "punct", 1),
    ]
)
DEPENDENT = unitonly(
    [
        ("Who", "who", "PRON", "WP", "nsubj", 1),
        ("fills", "fill", "VERB", "VBZ", "ROOT", 1),
        ("each", "each", "DET", "DT", "det", 3),
        ("role", "role", "NOUN", "NN", "dobj", 1),
        ("for", "for", "ADP", "IN", "prep", 3),
        ("Cedar", "Cedar", "PROPN", "NNP", "compound", 6),
        ("review", "review", "NOUN", "NN", "pobj", 4),
        ("and", "and", "CCONJ", "CC", "cc", 1),
        ("give", "give", "VERB", "VB", "conj", 1),
        ("their", "their", "PRON", "PRP$", "poss", 10),
        ("availability", "availability", "NOUN", "NN", "dobj", 8),
        (".", ".", "PUNCT", ".", "punct", 1),
    ]
)
EXTRA_ACTION = unitonly(
    [
        ("List", "list", "VERB", "VB", "ROOT", 0),
        ("role", "role", "NOUN", "NN", "compound", 2),
        ("labels", "label", "NOUN", "NNS", "dobj", 0),
        ("for", "for", "ADP", "IN", "prep", 2),
        ("Cedar", "Cedar", "PROPN", "NNP", "compound", 5),
        ("review", "review", "NOUN", "NN", "pobj", 3),
        ("and", "and", "CCONJ", "CC", "cc", 0),
        ("destroy", "destroy", "VERB", "VB", "conj", 0),
        ("records", "record", "NOUN", "NNS", "dobj", 7),
        (".", ".", "PUNCT", ".", "punct", 0),
    ]
)
EXTERNAL = unitonly(
    [
        ("Give", "give", "VERB", "VB", "ROOT", 0),
        ("the", "the", "DET", "DT", "det", 3),
        ("full", "full", "ADJ", "JJ", "amod", 3),
        ("procedure", "procedure", "NOUN", "NN", "dobj", 0),
        ("for", "for", "ADP", "IN", "prep", 3),
        ("Cedar", "Cedar", "PROPN", "NNP", "compound", 6),
        ("review", "review", "NOUN", "NN", "pobj", 4),
        ("from", "from", "ADP", "IN", "prep", 3),
        ("the", "the", "DET", "DT", "det", 10),
        ("separate", "separate", "ADJ", "JJ", "amod", 10),
        ("manual", "manual", "NOUN", "NN", "pobj", 7),
        (".", ".", "PUNCT", ".", "punct", 0),
    ]
)
