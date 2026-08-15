from app.parsers.base import BaseParser, ParsedDocument
from app.parsers.docx import DocxParser
from app.parsers.html import HtmlParser
from app.parsers.markdown import MarkdownParser
from app.parsers.office import PowerPointParser, SpreadsheetParser
from app.parsers.pdf import PdfParser
from app.parsers.tabular import DelimitedTextParser
from app.parsers.text import TextParser

_PARSERS = {
    "pdf": PdfParser,
    "md": MarkdownParser,
    "html": HtmlParser,
    "docx": DocxParser,
    "txt": TextParser,
    "csv": lambda: DelimitedTextParser(delimiter=",", file_type="csv"),
    "tsv": lambda: DelimitedTextParser(delimiter="\t", file_type="tsv"),
    "xlsx": SpreadsheetParser,
    "pptx": PowerPointParser,
}


def get_parser(source_type: str) -> BaseParser:
    """Return the appropriate parser instance for the given source type.

    Args:
        source_type: A registered text, document, tabular, or presentation type.

    Returns:
        An instance of the corresponding parser.

    Raises:
        ValueError: If the source type is not supported.
    """
    parser_cls = _PARSERS.get(source_type)
    if parser_cls is None:
        raise ValueError(f"Unsupported source type: {source_type}")
    return parser_cls()


__all__ = ["BaseParser", "ParsedDocument", "TextParser", "get_parser"]
