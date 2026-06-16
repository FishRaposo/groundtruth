import re

from app.parsers.base import BaseParser, ParsedDocument


class MarkdownParser(BaseParser):
    """Parser for Markdown documents.

    Extracts text content from Markdown files, preserving heading structure
    as section markers for downstream chunking.
    """

    async def parse(self, file_path: str) -> ParsedDocument:
        """Parse a Markdown file and extract content with heading sections.

        Args:
            file_path: Path to the Markdown file on disk.

        Returns:
            A ParsedDocument with full text and heading-based sections.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        headings = heading_pattern.findall(content)
        sections = [title.strip() for _, title in headings]

        return ParsedDocument(
            content=content,
            metadata={
                "file_type": "markdown",
                "heading_count": len(headings),
                "char_count": len(content),
                "word_count": len(content.split()),
            },
            sections=sections,
        )
