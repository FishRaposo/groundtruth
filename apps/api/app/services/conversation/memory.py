"""Deterministic bounded conversation-memory selection."""

from __future__ import annotations

from typing import Protocol, TypedDict

from app.models.query import BoundedMemoryPolicy
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class MemoryMessage(TypedDict):
    role: str
    content: str


class ConversationMemory(Protocol):
    """Persistence boundary used by query execution."""

    async def append(self, conversation_id: str, message: MemoryMessage) -> None: ...

    async def recent(
        self, conversation_id: str, *, max_tokens: int
    ) -> list[MemoryMessage]: ...


def estimate_tokens(content: str) -> int:
    """Return a stable offline token estimate based on whitespace words."""
    return max(1, len(content.split()))


def select_bounded_history(
    messages: list[MemoryMessage] | list[dict[str, str]],
    *,
    max_tokens: int,
) -> list[MemoryMessage]:
    """Keep the newest complete user/assistant turns within ``max_tokens``.

    History is selected in pairs so an assistant response is never injected
    without the user message that prompted it. A trailing user message is kept
    as a single pending turn when it fits.
    """
    if max_tokens <= 0:
        return []

    normalized = [
        MemoryMessage(role=str(item["role"]), content=str(item["content"]))
        for item in messages
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    turns: list[list[MemoryMessage]] = []
    current: list[MemoryMessage] = []
    for message in normalized:
        if message["role"] == "user":
            if current:
                turns.append(current)
            current = [message]
        elif current:
            current.append(message)
            turns.append(current)
            current = []
    if current:
        turns.append(current)

    selected: list[list[MemoryMessage]] = []
    used = 0
    for turn in reversed(turns):
        turn_tokens = sum(estimate_tokens(message["content"]) for message in turn)
        if used + turn_tokens > max_tokens:
            break
        selected.insert(0, turn)
        used += turn_tokens

    return [message for turn in selected for message in turn]


def format_memory_context(messages: list[MemoryMessage]) -> str:
    """Serialize selected turns for the existing string-context generator."""
    return "Conversation history:\n" + "\n".join(
        f"{message['role'].title()}: {message['content']}" for message in messages
    )


async def prepare_memory_context(
    *,
    conversation_id: str | None,
    policy: BoundedMemoryPolicy,
    max_tokens: int,
    question: str,
    memory: ConversationMemory,
) -> str | None:
    """Load prior turns and persist the current question in a stable order."""
    if conversation_id is None or policy is BoundedMemoryPolicy.DISABLED:
        return None
    previous = await memory.recent(conversation_id, max_tokens=max_tokens)
    await memory.append(conversation_id, MemoryMessage(role="user", content=question))
    return format_memory_context(previous) if previous else None


class SQLConversationMemory:
    """Persist/query conversation turns through the caller's transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(self, conversation_id: str, message: MemoryMessage) -> None:
        import uuid

        from app.models.conversation import Conversation, Message

        identifier = uuid.UUID(conversation_id)
        conversation = await self.session.get(Conversation, identifier)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        row = Message(
            conversation_id=identifier,
            role=message["role"],
            content=message["content"],
        )
        self.session.add(row)
        conversation.message_count = (conversation.message_count or 0) + 1
        conversation.total_tokens = (conversation.total_tokens or 0) + estimate_tokens(
            message["content"]
        )
        await self.session.flush()

    async def recent(
        self, conversation_id: str, *, max_tokens: int
    ) -> list[MemoryMessage]:
        import uuid

        from app.models.conversation import Message

        result = await self.session.execute(
            select(Message)
            .where(Message.conversation_id == uuid.UUID(conversation_id))
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        messages = [
            MemoryMessage(role=row.role, content=row.content)
            for row in result.scalars().all()
        ]
        return select_bounded_history(messages, max_tokens=max_tokens)
