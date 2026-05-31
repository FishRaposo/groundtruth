from app.parsers.base import BaseParser, ParsedDocument
from app.parsers.pdf import PdfParser
from app.parsers.markdown import MarkdownParser
from app.parsers.html import HtmlParser
from app.parsers.docx import DocxParser

_PARSERS = {
    "pdf": PdfParser,
    "md": MarkdownParser,
    "html": HtmlParser,
    "docx": DocxParser,
}


def get_parser(source_type: str) -> BaseParser:
    """Return the appropriate parser instance for the given source type.

    Args:
        source_type: One of 'pdf', 'md', 'html', 'docx'.

    Returns:
        An instance of the corresponding parser.

    Raises:
        ValueError: If the source type is not supported.
    """
    parser_cls = _PARSERS.get(source_type)
    if parser_cls is None:
        raise ValueError(f"Unsupported source type: {source_type}")
    return parser_cls()


__all__ = ["BaseParser", "ParsedDocument", "get_parser"]
