"""Representation contracts use invented protocol fixtures, never corpus assets."""

import hashlib
import json
from pathlib import Path

import pytest
from app.portfolio import load_corpus


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_fixture(root: Path, raw="1. Verify the seal.\n\n2. Record the code."):
    root.mkdir()
    source = {
        "document_id": "protocol",
        "version_number": 1,
        "content_hash": sha(raw),
        "quoted_text": raw,
        "acceptable_answer_spans": ["Verify the seal.", "Record the code."],
    }
    values = {
        "documents": [
            {
                "id": "protocol",
                "title": "Protocol",
                "family": "protocol",
                "split": "development",
                "owner": "author",
                "workspace_id": "test",
                "visibility": "private",
                "metadata": {},
                "current_version_number": 1,
                "versions": [
                    {"version_number": 1, "content": raw, "content_hash": sha(raw)}
                ],
            }
        ],
        "cases": [
            {
                "id": "protocol-1",
                "family": "protocol",
                "split": "development",
                "category": "answerable",
                "principal": "author",
                "question": "Return the protocol.",
                "document_ids": ["protocol"],
                "expected_behavior": "answer",
                "expected_sources": [source],
                "forbidden_sources": [],
                "required_facts": [["Verify the seal."]],
                "ordered_steps": [["Verify the seal."], ["Record the code."]],
            }
        ],
        "profile": {"top_k": 5},
    }
    files = {}
    for name, value in values.items():
        body = json.dumps(value).encode("utf-8")
        (root / f"{name}.json").write_bytes(body)
        files[f"{name}.json"] = hashlib.sha256(body).hexdigest()
    manifest = {
        "schema_version": 1,
        "revision": "invented-protocol-v1",
        "document_count": 1,
        "case_count": 1,
        "files": files,
        "expected_counts": {"development": {"answerable": 1}},
        "principals": {"author": {"workspace_id": "test", "role": "member"}},
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def edit_manifest(root, update):
    path = root / "manifest.json"
    manifest = json.loads(path.read_bytes())
    update(manifest)
    path.write_text(json.dumps(manifest), encoding="utf-8")


@pytest.mark.parametrize("profile", ["unknown", "legacy-flat-v1"])
def test_declared_representation_cannot_be_ignored_by_loader(tmp_path, profile):
    # Defect: a declared unknown/flat oracle currently accepts a multiline body.
    root = write_fixture(tmp_path / "common")
    edit_manifest(
        root,
        lambda m: m.update(
            comparison_representation={
                "contract": "comparison-representation-v1",
                "profile": profile,
            }
        ),
    )
    with pytest.raises(ValueError, match="[Rr]epresentation"):
        load_corpus(root)


@pytest.mark.parametrize(
    "raw,flat,paragraphs",
    [
        (
            "\r\n1. Verify the seal.\r\n\r\n2. Record the code.\r\n",
            "1. Verify the seal. 2. Record the code.",
            "1. Verify the seal.\n\n2. Record the code.",
        ),
        (
            "\t \n  key:\tvalue  \n    child: 😀e\u0301\t\n \t",
            "key: value child: 😀e\u0301",
            "  key:\tvalue  \n    child: 😀e\u0301\t",
        ),
        ("\u2003\n  A\u2028B  \rC\r\n", "A B C", "  A\u2028B  \nC"),
        ("Text\n", "Text", "Text"),
    ],
)
def test_oracles_have_independent_literal_goldens(raw, flat, paragraphs):
    from app.portfolio.representation import canonicalize

    assert canonicalize(raw, "legacy-flat-v1").text == flat
    assert canonicalize(raw, "connected-paragraphs-v1").text == paragraphs


@pytest.mark.parametrize("profile", ["legacy-flat-v1", "connected-paragraphs-v1"])
def test_compile_preserves_raw_and_semantic_contract(tmp_path, profile):
    from app.portfolio import version_upload_bytes
    from app.portfolio.representation import compile_corpus

    raw = "1. Verify the seal.\r\n\r\n2. Record the code.\r\n"
    source = write_fixture(tmp_path / "common", raw)
    original = load_corpus(source)
    original_files = {p.name: p.read_bytes() for p in source.iterdir()}
    target = tmp_path / "arm"
    projected = compile_corpus(source, target, profile)
    expected = (
        "1. Verify the seal. 2. Record the code."
        if profile == "legacy-flat-v1"
        else "1. Verify the seal.\n\n2. Record the code."
    )
    version = projected["documents"][0]["versions"][0]
    assert version_upload_bytes(version) == raw.encode()
    assert version["content"] == expected
    assert version["content_hash"] == sha(expected)
    assert projected["cases"][0]["expected_sources"][0]["quoted_text"] == expected
    for name in (
        "question",
        "principal",
        "document_ids",
        "required_facts",
        "ordered_steps",
        "expected_behavior",
        "forbidden_sources",
    ):
        assert projected["cases"][0][name] == original["cases"][0][name]
    assert projected["documents"][0]["owner"] == "author"
    assert {p.name: p.read_bytes() for p in source.iterdir()} == original_files
    descriptor = projected["manifest"]["comparison_representation"]
    assert (
        descriptor["origin_common_manifest_sha256"]
        == original["manifest"]["manifest_sha256"]
    )
    assert (
        descriptor["common_files"]["cases.json"].encode()
        == original_files["cases.json"]
    )
    assert version["comparison_representation"]["codepoint_map"]
    with pytest.raises(ValueError, match="target"):
        compile_corpus(source, target, profile)
    with pytest.raises(ValueError, match="target"):
        compile_corpus(source, source / "nested", profile)


def test_arm_pair_shared_identity_and_deterministic_bytes(tmp_path):
    from app.portfolio.representation import compile_corpus

    source = write_fixture(tmp_path / "common")
    flat = compile_corpus(source, tmp_path / "flat", "legacy-flat-v1")
    connected = compile_corpus(
        source, tmp_path / "connected", "connected-paragraphs-v1"
    )
    compile_corpus(source, tmp_path / "repeat", "legacy-flat-v1")
    for name in ("manifest.json", "documents.json", "cases.json", "profile.json"):
        assert (tmp_path / "flat" / name).read_bytes() == (
            tmp_path / "repeat" / name
        ).read_bytes()
    left = flat["manifest"]["comparison_representation"]
    right = connected["manifest"]["comparison_representation"]
    for key in (
        "common_contract_sha256",
        "common_source_contract_sha256",
        "common_case_contract_sha256",
        "origin_common_manifest_sha256",
    ):
        assert left[key] == right[key]
    assert left["projection_sha256"] != right["projection_sha256"]
    with pytest.raises(ValueError, match="[Rr]epresentation"):
        load_corpus(
            tmp_path / "flat", expected_representation_profile="connected-paragraphs-v1"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", "unknown"),
        ("profile", "legacy-flat-v1"),
        ("execution_arm", "baseline"),
        ("oracle_contract", "unknown"),
        ("compiler_sha256", "0" * 64),
        ("projection_sha256", "0" * 64),
        ("origin_common_manifest_sha256", "0" * 64),
        ("common_contract_sha256", "0" * 64),
        ("common_source_contract_sha256", "0" * 64),
        ("common_case_contract_sha256", "0" * 64),
    ],
)
def test_loader_rejects_descriptor_tampering(tmp_path, field, value):
    from app.portfolio.representation import compile_corpus

    source = write_fixture(tmp_path / "common")
    target = tmp_path / "arm"
    compile_corpus(source, target, "connected-paragraphs-v1")
    edit_manifest(
        target, lambda m: m["comparison_representation"].update({field: value})
    )
    with pytest.raises(ValueError, match="[Rr]epresentation"):
        load_corpus(target)


def rewrite_payload(root, name, mutate):
    path = root / f"{name}.json"
    value = json.loads(path.read_bytes())
    mutate(value)
    path.write_bytes(json.dumps(value).encode())
    edit_manifest(
        root,
        lambda m: m["files"].update(
            {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}
        ),
    )


@pytest.mark.parametrize(
    "mutation", ["body", "raw", "map", "quote", "span", "facts", "owner"]
)
def test_valid_self_hashes_cannot_override_oracle_or_common_contract(
    tmp_path, mutation
):
    from app.portfolio.representation import compile_corpus

    source = write_fixture(tmp_path / "common")
    target = tmp_path / "arm"
    compile_corpus(source, target, "connected-paragraphs-v1")
    if mutation in {"body", "raw", "map", "owner"}:

        def alter(docs):
            version = docs[0]["versions"][0]
            if mutation == "body":
                version.update(content="Changed body", content_hash=sha("Changed body"))
            elif mutation == "raw":
                version.update(
                    input_content="Changed raw", input_sha256=sha("Changed raw")
                )
            elif mutation == "owner":
                docs[0]["owner"] = "other"
            else:
                version["comparison_representation"]["codepoint_map"][0][
                    "raw_start"
                ] = 999

        rewrite_payload(target, "documents", alter)
    else:

        def alter(cases):
            ref = cases[0]["expected_sources"][0]
            if mutation == "quote":
                ref["quoted_text"] = "Verify the seal."
            elif mutation == "span":
                ref["acceptable_answer_spans"] = ["seal"]
            else:
                cases[0]["required_facts"] = [["new alternative"]]

        rewrite_payload(target, "cases", alter)
    with pytest.raises(ValueError, match="[Rr]epresentation"):
        load_corpus(target)


def test_repeated_selectors_enumerate_but_conflicting_or_empty_images_refuse():
    from app.portfolio.representation import canonicalize, project_literal

    raw = "😀 Seal.\nSeal.\n"
    result = project_literal(raw, "Seal.", canonicalize(raw, "connected-paragraphs-v1"))
    assert len(result["occurrences"]) == 2
    assert result["occurrences"][0]["raw_range"] == {"start": 2, "end": 7}
    assert result["text"] == "Seal."
    with pytest.raises(ValueError, match="conflicting"):
        project_literal(raw, "Seal.\n", canonicalize(raw, "connected-paragraphs-v1"))
    with pytest.raises(ValueError, match="empty"):
        project_literal(
            "\nSeal.\n", "\n", canonicalize("\nSeal.\n", "connected-paragraphs-v1")
        )
    with pytest.raises(ValueError, match="collapsed"):
        project_literal("A \t B", "A ", canonicalize("A \t B", "legacy-flat-v1"))


@pytest.mark.parametrize("raw", ["", " \n\t", "\r\n\r", "\u2003\n"])
def test_unusable_body_is_preflight_error(raw):
    from app.portfolio.representation import canonicalize

    with pytest.raises(ValueError, match="empty"):
        canonicalize(raw, "connected-paragraphs-v1")


def test_forbidden_and_nested_inspection_refs_are_projected_without_identity_changes(
    tmp_path,
):
    from app.portfolio.representation import compile_corpus

    source = write_fixture(tmp_path / "common")

    def add_refs(cases):
        ref = dict(cases[0]["expected_sources"][0])
        cases[0]["forbidden_sources"] = [ref]
        cases[0]["inspection_expectations"] = {"rejected_sources": [dict(ref)]}

    rewrite_payload(source, "cases", add_refs)
    result = compile_corpus(source, tmp_path / "arm", "legacy-flat-v1")
    case = result["cases"][0]
    for ref in (
        case["forbidden_sources"][0],
        case["inspection_expectations"]["rejected_sources"][0],
    ):
        assert ref["document_id"] == "protocol" and ref["version_number"] == 1
        assert ref["quoted_text"] == "1. Verify the seal. 2. Record the code."
        assert (
            ref["comparison_representation"]["original"]["quoted_text"].count("\n") == 2
        )


def test_no_envelope_legacy_fixture_remains_compatible(tmp_path):
    source = write_fixture(tmp_path / "common")
    assert (
        load_corpus(source)["documents"][0]["versions"][0]["content"].count("\n") == 2
    )


@pytest.mark.parametrize("profile", ["legacy-flat-v1", "connected-paragraphs-v1"])
def test_explicit_p91_raw_input_is_preserved_independently(tmp_path, profile):
    from app.portfolio import version_upload_bytes
    from app.portfolio.representation import compile_corpus

    source = write_fixture(tmp_path / "common")
    raw = "\r\n1. Verify the seal.\n\n2. Record the code.\r\n"
    rewrite_payload(
        source,
        "documents",
        lambda docs: docs[0]["versions"][0].update(
            input_content=raw, input_sha256=sha(raw)
        ),
    )
    result = compile_corpus(source, tmp_path / "arm", profile)
    assert version_upload_bytes(result["documents"][0]["versions"][0]) == raw.encode()


def test_missing_envelope_or_changed_embedded_original_is_rejected(tmp_path):
    from app.portfolio.representation import compile_corpus

    source = write_fixture(tmp_path / "common")
    target = tmp_path / "arm"
    compile_corpus(source, target, "legacy-flat-v1")
    original = (target / "manifest.json").read_bytes()
    edit_manifest(target, lambda m: m.pop("comparison_representation"))
    with pytest.raises(ValueError, match="[Rr]epresentation"):
        load_corpus(target)
    (target / "manifest.json").write_bytes(original)
    edit_manifest(
        target,
        lambda m: m["comparison_representation"]["common_files"].update(
            {"cases.json": "[]"}
        ),
    )
    with pytest.raises(ValueError, match="[Rr]epresentation"):
        load_corpus(target)


def test_unmappable_raw_reference_fails_before_output_directory_creation(tmp_path):
    from app.portfolio.representation import compile_corpus

    source = write_fixture(tmp_path / "common")
    rewrite_payload(
        source,
        "documents",
        lambda docs: docs[0]["versions"][0].update(
            input_content="Different raw text.", input_sha256=sha("Different raw text.")
        ),
    )
    target = tmp_path / "arm"
    with pytest.raises(ValueError, match="unmappable"):
        compile_corpus(source, target, "legacy-flat-v1")
    assert not target.exists()


def test_bom_and_exact_unicode_codepoint_coordinates_are_preserved():
    from app.portfolio.representation import canonicalize, project_literal

    raw = "\ufeff😀\r\n\tX\r\n"
    body = canonicalize(raw, "connected-paragraphs-v1")
    assert body.text == "\ufeff😀\n\tX"
    projected = project_literal(raw, "X", body)
    assert projected["occurrences"] == [
        {
            "raw_range": {"start": 5, "end": 6},
            "canonical_range": {"start": 4, "end": 5},
        }
    ]
    assert body.codepoint_map() == [
        {"raw_start": 0, "raw_end": 2, "canonical_start": 0, "canonical_end": 2},
        {"raw_start": 2, "raw_end": 4, "canonical_start": 2, "canonical_end": 3},
        {"raw_start": 4, "raw_end": 6, "canonical_start": 3, "canonical_end": 5},
    ]


def test_compiler_does_not_reinterpret_an_already_projected_arm(tmp_path):
    from app.portfolio.representation import compile_corpus

    source = write_fixture(tmp_path / "common")
    arm = tmp_path / "arm"
    compile_corpus(source, arm, "legacy-flat-v1")
    with pytest.raises(ValueError, match="unprojected"):
        compile_corpus(arm, tmp_path / "second", "connected-paragraphs-v1")
    assert not (tmp_path / "second").exists()


def test_reference_binds_both_hashes_without_authored_hash(
    tmp_path,
):
    from app.portfolio.representation import compile_corpus

    source = write_fixture(tmp_path / "common")
    rewrite_payload(
        source,
        "cases",
        lambda rows: rows[0].update(
            inspection_sources=[
                {
                    "document_id": "protocol",
                    "version_number": 1,
                    "quoted_text": "Verify the seal.",
                }
            ]
        ),
    )
    result = compile_corpus(source, tmp_path / "arm", "legacy-flat-v1")
    reference = result["cases"][0]["inspection_sources"][0]
    lineage = reference["comparison_representation"]
    assert lineage.get("canonical_content_hash") == sha(
        "1. Verify the seal. 2. Record the code."
    )
    assert lineage.get("input_sha256") == sha(
        "1. Verify the seal.\n\n2. Record the code."
    )


def test_declared_null_envelope_does_not_downgrade_to_legacy(tmp_path):
    source = write_fixture(tmp_path / "common")
    edit_manifest(source, lambda m: m.update(comparison_representation=None))
    with pytest.raises(ValueError, match="[Rr]epresentation"):
        load_corpus(source)
