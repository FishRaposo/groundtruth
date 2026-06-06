"""Tests for template detection and field extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.document.processing.templates import (
    ExtractedField,
    FieldDefinition,
    TemplateExtractor,
    TemplateMatch,
)


def _make_ocr(text: str) -> MagicMock:
    """Create a minimal OCResult mock."""
    result = MagicMock()
    result.text = text
    result.blocks = []
    return result


class TestTemplateExtractor:
    """Tests for TemplateExtractor.detect_template()."""

    def setup_method(self) -> None:
        self.extractor = TemplateExtractor()

    @pytest.mark.asyncio
    async def test_detects_invoice(self) -> None:
        ocr = _make_ocr(
            "Invoice #INV-001\nBill To: Acme Corp\nShip To: Acme Corp\n"
            "Total Amount Due: $1,200.00\nPayment Terms: Net 30"
        )
        match = await self.extractor.detect_template(ocr)
        assert match is not None
        assert match.template_name == "invoice"
        assert match.confidence >= 0.3

    @pytest.mark.asyncio
    async def test_detects_contract(self) -> None:
        ocr = _make_ocr(
            "AGREEMENT between parties\nTerms and Conditions\n"
            "Effective Date: 2024-01-01\nSignature: ___"
        )
        match = await self.extractor.detect_template(ocr)
        assert match is not None
        assert match.template_name == "contract"

    @pytest.mark.asyncio
    async def test_detects_receipt(self) -> None:
        ocr = _make_ocr(
            "Receipt\nTransaction #12345\nPayment Method: Visa\n"
            "Total: $45.00\nChange: $0.00\nThank you"
        )
        match = await self.extractor.detect_template(ocr)
        assert match is not None
        assert match.template_name == "receipt"

    @pytest.mark.asyncio
    async def test_detects_w9(self) -> None:
        ocr = _make_ocr(
            "W-9 Form\nTaxpayer Identification Number\n"
            "Certification\nBackup Withholding: No\nSSN: 123-45-6789"
        )
        match = await self.extractor.detect_template(ocr)
        assert match is not None
        assert match.template_name == "form_w9"

    @pytest.mark.asyncio
    async def test_returns_none_for_unrecognized(self) -> None:
        ocr = _make_ocr("Hello world. This is a generic document with no template keywords.")
        match = await self.extractor.detect_template(ocr)
        assert match is None

    @pytest.mark.asyncio
    async def test_empty_text_returns_none(self) -> None:
        ocr = _make_ocr("")
        match = await self.extractor.detect_template(ocr)
        assert match is None

    def test_builtin_templates_exist(self) -> None:
        assert "invoice" in self.extractor.templates
        assert "contract" in self.extractor.templates
        assert "receipt" in self.extractor.templates
        assert "form_w9" in self.extractor.templates

    def test_field_definition_attributes(self) -> None:
        field = FieldDefinition("amount", "Amount", "number", required=True, pattern=r"\d+")
        assert field.name == "amount"
        assert field.field_type == "number"
        assert field.required is True
        assert field.pattern == r"\d+"

    def test_template_match_attributes(self) -> None:
        match = TemplateMatch(
            template_name="invoice",
            confidence=0.75,
            matched_keywords=["invoice", "total"],
            fields=[],
        )
        assert match.template_name == "invoice"
        assert match.confidence == 0.75
        assert len(match.matched_keywords) == 2
