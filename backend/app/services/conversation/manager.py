"""Conversation manager for multi-turn RAG interactions.

Handles conversation lifecycle, context window management,
and message history compression.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, Message, ConversationContext
from app.models.chunk import Chunk
from app.services.retrieval.enhanced import EnhancedRetrievalService


class ConversationManager:
    """Manages conversations with context window and memory."""
    
    def __init__(self, db: AsyncSession) -> None:
        """Initialize conversation manager.
        
        Args:
            db: Database session.
        """
        self.db = db
        self.retrieval = EnhancedRetrievalService()
    
    async def create_conversation(
        self,
        title: str | None = None,
        document_ids: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> Conversation:
        """Create a new conversation.
        
        Args:
            title: Optional conversation title.
            document_ids: Documents to include in context.
            system_prompt: Custom system prompt.
            
        Returns:
            Created conversation.
        """
        conversation = Conversation(
            title=title,
            document_ids=[uuid.UUID(did) for did in (document_ids or [])],
            system_prompt=system_prompt,
        )
        
        self.db.add(conversation)
        await self.db.commit()
        await self.db.refresh(conversation)
        
        return conversation
    
    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        retrieved_chunks: list[dict[str, Any]] | None = None,
        sources: list[dict[str, Any]] | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> Message:
        """Add a message to a conversation.
        
        Args:
            conversation_id: Conversation ID.
            role: Message role (user, assistant, system).
            content: Message content.
            retrieved_chunks: Chunks retrieved for this message.
            sources: Source documents.
            input_tokens: Token count for input.
            output_tokens: Token count for output.
            
        Returns:
            Created message.
        """
        message = Message(
            conversation_id=uuid.UUID(conversation_id),
            role=role,
            content=content,
            retrieved_chunks=retrieved_chunks or [],
            sources=sources or [],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        
        self.db.add(message)
        
        # Update conversation stats
        conversation = await self.db.get(Conversation, uuid.UUID(conversation_id))
        if conversation:
            conversation.message_count = (conversation.message_count or 0) + 1
            if input_tokens:
                conversation.total_tokens = (conversation.total_tokens or 0) + input_tokens
            if output_tokens:
                conversation.total_tokens = (conversation.total_tokens or 0) + output_tokens
        
        await self.db.commit()
        await self.db.refresh(message)
        
        return message
    
    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        """Get messages for a conversation.
        
        Args:
            conversation_id: Conversation ID.
            limit: Maximum messages to return.
            offset: Number of messages to skip.
            
        Returns:
            List of messages.
        """
        result = await self.db.execute(
            select(Message)
            .where(Message.conversation_id == uuid.UUID(conversation_id))
            .order_by(Message.created_at.asc())
            .offset(offset)
            .limit(limit)
        )
        
        return list(result.scalars().all())
    
    async def build_context(
        self,
        conversation_id: str,
        current_query: str,
        max_tokens: int = 4000,
        strategy: str = "recent_relevant",
    ) -> list[dict[str, Any]]:
        """Build context window for a query.
        
        Args:
            conversation_id: Conversation ID.
            current_query: Current user query.
            max_tokens: Maximum tokens for context.
            strategy: Context building strategy.
            
        Returns:
            List of context items for LLM.
        """
        # Get conversation
        conversation = await self.db.get(Conversation, uuid.UUID(conversation_id))
        if not conversation:
            return []
        
        # Get recent messages
        messages = await self.get_messages(conversation_id, limit=10)
        
        # Retrieve relevant chunks based on current query
        chunks, trace = await self.retrieval.retrieve(
            current_query,
            top_k=5,
            trace=True,
        )
        
        # Update conversation context
        for chunk in chunks:
            await self._update_context_entry(conversation_id, str(chunk.id))
        
        # Build context messages
        context = []
        
        # Add system message
        system_content = conversation.system_prompt or self._default_system_prompt()
        context.append({
            "role": "system",
            "content": system_content,
        })
        
        # Add recent conversation history (compressed if needed)
        history = self._compress_history(messages, max_tokens // 2)
        context.extend(history)
        
        # Add retrieved context
        if chunks:
            context.append({
                "role": "system",
                "content": self._format_retrieved_context(chunks),
            })
        
        return context
    
    async def _update_context_entry(
        self,
        conversation_id: str,
        chunk_id: str,
    ) -> None:
        """Update or create context entry for a chunk.
        
        Args:
            conversation_id: Conversation ID.
            chunk_id: Chunk ID.
        """
        from datetime import datetime
        
        # Check if entry exists
        result = await self.db.execute(
            select(ConversationContext)
            .where(
                ConversationContext.conversation_id == uuid.UUID(conversation_id),
                ConversationContext.chunk_id == uuid.UUID(chunk_id),
            )
        )
        
        entry = result.scalar_one_or_none()
        
        if entry:
            # Update existing
            entry.access_count = (entry.access_count or 0) + 1
            entry.last_accessed_at = datetime.utcnow()
        else:
            # Create new
            entry = ConversationContext(
                conversation_id=uuid.UUID(conversation_id),
                chunk_id=uuid.UUID(chunk_id),
                access_count=1,
            )
            self.db.add(entry)
        
        await self.db.commit()
    
    def _compress_history(
        self,
        messages: list[Message],
        max_tokens: int,
    ) -> list[dict[str, str]]:
        """Compress conversation history to fit within token limit.
        
        Args:
            messages: List of messages.
            max_tokens: Maximum tokens allowed.
            
        Returns:
            Compressed history as dicts.
        """
        # Simple compression: take most recent messages
        # More sophisticated: summarize older messages
        
        result = []
        total_tokens = 0
        
        # Go backwards from most recent
        for message in reversed(messages):
            msg_tokens = (message.input_tokens or 0) + (message.output_tokens or 0)
            msg_tokens = msg_tokens or len(message.content.split())  # Rough estimate
            
            if total_tokens + msg_tokens > max_tokens:
                break
            
            result.insert(0, {
                "role": message.role,
                "content": message.content,
            })
            total_tokens += msg_tokens
        
        return result
    
    def _format_retrieved_context(
        self,
        chunks: list[Any],
    ) -> str:
        """Format retrieved chunks as context string.
        
        Args:
            chunks: List of chunks with scores.
            
        Returns:
            Formatted context string.
        """
        parts = ["Retrieved relevant information:"]
        
        for i, chunk in enumerate(chunks, 1):
            parts.append(f"\n[{i}] {chunk.content}")
        
        parts.append("\n\nUse the above information to answer the user's question.")
        
        return "\n".join(parts)
    
    def _default_system_prompt(self) -> str:
        """Get default system prompt."""
        return (
            "You are a helpful assistant that answers questions based on the provided context. "
            "Only use the information from the retrieved documents. "
            "If the answer is not in the context, say you don't know. "
            "Always cite sources using [1], [2], etc."
        )
    
    async def export_conversation(self, conversation_id: str) -> dict[str, Any]:
        """Export a conversation to a serializable format.
        
        Args:
            conversation_id: Conversation ID.
            
        Returns:
            Conversation export dict.
        """
        conversation = await self.db.get(Conversation, uuid.UUID(conversation_id))
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")
        
        messages = await self.get_messages(conversation_id, limit=1000)
        
        return {
            "conversation": conversation.to_dict(),
            "messages": [m.to_dict() for m in messages],
            "exported_at": datetime.utcnow().isoformat(),
        }
    
    async def import_conversation(self, data: dict[str, Any]) -> Conversation:
        """Import a conversation from exported data.
        
        Args:
            data: Exported conversation data.
            
        Returns:
            Imported conversation.
        """
        conv_data = data.get("conversation", {})
        messages_data = data.get("messages", [])
        
        # Create conversation
        conversation = Conversation(
            title=conv_data.get("title"),
            document_ids=[uuid.UUID(did) for did in conv_data.get("document_ids", [])],
            message_count=len(messages_data),
        )
        
        self.db.add(conversation)
        await self.db.flush()
        
        # Add messages
        for msg_data in messages_data:
            message = Message(
                conversation_id=conversation.id,
                role=msg_data["role"],
                content=msg_data["content"],
                input_tokens=msg_data.get("input_tokens"),
                output_tokens=msg_data.get("output_tokens"),
            )
            self.db.add(message)
        
        await self.db.commit()
        await self.db.refresh(conversation)
        
        return conversation
