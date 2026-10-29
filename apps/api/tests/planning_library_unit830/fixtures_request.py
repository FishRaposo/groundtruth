"""UNITONLY retained request graphs; application compiler only."""

from .fixtures_source import ASSIGN as ASSIGN
from .fixtures_source import CAT, NAME, capture, source, universe
from .fixtures_source import EXTERNAL as EXTERNAL
from .fixtures_source import UNKNOWN as UNKNOWN

LABELS = [
    ("List", "VERB", "list", "ROOT", 0),
    ("role", "NOUN", "role", "compound", 2),
    ("labels", "NOUN", "label", "dobj", 0),
    ("for", "ADP", "for", "prep", 2),
    ("Cedar", "PROPN", "Cedar", "compound", 5),
    ("inspection", "NOUN", "inspection", "pobj", 3),
    (".", "PUNCT", ".", "punct", 0),
]

ACTORS = [
    ("List", "VERB", "list", "ROOT", 0),
    ("role", "NOUN", "role", "compound", 2),
    ("incumbents", "NOUN", "incumbent", "dobj", 0),
    ("for", "ADP", "for", "prep", 2),
    ("Cedar", "PROPN", "Cedar", "compound", 5),
    ("inspection", "NOUN", "inspection", "pobj", 3),
    (".", "PUNCT", ".", "punct", 0),
]

DEPENDENT = ACTORS[:-1] + [
    ("and", "CCONJ", "and", "cc", 2),
    ("their", "PRON", "their", "poss", 8),
    ("availability", "NOUN", "availability", "conj", 2),
    (".", "PUNCT", ".", "punct", 0),
]


def question(rows=LABELS):
    return capture([rows])


def inputs(groups=(NAME, CAT), *, extra=()):
    pairs = [source(list(groups), doc="UNITONLY-base")] + list(extra)
    snaps = tuple(x[0] for x in pairs)
    caps = tuple(x[1] for x in pairs)
    return universe(snaps), snaps, caps
