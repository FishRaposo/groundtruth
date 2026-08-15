"""Offline-first notification outbox with optional delivery adapters."""

from __future__ import annotations

import asyncio
import json
import smtplib
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Protocol

from sqlalchemy import select

from app.models.notification import NotificationOutboxEntry
from app.services.audit import redact_audit_metadata
from app.utils.time import utc_now


@dataclass(slots=True)
class Notification:
    id: str
    workspace_id: str
    event_type: str
    recipient: str
    payload: dict[str, Any]
    deduplication_key: str
    state: str
    created_at: datetime


class NotificationSink(Protocol):
    async def deliver(self, notification: Notification) -> None: ...


class InMemoryNotificationSink:
    """Credential-free default sink used by the demo and CI."""

    def __init__(self) -> None:
        self.delivered: list[Notification] = []

    async def deliver(self, notification: Notification) -> None:
        self.delivered.append(notification)


class LogNotificationSink:
    """Local sink that emits a redacted structured notification to stdlib logging."""

    async def deliver(self, notification: Notification) -> None:
        import logging

        logging.getLogger("groundtruth.notifications").info(
            "notification %s %s %s",
            notification.event_type,
            notification.recipient,
            json.dumps(notification.payload, sort_keys=True),
        )


class SMTPNotificationSink:
    """Optional SMTP adapter; never constructed by the offline default."""

    def __init__(
        self, host: str, port: int = 25, sender: str = "groundtruth@localhost"
    ) -> None:
        self.host = host
        self.port = port
        self.sender = sender

    async def deliver(self, notification: Notification) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = notification.recipient
        message["Subject"] = notification.event_type
        message.set_content(json.dumps(notification.payload, indent=2, sort_keys=True))

        def send() -> None:
            with smtplib.SMTP(self.host, self.port, timeout=10) as client:
                client.send_message(message)

        await asyncio.to_thread(send)


class WebhookNotificationSink:
    """Optional stdlib JSON webhook adapter; never used unless explicitly configured."""

    def __init__(self, url: str) -> None:
        self.url = url

    async def deliver(self, notification: Notification) -> None:
        body = json.dumps(
            {
                "id": notification.id,
                "event": notification.event_type,
                "recipient": notification.recipient,
                "payload": notification.payload,
            },
            sort_keys=True,
        ).encode("utf-8")

        def send() -> None:
            request = urllib.request.Request(
                self.url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=10):  # noqa: S310
                pass

        await asyncio.to_thread(send)


class NotificationOutbox:
    """Deduplicate, optionally persist, and deliver redacted local events."""

    def __init__(self, sinks: list[NotificationSink] | None = None) -> None:
        self.sinks = sinks or [InMemoryNotificationSink()]
        self._events: dict[str, Notification] = {}

    async def enqueue(
        self,
        *,
        workspace_id: str,
        event_type: str,
        recipient: str,
        payload: dict[str, Any],
        deduplication_key: str,
        db: Any | None = None,
    ) -> Notification:
        existing = self._events.get(deduplication_key)
        if existing is not None:
            return existing
        if db is not None:
            result = await db.execute(
                select(NotificationOutboxEntry).where(
                    NotificationOutboxEntry.deduplication_key == deduplication_key
                )
            )
            row = result.scalar_one_or_none()
            if row is not None:
                return Notification(
                    id=str(row.id),
                    workspace_id=row.workspace_id,
                    event_type=row.event_type,
                    recipient=row.recipient,
                    payload=row.payload,
                    deduplication_key=row.deduplication_key,
                    state=row.state,
                    created_at=row.created_at,
                )

        notification = Notification(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            event_type=event_type,
            recipient=recipient,
            payload=redact_audit_metadata(payload),
            deduplication_key=deduplication_key,
            state="delivered",
            created_at=utc_now(),
        )
        for sink in self.sinks:
            await sink.deliver(notification)
        self._events[deduplication_key] = notification
        if db is not None:
            db.add(
                NotificationOutboxEntry(
                    id=uuid.UUID(notification.id),
                    workspace_id=workspace_id,
                    event_type=event_type,
                    recipient=recipient,
                    payload=notification.payload,
                    deduplication_key=deduplication_key,
                    state="delivered",
                    delivered_at=utc_now(),
                )
            )
            await db.flush()
        return notification


notification_outbox = NotificationOutbox()
