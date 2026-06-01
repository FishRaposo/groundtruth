"""Webhook delivery service with retry logic.

Handles webhook payload signing, delivery, and exponential backoff retry.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookSubscription, WebhookDelivery, WebhookEventType


class WebhookDeliveryService:
    """Service for delivering webhooks with retry logic.
    
    Features:
    - HMAC-SHA256 payload signing
    - Exponential backoff retry
    - Delivery tracking and logging
    - Automatic disabling on repeated failures
    """
    
    # Retry configuration
    MAX_RETRIES = 5
    BASE_DELAY_SECONDS = 5
    MAX_DELAY_SECONDS = 3600  # 1 hour
    
    # Failure threshold for auto-disabling
    FAILURE_THRESHOLD = 10
    FAILURE_WINDOW_HOURS = 24
    
    def __init__(self, db: AsyncSession) -> None:
        """Initialize webhook delivery service.
        
        Args:
            db: Database session.
        """
        self.db = db
    
    async def send_event(
        self,
        event_type: WebhookEventType,
        payload: dict[str, Any],
        document_id: str | None = None,
    ) -> list[WebhookDelivery]:
        """Send an event to all matching subscriptions.
        
        Args:
            event_type: Type of event.
            payload: Event payload data.
            document_id: Optional document ID for filtering.
            
        Returns:
            List of delivery records.
        """
        # Find matching subscriptions
        subscriptions = await self._get_matching_subscriptions(event_type, document_id)
        
        deliveries = []
        for sub in subscriptions:
            delivery = await self._queue_delivery(sub, event_type, payload)
            deliveries.append(delivery)
        
        return deliveries
    
    async def _get_matching_subscriptions(
        self,
        event_type: WebhookEventType,
        document_id: str | None = None,
    ) -> list[WebhookSubscription]:
        """Get subscriptions matching the event criteria.
        
        Args:
            event_type: Event type to match.
            document_id: Optional document filter.
            
        Returns:
            List of matching subscriptions.
        """
        result = await self.db.execute(
            select(WebhookSubscription)
            .where(WebhookSubscription.status == "active")
        )
        
        subscriptions = list(result.scalars().all())
        
        # Filter by event type
        matching = []
        for sub in subscriptions:
            events = sub.events or []
            if event_type.value in events or "*" in events:
                # Check document filter if present
                if sub.document_filter and document_id:
                    allowed_docs = sub.document_filter.get("document_ids", [])
                    if document_id not in allowed_docs:
                        continue
                matching.append(sub)
        
        return matching
    
    async def _queue_delivery(
        self,
        subscription: WebhookSubscription,
        event_type: WebhookEventType,
        payload: dict[str, Any],
    ) -> WebhookDelivery:
        """Queue a webhook for delivery.
        
        Args:
            subscription: Target subscription.
            event_type: Event type.
            payload: Event payload.
            
        Returns:
            Created delivery record.
        """
        delivery = WebhookDelivery(
            subscription_id=subscription.id,
            event_type=event_type.value,
            payload=payload,
            attempt_number=1,
        )
        
        self.db.add(delivery)
        await self.db.commit()
        await self.db.refresh(delivery)
        
        return delivery
    
    async def execute_delivery(self, delivery_id: str) -> bool:
        """Execute a webhook delivery attempt.
        
        Args:
            delivery_id: Delivery ID to execute.
            
        Returns:
            True if successful, False otherwise.
        """
        delivery = await self.db.get(WebhookDelivery, uuid.UUID(delivery_id))
        if not delivery:
            return False
        
        subscription = await self.db.get(
            WebhookSubscription,
            delivery.subscription_id,
        )
        if not subscription:
            return False
        
        # Prepare payload
        payload = {
            "event_id": str(delivery.id),
            "event_type": delivery.event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": delivery.payload,
        }
        
        # Sign payload
        signature = self._sign_payload(payload, subscription.secret)
        
        # Execute HTTP request
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    subscription.url,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Signature": f"sha256={signature}",
                        "X-Webhook-Event": delivery.event_type,
                        "X-Webhook-ID": str(delivery.id),
                    },
                )
                
                delivery.response_status = response.status_code
                delivery.response_body = response.text[:1000]  # Truncate
                
                if response.status_code >= 200 and response.status_code < 300:
                    delivery.success = 1
                    delivery.error_message = None
                    
                    # Update subscription stats
                    subscription.delivery_count = (subscription.delivery_count or 0) + 1
                    subscription.last_delivered_at = datetime.now(timezone.utc)
                else:
                    delivery.success = 0
                    delivery.error_message = f"HTTP {response.status_code}"
                    
                    # Schedule retry
                    await self._schedule_retry(delivery, subscription)
                
        except Exception as e:
            delivery.success = 0
            delivery.error_message = str(e)[:500]
            
            # Schedule retry
            await self._schedule_retry(delivery, subscription)
        
        await self.db.commit()
        
        return delivery.success == 1
    
    def _sign_payload(self, payload: dict[str, Any], secret: str) -> str:
        """Sign payload with HMAC-SHA256.
        
        Args:
            payload: Event payload.
            secret: Webhook secret.
            
        Returns:
            Hex signature.
        """
        payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        signature = hmac.new(
            secret.encode(),
            payload_json.encode(),
            hashlib.sha256,
        ).hexdigest()
        return signature
    
    async def _schedule_retry(
        self,
        delivery: WebhookDelivery,
        subscription: WebhookSubscription,
    ) -> None:
        """Schedule a retry for a failed delivery.
        
        Args:
            delivery: Failed delivery.
            subscription: Subscription to update.
        """
        if delivery.attempt_number >= self.MAX_RETRIES:
            # Max retries reached
            subscription.failure_count = (subscription.failure_count or 0) + 1
            subscription.last_error = f"Max retries exceeded for delivery {delivery.id}"
            
            # Check if should disable
            await self._check_disable_threshold(subscription)
            return
        
        # Calculate next retry time with exponential backoff
        delay = min(
            self.BASE_DELAY_SECONDS * (2 ** (delivery.attempt_number - 1)),
            self.MAX_DELAY_SECONDS,
        )
        
        delivery.attempt_number += 1
        delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    
    async def _check_disable_threshold(self, subscription: WebhookSubscription) -> None:
        """Check if subscription should be auto-disabled.
        
        Args:
            subscription: Subscription to check.
        """
        if subscription.failure_count >= self.FAILURE_THRESHOLD:
            subscription.status = "disabled"
            subscription.last_error = (
                f"Auto-disabled after {subscription.failure_count} failures"
            )
    
    async def process_pending_deliveries(self, batch_size: int = 100) -> int:
        """Process all pending webhook deliveries.
        
        Args:
            batch_size: Maximum deliveries to process.
            
        Returns:
            Number of deliveries processed.
        """
        from sqlalchemy import or_
        
        result = await self.db.execute(
            select(WebhookDelivery)
            .where(
                or_(
                    WebhookDelivery.success == 0,
                    WebhookDelivery.success.is_(None),
                )
            )
            .where(
                or_(
                    WebhookDelivery.next_retry_at.is_(None),
                    WebhookDelivery.next_retry_at <= datetime.now(timezone.utc),
                )
            )
            .limit(batch_size)
        )
        
        deliveries = result.scalars().all()
        
        processed = 0
        for delivery in deliveries:
            success = await self.execute_delivery(str(delivery.id))
            if success:
                processed += 1
        
        return processed
    
    def verify_signature(
        self,
        payload: dict[str, Any],
        signature: str,
        secret: str,
    ) -> bool:
        """Verify webhook signature.
        
        Args:
            payload: Received payload.
            signature: Signature from header (without "sha256=" prefix).
            secret: Webhook secret.
            
        Returns:
            True if signature is valid.
        """
        expected = self._sign_payload(payload, secret)
        return hmac.compare_digest(expected, signature)
