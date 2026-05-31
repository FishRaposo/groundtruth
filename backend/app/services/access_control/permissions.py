"""Permission service for access control.

Manages document and collection permissions with RBAC.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionShare
from app.models.document import Document


class Permission(Enum):
    """Permission levels."""
    NONE = 0
    READ = 1
    WRITE = 2
    ADMIN = 3


class AccessControlService:
    """Service for checking and managing access permissions.
    
    Implements RBAC with:
    - Owner has full access
    - Organization members have org-level access
    - Explicit shares grant specific permissions
    - Public collections are readable by all
    """
    
    def __init__(self, db: AsyncSession) -> None:
        """Initialize service.
        
        Args:
            db: Database session.
        """
        self.db = db
    
    async def check_document_access(
        self,
        document_id: str,
        user_id: str,
        required_permission: Permission = Permission.READ,
        organization_id: str | None = None,
    ) -> bool:
        """Check if user has access to a document.
        
        Args:
            document_id: Document ID.
            user_id: User ID.
            required_permission: Required permission level.
            organization_id: User's organization.
            
        Returns:
            True if access granted.
        """
        # Check document ownership
        from sqlalchemy import select
        import uuid
        
        result = await self.db.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
        document = result.scalar_one_or_none()
        
        if not document:
            return False
        
        # Owner has full access
        if hasattr(document, 'owner_id') and document.owner_id == user_id:
            return True
        
        # Check collections the document belongs to
        for collection in document.collections:
            if await self.check_collection_access(
                str(collection.id),
                user_id,
                required_permission,
                organization_id,
            ):
                return True
        
        return False
    
    async def check_collection_access(
        self,
        collection_id: str,
        user_id: str,
        required_permission: Permission = Permission.READ,
        organization_id: str | None = None,
    ) -> bool:
        """Check if user has access to a collection.
        
        Args:
            collection_id: Collection ID.
            user_id: User ID.
            required_permission: Required permission level.
            organization_id: User's organization.
            
        Returns:
            True if access granted.
        """
        from sqlalchemy import select
        import uuid
        
        result = await self.db.execute(
            select(Collection).where(Collection.id == uuid.UUID(collection_id))
        )
        collection = result.scalar_one_or_none()
        
        if not collection:
            return False
        
        # Owner has full access
        if collection.owner_id == user_id:
            return True
        
        # Public collections are readable
        if collection.is_public == "public" and required_permission == Permission.READ:
            return True
        
        # Organization access
        if (collection.is_public == "organization" and 
            organization_id and 
            collection.organization_id == organization_id):
            return True
        
        # Check explicit shares
        share = await self._get_share(collection_id, user_id)
        if share:
            share_perm = self._permission_from_string(share.permission)
            return share_perm.value >= required_permission.value
        
        return False
    
    async def _get_share(
        self,
        collection_id: str,
        user_id: str,
    ) -> CollectionShare | None:
        """Get share record for user.
        
        Args:
            collection_id: Collection ID.
            user_id: User ID.
            
        Returns:
            Share record or None.
        """
        from sqlalchemy import select
        from datetime import datetime
        import uuid
        
        result = await self.db.execute(
            select(CollectionShare)
            .where(CollectionShare.collection_id == uuid.UUID(collection_id))
            .where(
                or_(
                    CollectionShare.user_id == user_id,
                    CollectionShare.group_id.in_(["everyone"])  # TODO: check group membership
                )
            )
            .where(
                or_(
                    CollectionShare.expires_at == None,
                    CollectionShare.expires_at > datetime.utcnow()
                )
            )
        )
        
        return result.scalar_one_or_none()
    
    def _permission_from_string(self, perm: str) -> Permission:
        """Convert string to Permission enum.
        
        Args:
            perm: Permission string.
            
        Returns:
            Permission enum.
        """
        mapping = {
            "read": Permission.READ,
            "write": Permission.WRITE,
            "admin": Permission.ADMIN,
        }
        return mapping.get(perm, Permission.NONE)
    
    async def share_collection(
        self,
        collection_id: str,
        shared_with: str,
        permission: str,
        shared_by: str,
        expires_days: int | None = None,
    ) -> CollectionShare:
        """Share a collection with a user.
        
        Args:
            collection_id: Collection ID.
            shared_with: User ID to share with.
            permission: Permission level (read, write, admin).
            shared_by: User ID sharing.
            expires_days: Optional expiration in days.
            
        Returns:
            Created share record.
        """
        from datetime import datetime, timedelta
        import uuid
        
        expires_at = None
        if expires_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_days)
        
        share = CollectionShare(
            collection_id=uuid.UUID(collection_id),
            user_id=shared_with,
            permission=permission,
            created_by=shared_by,
            expires_at=expires_at,
        )
        
        self.db.add(share)
        await self.db.commit()
        await self.db.refresh(share)
        
        return share
    
    async def log_access(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str | None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
        api_key_id: str | None = None,
    ) -> None:
        """Log an access event.
        
        Args:
            user_id: User ID.
            action: Action performed.
            resource_type: Type of resource.
            resource_id: Resource ID.
            details: Additional details.
            ip_address: Client IP.
            api_key_id: API key used.
        """
        from app.models.collection import AuditLog
        import uuid
        
        log = AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            api_key_id=api_key_id,
        )
        
        self.db.add(log)
        await self.db.commit()
