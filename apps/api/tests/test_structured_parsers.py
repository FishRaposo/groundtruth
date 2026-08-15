"""Offline structured-parser contracts."""

from __future__ import annotations

import builtins

import pytest
from app.api.documents import _detect_source_type
from app.models.document import SourceType
from app.parsers import get_parser
from app.parsers.office import PowerPointParser, SpreadsheetParser
from app.parsers.tabular import DelimitedTextParser
from fastapi import HTTPException


@pytest.mark.asyncio
@pytest.mark.parametrize(("suffix", "delimiter"), [("csv", ","), ("tsv", "\t")])
async def test_delimited_parser_preserves_row_boundaries(
    tmp_path: object, suffix: str, delimiter: str
) -> None:
    path = tmp_path / f"people.{suffix}"  # type: ignore[operator]
    path.write_text(  # type: ignore[attr-defined]
        f"name{delimiter}role\nAda{delimiter}Engineer\nLin{delimiter}Reviewer\n",
        encoding="utf-8",
    )

    result = await DelimitedTextParser(delimiter=delimiter, file_type=suffix).parse(
        str(path)
    )

    assert result.sections == ["Row 1", "Row 2"]
    assert "Row 1: name=Ada | role=Engineer" in result.content
    assert result.metadata["row_count"] == 2
    assert result.metadata["columns"] == ["name", "role"]


@pytest.mark.parametrize(
    ("source_type", "parser_type"),
    [
        ("csv", DelimitedTextParser),
        ("tsv", DelimitedTextParser),
        ("xlsx", SpreadsheetParser),
        ("pptx", PowerPointParser),
    ],
)
def test_parser_registry_includes_structured_formats(
    source_type: str, parser_type: type[object]
) -> None:
    assert isinstance(get_parser(source_type), parser_type)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("rates.csv", SourceType.CSV),
        ("rates.tsv", SourceType.TSV),
        ("rates.xlsx", SourceType.XLSX),
        ("deck.pptx", SourceType.PPTX),
    ],
)
def test_upload_detection_includes_structured_formats(
    filename: str, expected: SourceType
) -> None:
    assert _detect_source_type(filename) is expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("parser", "module_name", "expected"),
    [
        (SpreadsheetParser(), "openpyxl", "groundtruth[office]"),
        (PowerPointParser(), "pptx", "groundtruth[office]"),
    ],
)
async def test_office_parser_missing_dependency_fails_clearly(
    monkeypatch: pytest.MonkeyPatch,
    parser: object,
    module_name: str,
    expected: str,
) -> None:
    original_import = builtins.__import__

    def blocked_import(name: str, *args: object, **kwargs: object) -> object:
        if name == module_name:
            raise ImportError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    with pytest.raises(RuntimeError, match=expected.replace("[", r"\[")):
        await parser.parse("missing.file")  # type: ignore[attr-defined]


def test_unsupported_binary_office_format_still_rejected() -> None:
    with pytest.raises(HTTPException, match="Unsupported file type"):
        _detect_source_type("legacy.xls")
