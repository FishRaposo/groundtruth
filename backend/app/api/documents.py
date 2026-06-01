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


def _detect_source_type(filename: str) -> SourceType:
    """Determine the source type from a file extension."""
    extension_map: dict[str, SourceType] = {
        ".pdf": SourceType.PDF,
        ".md": SourceType.MARKDOWN,
        ".markdown": SourceType.MARKDOWN,
        ".html": SourceType.HTML,
        ".htm": SourceType.HTML,
        ".docx": SourceType.DOCX,
    }
    lower = filename.lower()
    for ext, source_type in extension_map.items():
        if lower.endswith(ext):
            return source_type
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")


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
        file_path = os.path.join(upload_dir, file.filename)
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

    return {"id": str(document_id), "status": "pending", "message": "Re-indexing started"}
