"""Celery worker configuration."""

import logging
from celery import Celery

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.task_routes = {
    "app.tasks.email.process_email": {"queue": "emails"},
    "app.tasks.email.tag_email": {"queue": "tagging"},
    "app.tasks.worker.test_task": {"queue": "emails"},
}

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_hijack_root_logger=False,
)

# Autodiscover tasks in the app package
celery_app.autodiscover_tasks(["app.tasks"])


@celery_app.task(bind=True, name="app.tasks.worker.test_task")
def test_task(self):
    """Test task to verify Celery setup."""
    logger.info("Test task fucking executed")
    return {"status": "ok"} 