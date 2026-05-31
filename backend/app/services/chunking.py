import re
from typing import Any

from app.config import get_settings

settings = get_settings()


class ChunkingService:
    """Splits document text into retrievable chunks using configurable strategies.

    Supports fixed-size chunking with overlap, structural chunking by headings,
    and sentence-aware semantic chunking.
    """

    def chunk_text(
        self,
        text: str,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> list[str]:
        """Split text into fixed-size chunks with configurable overlap.

        Uses word boundaries to avoid splitting mid-word when possible.

        Args:
            text: The full document text to chunk.
            chunk_size: Target number of characters per chunk.
            overlap: Number of overlapping characters between adjacent chunks.

        Returns:
            A list of text chunks.
        """
        chunk_size = chunk_size or settings.CHUNK_SIZE
        overlap = overlap or settings.CHUNK_OVERLAP

        if len(text) <= chunk_size:
            return [text.strip()] if text.strip() else []

        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]

            if end < len(text):
                boundary = chunk.rfind(" ")
                if boundary > chunk_size // 2:
                    chunk = text[start : start + boundary]
                    end = start + boundary

            stripped = chunk.strip()
            if stripped:
                chunks.append(stripped)

            start = end - overlap
            if start <= (end - chunk_size):
                start = end

        return chunks

    def chunk_by_semantic(self, text: str) -> list[str]:
        """Split text using semantic similarity boundaries.

        This lightweight implementation keeps nearby sentences together
        while starting a new chunk at paragraph breaks, topic-heading style
        transitions, or when the configured chunk size is reached.

        Args:
            text: The full document text to chunk.

        Returns:
            A list of semantically coherent text chunks.
        """
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+|\n{2,}", text.strip())
            if s.strip()
        ]
        if not sentences:
            return []

        chunks: list[str] = []
        current: list[str] = []
        current_terms: set[str] = set()

        for sentence in sentences:
            terms = self._semantic_terms(sentence)
            current_text = " ".join(current)
            next_size = len(current_text) + len(sentence) + (1 if current else 0)
            overlap = len(current_terms & terms) / max(len(terms), 1)
            topic_shift = bool(current) and overlap < 0.12 and len(current_text) >= settings.CHUNK_SIZE * 0.35

            if current and (next_size > settings.CHUNK_SIZE or topic_shift):
                chunks.append(current_text)
                current = []
                current_terms = set()

            current.append(sentence)
            current_terms.update(terms)

        if current:
            chunks.append(" ".join(current))

        final_chunks: list[str] = []
        for chunk in chunks:
            if len(chunk) > settings.CHUNK_SIZE:
                final_chunks.extend(self.chunk_text(chunk))
            else:
                final_chunks.append(chunk)
        return final_chunks

    @staticmethod
    def _semantic_terms(text: str) -> set[str]:
        """Extract coarse content terms for sentence grouping."""
        stopwords = {
            "the", "and", "for", "with", "that", "this", "from", "are", "was",
            "were", "into", "about", "your", "you", "our", "has", "have",
        }
        return {
            word
            for word in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text.lower())
            if word not in stopwords
        }

    def chunk_by_structure(self, text: str, structure: str = "heading") -> list[str]:
        """Split text using structural markers such as headings.

        Splits on markdown-style headings (## or ===) and returns
        each section as a separate chunk.

        Args:
            text: The full document text to chunk.
            structure: The structural marker type. Currently only 'heading' is supported.

        Returns:
            A list of text chunks aligned to structural boundaries.
        """
        if structure == "heading":
            pattern = r"\n(?=#{1,6}\s)"
            sections = re.split(pattern, text)
            chunks: list[str] = []
            for section in sections:
                section = section.strip()
                if section:
                    if len(section) > settings.CHUNK_SIZE:
                        chunks.extend(self.chunk_text(section))
                    else:
                        chunks.append(section)
            return chunks

        return self.chunk_text(text)


chunking_service = ChunkingService()
