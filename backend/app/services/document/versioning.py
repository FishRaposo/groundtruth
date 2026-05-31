"""Document versioning with diff visualization.

Tracks document changes over time and provides diff views
for understanding what changed between versions.
"""

from __future__ import annotations

import difflib
import hashlib
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.chunk import Chunk


class DocumentVersion:
    """Represents a version snapshot of a document."""
    
    def __init__(
        self,
        document_id: str,
        version_number: int,
        content_hash: str,
        content: str,
        chunks: list[dict[str, Any]],
        created_at: datetime,
        change_summary: str | None = None,
    ) -> None:
        self.document_id = document_id
        self.version_number = version_number
        self.content_hash = content_hash
        self.content = content
        self.chunks = chunks
        self.created_at = created_at
        self.change_summary = change_summary
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "document_id": self.document_id,
            "version_number": self.version_number,
            "content_hash": self.content_hash,
            "created_at": self.created_at.isoformat(),
            "change_summary": self.change_summary,
            "chunk_count": len(self.chunks),
        }


class DocumentVersionManager:
    """Manages document versioning and history.
    
    Provides:
    - Version creation on document updates
    - Diff visualization between versions
    - Version restoration
    - Change summaries
    """
    
    def __init__(self, db: AsyncSession) -> None:
        """Initialize version manager.
        
        Args:
            db: Database session.
        """
        self.db = db
    
    @staticmethod
    def compute_content_hash(content: str) -> str:
        """Compute hash for content.
        
        Args:
            content: Document content.
            
        Returns:
            SHA256 hash of content.
        """
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def create_version(
        self,
        document_id: str,
        content: str,
        chunks: list[Chunk],
        change_summary: str | None = None,
    ) -> DocumentVersion:
        """Create a new version for a document.
        
        Args:
            document_id: Document ID.
            content: Full document content.
            chunks: Document chunks.
            change_summary: Human-readable summary of changes.
            
        Returns:
            Created version.
        """
        # Get current version number
        result = await self.db.execute(
            select(Document)
            .where(Document.id == uuid.UUID(document_id))
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        # Determine next version number
        current_version = getattr(document, 'version_number', 0) or 0
        next_version = current_version + 1
        
        # Compute content hash
        content_hash = self.compute_content_hash(content)
        
        # Check if content actually changed
        if hasattr(document, 'content_hash') and document.content_hash == content_hash:
            # No change, don't create new version
            return DocumentVersion(
                document_id=document_id,
                version_number=current_version,
                content_hash=content_hash,
                content=content,
                chunks=[{"id": str(c.id), "content": c.content} for c in chunks],
                created_at=datetime.utcnow(),
                change_summary="No changes",
            )
        
        # Store chunks for this version
        chunk_data = [
            {
                "id": str(chunk.id),
                "content": chunk.content,
                "index": chunk.chunk_index,
                "embedding": None,  # Don't store embeddings in version
            }
            for chunk in chunks
        ]
        
        # TODO: Store version in separate table
        # For now, update document metadata
        document.version_number = next_version
        document.content_hash = content_hash
        if hasattr(document, 'previous_version_id'):
            document.previous_version_id = document.id if current_version > 0 else None
        
        await self.db.commit()
        
        return DocumentVersion(
            document_id=document_id,
            version_number=next_version,
            content_hash=content_hash,
            content=content,
            chunks=chunk_data,
            created_at=datetime.utcnow(),
            change_summary=change_summary,
        )
    
    async def get_version_history(
        self,
        document_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get version history for a document.
        
        Args:
            document_id: Document ID.
            limit: Maximum versions to return.
            
        Returns:
            List of version metadata.
        """
        # TODO: Query from version table when implemented
        # For now, return current version only
        
        result = await self.db.execute(
            select(Document)
            .where(Document.id == uuid.UUID(document_id))
        )
        document = result.scalar_one_or_none()
        
        if not document:
            return []
        
        current_version = getattr(document, 'version_number', 1) or 1
        
        return [
            {
                "version_number": current_version,
                "created_at": document.updated_at.isoformat() if document.updated_at else None,
                "content_hash": getattr(document, 'content_hash', 'unknown'),
                "change_summary": "Current version",
            }
        ]
    
    def compute_diff(
        self,
        old_content: str,
        new_content: str,
        old_chunks: list[dict[str, Any]] | None = None,
        new_chunks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Compute diff between two versions.
        
        Args:
            old_content: Previous version content.
            new_content: Current version content.
            old_chunks: Previous chunks.
            new_chunks: Current chunks.
            
        Returns:
            Diff information including line and chunk changes.
        """
        # Line-level diff
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        
        line_diff = list(difflib.unified_diff(
            old_lines,
            new_lines,
            lineterm='',
            fromfile='previous',
            tofile='current',
        ))
        
        # Compute statistics
        added_lines = sum(1 for line in line_diff if line.startswith('+') and not line.startswith('+++'))
        removed_lines = sum(1 for line in line_diff if line.startswith('-') and not line.startswith('---'))
        
        # Chunk-level diff if chunks provided
        chunk_changes = []
        if old_chunks and new_chunks:
            chunk_changes = self._compute_chunk_diff(old_chunks, new_chunks)
        
        return {
            "line_diff": '\n'.join(line_diff),
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "total_changes": added_lines + removed_lines,
            "chunk_changes": chunk_changes,
            "similarity_ratio": difflib.SequenceMatcher(None, old_content, new_content).ratio(),
        }
    
    def _compute_chunk_diff(
        self,
        old_chunks: list[dict[str, Any]],
        new_chunks: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Compute differences at chunk level.
        
        Args:
            old_chunks: Previous chunks.
            new_chunks: Current chunks.
            
        Returns:
            List of chunk changes.
        """
        changes = []
        
        # Build lookup by chunk index
        old_by_index = {c.get('index', i): c for i, c in enumerate(old_chunks)}
        new_by_index = {c.get('index', i): c for i, c in enumerate(new_chunks)}
        
        # Find added chunks
        for idx, chunk in new_by_index.items():
            if idx not in old_by_index:
                changes.append({
                    "type": "added",
                    "chunk_index": idx,
                    "preview": chunk.get('content', '')[:100] + "...",
                })
        
        # Find removed chunks
        for idx, chunk in old_by_index.items():
            if idx not in new_by_index:
                changes.append({
                    "type": "removed",
                    "chunk_index": idx,
                    "preview": chunk.get('content', '')[:100] + "...",
                })
        
        # Find modified chunks
        for idx in set(old_by_index.keys()) & set(new_by_index.keys()):
            old_content = old_by_index[idx].get('content', '')
            new_content = new_by_index[idx].get('content', '')
            
            if old_content != new_content:
                similarity = difflib.SequenceMatcher(None, old_content, new_content).ratio()
                changes.append({
                    "type": "modified",
                    "chunk_index": idx,
                    "similarity": round(similarity, 2),
                    "preview": new_content[:100] + "...",
                })
        
        return changes
    
    async def restore_version(
        self,
        document_id: str,
        version_number: int,
    ) -> Document:
        """Restore a document to a specific version.
        
        Args:
            document_id: Document ID.
            version_number: Version to restore.
            
        Returns:
            Restored document.
        """
        # TODO: Implement version restoration from version table
        raise NotImplementedError("Version restoration requires version table implementation")
    
    def generate_change_summary(
        self,
        old_content: str,
        new_content: str,
    ) -> str:
        """Generate human-readable change summary.
        
        Args:
            old_content: Previous content.
            new_content: Current content.
            
        Returns:
            Summary of changes.
        """
        diff = self.compute_diff(old_content, new_content)
        
        if diff["total_changes"] == 0:
            return "No changes"
        
        parts = []
        
        if diff["added_lines"] > 0:
            parts.append(f"{diff['added_lines']} lines added")
        
        if diff["removed_lines"] > 0:
            parts.append(f"{diff['removed_lines']} lines removed")
        
        similarity_pct = round(diff["similarity_ratio"] * 100, 1)
        parts.append(f"{similarity_pct}% similarity to previous version")
        
        return ", ".join(parts)
