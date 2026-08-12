"""Focused behavior tests for the document-intelligence ingestion port."""

import importlib.util
from pathlib import Path


_MODULE_PATH = (
    Path(__file__).parents[1] / "app" / "services" / "document_intelligence.py"
)
_SPEC = importlib.util.spec_from_file_location("document_intelligence", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

content_hash = _MODULE.content_hash
deduplicate_chunks = _MODULE.deduplicate_chunks
extract_entities = _MODULE.extract_entities
normalize_content = _MODULE.normalize_content


def test_content_hash_treats_whitespace_only_variants_as_duplicates() -> None:
    assert content_hash("Policy  terms\n\napply") == content_hash(
        "  Policy terms apply  "
    )


def test_deduplicate_chunks_keeps_first_seen_order() -> None:
    chunks = ["alpha", "beta", " alpha  ", "gamma", "beta"]

    assert deduplicate_chunks(chunks) == ["alpha", "beta", "gamma"]


def test_normalize_content_collapses_extraction_whitespace() -> None:
    assert normalize_content("  one\t two\n\nthree  ") == "one two three"


def test_extract_entities_is_offline_deterministic_and_deduplicated() -> None:
    entities = extract_entities(
        "Jane Smith at Acme Corporation: jane@example.com, jane@example.com. "
        "See https://example.com/docs. Call +1 555 123 4567."
    )

    assert entities["emails"] == ["jane@example.com"]
    assert entities["urls"] == ["https://example.com/docs"]
    assert any("555" in phone for phone in entities["phones"])
    assert "Jane Smith" in entities["capitalised"]
    assert "Acme Corporation" in entities["capitalised"]


def test_extract_entities_handles_empty_content() -> None:
    assert extract_entities("") == {
        "emails": [],
        "urls": [],
        "phones": [],
        "capitalised": [],
    }
