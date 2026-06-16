"""Bytes-based parsing adapter over ``shared_core.docparse``.

The file-path parsers in this package (:mod:`app.parsers.markdown`,
:mod:`app.parsers.html`, ...) remain the ingestion default. This adapter adds a
*complementary* capability: parsing in-memory ``bytes`` (e.g. a freshly uploaded
file) through the shared-core parser registry, then mapping the result back into
GroundTruth's :class:`~app.parsers.base.ParsedDocument` shape (including the
heading ``sections`` the rest of the pipeline expects).

This converges document parsing onto ``shared_core.docparse`` without disturbing
the working file-path code paths or their golden tests.
"""

from __future__ import annotations

import re

from shared_core.docparse import get_parser as get_shared_parser

from app.parsers.base import ParsedDocument

_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_HTML_HEADING_RE = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.IGNORECASE | re.DOTALL)


def _extract_sections(text: str) -> list[str]:
    """Best-effort heading extraction from normalized parser text.

    shared-core parsers emit plain text (Markdown passthrough or stripped HTML),
    so we recover sections from Markdown ``#`` headings, falling back to any
    residual HTML heading tags.
    """
    sections = [m.strip() for m in _MD_HEADING_RE.findall(text)]
    if sections:
        return sections
    return [re.sub(r"<[^>]+>", "", m).strip() for m in _HTML_HEADING_RE.findall(text)]


def parse_bytes(
    data: bytes,
    *,
    filename: str,
) -> ParsedDocument:
    """Parse ``data`` via ``shared_core.docparse`` into a ``ParsedDocument``.

    Args:
        data: Raw file bytes.
        filename: Original filename (or MIME hint) used to resolve a parser.

    Returns:
        A GroundTruth :class:`ParsedDocument` with content, sections, and
        metadata (including the shared-core title and page count when present).

    Raises:
        shared_core.errors.ValidationError: If no parser matches ``filename``.
    """
    parser = get_shared_parser(filename)
    parsed = parser.parse(data, filename=filename)

    content = parsed.text
    sections = _extract_sections(content)

    metadata: dict[str, object] = {
        "file_type": type(parser).__name__.replace("Parser", "").lower(),
        "char_count": len(content),
        "word_count": len(content.split()),
        "heading_count": len(sections),
        "page_count": parsed.page_count,
        "parser": "shared_core.docparse",
    }
    if parsed.title:
        metadata["title"] = parsed.title

    return ParsedDocument(content=content, metadata=metadata, sections=sections)
