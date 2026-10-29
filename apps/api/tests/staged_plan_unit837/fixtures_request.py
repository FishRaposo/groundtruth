"""Retained828 UNITONLY request graphs, no Q runtime dependency."""

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

FIELD = [
    ("Give", "VERB", "give", "ROOT", 0),
    ("quantity", "NOUN", "quantity", "dobj", 0),
    ("for", "ADP", "for", "prep", 1),
    ("Cedar", "PROPN", "Cedar", "compound", 4),
    ("inspection", "NOUN", "inspection", "pobj", 2),
    (".", "PUNCT", ".", "punct", 0),
]
