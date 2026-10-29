"""Prefrozen actual CPU engineering graphs, no answer/source truth labels."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from app.services.linguistic_requirements import plan_request, validate_request_plan
from app.services.request_parser import _PROTECTED, _cover, _proposals, make_capture

F = Path(__file__).parent / "fixtures/dependency_graphs_v634.json"
EXPECTED = [
    ("ordinary-passive", ["quantity", "duration", "location"], True),
    ("ordinary-need", ["quantity", "duration", "location"], True),
    ("procedure-governors", ["procedure"], True),
    ("procedure-extent", ["procedure"], True),
    ("conditional-role", ["owner"], True),
    ("no-assignment", ["owner", "deputy"], True),
    ("availability", ["owner", "availability"], True),
    ("quantity-pronoun", ["location", "quantity", "duration"], True),
    ("polite-ambiguous", ["generic"], False),
    ("unknown-sibling", ["quantity", "generic"], False),
    ("scope-conflict", ["generic"], False),
    ("unit-constraint", ["duration"], True),
    ("unknown-why", ["generic"], False),
    ("conditional-wh", ["owner"], True),
    ("conditional-malformed", ["generic"], False),
    ("qualified-quantity", ["quantity"], True),
    ("meta-report", ["quantity", "duration", "location"], True),
]
EXPECTED += [
    ("joint-role-verbs", ["owner", "deputy"], True),
    ("role-availability-wh", ["owner", "availability"], True),
    ("role-availability-order", ["owner", "availability"], True),
    ("distinct-roles", ["owner", "deputy"], True),
    ("passive-wh-fields", ["quantity", "duration", "location"], True),
    ("procedure-coordinated-governor", ["procedure"], True),
    ("procedure-retained", ["procedure"], True),
    ("polite-procedure-unknown", ["generic"], False),
    ("foreign-role-scope", ["generic", "generic"], False),
    ("role-why", ["owner", "generic"], False),
    ("subject-condition", ["owner"], True),
    ("condition-extra-action", ["owner", "generic"], False),
]


def actual(identifier):
    row = next(
        r for r in json.loads(F.read_text())["captures"] if r["id"] == identifier
    )
    capture = row["capture"]
    return capture["annotation"]["raw_text"], capture


@pytest.mark.parametrize("identifier,kinds,resolved", EXPECTED)
def test_actual_engineering_request_grammar(identifier, kinds, resolved):
    q, cap = actual(identifier)
    p = plan_request(q, cap)
    assert [r.kind for r in p.requirements] == kinds
    assert p.resolved_request is resolved
    assert validate_request_plan(p.record(), question=q, capture=cap)
    assert "".join(t.evidence.text for t in p.consumption) == "".join(
        t["text"] for t in cap["annotation"]["tokens"]
    )
    if identifier.startswith("conditional") and resolved:
        assert p.uses[0].condition_ast
        assert all(s.text in p.requirements[0].question for s in p.uses[0].conditions)
        clause = p.uses[0].condition_ast[0]
        assert clause.subjects and clause.predicate and clause.complements
    if identifier == "no-assignment":
        assert "Nickel review session" in p.uses[0].condition_ast[0].subjects[0].text
        assert p.uses[0].condition_ast[0].negation[0].text == "no"
    if identifier == "quantity-pronoun":
        assert p.requirements[1].topic == "Nickel review"
        assert p.uses[1].references
        assert (
            p.requirements[1].depends_on == ()
        )  # entity anaphora is not evidence-value data
    if identifier == "availability":
        assert p.requirements[1].depends_on == ("r1",)
    if identifier == "qualified-quantity":
        assert "owner-only" in p.requirements[0].question
        assert not p.uses[0].modality  # lexical modifier, not deontic "only"
    assert p.record()["support_or_permissions"] == "NOT_ASSESSED"


def test_unitonly_unknown_np_sibling_is_not_swallowed_by_whole_procedure():
    # Coherent adversarial mutation of actual graph; NOT a new model capture.
    rows = json.loads(F.read_text())["captures"]
    source = next(
        r["capture"]
        for r in rows
        if r["capture"]["annotation"]["raw_text"]
        == "Give the complete Onyx calibration routine."
    )
    a = deepcopy(source["annotation"])
    ts = a["tokens"]
    punct = ts.pop()
    ts[-1]["whitespace"] = " "
    routine = next(t["i"] for t in ts if t["lemma"] == "routine")
    for word, dep, pos, tag, head in [
        ("and", "cc", "CCONJ", "CC", routine),
        ("rotation", "compound", "NOUN", "NN", len(ts) + 2),
        ("angle", "conj", "NOUN", "NN", routine),
    ]:
        t = dict(
            punct,
            i=len(ts),
            text=word,
            lemma=word,
            dep=dep,
            pos=pos,
            tag=tag,
            head=head,
            whitespace=" ",
            morph="",
            sentence_start=False,
        )
        ts.append(t)
    ts.append(dict(punct, i=len(ts)))
    cursor = 0
    for t in ts:
        if t["text"] == ".":
            ts[t["i"] - 1]["whitespace"] = ""
            cursor -= 1
        t["start"], t["end"] = cursor, cursor + len(t["text"])
        cursor = t["end"] + len(t["whitespace"])
        t["children"] = [c["i"] for c in ts if c["head"] == t["i"] and c["i"] != t["i"]]
    q = "".join(t["text"] + t["whitespace"] for t in ts)
    a.update(
        raw_text=q,
        raw_sha256=hashlib.sha256(q.encode()).hexdigest(),
        lossless_input_cover=_cover(q, ts),
        all_token_indices_retained=list(range(len(ts))),
    )
    a["sentences"][0].update(end=len(q), text=q, token_end=len(ts))
    a["linguistic_proposals"] = _proposals(ts, a["sentences"])
    a["protected_token_indices"] = [
        t["i"] for t in ts if t["dep"] in _PROTECTED or t["tag"] == "MD"
    ]
    p = plan_request(q, make_capture(a))
    assert not p.resolved_request
    assert [r.kind for r in p.requirements] == ["procedure", "generic"]
    assert "rotation angle" in p.requirements[1].question
