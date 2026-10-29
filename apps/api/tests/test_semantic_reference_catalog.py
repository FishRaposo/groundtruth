"""Pure source-bound catalog tests; retained/synthetic captures, no inference."""

import hashlib
import importlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest
from app.services.linguistic_source_scope import _Graph
from app.services.request_parser import (
    _cover,
    _proposals,
    make_capture,
    validate_capture,
)


def module():
    # RED is a behavior assertion, not a collection/import error.
    assert importlib.util.find_spec("app.semantic_reference_catalog") is not None, (
        "The source-bound reference catalog is not implemented"
    )
    return importlib.import_module("app.semantic_reference_catalog")


def mechanical(raw, spec):
    """Complete synthetic capture, independently specified dependency edges."""
    tokens = []
    cursor = 0
    for index, (text, pos, dep, head, lemma) in enumerate(spec):
        start = raw.index(text, cursor)
        cursor = start + len(text)
        tokens.append(
            {
                "i": index,
                "text": text,
                "start": start,
                "end": cursor,
                "whitespace": "",
                "pos": pos,
                "tag": "VB" if pos == "VERB" else "NN",
                "dep": dep,
                "head": head,
                "lemma": lemma,
                "morph": "",
                "sentence_start": index == 0,
                "children": [],
            }
        )
    for i, token in enumerate(tokens):
        right = tokens[i + 1]["start"] if i + 1 < len(tokens) else len(raw)
        token["whitespace"] = raw[token["end"] : right]
        token["children"] = [
            j for j, child in enumerate(tokens) if child["head"] == i and j != i
        ]
    sentences = [
        {
            "start": 0,
            "end": tokens[-1]["end"],
            "text": raw[: tokens[-1]["end"]],
            "token_start": 0,
            "token_end": len(tokens),
        }
    ]
    capture = make_capture(
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
    annotation = validate_capture(raw, capture)
    return _Graph(raw, 0, annotation, 0, len(raw)), {
        "document_id": "mechanical-reference-catalog",
        "document_version": 1,
        "content_hash": hashlib.sha256(raw.encode()).hexdigest(),
    }


def inspect(graph, identity, predicate=0):
    return module().inspect_predicate(
        graph,
        predicate,
        source_identity=identity,
        clause_range={"start": 0, "end": len(graph.body)},
    )


def test_pinned_catalog_is_package_relative_and_metadata_is_not_mutable(monkeypatch):
    # Break: a CWD resource path, unpinned data, or a leaked cached record.
    catalog = module()
    monkeypatch.chdir(Path(__file__).parent / "fixtures")
    metadata = catalog.catalog_metadata()
    assert metadata["payload_sha256"] == (
        "928bab0717a3a37d54074de4ea811bc38831b1f1b9e72fb4bccf50b7b58a266c"
    )
    assert metadata["source_commit"] == "ae8e9cfdc2c0d3414b748763612f1a0a34194cc1"
    metadata["source_commit"] = "changed-by-caller"
    assert catalog.catalog_metadata()["source_commit"] != "changed-by-caller"
    assert "path" not in catalog.catalog_metadata()


def test_oov_is_disclosed_policy_default_not_proof_of_reference_absence():
    # Break: absent dictionary entry becomes supported semantic absence.
    graph, identity = mechanical(
        "Frobnicate the widget.",
        [
            ("Frobnicate", "VERB", "ROOT", 0, "frobnicate"),
            ("the", "DET", "det", 2, "the"),
            ("widget", "NOUN", "dobj", 0, "widget"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    assert record["lexical_status"] == "not_in_resource"
    assert record["potential_instruction_content"] is False
    assert record["unresolved_risk"] is False
    assert (
        record["interpretation"] == "ordinary_literal_arguments_under_declared_policy"
    )
    assert record["actual_sense"] == "NOT_ESTABLISHED"
    assert record["implicit_reference_absence"] == "NOT_ESTABLISHED"


def test_actual654_action_occurrences_do_not_acquire_content_risk_or_entity_facts():
    # Break: blanket semantic-operand gates or unbound noun/participle matching.
    data = json.loads(
        (Path(__file__).parent / "fixtures/source_copy_capture_v654.json").read_text(
            encoding="utf8"
        )
    )
    observed = []
    for window in data["source_windows"]:
        annotation = validate_capture(
            data["body"][window["start"] : window["end"]], window["capture"]
        )
        for sentence in annotation["sentences"]:
            start, end = (window["start"] + sentence[k] for k in ("start", "end"))
            graph = _Graph(data["body"], window["start"], annotation, start, end)
            for index in sorted(graph.indices):
                token = graph.tokens[index]
                if token["pos"] != "VERB" or token["dep"] in {"amod", "aux", "auxpass"}:
                    continue
                if graph.lemma(index) not in {
                    "inspect",
                    "place",
                    "reset",
                    "store",
                    "retain",
                }:
                    continue
                result = module().inspect_predicate(
                    graph,
                    index,
                    source_identity=data["identity"],
                    clause_range={"start": start, "end": end},
                )
                assert not result["potential_instruction_content"]
                assert not result["unresolved_risk"]
                assert result["source_identity"] == data["identity"]
                assert result["actual_sense"] == "NOT_ESTABLISHED"
                observed.append(graph.lemma(index))
    assert observed == ["inspect", "place", "reset", "store", "retain"]


@pytest.mark.parametrize("case", range(5))
def test_retained665_argument_occurrences_raise_potential_or_unresolved_risk(case):
    # Break: dictionary membership without actual slot binding, or missed senses.
    data = json.loads(
        (
            Path(__file__).parent / "fixtures/source_copy_closure_cases_v665.json"
        ).read_text(encoding="utf8")
    )
    raw, spec = data["cases"][case]
    graph, identity = mechanical(raw, spec)
    result = inspect(graph, identity)
    assert result["potential_instruction_content"] or result["unresolved_risk"]
    assert result["analyses"]
    assert result["implicit_reference_absence"] == "NOT_ESTABLISHED"


def test_execute_binds_full_object_not_its_attached_location():
    # Break: flattening every NP into every non-agent slot.
    data = json.loads(
        (
            Path(__file__).parent / "fixtures/source_copy_closure_cases_v665.json"
        ).read_text(encoding="utf8")
    )
    graph, identity = mechanical(*data["cases"][0])
    result = inspect(graph, identity)
    targets = [
        binding["argument"]["text"]
        for row in result["analyses"]
        for binding in row["risk_bindings"]
    ]
    assert "the commands on the wall" in targets
    assert "the wall" not in targets


def test_source_identity_and_clause_boundaries_are_checked():
    # Break: record claims a different body or binds an out-of-clause token.
    graph, identity = mechanical(
        "Execute X.",
        [
            ("Execute", "VERB", "ROOT", 0, "execute"),
            ("X", "NOUN", "dobj", 0, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    with pytest.raises(ValueError):
        inspect(graph, {**identity, "content_hash": "0" * 64})
    with pytest.raises(ValueError):
        module().inspect_predicate(
            graph, 0, source_identity=identity, clause_range={"start": 8, "end": 10}
        )


def test_records_are_independent_of_caller_mutation():
    # Break: public records expose cached lexical data or source dictionaries.
    graph, identity = mechanical(
        "Execute X.",
        [
            ("Execute", "VERB", "ROOT", 0, "execute"),
            ("X", "NOUN", "dobj", 0, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    first = inspect(graph, identity)
    retained = deepcopy(first)
    first["analyses"].clear()
    first["source_identity"]["document_id"] = "changed"
    assert inspect(graph, identity) == retained


def test_multiple_possible_object_bindings_keep_risky_frame_unknown():
    # Break: ambiguous source slots incorrectly become incompatible senses.
    graph, identity = mechanical(
        "Execute Pat X.",
        [
            ("Execute", "VERB", "ROOT", 0, "execute"),
            ("Pat", "PROPN", "dative", 0, "Pat"),
            ("X", "NOUN", "dobj", 0, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    assert record["unresolved_risk"] is True
    act = next(
        row for row in record["analyses"] if row["frame_id"] == "act-114:frame:0"
    )
    assert act["compatibility"] == "unknown"


def test_modifier_participle_is_not_an_action_predicate():
    # Break: source modifiers become independent operative lexical facts.
    graph, identity = mechanical(
        "Provided tokens.",
        [
            ("Provided", "VERB", "amod", 1, "provide"),
            ("tokens", "NOUN", "ROOT", 1, "token"),
            (".", "PUNCT", "punct", 1, "."),
        ],
    )
    with pytest.raises(ValueError):
        inspect(graph, identity)


def test_bound_multiword_particle_has_source_token_identity():
    # Break: base-only lookup drops risk or an unattached word creates the MWE.
    graph, identity = mechanical(
        "Carry X out.",
        [
            ("Carry", "VERB", "ROOT", 0, "carry"),
            ("X", "NOUN", "dobj", 0, "x"),
            ("out", "PART", "prt", 0, "out"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    unit = next(row for row in record["lexical_units"] if row["name"] == "carry_out")
    assert unit["decision"] == "matched"
    assert unit["token_indices"] == [0, 2]
    assert record["potential_instruction_content"]
    assert any(
        row["lexical_unit"] == "carry_out" and row["risk_bindings"]
        for row in record["analyses"]
    )


def test_missing_particle_does_not_inherit_phrasal_member_frames():
    # Break: substring matching invents carry_out for bare carry.
    graph, identity = mechanical(
        "Carry X.",
        [
            ("Carry", "VERB", "ROOT", 0, "carry"),
            ("X", "NOUN", "dobj", 0, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    unit = next(row for row in record["lexical_units"] if row["name"] == "carry_out")
    assert unit["decision"] == "lexical_incompatible"
    assert not [row for row in record["analyses"] if row["lexical_unit"] == "carry_out"]


def test_lexical_preposition_binds_its_object_without_inventing_extra_np():
    # Break: adhere_to disappears or its preposition itself becomes the target.
    graph, identity = mechanical(
        "Adhere to X.",
        [
            ("Adhere", "VERB", "ROOT", 0, "adhere"),
            ("to", "ADP", "prep", 0, "to"),
            ("X", "NOUN", "pobj", 1, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    rows = [row for row in record["analyses"] if row["lexical_unit"] == "adhere_to"]
    assert rows
    assert any(
        binding["argument"]["text"] == "X"
        for row in rows
        for binding in row["risk_bindings"]
    )


def test_implicit_performance_target_stays_unresolved_without_phantom_np():
    # Break: optional semantic target either disappears or becomes a fake span.
    graph, identity = mechanical(
        "Perform.",
        [("Perform", "VERB", "ROOT", 0, "perform"), (".", "PUNCT", "punct", 0, ".")],
    )
    record = inspect(graph, identity)
    assert record["unresolved_risk"]
    row = next(r for r in record["analyses"] if r["frame_id"] == "act-114-1:frame:0")
    assert row["implicit_risk"]
    assert row["risk_bindings"] == []


def test_passive_risk_never_disappears_through_unimplemented_voice_alignment():
    # Break: passive subjects are mismatched against active frames and cleared.
    graph, identity = mechanical(
        "X is executed.",
        [
            ("X", "NOUN", "nsubjpass", 2, "x"),
            ("is", "AUX", "auxpass", 2, "be"),
            ("executed", "VERB", "ROOT", 2, "execute"),
            (".", "PUNCT", "punct", 2, "."),
        ],
    )
    record = inspect(graph, identity, 2)
    assert record["unresolved_risk"]
    assert any(
        row["compatibility"] == "unknown" and row["possible_content_sense"]
        for row in record["analyses"]
    )


def test_frame_limit_refuses_complete_inventory_instead_of_returning_prefix(
    monkeypatch,
):
    # Break: an early favorable result or truncation hides a later risky sense.
    catalog = module()
    monkeypatch.setattr(catalog, "MAX_FRAME_CANDIDATES", 1)
    graph, identity = mechanical(
        "Execute X.",
        [
            ("Execute", "VERB", "ROOT", 0, "execute"),
            ("X", "NOUN", "dobj", 0, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    with pytest.raises(catalog.ReferenceCandidateLimit):
        inspect(graph, identity)


@pytest.mark.parametrize("failure", ["missing", "payload", "license"])
def test_asset_failure_is_runtime_unavailable_not_content_refusal(monkeypatch, failure):
    # Break: missing/tampered assets are mistaken for an unsupported document.
    catalog = module()
    package = catalog.resources.files("app").joinpath("data")
    payload = package.joinpath("procedure_reference_lexicon_v1.json").read_bytes()
    license_bytes = package.joinpath("VERBNET_LICENSE.txt").read_bytes()

    class Assets:
        def __init__(self, name=""):
            self.name = name

        def joinpath(self, name):
            return Assets(name)

        def read_bytes(self):
            if failure == "missing":
                raise FileNotFoundError("Controlled missing package resource")
            if self.name.endswith(".json"):
                return b"{}" if failure == "payload" else payload
            return b"changed" if failure == "license" else license_bytes

    catalog._catalog.cache_clear()
    monkeypatch.setattr(catalog.resources, "files", lambda _: Assets())
    with pytest.raises(catalog.ReferenceCatalogUnavailable):
        catalog.catalog_metadata()
    catalog._catalog.cache_clear()


def test_unimplemented_frame_syntax_cannot_clear_risk_on_a_later_missing_slot(
    monkeypatch,
):
    # Break: encountering a missing slot before VP silently prunes an unknown frame.
    catalog = module()
    data = deepcopy(catalog._catalog())
    frame = data["frames"]["act-114:frame:0"]
    frame["syntax"].extend(
        [
            {
                "tag": "NP",
                "attributes": {"value": "Instrument"},
                "children": [],
                "text": "",
            },
            {"tag": "VP", "attributes": {}, "children": [], "text": ""},
        ]
    )
    monkeypatch.setattr(catalog, "_catalog", lambda: data)
    graph, identity = mechanical(
        "Execute X.",
        [
            ("Execute", "VERB", "ROOT", 0, "execute"),
            ("X", "NOUN", "dobj", 0, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    row = next(r for r in record["analyses"] if r["frame_id"] == "act-114:frame:0")
    assert row["compatibility"] == "unknown"
    assert record["unresolved_risk"]


def test_unresolved_multiword_attachment_keeps_possible_content_risk():
    # Break: unsupported attachment is treated as an absent risky lexical unit.
    graph, identity = mechanical(
        "Adhere to X.",
        [
            ("Adhere", "VERB", "ROOT", 0, "adhere"),
            ("to", "ADP", "dep", 0, "to"),
            ("X", "NOUN", "pobj", 1, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    assert record["unresolved_risk"]
    assert any(
        r["lexical_unit"] == "adhere_to" and r["possible_content_sense"]
        for r in record["analyses"]
    )


def test_inherited_frames_and_class_role_declarations_are_retained_downward_only():
    # Break: missing ancestor constraints, or child-only frames leak upward.
    graph, identity = mechanical(
        "Perform X.",
        [
            ("Perform", "VERB", "ROOT", 0, "perform"),
            ("X", "NOUN", "dobj", 0, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    inherited = next(
        row for row in record["analyses"] if row["frame_id"] == "act-114:frame:0"
    )
    assert inherited["member"]["class"] == "act-114-1"
    assert [row["class"] for row in inherited["role_declaration_chain"]] == [
        "act-114",
        "act-114-1",
    ]
    roles = inherited["role_declaration_chain"][0]["role_declarations"]
    assert [role["attributes"]["type"] for role in roles] == ["Agent", "Eventuality"]
    assert not [
        row for row in record["analyses"] if row["frame_id"].startswith("act-114-1-1:")
    ]


def test_mapping_only_risk_preserves_patient_and_instrument_candidates():
    # Break: a coarse FrameNet mapping fabricates a single FE-to-NP target.
    graph, identity = mechanical(
        "Implement X with Y.",
        [
            ("Implement", "VERB", "ROOT", 0, "implement"),
            ("X", "NOUN", "dobj", 0, "x"),
            ("with", "ADP", "prep", 0, "with"),
            ("Y", "NOUN", "pobj", 2, "y"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    row = next(
        r for r in record["analyses"] if r["frame_id"] == "establish-55.5-1:frame:0"
    )
    assert {b["argument"]["text"] for b in row["risk_bindings"]} == {"X", "Y"}
    assert all(
        reason["meaning"] == "frame_risk_not_FE_to_argument_mapping"
        for binding in row["risk_bindings"]
        for reason in binding["reasons"]
    )


def test_clausal_restriction_cannot_be_satisfied_by_plain_nominal_argument():
    # Break: every XML NP is treated as an unrestricted surface noun phrase.
    graph, identity = mechanical(
        "Repeat X.",
        [
            ("Repeat", "VERB", "ROOT", 0, "repeat"),
            ("X", "NOUN", "dobj", 0, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    infinitive = next(
        row for row in record["analyses"] if row["frame_id"] == "begin-55.1:frame:0"
    )
    transitive = next(
        row for row in record["analyses"] if row["frame_id"] == "begin-55.1-1-1:frame:1"
    )
    assert infinitive["compatibility"] == "incompatible"
    assert infinitive["risk_bindings"] == []
    assert transitive["possible_content_sense"]


def test_exact_lexical_unit_token_does_not_require_a_duplicate_particle():
    # Break: an already exact indexed lemma is treated as a missing MWE suffix.
    graph, identity = mechanical(
        "Carry_out X.",
        [
            ("Carry_out", "VERB", "ROOT", 0, "carry_out"),
            ("X", "NOUN", "dobj", 0, "x"),
            (".", "PUNCT", "punct", 0, "."),
        ],
    )
    record = inspect(graph, identity)
    assert record["lexical_status"] == "resource_checked"
    assert record["potential_instruction_content"] or record["unresolved_risk"]
