import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import get_settings
from app.db.session import get_db
from app.models.document import (
    Document,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatus,
    SourceType,
)
from app.models.ingestion import IngestionJob
from app.services.access_control.scope import document_scope, require_document
from app.services.audit import audit_trail
from app.services.ingestion import ingestion_service

router = APIRouter(tags=["documents"])
settings = get_settings()


async def document_response(
    db: AsyncSession, document: Document, user: dict[str, Any]
) -> DocumentResponse:
    response = DocumentResponse.model_validate(document)
    writable = await db.scalar(
        select(Document.id).where(
            Document.id == document.id, document_scope(user, write=True)
        )
    )
    response.permissions = {
        "read": True,
        "write": writable is not None,
        "admin": bool(user.get("is_admin") or document.owner_id == user["id"]),
    }
    latest = await db.scalar(
        select(IngestionJob)
        .where(IngestionJob.document_id == document.id)
        .order_by(IngestionJob.updated_at.desc(), IngestionJob.created_at.desc())
        .limit(1)
    )
    response.latest_ingestion = latest.to_dict() if latest else None
    if response.metadata:
        response.metadata = {
            key: value
            for key, value in response.metadata.items()
            if key not in {"source_path", "quarantine", "error"}
        }
    return response


_EXTENSION_MAP: dict[str, SourceType] = {
    ".txt": SourceType.TEXT,
    ".pdf": SourceType.PDF,
    ".md": SourceType.MARKDOWN,
    ".markdown": SourceType.MARKDOWN,
    ".html": SourceType.HTML,
    ".htm": SourceType.HTML,
    ".docx": SourceType.DOCX,
    ".csv": SourceType.CSV,
    ".tsv": SourceType.TSV,
    ".xlsx": SourceType.XLSX,
    ".pptx": SourceType.PPTX,
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


@router.post("/documents/upload")
async def upload_documents(  # noqa: C901 - bounded validation and legacy adapter
    files: list[UploadFile],
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload one or more documents for ingestion and processing.

    Accepts text, PDF, Markdown, HTML, DOCX, CSV/TSV, XLSX, and PPTX files. Each is
    parsed, chunked, and embedded asynchronously after upload.
    """
    if settings.AUTH_ENABLED and not settings.connected:
        raise HTTPException(
            503,
            (
                "Configure explicit connected embedding and generation "
                "modes before authenticated ingestion."
            ),
        )
    if settings.connected:
        from app.services.ingestion_jobs import create_job, dispatch_job

        if not files or len(files) > 5:
            raise HTTPException(400, "Upload between one and five files")
        # Validate the complete request before creating records or writing files.
        validated = []
        for file in files:
            if not file.filename:
                raise HTTPException(400, "Filename is required")
            contents = await file.read(10 * 1024 * 1024 + 1)
            if len(contents) > 10 * 1024 * 1024:
                raise HTTPException(413, "Each file must be at most 10 MiB")
            validated.append(
                (
                    file,
                    contents,
                    _detect_source_type(file.filename),
                    _safe_extension(file.filename),
                )
            )
        documents, jobs = [], []
        for file, contents, source_type, extension in validated:
            document = Document(
                title=os.path.basename(
                    (file.filename or "document").replace("\\", "/")
                ),
                source_type=source_type,
                status=DocumentStatus.PENDING,
                workspace_id=current_user.get("workspace_id", "default"),
                owner_id=str(current_user["id"]),
                file_size=len(contents),
            )
            db.add(document)
            await db.flush()
            upload_dir = os.path.join(settings.STORAGE_ROOT, str(document.id))
            os.makedirs(upload_dir, exist_ok=True)
            file_path = _resolve_storage_path(upload_dir, f"{uuid.uuid4()}{extension}")
            with open(file_path, "wb") as handle:
                handle.write(contents)
            job = await create_job(
                db, document, current_user, source_path=os.path.abspath(file_path)
            )
            await dispatch_job(job.id)
            await db.refresh(document)
            await db.refresh(job)
            documents.append(
                (await document_response(db, document, current_user)).model_dump(
                    mode="json"
                )
            )
            jobs.append(job.to_dict())
        return {"documents": documents, "ingestions": jobs}
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
        await audit_trail.record(
            actor_id="request",
            action="create",
            resource_type="document",
            resource_id=str(doc_response.id),
            metadata={"source_type": doc_response.source_type.value},
        )

    for doc_response in uploaded:
        await ingestion_service.process_document(doc_response.id)

    return {"documents": uploaded}


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    status: DocumentStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DocumentListResponse:
    "List all uploaded documents with optional status filtering and pagination."
    query = (
        select(Document)
        .where(document_scope(current_user))
        .order_by(Document.created_at.desc())
    )
    count_query = (
        select(func.count()).select_from(Document).where(document_scope(current_user))
    )

    if status is not None:
        query = query.where(Document.status == status)
        count_query = count_query.where(Document.status == status)

    total_result = await db.execute(count_query)
    total: int = total_result.scalar() or 0

    result = await db.execute(query.offset(offset).limit(limit))
    documents = list(result.scalars().all())

    return DocumentListResponse(
        documents=[await document_response(db, d, current_user) for d in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DocumentResponse:
    """Retrieve details for a specific document by its identifier."""
    document = await require_document(db, document_id, current_user)
    return await document_response(db, document, current_user)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> None:
    """Delete a document and all associated chunks and embeddings."""
    document = await require_document(db, document_id, current_user, write=True)
    from sqlalchemy import delete

    from app.models.chunk import Chunk
    from app.models.collection import collection_documents
    from app.models.document import DocumentVersion

    await db.execute(
        delete(IngestionJob).where(IngestionJob.document_id == document_id)
    )
    await db.execute(
        delete(DocumentVersion).where(DocumentVersion.document_id == document_id)
    )
    await db.execute(
        delete(collection_documents).where(
            collection_documents.c.document_id == document_id
        )
    )
    await db.execute(delete(Chunk).where(Chunk.document_id == document_id))
    await db.delete(document)
    await db.commit()
    await audit_trail.record(
        actor_id="request",
        action="delete",
        resource_type="document",
        resource_id=str(document_id),
    )


@router.post("/documents/{document_id}/reindex", response_model=dict[str, str])
async def reindex_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, str]:
    """Re-process and re-embed a document, replacing all existing chunks."""
    document = await require_document(db, document_id, current_user, write=True)
    if settings.connected:
        from app.services.ingestion_jobs import create_job, dispatch_job

        job = await create_job(
            db, document, current_user, source_path=None, kind="reindex"
        )
        await dispatch_job(job.id)
        await db.refresh(job)
        return {
            "id": str(document.id),
            "status": job.status,
            "message": "Explicit reindex requested",
            "ingestion_id": str(job.id),
        }

    document.status = DocumentStatus.PENDING
    await db.commit()

    await ingestion_service.reindex_document(document_id)
    await audit_trail.record(
        actor_id="request",
        action="reindex",
        resource_type="document",
        resource_id=str(document_id),
    )

    return {
        "id": str(document_id),
        "status": "pending",
        "message": "Re-indexing started",
    }
