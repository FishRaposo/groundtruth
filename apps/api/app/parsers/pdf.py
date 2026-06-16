from app.parsers.base import BaseParser, ParsedDocument


class PdfParser(BaseParser):
    """Parser for PDF documents.

    Extracts text content from PDF files using PyPDF2 or pdfplumber.
    Handles multi-page documents and preserves page boundaries as sections.
    """

    async def parse(self, file_path: str) -> ParsedDocument:
        """Parse a PDF file and extract text content.

        Args:
            file_path: Path to the PDF file on disk.

        Returns:
            A ParsedDocument with extracted text and page-level sections.
        """
        try:
            import pdfplumber

            sections: list[str] = []
            all_text: list[str] = []

            with pdfplumber.open(file_path) as pdf:
                page_count = len(pdf.pages)
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    if page_text.strip():
                        all_text.append(page_text)
                        sections.append(f"Page {page.page_number}")

                content = "\n\n".join(all_text)

                return ParsedDocument(
                    content=content,
                    metadata={
                        "page_count": page_count,
                        "file_type": "pdf",
                        "char_count": len(content),
                    },
                    sections=sections,
                )
        except ImportError:
            return ParsedDocument(
                content="",
                metadata={"error": "pdfplumber not installed", "file_type": "pdf"},
                sections=[],
            )
