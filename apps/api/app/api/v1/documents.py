"""Document processing API endpoints for GroundTruth."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.services.audit import audit_trail
from app.services.document.processing.ocr import (
    OCRService,
    OCRUnavailableError,
    ocr_available,
)
from app.services.document.processing.templates import TemplateExtractor
from app.services.document.versioning import DocumentVersionManager

router = APIRouter(prefix="/documents", tags=["documents"])

_OCR_UNAVAILABLE_DETAIL = (
    "OCR is not available: the optional OCR dependencies "
    "(pytesseract, pillow, pdf2image) are not installed on this deployment."
)


def _require_ocr() -> None:
    """Return a clean 503 when OCR dependencies are unavailable (offline default)."""
    if not ocr_available():
        raise HTTPException(status_code=503, detail=_OCR_UNAVAILABLE_DETAIL)


@router.post("/{document_id}/ocr")
async def process_ocr(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Process document with OCR."""
    from sqlalchemy import select

    from app.models.document import Document

    _require_ocr()

    result = await db.execute(select(Document).where(Document.id == UUID(document_id)))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    ocr_service = OCRService()
    try:
        ocr_result = await ocr_service.process_document(document)
    except OCRUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {
        "document_id": document_id,
        "text": ocr_result.text[:500] + "..."
        if len(ocr_result.text) > 500
        else ocr_result.text,
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

    _require_ocr()

    result = await db.execute(select(Document).where(Document.id == UUID(document_id)))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    ocr_service = OCRService()
    try:
        ocr_result = await ocr_service.process_document(document)
    except OCRUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    template_extractor = TemplateExtractor()
    template_match = await template_extractor.detect_template(ocr_result)

    if template_match:
        extracted_fields = await template_extractor.extract_fields(
            ocr_result, template_match
        )

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


@router.get("/{document_id}/versions")
async def list_document_versions(
    document_id: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List immutable document snapshots newest first."""
    return await DocumentVersionManager(db).get_version_history(
        document_id,
        limit,
        workspace_id=current_user.get("workspace_id", "default"),
    )


@router.get("/{document_id}/versions/diff")
async def diff_document_versions(
    document_id: str,
    from_version: int,
    to_version: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return a deterministic diff for two visible snapshots."""
    try:
        return await DocumentVersionManager(db).diff_versions(
            document_id,
            from_version,
            to_version,
            workspace_id=current_user.get("workspace_id", "default"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{document_id}/versions/{version_number}/restore")
async def restore_document_version(
    document_id: str,
    version_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Restore an immutable snapshot as a new current version."""
    try:
        document = await DocumentVersionManager(db).restore_version(
            document_id,
            version_number,
            workspace_id=current_user.get("workspace_id", "default"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await audit_trail.record(
        actor_id=current_user["id"],
        action="restore_version",
        resource_type="document",
        resource_id=document_id,
        workspace_id=current_user.get("workspace_id", "default"),
        metadata={"restored_version": version_number},
        db=db,
    )
    return {
        "document_id": document_id,
        "restored_version": version_number,
        "new_version": document.version_number,
        "content_hash": document.content_hash,
    }
