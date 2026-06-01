"""Template extraction service for document processing.

Detects document templates and extracts structured fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.document.processing.ocr import OCResult, OCRBlock


@dataclass
class FieldDefinition:
    """Definition of a field in a template."""
    name: str
    label: str
    field_type: str  # text, number, date, signature, checkbox
    required: bool = False
    pattern: str | None = None
    default_value: str | None = None
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


@dataclass
class TemplateMatch:
    """Result of template matching."""
    template_name: str
    confidence: float
    matched_keywords: list[str]
    fields: list[FieldDefinition]
    page_count: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedField:
    """Extracted field value."""
    name: str
    value: str
    confidence: float
    source_text: str


class TemplateExtractor:
    """Extract structured fields from documents using template matching.
    
    Supports:
    - Invoice templates
    - Contract templates
    - Form templates
    - Custom user-defined templates
    """
    
    # Built-in template definitions
    BUILT_IN_TEMPLATES: dict[str, dict[str, Any]] = {
        "invoice": {
            "keywords": ["invoice", "bill to", "ship to", "total", "amount due", "payment terms"],
            "fields": [
                FieldDefinition("invoice_number", "Invoice #", "text", True, r"INV?[-#]?\s*(\w+)"),
                FieldDefinition("date", "Date", "date", True, r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"),
                FieldDefinition("total", "Total", "number", True, r"[$€£]?\s*([\d,]+\.?\d*)"),
                FieldDefinition("vendor", "From/Vendor", "text"),
                FieldDefinition("customer", "Bill To", "text"),
            ],
        },
        "contract": {
            "keywords": ["agreement", "contract", "parties", "terms and conditions", "signature"],
            "fields": [
                FieldDefinition("parties", "Parties", "text", True),
                FieldDefinition("effective_date", "Effective Date", "date", True),
                FieldDefinition("term", "Term", "text"),
                FieldDefinition("value", "Contract Value", "number"),
                FieldDefinition("signatures", "Signatures", "signature", True),
            ],
        },
        "receipt": {
            "keywords": ["receipt", "transaction", "payment method", "change", "thank you"],
            "fields": [
                FieldDefinition("transaction_id", "Transaction #", "text", True),
                FieldDefinition("date", "Date/Time", "date", True),
                FieldDefinition("total", "Total", "number", True),
                FieldDefinition("payment_method", "Payment Method", "text"),
                FieldDefinition("merchant", "Merchant", "text"),
            ],
        },
        "form_w9": {
            "keywords": ["w-9", "taxpayer identification", "certification", "backup withholding"],
            "fields": [
                FieldDefinition("name", "Name", "text", True),
                FieldDefinition("business_name", "Business Name", "text"),
                FieldDefinition("tax_classification", "Tax Classification", "text"),
                FieldDefinition("ssn", "SSN", "text", True, r"\d{3}-\d{2}-\d{4}"),
                FieldDefinition("ein", "EIN", "text", False, r"\d{2}-\d{7}"),
                FieldDefinition("address", "Address", "text", True),
                FieldDefinition("signature_date", "Date", "date", True),
                FieldDefinition("signature", "Signature", "signature", True),
            ],
        },
    }
    
    def __init__(self) -> None:
        """Initialize template extractor."""
        self.templates = dict(self.BUILT_IN_TEMPLATES)
    
    async def detect_template(self, ocr_result: OCResult) -> TemplateMatch | None:
        """Detect which template a document matches.
        
        Args:
            ocr_result: OCR result from document processing.
            
        Returns:
            TemplateMatch if template detected, None otherwise.
        """
        text_lower = ocr_result.text.lower()
        words = set(re.findall(r'\b\w+\b', text_lower))
        
        best_match: TemplateMatch | None = None
        best_score = 0.0
        
        for template_name, template_def in self.templates.items():
            keywords = [k.lower() for k in template_def["keywords"]]
            matched = [k for k in keywords if k in text_lower]
            
            score = len(matched) / len(keywords)
            
            # Boost score for exact keyword matches
            keyword_score = sum(1 for k in keywords if k in words) / len(keywords)
            score = score * 0.5 + keyword_score * 0.5
            
            if score > best_score and score >= 0.3:  # Minimum threshold
                best_score = score
                best_match = TemplateMatch(
                    template_name=template_name,
                    confidence=score,
                    matched_keywords=matched,
                    fields=template_def["fields"],
                    page_count=ocr_result.total_pages,
                )
        
        return best_match
    
    async def extract_fields(
        self,
        ocr_result: OCResult,
        template_match: TemplateMatch,
    ) -> list[ExtractedField]:
        """Extract field values from document using template.
        
        Args:
            ocr_result: OCR result.
            template_match: Detected template match.
            
        Returns:
            List of extracted fields with values.
        """
        extracted: list[ExtractedField] = []
        text = ocr_result.text
        blocks_by_position = sorted(ocr_result.blocks, key=lambda b: (b.y, b.x))
        
        for template_field in template_match.fields:
            value = None
            confidence = 0.0
            source_text = ""
            
            # Strategy 1: Pattern matching (regex)
            if template_field.pattern:
                match = re.search(template_field.pattern, text, re.IGNORECASE)
                if match:
                    value = match.group(1) if match.groups() else match.group(0)
                    confidence = 0.8
                    source_text = match.group(0)
            
            # Strategy 2: Label proximity (find label text, look nearby for value)
            if value is None:
                value, confidence, source_text = self._find_by_proximity(
                    template_field, blocks_by_position, ocr_result.blocks
                )
            
            # Strategy 3: Section-based extraction (find section header, extract below)
            if value is None:
                value, confidence, source_text = self._find_in_section(
                    template_field, ocr_result.blocks
                )
            
            if value:
                extracted.append(ExtractedField(
                    name=template_field.name,
                    value=value,
                    confidence=confidence,
                    source_text=source_text,
                ))
        
        return extracted
    
    def _find_by_proximity(
        self,
        field: FieldDefinition,
        sorted_blocks: list[OCRBlock],
        all_blocks: list[OCRBlock],
    ) -> tuple[str | None, float, str]:
        """Find field value by proximity to label."""
        label_lower = field.label.lower()
        
        for i, block in enumerate(sorted_blocks):
            if label_lower in block.text.lower():
                # Look at blocks to the right (same line) or below
                nearby = [
                    b for b in all_blocks
                    if b != block
                    and abs(b.y - block.y) < 50  # Same row
                    and b.x > block.x  # To the right
                ]
                
                if nearby:
                    nearest = min(nearby, key=lambda b: b.x)
                    return nearest.text, 0.7, nearest.text
                
                # Try below
                below = [
                    b for b in all_blocks
                    if b != block
                    and block.y < b.y < block.y + 100
                    and abs(b.x - block.x) < 200
                ]
                
                if below:
                    nearest = min(below, key=lambda b: b.y)
                    return nearest.text, 0.6, nearest.text
        
        return None, 0.0, ""
    
    def _find_in_section(
        self,
        field: FieldDefinition,
        blocks: list[OCRBlock],
    ) -> tuple[str | None, float, str]:
        """Find field value within a document section."""
        # Find section header
        section_keywords = {
            "vendor": ["from", "seller", "vendor", "billed by"],
            "customer": ["bill to", "ship to", "customer", "buyer"],
            "total": ["total", "amount due", "balance due"],
        }
        
        keywords = section_keywords.get(field.name, [field.label.lower()])
        
        for block in blocks:
            block_text = block.text.lower()
            if any(kw in block_text for kw in keywords):
                # Look for value in nearby blocks
                nearby = [
                    b for b in blocks
                    if b != block
                    and abs(b.y - block.y) < 150
                    and abs(b.x - block.x) < 300
                ]
                
                if nearby:
                    values = [b.text for b in nearby if len(b.text) > 2]
                    if values:
                        return values[0], 0.5, values[0]
        
        return None, 0.0, ""
    
    def add_custom_template(
        self,
        name: str,
        keywords: list[str],
        fields: list[FieldDefinition],
    ) -> None:
        """Add a custom template definition.
        
        Args:
            name: Template name.
            keywords: List of keywords that identify this template.
            fields: List of field definitions.
        """
        self.templates[name] = {
            "keywords": keywords,
            "fields": fields,
        }
    
    def get_template_list(self) -> list[dict[str, Any]]:
        """Get list of available templates."""
        return [
            {
                "name": name,
                "keywords": def_["keywords"],
                "field_count": len(def_["fields"]),
            }
            for name, def_ in self.templates.items()
        ]
