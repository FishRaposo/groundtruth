from app.parsers.base import BaseParser, ParsedDocument


class TextParser(BaseParser):
    """Parse dependency-free UTF-8 plain-text documents."""

    async def parse(self, file_path: str) -> ParsedDocument:
        """Decode text with replacement for malformed byte sequences."""
        with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()

        return ParsedDocument(
            content=content,
            metadata={
                "file_type": "text",
                "char_count": len(content),
                "word_count": len(content.split()),
                "line_count": len(content.splitlines()),
            },
            sections=[],
        )
