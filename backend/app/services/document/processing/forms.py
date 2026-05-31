"""Form filling service for document processing.

Auto-fills forms from extracted data and external sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.document.processing.templates import ExtractedField, FieldDefinition


@dataclass
class FillResult:
    """Result of form filling operation."""
    field_name: str
    original_value: str | None
    filled_value: str
    source: str  # extracted, api, database, default, manual
    confidence: float


@dataclass
class FormFillReport:
    """Report for a complete form filling operation."""
    template_name: str
    filled_fields: list[FillResult]
    missing_fields: list[str]
    completion_rate: float
    sources_used: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class FormFiller:
    """Service for automatically filling forms from extracted data.
    
    Supports:
    - Filling from extracted OCR fields
    - API lookups (customer database, product catalog)
    - Database queries
    - Default values
    - Validation and formatting
    """
    
    def __init__(self) -> None:
        """Initialize form filler."""
        self.formatters: dict[str, callable] = {
            "date": self._format_date,
            "number": self._format_number,
            "currency": self._format_currency,
            "ssn": self._format_ssn,
            "phone": self._format_phone,
            "email": self._format_email,
        }
    
    async def fill_form(
        self,
        template_name: str,
        extracted_fields: list[ExtractedField],
        field_definitions: list[FieldDefinition],
        external_data: dict[str, Any] | None = None,
    ) -> FormFillReport:
        """Fill a form using extracted data and external sources.
        
        Args:
            template_name: Name of the template.
            extracted_fields: Fields extracted from document.
            field_definitions: Definitions of all fields in form.
            external_data: Optional external data sources.
            
        Returns:
            FormFillReport with filling results.
        """
        external_data = external_data or {}
        filled: list[FillResult] = []
        missing: list[str] = []
        sources: dict[str, int] = {}
        errors: list[str] = []
        
        # Create lookup from extracted fields
        extracted_lookup = {f.name: f for f in extracted_fields}
        
        for field_def in field_definitions:
            result = await self._fill_field(
                field_def,
                extracted_lookup.get(field_def.name),
                external_data,
            )
            
            if result:
                filled.append(result)
                sources[result.source] = sources.get(result.source, 0) + 1
            else:
                missing.append(field_def.name)
                if field_def.required:
                    errors.append(f"Required field '{field_def.name}' not filled")
        
        completion = len(filled) / len(field_definitions) if field_definitions else 1.0
        
        return FormFillReport(
            template_name=template_name,
            filled_fields=filled,
            missing_fields=missing,
            completion_rate=completion,
            sources_used=sources,
            errors=errors,
        )
    
    async def _fill_field(
        self,
        field_def: FieldDefinition,
        extracted: ExtractedField | None,
        external_data: dict[str, Any],
    ) -> FillResult | None:
        """Fill a single field using multiple strategies."""
        value: str | None = None
        source = "unknown"
        confidence = 0.0
        
        # Strategy 1: Use extracted value
        if extracted and extracted.value:
            value = extracted.value
            source = "extracted"
            confidence = extracted.confidence
        
        # Strategy 2: External API data
        if value is None and field_def.name in external_data:
            value = str(external_data[field_def.name])
            source = "api"
            confidence = 0.9
        
        # Strategy 3: Database lookup (placeholder)
        if value is None:
            db_value = await self._lookup_database(field_def)
            if db_value:
                value = db_value
                source = "database"
                confidence = 0.85
        
        # Strategy 4: Default value
        if value is None and field_def.default_value:
            value = field_def.default_value
            source = "default"
            confidence = 0.5
        
        if value is None:
            return None
        
        # Format value based on type
        formatted = self._format_value(value, field_def.field_type)
        
        # Validate
        if field_def.pattern and not re.match(field_def.pattern, formatted):
            # Try to fix
            formatted = self._attempt_fix(formatted, field_def)
        
        return FillResult(
            field_name=field_def.name,
            original_value=extracted.value if extracted else None,
            filled_value=formatted,
            source=source,
            confidence=confidence,
        )
    
    async def _lookup_database(self, field_def: FieldDefinition) -> str | None:
        """Look up field value from database.
        
        Placeholder for actual database integration.
        """
        # TODO: Integrate with actual database service
        return None
    
    def _format_value(self, value: str, field_type: str) -> str:
        """Format value based on field type."""
        formatter = self.formatters.get(field_type)
        if formatter:
            return formatter(value)
        return value
    
    def _format_date(self, value: str) -> str:
        """Standardize date format."""
        # Convert various date formats to ISO 8601
        patterns = [
            (r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", "{2}-{1:0>2}-{0:0>2}"),
            (r"(\d{1,2})[/-](\d{1,2})[/-](\d{2})", "20{2}-{1:0>2}-{0:0>2}"),
            (r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", "{0}-{1:0>2}-{2:0>2}"),
        ]
        
        for pattern, fmt in patterns:
            match = re.match(pattern, value)
            if match:
                groups = match.groups()
                return fmt.format(*groups)
        
        return value
    
    def _format_number(self, value: str) -> str:
        """Standardize number format."""
        # Remove currency symbols and commas
        cleaned = re.sub(r"[$€£,]", "", value)
        try:
            return str(float(cleaned))
        except ValueError:
            return value
    
    def _format_currency(self, value: str) -> str:
        """Standardize currency format."""
        return self._format_number(value)
    
    def _format_ssn(self, value: str) -> str:
        """Standardize SSN format."""
        digits = re.sub(r"\D", "", value)
        if len(digits) == 9:
            return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
        return value
    
    def _format_phone(self, value: str) -> str:
        """Standardize phone format."""
        digits = re.sub(r"\D", "", value)
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        return value
    
    def _format_email(self, value: str) -> str:
        """Standardize email format."""
        return value.lower().strip()
    
    def _attempt_fix(self, value: str, field_def: FieldDefinition) -> str:
        """Attempt to fix formatting issues."""
        if field_def.field_type == "date":
            return self._format_date(value)
        elif field_def.field_type == "number":
            return self._format_number(value)
        return value
    
    def validate_form(
        self,
        filled_fields: list[FillResult],
        field_definitions: list[FieldDefinition],
    ) -> list[str]:
        """Validate filled form and return list of errors."""
        errors: list[str] = []
        filled_names = {f.field_name for f in filled_fields}
        
        for field_def in field_definitions:
            if field_def.required and field_def.name not in filled_names:
                errors.append(f"Required field '{field_def.name}' is missing")
        
        for fill_result in filled_fields:
            if fill_result.confidence < 0.3:
                errors.append(
                    f"Low confidence ({fill_result.confidence:.2f}) for field "
                    f"'{fill_result.field_name}'"
                )
        
        return errors
