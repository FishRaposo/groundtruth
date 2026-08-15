"""In-process workflow status publication for local SSE/WebSocket facades."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    event_id: int
    event_type: str
    data: dict[str, Any]


class WorkflowEventBroker:
    def __init__(self) -> None:
        self._events: dict[str, list[WorkflowEvent]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[WorkflowEvent]]] = {}

    async def publish(
        self, workflow_id: str, event_type: str, data: dict[str, Any]
    ) -> WorkflowEvent:
        events = self._events.setdefault(workflow_id, [])
        event = WorkflowEvent(len(events) + 1, event_type, dict(data))
        events.append(event)
        for queue in tuple(self._subscribers.get(workflow_id, set())):
            await queue.put(event)
        return event

    def snapshot(
        self, workflow_id: str, after_event_id: int = 0
    ) -> list[WorkflowEvent]:
        return [
            event
            for event in self._events.get(workflow_id, [])
            if event.event_id > after_event_id
        ]

    async def subscribe(
        self, workflow_id: str, after_event_id: int = 0
    ) -> AsyncIterator[WorkflowEvent]:
        for event in self.snapshot(workflow_id, after_event_id):
            yield event
        queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue()
        self._subscribers.setdefault(workflow_id, set()).add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers[workflow_id].discard(queue)


workflow_event_broker = WorkflowEventBroker()
