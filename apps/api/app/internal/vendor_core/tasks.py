# Vendored from FishRaposo/operator-shared-core v1.3.0.
# Source commit: dbf276a7708da65b55e1f10b35af634b300d1f07.
from typing import Any

from loguru import logger


def create_celery_app(
    service_name: str,
    broker_url: str = "redis://localhost:6379/0",
    backend_url: str = "redis://localhost:6379/0",
) -> Any:
    """Dynamically bootstraps a Celery application with unified logging and settings."""
    try:
        from celery import Celery  # type: ignore
    except ImportError:
        raise ImportError(
            "celery module is not installed. "
            "Install it via 'pip install celery' in your service."
        ) from None

    app = Celery(
        service_name,
        broker=broker_url,
        backend=backend_url,
    )

    # Apply configuration defaults
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=3600,
    )

    from celery.signals import task_failure, task_postrun, task_prerun  # type: ignore

    @task_prerun.connect
    def on_task_prerun(task_id: str, task: Any, *args: Any, **kwargs: Any) -> None:
        logger.info(f"Celery task started: {task.name}[{task_id}]")

    @task_postrun.connect
    def on_task_postrun(
        task_id: str,
        task: Any,
        retval: Any,
        state: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        logger.info(f"Celery task completed: {task.name}[{task_id}] - State: {state}")

    @task_failure.connect
    def on_task_failure(
        task_id: str,
        exception: Exception,
        traceback: Any,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        logger.error(
            f"Celery task failed: task_id={task_id} - Exception: {str(exception)}"
        )

    return app
