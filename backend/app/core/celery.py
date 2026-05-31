"""Celery configuration and app instance.

Configures Celery for async task processing with Redis as broker.
"""

from celery import Celery

from app.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    "groundtruth",
    broker=settings.CELERY_BROKER_URL or "redis://localhost:6379/0",
    backend=settings.CELERY_RESULT_URL or "redis://localhost:6379/0",
    include=[
        "app.tasks.documents",
        "app.tasks.webhooks",
        "app.tasks.workflows",
    ],
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    # Result backend
    result_expires=3600,
    # Retry configuration
    task_default_retry_delay=10,
    task_max_retries=3,
    # Queue configuration
    task_routes={
        "app.tasks.documents.*": {"queue": "documents"},
        "app.tasks.webhooks.*": {"queue": "webhooks"},
    },
)

# Beat schedule for periodic tasks
celery_app.conf.beat_schedule = {
    "process-webhooks": {
        "task": "app.tasks.webhooks.process_webhook_batch_task",
        "schedule": 60.0,  # Every minute
    },
    "check-workflow-slas": {
        "task": "app.tasks.workflows.check_workflow_slas",
        "schedule": 300.0,  # Every 5 minutes
    },
}
