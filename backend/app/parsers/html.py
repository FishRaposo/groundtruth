import re

from app.parsers.base import BaseParser, ParsedDocument


class HtmlParser(BaseParser):
    """Parser for HTML documents.

    Extracts readable text content from HTML files, stripping tags
    and preserving heading structure as sections.
    """

    async def parse(self, file_path: str) -> ParsedDocument:
        """Parse an HTML file and extract text content.

        Strips HTML tags, extracts heading text for sections,
        and normalizes whitespace.

        Args:
            file_path: Path to the HTML file on disk.

        Returns:
            A ParsedDocument with cleaned text and heading sections.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            raw_html = f.read()

        heading_pattern = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.IGNORECASE | re.DOTALL)
        headings = heading_pattern.findall(raw_html)
        sections = [re.sub(r"<[^>]+>", "", h).strip() for h in headings]

        tag_pattern = re.compile(r"<[^>]+>")
        content = tag_pattern.sub("", raw_html)

        content = re.sub(r"\n{3,}", "\n\n", content)
        content = re.sub(r"  +", " ", content)
        content = content.strip()

        return ParsedDocument(
            content=content,
            metadata={
                "file_type": "html",
                "heading_count": len(sections),
                "char_count": len(content),
            },
            sections=sections,
        )
