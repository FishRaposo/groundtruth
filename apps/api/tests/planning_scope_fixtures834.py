"""UNITONLY scope inputs; no inference or file writes."""

import hashlib
import json
import re

from app.services import planning_declarations as d
from app.services.staged_request import compile_request

from tests.staged_planning_fixtures834 import LABELS as REQUEST
from tests.test_planning_declarations import capture


def source(body, ident):
    # Graphs are explicitly synthetic. All lexical source semantics are read by
    # the actual existing source-cover parser, never these opaque dependencies.
    words = re.findall(r"[A-Za-z]+|[.!?]", body)
    rows = [
        (
            word,
            "PUNCT" if word in ".!?" else "NOUN",
            word.lower(),
            "ROOT" if i == 0 else "dep",
            0,
        )
        for i, word in enumerate(words)
    ]
    actual, cap = capture([rows])
    assert actual == body, (actual, body)
    identity = d.SourceIdentity(
        ident,
        1,
        hashlib.sha256(body.encode()).hexdigest(),
        "UNITONLY-workspace",
        "UNITONLY-" + ident,
    )
    snapshot = d.SourceSnapshot(
        identity,
        "UNTRUSTED Cedar title",
        body,
        "{}",
        (d.SourceChunk(ident + "-chunk", 0, d.RawRange(0, len(body), body)),),
    )
    caps = d.SourceCaptures(
        identity, (d.CaptureWindow(0, len(body), d.canonical(cap)),)
    )
    return snapshot, caps


def inputs(*bodies):
    pairs = [source(body, "UNITONLY-" + str(i)) for i, body in enumerate(bodies)]
    snapshots = tuple(x[0] for x in pairs)
    captures = tuple(x[1] for x in pairs)
    manifest = d.PlanningUniverse(
        d.canonical({"contract": "UNITONLY-scope-scan"}),
        tuple(s.identity for s in snapshots),
        "bounded_authorized_scan",
    )
    question, cap = capture([REQUEST])
    return compile_request(question, cap), manifest, snapshots, captures


def request_modifier(word, pos, dep, lemma=None):
    rows = [(t, p, lemma, r, h + 1 if h >= 1 else h) for t, p, lemma, r, h in REQUEST]
    rows.insert(1, (word, pos, lemma or word, dep, 3))
    q, cap = capture([rows])
    return compile_request(q, cap)


def retain_evidence(label, partial, result):
    packet = {"partial": partial.record(), "result": result}
    assert json.loads(json.dumps(packet)) == packet
