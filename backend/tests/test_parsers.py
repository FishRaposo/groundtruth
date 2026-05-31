import pytest
from app.parsers import get_parser
from app.parsers.base import BaseParser, ParsedDocument
from app.parsers.markdown import MarkdownParser
from app.parsers.html import HtmlParser
from app.parsers.pdf import PdfParser
from app.parsers.docx import DocxParser


def test_get_parser_returns_markdown_parser() -> None:
    parser = get_parser("md")
    assert isinstance(parser, MarkdownParser)
    assert isinstance(parser, BaseParser)


def test_get_parser_returns_html_parser() -> None:
    parser = get_parser("html")
    assert isinstance(parser, HtmlParser)


def test_get_parser_returns_pdf_parser() -> None:
    parser = get_parser("pdf")
    assert isinstance(parser, PdfParser)


def test_get_parser_returns_docx_parser() -> None:
    parser = get_parser("docx")
    assert isinstance(parser, DocxParser)


def test_get_parser_raises_for_unsupported_type() -> None:
    with pytest.raises(ValueError, match="Unsupported source type: txt"):
        get_parser("txt")


def test_get_parser_raises_for_empty_string() -> None:
    with pytest.raises(ValueError, match="Unsupported source type"):
        get_parser("")


@pytest.mark.asyncio
async def test_markdown_parser_extracts_content(tmp_path: object) -> None:
    import os
    tmp = os.fspath(tmp_path)
    file_path = tmp + "/test.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# Introduction\nThis is the intro.\n\n## Details\nMore details here.")

    parser = MarkdownParser()
    result = await parser.parse(file_path)

    assert isinstance(result, ParsedDocument)
    assert "Introduction" in result.content
    assert "Details" in result.content
    assert result.metadata["file_type"] == "markdown"
    assert result.metadata["heading_count"] == 2
    assert "Introduction" in result.sections
    assert "Details" in result.sections


@pytest.mark.asyncio
async def test_markdown_parser_handles_no_headings(tmp_path: object) -> None:
    import os
    tmp = os.fspath(tmp_path)
    file_path = tmp + "/plain.md"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("Just plain text without any headings.")

    parser = MarkdownParser()
    result = await parser.parse(file_path)

    assert result.content == "Just plain text without any headings."
    assert result.sections == []
    assert result.metadata["heading_count"] == 0


@pytest.mark.asyncio
async def test_html_parser_strips_tags(tmp_path: object) -> None:
    import os
    tmp = os.fspath(tmp_path)
    file_path = tmp + "/test.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("<html><body><h1>Title</h1><p>Paragraph text.</p></body></html>")

    parser = HtmlParser()
    result = await parser.parse(file_path)

    assert isinstance(result, ParsedDocument)
    assert "<h1>" not in result.content
    assert "<p>" not in result.content
    assert "Title" in result.content
    assert "Paragraph text." in result.content
    assert result.metadata["file_type"] == "html"
    assert result.metadata["heading_count"] == 1
    assert "Title" in result.sections


@pytest.mark.asyncio
async def test_html_parser_extracts_multiple_headings(tmp_path: object) -> None:
    import os
    tmp = os.fspath(tmp_path)
    file_path = tmp + "/multi.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("<h2>Section A</h2><p>A content</p><h3>Section B</h3><p>B content</p>")

    parser = HtmlParser()
    result = await parser.parse(file_path)

    assert result.metadata["heading_count"] == 2
    assert "Section A" in result.sections
    assert "Section B" in result.sections


@pytest.mark.asyncio
async def test_html_parser_handles_no_headings(tmp_path: object) -> None:
    import os
    tmp = os.fspath(tmp_path)
    file_path = tmp + "/nohead.html"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("<html><body><p>Just a paragraph.</p></body></html>")

    parser = HtmlParser()
    result = await parser.parse(file_path)

    assert result.sections == []
    assert "Just a paragraph." in result.content


@pytest.mark.asyncio
async def test_pdf_parser_handles_missing_library() -> None:
    parser = PdfParser()
    with pytest.raises(Exception):
        await parser.parse("/nonexistent/file.pdf")


@pytest.mark.asyncio
async def test_docx_parser_handles_missing_library() -> None:
    parser = DocxParser()
    with pytest.raises(Exception):
        await parser.parse("/nonexistent/file.docx")
