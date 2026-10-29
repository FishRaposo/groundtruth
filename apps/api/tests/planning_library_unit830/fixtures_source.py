"""UNITONLY dependency graphs from805; app imports only, no Q dependency."""

import hashlib

from app.services import planning_declarations as d
from app.services import request_parser as parser


def deny(*args, **kwargs):
    raise AssertionError("No actual process/socket/native/model action")


def capture(groups):
    """UNITONLY graph constructor; it creates no actual linguistic observation."""
    flat = []
    sentences = []
    cursor = 0
    for group in groups:
        base = len(flat)
        left = cursor
        for i, (text, pos, lemma, dep, head) in enumerate(group):
            ws = (
                "" if i == len(group) - 1 or group[i + 1][0] in {",", ".", ";"} else " "
            )
            if i == len(group) - 1 and group is not groups[-1]:
                ws = " "
            flat.append(
                {
                    "i": base + i,
                    "start": cursor,
                    "end": cursor + len(text),
                    "text": text,
                    "whitespace": ws,
                    "pos": pos,
                    "tag": "MD"
                    if text in {"may", "must", "should"}
                    else "NN"
                    if pos not in {"VERB", "AUX", "PUNCT"}
                    else "VB"
                    if pos in {"VERB", "AUX"}
                    else ".",
                    "dep": dep,
                    "head": base + head,
                    "lemma": lemma,
                    "morph": "",
                    "sentence_start": i == 0,
                    "children": [],
                }
            )
            cursor += len(text) + len(ws)
        sentences.append(
            {
                "start": left,
                "end": flat[-1]["end"],
                "text": "",
                "token_start": base,
                "token_end": len(flat),
            }
        )
    raw = "".join(t["text"] + t["whitespace"] for t in flat)
    for s in sentences:
        s["text"] = raw[s["start"] : s["end"]]
    for t in flat:
        t["children"] = [
            x["i"] for x in flat if x["head"] == t["i"] and x["i"] != t["i"]
        ]
    annotation = {
        "raw_text": raw,
        "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "coordinate_system": "python-unicode-codepoints",
        "tokens": flat,
        "sentences": sentences,
        "lossless_input_cover": parser._cover(raw, flat),
        "linguistic_proposals": parser._proposals(flat, sentences),
        "protected_token_indices": [
            t["i"] for t in flat if t["dep"] in parser._PROTECTED or t["tag"] == "MD"
        ],
        "all_token_indices_retained": list(range(len(flat))),
        "semantic_obligation_completeness": "NOT_ESTABLISHED",
        "support_or_permissions": "NOT_ASSESSED",
    }
    return raw, parser.make_capture(annotation)


CAT = [
    ("Roles", "NOUN", "role", "nsubj", 4),
    ("for", "ADP", "for", "prep", 0),
    ("Cedar", "PROPN", "Cedar", "compound", 3),
    ("inspection", "NOUN", "inspection", "pobj", 1),
    ("are", "AUX", "be", "ROOT", 4),
    ("coordinator", "NOUN", "coordinator", "attr", 4),
    (",", "PUNCT", ",", "punct", 5),
    ("observer", "NOUN", "observer", "conj", 5),
    ("and", "CCONJ", "and", "cc", 5),
    ("recorder", "NOUN", "recorder", "conj", 5),
    (".", "PUNCT", ".", "punct", 4),
]

NAME = [
    ("The", "DET", "the", "det", 1),
    ("activity", "NOUN", "activity", "nsubjpass", 3),
    ("is", "AUX", "be", "auxpass", 3),
    ("called", "VERB", "call", "ROOT", 3),
    ("Cedar", "PROPN", "Cedar", "compound", 5),
    ("inspection", "NOUN", "inspection", "oprd", 3),
    (".", "PUNCT", ".", "punct", 3),
]

ASSIGN = [
    ("The", "DET", "the", "det", 2),
    ("coordinator", "NOUN", "coordinator", "compound", 2),
    ("role", "NOUN", "role", "nsubj", 6),
    ("for", "ADP", "for", "prep", 2),
    ("Cedar", "PROPN", "Cedar", "compound", 5),
    ("inspection", "NOUN", "inspection", "pobj", 3),
    ("is", "AUX", "be", "ROOT", 6),
    ("Rowan", "PROPN", "Rowan", "attr", 6),
    (".", "PUNCT", ".", "punct", 6),
]

FIELD = [
    ("Inspection", "NOUN", "inspection", "compound", 1),
    ("time", "NOUN", "time", "nsubj", 5),
    ("for", "ADP", "for", "prep", 1),
    ("Cedar", "PROPN", "Cedar", "compound", 4),
    ("inspection", "NOUN", "inspection", "pobj", 2),
    ("is", "AUX", "be", "ROOT", 5),
    ("09:00", "NUM", "09:00", "attr", 5),
    (".", "PUNCT", ".", "punct", 5),
]

COND = [
    ("Roles", "NOUN", "role", "nsubj", 6),
    ("for", "ADP", "for", "prep", 0),
    ("Cedar", "PROPN", "Cedar", "compound", 3),
    ("inspection", "NOUN", "inspection", "pobj", 1),
    ("may", "AUX", "may", "aux", 6),
    ("not", "PART", "not", "neg", 6),
    ("be", "AUX", "be", "ROOT", 6),
    ("coordinator", "NOUN", "coordinator", "attr", 6),
    ("and", "CCONJ", "and", "cc", 7),
    ("observer", "NOUN", "observer", "conj", 7),
    ("unless", "SCONJ", "unless", "mark", 12),
    ("permit", "NOUN", "permit", "nsubj", 12),
    ("applies", "VERB", "apply", "advcl", 6),
    (".", "PUNCT", ".", "punct", 6),
]

EXTERNAL = [
    ("Follow", "VERB", "follow", "ROOT", 0),
    ("Note", "NOUN", "note", "dobj", 0),
    ("Amber", "PROPN", "Amber", "appos", 1),
    (".", "PUNCT", ".", "punct", 0),
]

UNKNOWN = [
    ("Perhaps", "ADV", "perhaps", "advmod", 1),
    ("something", "NOUN", "something", "ROOT", 1),
    (".", "PUNCT", ".", "punct", 1),
]


def source(groups, doc="UNITONLY-doc", title="UNITONLY source"):
    body, cap = capture(groups)
    ident = d.SourceIdentity(
        doc, 1, d.body_hash(body), "UNITONLY-workspace", doc + "-snapshot"
    )
    snap = d.SourceSnapshot(
        ident,
        title,
        body,
        d.canonical({"fixture": "UNITONLY"}),
        (d.SourceChunk(doc + "-chunk", 0, d.RawRange(0, len(body), body)),),
    )
    caps = d.SourceCaptures(ident, (d.CaptureWindow(0, len(body), d.canonical(cap)),))
    return snap, caps


def universe(snaps, mode="bounded_authorized_scan"):
    return d.PlanningUniverse(
        d.canonical(
            {
                "fixture": "UNITONLY",
                "workspace": "UNITONLY-workspace",
                "selector": "caller-applied filters; authorization NOT_ASSESSED",
            }
        ),
        tuple(s.identity for s in snaps),
        mode,
    )


def inventory(groups):
    s, c = source(groups)
    return d.declaration_inventory(universe([s]), (s,), (c,))


def of_kind(inv, kind):
    return [x for x in inv.declarations if x.kind == kind]
