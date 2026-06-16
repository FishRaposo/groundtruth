import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.document import (
    Document,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    SourceType,
)
from app.services.ingestion import ingestion_service

router = APIRouter(tags=["documents"])


_EXTENSION_MAP: dict[str, SourceType] = {
    ".pdf": SourceType.PDF,
    ".md": SourceType.MARKDOWN,
    ".markdown": SourceType.MARKDOWN,
    ".html": SourceType.HTML,
    ".htm": SourceType.HTML,
    ".docx": SourceType.DOCX,
}


def _detect_source_type(filename: str) -> SourceType:
    """Determine the source type from a file extension."""
    lower = filename.lower()
    for ext, source_type in _EXTENSION_MAP.items():
        if lower.endswith(ext):
            return source_type
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")


def _safe_extension(filename: str) -> str:
    """Return the validated, lowercased extension for a supported filename.

    The raw multipart filename is attacker-controlled, so we never trust it
    for path construction. Only the extension (validated against the supported
    set) is reused; the stored filename is derived from the document UUID.
    """
    lower = filename.lower()
    for ext in _EXTENSION_MAP:
        if lower.endswith(ext):
            return ext
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")


def _resolve_storage_path(upload_dir: str, stored_name: str) -> str:
    """Join ``stored_name`` into ``upload_dir`` and assert it cannot escape it.

    ``stored_name`` is derived from a trusted document UUID, but we defensively
    strip any path components with ``basename`` and verify via ``realpath`` that
    the result stays inside ``upload_dir`` before any file is written. Raises a
    400 if containment cannot be guaranteed.
    """
    safe_name = os.path.basename(stored_name)
    file_path = os.path.join(upload_dir, safe_name)
    real_upload_dir = os.path.realpath(upload_dir)
    real_file_path = os.path.realpath(file_path)
    if os.path.commonpath([real_upload_dir, real_file_path]) != real_upload_dir:
        raise HTTPException(status_code=400, detail="Invalid upload path")
    return file_path


@router.post("/documents/upload", response_model=dict[str, list[DocumentResponse]])
async def upload_documents(
    files: list[UploadFile],
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[DocumentResponse]]:
    """Upload one or more documents for ingestion and processing.

    Accepts PDF, Markdown, HTML, and DOCX files. Each file is parsed,
    chunked, and embedded asynchronously after upload.
    """
    uploaded: list[DocumentResponse] = []

    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        source_type = _detect_source_type(file.filename)
        extension = _safe_extension(file.filename)
        document = Document(
            title=file.filename,
            source_type=source_type,
            status=DocumentStatus.PENDING,
        )
        db.add(document)
        await db.flush()
        doc_response = DocumentResponse.model_validate(document)

        upload_dir = f"data/uploads/{document.id}"
        os.makedirs(upload_dir, exist_ok=True)
        # Never trust the attacker-controlled multipart filename for path
        # construction: store under a name derived from the document UUID plus
        # the validated extension. _resolve_storage_path strips directory
        # components and asserts realpath containment within upload_dir.
        stored_name = f"{document.id}{extension}"
        file_path = _resolve_storage_path(upload_dir, stored_name)
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        uploaded.append(doc_response)

    await db.commit()

    for doc_response in uploaded:
        await ingestion_service.process_document(doc_response.id)

    return {"documents": uploaded}


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    status: DocumentStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> DocumentListResponse:
    """List all uploaded documents with optional status filtering and pagination."""
    query = select(Document).order_by(Document.created_at.desc())
    count_query = select(func.count()).select_from(Document)

    if status is not None:
        query = query.where(Document.status == status)
        count_query = count_query.where(Document.status == status)

    total_result = await db.execute(count_query)
    total: int = total_result.scalar() or 0

    result = await db.execute(query.offset(offset).limit(limit))
    documents = list(result.scalars().all())

    return DocumentListResponse(
        documents=[DocumentResponse.model_validate(d) for d in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    """Retrieve details for a specific document by its identifier."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentResponse.model_validate(document)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a document and all associated chunks and embeddings."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    await ingestion_service.delete_document(document_id)
    await db.delete(document)
    await db.commit()


@router.post("/documents/{document_id}/reindex", response_model=dict[str, str])
async def reindex_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Re-process and re-embed a document, replacing all existing chunks."""
    result = await db.execute(select(Document).where(Document.id == document_id))
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    document.status = DocumentStatus.PENDING
    await db.commit()

    await ingestion_service.reindex_document(document_id)

    return {
        "id": str(document_id),
        "status": "pending",
        "message": "Re-indexing started",
    }
