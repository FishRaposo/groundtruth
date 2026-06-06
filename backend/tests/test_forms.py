"""Tests for form filling service."""

from __future__ import annotations

import pytest

from app.services.document.processing.forms import FormFiller, FormFillReport
from app.services.document.processing.templates import ExtractedField, FieldDefinition


def _make_field_def(name: str, field_type: str = "text", required: bool = False, default: str | None = None) -> FieldDefinition:
    return FieldDefinition(name=name, label=name.title(), field_type=field_type, required=required, default_value=default)


def _make_extracted(name: str, value: str, confidence: float = 0.9) -> ExtractedField:
    return ExtractedField(name=name, value=value, confidence=confidence, source_text=value)


class TestFormFiller:
    """Tests for FormFiller.fill_form()."""

    def setup_method(self) -> None:
        self.filler = FormFiller()

    @pytest.mark.asyncio
    async def test_fills_from_extracted_fields(self) -> None:
        field_defs = [_make_field_def("invoice_number"), _make_field_def("total", "number")]
        extracted = [_make_extracted("invoice_number", "INV-001"), _make_extracted("total", "1200.00")]
        report = await self.filler.fill_form("invoice", extracted, field_defs)
        assert len(report.filled_fields) == 2
        assert report.completion_rate == 1.0
        assert report.missing_fields == []

    @pytest.mark.asyncio
    async def test_fills_from_external_data(self) -> None:
        field_defs = [_make_field_def("customer_name")]
        extracted: list[ExtractedField] = []
        external = {"customer_name": "Acme Corp"}
        report = await self.filler.fill_form("invoice", extracted, field_defs, external)
        assert len(report.filled_fields) == 1
        assert report.filled_fields[0].source == "api"
        assert report.filled_fields[0].filled_value == "Acme Corp"

    @pytest.mark.asyncio
    async def test_uses_default_value(self) -> None:
        field_defs = [_make_field_def("payment_terms", default="Net 30")]
        extracted: list[ExtractedField] = []
        report = await self.filler.fill_form("invoice", extracted, field_defs)
        assert len(report.filled_fields) == 1
        assert report.filled_fields[0].source == "default"
        assert report.filled_fields[0].filled_value == "Net 30"

    @pytest.mark.asyncio
    async def test_missing_required_field_reports_error(self) -> None:
        field_defs = [_make_field_def("signature", required=True)]
        extracted: list[ExtractedField] = []
        report = await self.filler.fill_form("contract", extracted, field_defs)
        assert "signature" in report.missing_fields
        assert any("signature" in e for e in report.errors)

    @pytest.mark.asyncio
    async def test_missing_optional_field_no_error(self) -> None:
        field_defs = [_make_field_def("optional_note", required=False)]
        extracted: list[ExtractedField] = []
        report = await self.filler.fill_form("form", extracted, field_defs)
        assert "optional_note" in report.missing_fields
        assert len(report.errors) == 0

    @pytest.mark.asyncio
    async def test_completion_rate_calculation(self) -> None:
        field_defs = [
            _make_field_def("f1"),
            _make_field_def("f2"),
            _make_field_def("f3"),
        ]
        extracted = [_make_extracted("f1", "v1"), _make_extracted("f2", "v2")]
        report = await self.filler.fill_form("test", extracted, field_defs)
        assert report.completion_rate == pytest.approx(2 / 3)

    @pytest.mark.asyncio
    async def test_empty_field_definitions(self) -> None:
        report = await self.filler.fill_form("empty", [], [])
        assert report.completion_rate == 1.0
        assert report.filled_fields == []
        assert report.missing_fields == []

    @pytest.mark.asyncio
    async def test_sources_used_tracking(self) -> None:
        field_defs = [_make_field_def("f1"), _make_field_def("f2")]
        extracted = [_make_extracted("f1", "v1")]
        external = {"f2": "v2"}
        report = await self.filler.fill_form("test", extracted, field_defs, external)
        assert report.sources_used.get("extracted", 0) == 1
        assert report.sources_used.get("api", 0) == 1

    def test_fill_result_dataclass(self) -> None:
        from app.services.document.processing.forms import FillResult
        r = FillResult(field_name="x", original_value=None, filled_value="y", source="extracted", confidence=0.9)
        assert r.field_name == "x"
        assert r.filled_value == "y"
        assert r.confidence == 0.9
