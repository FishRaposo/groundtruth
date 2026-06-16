from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ParsedDocument(BaseModel):
    """Represents a document after parsing, with extracted content and metadata."""

    content: str = Field(description="Full text content extracted from the document")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Metadata extracted during parsing"
    )
    sections: list[str] = Field(
        default_factory=list, description="Detected sections or headings"
    )


class BaseParser(ABC):
    """Abstract base class for document parsers.

    Each parser implementation handles a specific file format and
    returns a ParsedDocument with extracted content and metadata.
    """

    @abstractmethod
    async def parse(self, file_path: str) -> ParsedDocument:
        """Parse a document file and extract its content.

        Args:
            file_path: Path to the file on disk.

        Returns:
            A ParsedDocument with extracted content and metadata.
        """
