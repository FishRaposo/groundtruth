"""Celery configuration and app instance (shared_core-backed).

Bootstraps Celery via ``shared_core.tasks.create_celery_app`` (unified logging +
sane defaults), then re-applies GroundTruth's task routing and beat schedule.
"""

from shared_core.tasks import create_celery_app

from app.config import get_settings

settings = get_settings()

celery_app = create_celery_app(
    "groundtruth",
    settings.CELERY_BROKER_URL or "redis://localhost:6379/0",
    settings.CELERY_RESULT_URL or "redis://localhost:6379/0",
)

celery_app.conf.update(
    imports=(
        "app.tasks.documents",
        "app.tasks.webhooks",
        "app.tasks.workflows",
    ),
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    result_expires=3600,
    task_default_retry_delay=10,
    task_max_retries=3,
    task_routes={
        "app.tasks.documents.*": {"queue": "documents"},
        "app.tasks.webhooks.*": {"queue": "webhooks"},
    },
)

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
