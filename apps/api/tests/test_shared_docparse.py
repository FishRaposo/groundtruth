"""Tests for the bytes-based shared_core.docparse adapter."""

import pytest
from app.parsers.base import ParsedDocument
from app.parsers.shared_docparse import parse_bytes
from shared_core.errors import ValidationError


def test_parse_markdown_bytes_extracts_sections() -> None:
    data = b"# Title\n\nIntro text.\n\n## Details\nMore."
    result = parse_bytes(data, filename="doc.md")
    assert isinstance(result, ParsedDocument)
    assert "Title" in result.content
    assert "Details" in result.content
    assert result.sections == ["Title", "Details"]
    assert result.metadata["heading_count"] == 2
    assert result.metadata["parser"] == "shared_core.docparse"
    assert result.metadata["title"] == "Title"


def test_parse_plain_text_has_no_sections() -> None:
    result = parse_bytes(b"just some plain text", filename="notes.txt")
    assert result.sections == []
    assert result.metadata["heading_count"] == 0
    assert result.content == "just some plain text"


def test_parse_counts_words_and_chars() -> None:
    result = parse_bytes(b"one two three", filename="x.md")
    assert result.metadata["word_count"] == 3
    assert result.metadata["char_count"] == len("one two three")


def test_parse_html_bytes_strips_tags() -> None:
    data = b"<html><body><h1>Heading</h1><p>Body text.</p></body></html>"
    result = parse_bytes(data, filename="page.html")
    # shared_core's HTML parser returns stripped plain text.
    assert "Body text." in result.content
    assert "Heading" in result.content
    assert "<h1>" not in result.content
    assert "<p>" not in result.content


def test_parse_unknown_extension_raises() -> None:
    with pytest.raises(ValidationError):
        parse_bytes(b"data", filename="archive.zip")


def test_parse_decodes_utf8_replacement_safely() -> None:
    # Invalid UTF-8 bytes should not raise; markdown parser uses errors=replace.
    result = parse_bytes(b"\xff\xfe text", filename="weird.md")
    assert isinstance(result.content, str)
