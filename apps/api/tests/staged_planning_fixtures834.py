"""UNITONLY request fixture; reuse actual capture helper."""

from tests.test_planning_declarations import capture

LABELS = [
    ("List", "VERB", "list", "ROOT", 0),
    ("role", "NOUN", "role", "compound", 2),
    ("labels", "NOUN", "label", "dobj", 0),
    ("for", "ADP", "for", "prep", 2),
    ("Cedar", "PROPN", "Cedar", "compound", 5),
    ("inspection", "NOUN", "inspection", "pobj", 3),
    (".", "PUNCT", ".", "punct", 0),
]


def question(rows=LABELS):
    return capture([rows])
