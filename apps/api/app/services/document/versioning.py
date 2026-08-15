"""Persistent document snapshots, deterministic diffs, and restoration."""

from __future__ import annotations

import difflib
import hashlib
import uuid
from typing import Any

from app.internal.context import DEFAULT_WORKSPACE_ID
from app.models.chunk import Chunk
from app.models.document import Document, DocumentVersion
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


class DocumentVersionManager:
    """Manage immutable, workspace-scoped document snapshots."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Return the SHA-256 of normalized UTF-8 content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def _chunk_data(chunks: list[Chunk]) -> list[dict[str, Any]]:
        return [
            {
                "id": str(chunk.id) if chunk.id else None,
                "content": chunk.content,
                "index": chunk.chunk_index,
                "metadata": chunk.metadata_ or {},
            }
            for chunk in sorted(chunks, key=lambda value: value.chunk_index)
        ]

    async def _document(self, document_id: str, workspace_id: str) -> Document | None:
        try:
            identifier = uuid.UUID(document_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(Document).where(
                Document.id == identifier,
                Document.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def _version(
        self, document_id: str, version_number: int, workspace_id: str
    ) -> DocumentVersion | None:
        try:
            identifier = uuid.UUID(document_id)
        except ValueError:
            return None
        result = await self.db.execute(
            select(DocumentVersion).where(
                DocumentVersion.document_id == identifier,
                DocumentVersion.version_number == version_number,
                DocumentVersion.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_version(
        self,
        document_id: str,
        content: str,
        chunks: list[Chunk],
        change_summary: str | None = None,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        document: Document | None = None,
    ) -> DocumentVersion:
        """Persist the next immutable version, unless content is unchanged."""
        document = document or await self._document(document_id, workspace_id)
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        content_hash = self.compute_content_hash(content)
        raw_version = getattr(document, "version_number", 0)
        current_version = raw_version if isinstance(raw_version, int) else 0
        if document.content_hash == content_hash and current_version:
            existing = await self._version(document_id, current_version, workspace_id)
            if existing is not None:
                return existing

        snapshot = DocumentVersion(
            document_id=document.id,
            workspace_id=workspace_id,
            version_number=current_version + 1,
            content_hash=content_hash,
            normalized_content=content,
            chunks=self._chunk_data(chunks),
            change_summary=change_summary,
        )
        self.db.add(snapshot)
        document.previous_version_id = (
            document.id if current_version > 0 else document.previous_version_id
        )
        document.version_number = snapshot.version_number
        document.content_hash = content_hash
        metadata = dict(document.metadata_ or {})
        metadata["normalized_content"] = content
        document.metadata_ = metadata
        await self.db.commit()
        await self.db.refresh(snapshot)
        return snapshot

    async def get_version_history(
        self,
        document_id: str,
        limit: int = 10,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> list[dict[str, Any]]:
        """Return newest-first version metadata visible in one workspace."""
        document = await self._document(document_id, workspace_id)
        if document is None:
            return []
        result = await self.db.execute(
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.workspace_id == workspace_id,
            )
            .order_by(DocumentVersion.version_number.desc())
            .limit(limit)
        )
        return [version.to_dict() for version in result.scalars().all()]

    async def diff_versions(
        self,
        document_id: str,
        from_version: int,
        to_version: int,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> dict[str, Any]:
        """Compute a deterministic line/chunk diff between stored versions."""
        old = await self._version(document_id, from_version, workspace_id)
        new = await self._version(document_id, to_version, workspace_id)
        if old is None or new is None:
            raise ValueError("Document version not found")
        result = self.compute_diff(
            old.normalized_content,
            new.normalized_content,
            old.chunks,
            new.chunks,
        )
        result.update({"from_version": from_version, "to_version": to_version})
        return result

    def compute_diff(
        self,
        old_content: str,
        new_content: str,
        old_chunks: list[dict[str, Any]] | None = None,
        new_chunks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        line_diff = list(
            difflib.unified_diff(
                old_lines,
                new_lines,
                lineterm="",
                fromfile="previous",
                tofile="current",
            )
        )
        added_lines = sum(
            line.startswith("+") and not line.startswith("+++") for line in line_diff
        )
        removed_lines = sum(
            line.startswith("-") and not line.startswith("---") for line in line_diff
        )
        chunk_changes = self._compute_chunk_diff(old_chunks or [], new_chunks or [])
        return {
            "line_diff": "\n".join(line_diff),
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "total_changes": added_lines + removed_lines,
            "chunk_changes": chunk_changes,
            "similarity_ratio": difflib.SequenceMatcher(
                None, old_content, new_content
            ).ratio(),
        }

    @staticmethod
    def _compute_chunk_diff(
        old_chunks: list[dict[str, Any]], new_chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        changes: list[dict[str, Any]] = []
        old_by_index = {
            chunk.get("index", i): chunk for i, chunk in enumerate(old_chunks)
        }
        new_by_index = {
            chunk.get("index", i): chunk for i, chunk in enumerate(new_chunks)
        }
        for index in sorted(set(old_by_index) | set(new_by_index)):
            old = old_by_index.get(index)
            new = new_by_index.get(index)
            if old is None and new is not None:
                changes.append(
                    {
                        "type": "added",
                        "chunk_index": index,
                        "preview": new.get("content", "")[:100] + "...",
                    }
                )
            elif new is None and old is not None:
                changes.append(
                    {
                        "type": "removed",
                        "chunk_index": index,
                        "preview": old.get("content", "")[:100] + "...",
                    }
                )
            elif (
                old is not None
                and new is not None
                and old.get("content", "") != new.get("content", "")
            ):
                content = new.get("content", "")
                changes.append(
                    {
                        "type": "modified",
                        "chunk_index": index,
                        "similarity": round(
                            difflib.SequenceMatcher(
                                None, old.get("content", ""), content
                            ).ratio(),
                            2,
                        ),
                        "preview": content[:100] + "...",
                    }
                )
        return changes

    async def restore_version(
        self,
        document_id: str,
        version_number: int,
        *,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> Document:
        """Restore a snapshot as a new version, preserving immutable history."""
        document = await self._document(document_id, workspace_id)
        snapshot = await self._version(document_id, version_number, workspace_id)
        if document is None or snapshot is None:
            raise ValueError("Document version not found")

        await self.db.execute(delete(Chunk).where(Chunk.document_id == document.id))
        chunks = [
            Chunk(
                document_id=document.id,
                content=str(item.get("content", "")),
                chunk_index=int(item.get("index", index)),
                metadata_=dict(item.get("metadata", {})),
            )
            for index, item in enumerate(snapshot.chunks or [])
        ]
        self.db.add_all(chunks)
        document.content_hash = None
        restored = await self.create_version(
            document_id,
            snapshot.normalized_content,
            chunks,
            f"Restored version {version_number}",
            workspace_id=workspace_id,
        )
        document.chunk_count = len(chunks)
        document.content_hash = restored.content_hash
        await self.db.commit()
        return document

    def generate_change_summary(self, old_content: str, new_content: str) -> str:
        diff = self.compute_diff(old_content, new_content)
        if diff["total_changes"] == 0:
            return "No changes"
        parts: list[str] = []
        if diff["added_lines"]:
            parts.append(f"{diff['added_lines']} lines added")
        if diff["removed_lines"]:
            parts.append(f"{diff['removed_lines']} lines removed")
        similarity = round(diff["similarity_ratio"] * 100, 1)
        parts.append(f"{similarity}% similarity to previous version")
        return ", ".join(parts)
