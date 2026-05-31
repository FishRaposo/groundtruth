"""Document processing API endpoints for GroundTruth."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.services.document.processing.ocr import OCRService
from app.services.document.processing.templates import TemplateExtractor

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/{document_id}/ocr")
async def process_ocr(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Process document with OCR."""
    from sqlalchemy import select
    from app.models.document import Document
    
    result = await db.execute(
        select(Document).where(Document.id == UUID(document_id))
    )
    document = result.scalar_one_or_none()
    
    if not document:
        return {"error": "Document not found"}
    
    ocr_service = OCRService()
    ocr_result = await ocr_service.process_document(document)
    
    return {
        "document_id": document_id,
        "text": ocr_result.text[:500] + "..." if len(ocr_result.text) > 500 else ocr_result.text,
        "total_pages": ocr_result.total_pages,
        "confidence": ocr_result.confidence,
        "blocks_count": len(ocr_result.blocks),
    }


@router.post("/{document_id}/detect-template")
async def detect_template(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Detect document template and extract fields."""
    from sqlalchemy import select
    from app.models.document import Document
    
    result = await db.execute(
        select(Document).where(Document.id == UUID(document_id))
    )
    document = result.scalar_one_or_none()
    
    if not document:
        return {"error": "Document not found"}
    
    ocr_service = OCRService()
    ocr_result = await ocr_service.process_document(document)
    
    template_extractor = TemplateExtractor()
    template_match = await template_extractor.detect_template(ocr_result)
    
    if template_match:
        extracted_fields = await template_extractor.extract_fields(ocr_result, template_match)
        
        return {
            "document_id": document_id,
            "template": template_match.template_name,
            "confidence": template_match.confidence,
            "matched_keywords": template_match.matched_keywords,
            "fields": [
                {
                    "name": field.name,
                    "value": field.value,
                    "confidence": field.confidence,
                }
                for field in extracted_fields
            ],
        }
    
    return {
        "document_id": document_id,
        "template": None,
        "message": "No matching template found",
    }


@router.get("/templates")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List available document templates."""
    extractor = TemplateExtractor()
    return extractor.get_template_list()
