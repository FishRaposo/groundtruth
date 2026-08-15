"""Dependency-free CSV and TSV parsing with row-aware provenance."""

from __future__ import annotations

import csv

from app.parsers.base import BaseParser, ParsedDocument


class DelimitedTextParser(BaseParser):
    """Parse a delimited text file into deterministic row records."""

    def __init__(self, *, delimiter: str, file_type: str) -> None:
        self.delimiter = delimiter
        self.file_type = file_type

    async def parse(self, file_path: str) -> ParsedDocument:
        with open(
            file_path, encoding="utf-8-sig", errors="replace", newline=""
        ) as file:
            reader = csv.DictReader(file, delimiter=self.delimiter)
            columns = [str(name) for name in (reader.fieldnames or []) if name]
            rows = [dict(row) for row in reader]

        rendered: list[str] = []
        sections: list[str] = []
        for index, row in enumerate(rows, start=1):
            label = f"Row {index}"
            values = [f"{column}={row.get(column, '') or ''}" for column in columns]
            rendered.append(f"{label}: " + " | ".join(values))
            sections.append(label)

        return ParsedDocument(
            content="\n".join(rendered),
            metadata={
                "file_type": self.file_type,
                "delimiter": self.delimiter,
                "columns": columns,
                "row_count": len(rows),
                "chunk_provenance": [
                    {"section": section, "row": index}
                    for index, section in enumerate(sections, start=1)
                ],
            },
            sections=sections,
        )
