"""Actual engineering syntax captures, plus explicitly UNITONLY graph fixtures.

No source authority, model correctness, support or application quality is proved.
"""

import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

SERVICES = Path(__file__).resolve().parents[1] / "app/services"
from app.services.linguistic_source_scope import (  # noqa: E402
    source_scope,
    validate_source_scope,
)
from app.services.request_parser import (  # noqa: E402
    _cover,
    _proposals,
    make_capture,
)

ACTUAL = json.loads(
    (
        Path(__file__).parent / "fixtures/linguistic_source_scope_engineering.json"
    ).read_text(encoding="utf-8")
)


def identity(body):
    return {
        "document_id": "engineering-source",
        "document_version": 3,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
    }


def build(row, topic):
    return source_scope(
        row["body"], identity(row["body"]), row["windows"], asked_topic=topic
    )


# Defect: returning discovery seeds or dropping gaps fails the whole immutable cover.
def test_actual_source_cover_is_exact_from_zero_through_immutable_eof():
    row = ACTUAL[0]
    result = build(row, "ordinary Amber weave routine")
    assert result["contract"] == "declared-source-scope-cover-v2"
    assert "".join(unit["text"] for unit in result["units"]) == row["body"]
    cursor = 0
    for unit in result["units"]:
        assert unit["start"] == cursor < unit["end"]
        assert row["body"][unit["start"] : unit["end"]] == unit["text"]
        cursor = unit["end"]
    assert cursor == len(row["body"])
    assert validate_source_scope(
        result,
        row["body"],
        identity(row["body"]),
        row["windows"],
        asked_topic="ordinary Amber weave routine",
    )


def test_unlisted_action_lemmas_inherit_only_an_explicit_operative_declaration():
    result = build(ACTUAL[0], "ordinary Amber weave routine")
    units = [u for u in result["units"] if u["kind"] != "separator"]
    assert units[0]["kind"] == "governing_declaration"
    assert units[1]["kind"] == units[2]["kind"] == "instruction"
    assert "unbraid" in units[2]["text"]
    assert all(u["scope_relation"] == "literal_topic_match_candidate" for u in units)
    assert units[2]["scope"]["inherited"] is True
    assert units[2]["scope"]["disclosure_required"] is True
    assert all(
        o["status"] == "pending_independent_discharge"
        for o in result["consumer_obligations"]
    )


def test_role_targets_are_full_literal_nps_with_modifiers_and_different_named_scope():
    result = build(ACTUAL[2], "ordinary Lumen session")
    units = [u for u in result["units"] if u["kind"] != "separator"]
    assert [u["kind"] for u in units] == ["role_assignment"] * 3
    assert units[0]["role_facts"][0]["actor"]["text"] == "the records clerk"
    assert units[0]["scope"]["target"]["text"] == "the ordinary Lumen session"
    assert units[1]["scope"]["target"]["text"] == "the Lumen session"
    assert units[1]["scope_relation"] == "unresolved"
    assert units[2]["scope_relation"] == "different_named_scope_candidate"
    assert units[2]["exclusion_candidate"] is True


def test_global_governor_and_conditions_cannot_be_dropped_for_local_context():
    result = build(ACTUAL[4], "Amber review")
    units = [u for u in result["units"] if u["kind"] != "separator"]
    assert any(u["kind"] == "global_governor" for u in units)
    conditional = next(u for u in units if u["conditions"])
    assert conditional["conditions"][0]["text"] == conditional["text"].strip()
    assert not any(u["exclusion_candidate"] for u in units)
    assert result["blocking_units"]
    reference = next(u for u in units if u["references"])
    assert reference["reference_closure"] == "pending_actual_reference_resolution"


def test_embedded_example_and_fenced_declarations_never_create_operative_scope():
    result = build(ACTUAL[5], "Amber review")
    assert not any(u["kind"] == "governing_declaration" for u in result["units"])
    assert not any(u["exclusion_candidate"] for u in result["units"])


def test_title_alone_and_unknown_factual_fields_are_not_safe_exclusion():
    result = build(ACTUAL[6], "Boreal review")
    assert not any(u["scope"] for u in result["units"])
    assert not any(u["exclusion_candidate"] for u in result["units"])
    assert any(
        "interval" in u["text"] and u["kind"] == "unknown" for u in result["units"]
    )


@pytest.mark.parametrize(
    "change",
    [
        "body",
        "hash",
        "version_bool",
        "window_bool",
        "window_gap",
        "window_end",
        "capture_question",
        "capture_model",
    ],
)
def test_actual_inputs_and_window_capture_identity_are_mandatory(change):
    row = deepcopy(ACTUAL[0])
    body = row["body"]
    bound = identity(body)
    if change == "body":
        body += "x"
    elif change == "hash":
        bound["content_hash"] = "0" * 64
    elif change == "version_bool":
        bound["document_version"] = True
    elif change == "window_bool":
        row["windows"][0]["start"] = False
    elif change == "window_gap":
        row["windows"][0]["start"] = 1
    elif change == "window_end":
        row["windows"][0]["end"] -= 1
    elif change == "capture_question":
        row["windows"][0]["capture"]["annotation"]["raw_text"] += "x"
    else:
        row["windows"][0]["capture"]["parser"]["device"] = "gpu"
    with pytest.raises(ValueError):
        source_scope(body, bound, row["windows"], asked_topic="Amber review")


@pytest.mark.parametrize(
    "change",
    ["range_bool", "tail", "relation", "scope", "resolved_guard", "extra", "tuple"],
)
def test_producer_record_must_reconstruct_from_all_actual_inputs(change):
    row = ACTUAL[0]
    topic = "ordinary Amber weave routine"
    record = build(row, topic)
    if change == "range_bool":
        record["units"][0]["start"] = False
    elif change == "tail":
        record["units"].pop()
    elif change == "relation":
        record["units"][0]["scope_relation"] = "irrelevant"
    elif change == "scope":
        record["units"][0]["scope"]["target"]["text"] = "Boreal review"
    elif change == "resolved_guard":
        record["consumer_obligations"][0]["status"] = "supported"
    elif change == "extra":
        record["publishable"] = True
    else:
        record["units"] = tuple(record["units"])
    assert not validate_source_scope(
        record, row["body"], identity(row["body"]), row["windows"], asked_topic=topic
    )


def unitonly_capture(raw, specification):
    """UNITONLY supplied graph; derived graph fields use621pure validator helpers."""
    tokens = []
    cursor = 0
    for i, (text, pos, dep, head, lemma) in enumerate(specification):
        start = raw.index(text, cursor)
        end = start + len(text)
        tokens.append(
            {
                "i": i,
                "start": start,
                "end": end,
                "text": text,
                "whitespace": "",
                "pos": pos,
                "tag": "NNP"
                if pos == "PROPN"
                else "VB"
                if pos == "VERB"
                else "."
                if pos == "PUNCT"
                else "NN",
                "dep": dep,
                "head": head,
                "lemma": lemma,
                "morph": "",
                "sentence_start": i == 0,
                "children": [],
            }
        )
        cursor = end
    for i, t in enumerate(tokens):
        right = tokens[i + 1]["start"] if i + 1 < len(tokens) else len(raw)
        t["whitespace"] = raw[t["end"] : right]
        t["children"] = [j for j, c in enumerate(tokens) if j != i and c["head"] == i]
    sentences = [
        {
            "start": tokens[0]["start"],
            "end": tokens[-1]["end"],
            "text": raw[tokens[0]["start"] : tokens[-1]["end"]],
            "token_start": 0,
            "token_end": len(tokens),
        }
    ]
    return make_capture(
        {
            "raw_text": raw,
            "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            "coordinate_system": "python-unicode-codepoints",
            "tokens": tokens,
            "sentences": sentences,
            "lossless_input_cover": _cover(raw, tokens),
            "linguistic_proposals": _proposals(tokens, sentences),
            "protected_token_indices": [
                t["i"]
                for t in tokens
                if t["dep"] in {"neg", "cc", "conj", "mark", "aux", "auxpass", "nummod"}
                or t["tag"] == "MD"
            ],
            "all_token_indices_retained": list(range(len(tokens))),
            "semantic_obligation_completeness": "NOT_ESTABLISHED",
            "support_or_permissions": "NOT_ASSESSED",
        }
    )


def test_unitonly_unicode_named_scope_uses_codepoints_not_casefold_offsets():
    raw = "Instructions govern Straße 🪶 only."
    specs = [
        ("Instructions", "NOUN", "nsubj", 1, "instruction"),
        ("govern", "VERB", "ROOT", 1, "govern"),
        ("Straße", "PROPN", "dobj", 1, "Straße"),
        ("🪶", "SYM", "compound", 2, "🪶"),
        ("only", "ADV", "advmod", 1, "only"),
        (".", "PUNCT", "punct", 1, "."),
    ]
    record = source_scope(
        raw,
        identity(raw),
        [{"start": 0, "end": len(raw), "capture": unitonly_capture(raw, specs)}],
        asked_topic="Boreal review",
    )
    unit = record["units"][0]
    assert unit["scope"]["target"]["text"] == "Straße 🪶"
    target = unit["scope"]["target"]
    assert raw[target["start"] : target["end"]] == "Straße 🪶"


def test_window_splits_do_not_guess_cross_window_scope_from_unfinished_sentence():
    left = deepcopy(ACTUAL[0]["windows"][0]["capture"])
    # Whole valid captures can be concatenated; the absent separator is literal.
    first = left["annotation"]["raw_text"]
    second = ACTUAL[2]["body"]
    body = first + second
    windows = [
        {"start": 0, "end": len(first), "capture": left},
        {
            "start": len(first),
            "end": len(body),
            "capture": ACTUAL[2]["windows"][0]["capture"],
        },
    ]
    result = source_scope(body, identity(body), windows, asked_topic="Amber review")
    assert "".join(u["text"] for u in result["units"]) == body
    assert any("capture_boundary" in u["unresolved"] for u in result["units"])


def unitonly_source(parts, topic="Amber review"):
    windows = []
    body = ""
    for raw, spec in parts:
        start = len(body)
        body += raw
        windows.append(
            {"start": start, "end": len(body), "capture": unitonly_capture(raw, spec)}
        )
    return source_scope(body, identity(body), windows, asked_topic=topic)


DECL_RAW = "Instructions govern Boreal review only. "
DECL_SPEC = [
    ("Instructions", "NOUN", "nsubj", 1, "instruction"),
    ("govern", "VERB", "ROOT", 1, "govern"),
    ("Boreal", "PROPN", "compound", 3, "Boreal"),
    ("review", "NOUN", "dobj", 1, "review"),
    ("only", "ADV", "advmod", 1, "only"),
    (".", "PUNCT", "punct", 1, "."),
]


def test_unitonly_negated_declaration_does_not_establish_inherited_context():
    raw = "This note does not apply to Boreal review. "
    spec = [
        ("This", "DET", "det", 1, "this"),
        ("note", "NOUN", "nsubj", 4, "note"),
        ("does", "AUX", "aux", 4, "do"),
        ("not", "PART", "neg", 4, "not"),
        ("apply", "VERB", "ROOT", 4, "apply"),
        ("to", "ADP", "prep", 4, "to"),
        ("Boreal", "PROPN", "compound", 7, "Boreal"),
        ("review", "NOUN", "pobj", 5, "review"),
        (".", "PUNCT", "punct", 4, "."),
    ]
    result = unitonly_source([(raw, spec)])
    assert not any(u["exclusion_candidate"] for u in result["units"])
    assert not any(
        u["scope"] and u["scope"]["full_governing_scope_candidate"]
        for u in result["units"]
    )


def test_unitonly_single_quoted_declaration_is_not_operative():
    raw = "'Instructions govern Boreal review only.'"
    spec = [
        ("'", "PUNCT", "punct", 2, "'"),
        ("Instructions", "NOUN", "nsubj", 2, "instruction"),
        ("govern", "VERB", "ROOT", 2, "govern"),
        ("Boreal", "PROPN", "compound", 4, "Boreal"),
        ("review", "NOUN", "dobj", 2, "review"),
        ("only", "ADV", "advmod", 2, "only"),
        (".", "PUNCT", "punct", 2, "."),
        ("'", "PUNCT", "punct", 2, "'"),
    ]
    result = unitonly_source([(raw, spec)])
    assert not any(u["scope"] for u in result["units"])


def test_unitonly_secondary_actor_and_modal_clause_cannot_inherit_local_scope():
    raw = "Rotate spindle; everyone must report."
    spec = [
        ("Rotate", "VERB", "ROOT", 0, "rotate"),
        ("spindle", "NOUN", "dobj", 0, "spindle"),
        (";", "PUNCT", "punct", 0, ";"),
        ("everyone", "PRON", "nsubj", 5, "everyone"),
        ("must", "AUX", "aux", 5, "must"),
        ("report", "VERB", "parataxis", 0, "report"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    result = unitonly_source([(DECL_RAW, DECL_SPEC), (raw, spec)])
    assert not any(u["exclusion_candidate"] for u in result["units"])
    assert result["blocking_units"]
    assert any(u["modality"] for u in result["units"])


def test_unitonly_fronted_for_scope_is_local_to_its_whole_instruction():
    raw = "For Boreal review, rotate spindle."
    spec = [
        ("For", "ADP", "prep", 4, "for"),
        ("Boreal", "PROPN", "compound", 2, "Boreal"),
        ("review", "NOUN", "pobj", 0, "review"),
        (",", "PUNCT", "punct", 4, ","),
        ("rotate", "VERB", "ROOT", 4, "rotate"),
        ("spindle", "NOUN", "dobj", 4, "spindle"),
        (".", "PUNCT", "punct", 4, "."),
    ]
    result = unitonly_source([(raw, spec)])
    unit = result["units"][0]
    assert (
        unit["kind"] == "instruction"
        and unit["scope"]["target"]["text"] == "Boreal review"
    )
    assert not unit["scope"]["inherited"]
    assert unit["exclusion_candidate"]


def test_unitonly_scoped_external_reference_is_retained_without_claiming_closure():
    raw = "Follow the required appendix Delta."
    spec = [
        ("Follow", "VERB", "ROOT", 0, "follow"),
        ("the", "DET", "det", 3, "the"),
        ("required", "VERB", "amod", 3, "require"),
        ("appendix", "NOUN", "dobj", 0, "appendix"),
        ("Delta", "PROPN", "appos", 3, "Delta"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    result = unitonly_source([(DECL_RAW, DECL_SPEC), (raw, spec)])
    unit = next(u for u in result["units"] if u["kind"] == "reference")
    assert unit["scope"]["target"]["text"] == "Boreal review"
    assert unit["scope_relation"] == "different_named_scope_candidate"
    assert unit["reference_closure"] == "pending_actual_reference_resolution"
    assert result["reference_inventory_complete"] is False
    assert any(
        o["kind"] == "actual_required_reference_closure"
        and o["status"] == "pending_independent_discharge"
        for o in result["consumer_obligations"]
    )


def test_unitonly_unclosed_quotation_blocks_inherited_negative_pruning():
    raw = "'Rotate spindle."
    spec = [
        ("'", "PUNCT", "punct", 1, "'"),
        ("Rotate", "VERB", "ROOT", 1, "rotate"),
        ("spindle", "NOUN", "dobj", 1, "spindle"),
        (".", "PUNCT", "punct", 1, "."),
    ]
    result = unitonly_source([(DECL_RAW, DECL_SPEC), (raw, spec)])
    assert result["blocking_units"]
    assert not any(u["exclusion_candidate"] for u in result["units"])


def test_unitonly_whitespace_does_not_prove_an_internal_capture_sentence_boundary():
    raw = "Rotate spindle."
    spec = [
        ("Rotate", "VERB", "ROOT", 0, "rotate"),
        ("spindle", "NOUN", "dobj", 0, "spindle"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    result = unitonly_source([(DECL_RAW.replace(".", ""), DECL_SPEC[:-1]), (raw, spec)])
    assert any("capture_boundary" in u["unresolved"] for u in result["units"])
    assert not any(u["exclusion_candidate"] for u in result["units"])


def test_unitonly_opposing_explicit_role_target_blocks_bare_context_inheritance():
    raw = "Mira leads Amber review. "
    spec = [
        ("Mira", "PROPN", "nsubj", 1, "Mira"),
        ("leads", "VERB", "ROOT", 1, "lead"),
        ("Amber", "PROPN", "compound", 3, "Amber"),
        ("review", "NOUN", "dobj", 1, "review"),
        (".", "PUNCT", "punct", 1, "."),
    ]
    command = "Rotate spindle."
    command_spec = [
        ("Rotate", "VERB", "ROOT", 0, "rotate"),
        ("spindle", "NOUN", "dobj", 0, "spindle"),
        (".", "PUNCT", "punct", 0, "."),
    ]
    result = unitonly_source(
        [(DECL_RAW, DECL_SPEC), (raw, spec), (command, command_spec)]
    )
    unit = next(u for u in result["units"] if u["text"] == command)
    assert unit["scope"] is None
    assert result["blocking_units"]


def test_pure_replay_does_not_import_parser_or_application_runtime():
    script = r"""
import importlib.abc,sys,types,json,hashlib
from pathlib import Path
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if (fullname.split('.')[0] in {'spacy','sqlalchemy','torch','transformers',
                                      'pydantic','openai'}
            or fullname.startswith(('app.models','app.db','app.config','app.main'))):
            raise AssertionError('Runtime import: '+fullname)
sys.meta_path.insert(0,Guard())
services=Path(sys.argv[1])
for name,path in [('app',services.parent),('app.services',services)]:
    package=types.ModuleType(name)
    package.__path__=[str(path)]
    sys.modules[name]=package
from app.services.linguistic_source_scope import source_scope,validate_source_scope
row=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))[0]
body=row['body']
identity={'document_id':'unit','document_version':1,
          'content_hash':hashlib.sha256(body.encode()).hexdigest()}
record=source_scope(body,identity,row['windows'],asked_topic='Amber weave routine')
assert validate_source_scope(record,body,identity,row['windows'],
                             asked_topic='Amber weave routine')
assert ''.join(u['text'] for u in record['units'])==body
print('pure source replay')
"""
    fixture = (
        Path(__file__).parent / "fixtures/linguistic_source_scope_engineering.json"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(SERVICES), str(fixture)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "pure source replay"


def test_unitonly_bare_fixture_noun_is_unknown_not_a_whole_document_test_container():
    raw = "Fixture. "
    spec = [("Fixture", "PROPN", "ROOT", 0, "Fixture"), (".", "PUNCT", "punct", 0, ".")]
    result = unitonly_source([(raw, spec), (DECL_RAW, DECL_SPEC)])
    unit = result["units"][0]
    assert unit["kind"] == "unknown"
    assert result["blocking_units"]
    assert any(u["kind"] == "governing_declaration" for u in result["units"])
