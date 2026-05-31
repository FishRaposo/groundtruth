"""Webhook Celery tasks.

Handles webhook delivery asynchronously with retry logic.
"""

from __future__ import annotations

from typing import Any

from celery import shared_task


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def deliver_webhook_task(
    self,
    event_type: str,
    payload: dict[str, Any],
    document_id: str | None = None,
) -> dict[str, Any]:
    """Deliver webhook to all matching subscriptions.
    
    Args:
        event_type: Event type.
        payload: Event payload.
        document_id: Optional document ID for filtering.
        
    Returns:
        Delivery result.
    """
    import asyncio
    return asyncio.run(_deliver_webhook_async(event_type, payload, document_id))


async def _deliver_webhook_async(
    event_type: str,
    payload: dict[str, Any],
    document_id: str | None,
) -> dict[str, Any]:
    """Async webhook delivery."""
    from app.db.session import AsyncSessionLocal
    from app.services.webhooks.delivery import WebhookDeliveryService
    
    async with AsyncSessionLocal() as db:
        service = WebhookDeliveryService(db)
        
        from app.models.webhook import WebhookEventType
        
        # Send event
        deliveries = await service.send_event(
            WebhookEventType(event_type),
            payload,
            document_id,
        )
        
        # Execute deliveries immediately (or could queue separately)
        success_count = 0
        for delivery in deliveries:
            success = await service.execute_delivery(str(delivery.id))
            if success:
                success_count += 1
        
        return {
            "success": True,
            "deliveries_attempted": len(deliveries),
            "deliveries_successful": success_count,
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def process_webhook_batch_task(self, batch_size: int = 100) -> dict[str, Any]:
    """Process pending webhook deliveries in batch.
    
    Args:
        batch_size: Maximum deliveries to process.
        
    Returns:
        Processing result.
    """
    import asyncio
    return asyncio.run(_process_webhook_batch_async(batch_size))


async def _process_webhook_batch_async(batch_size: int) -> dict[str, Any]:
    """Async batch processing."""
    from app.db.session import AsyncSessionLocal
    from app.services.webhooks.delivery import WebhookDeliveryService
    
    async with AsyncSessionLocal() as db:
        service = WebhookDeliveryService(db)
        
        processed = await service.process_pending_deliveries(batch_size)
        
        return {
            "success": True,
            "processed": processed,
        }
