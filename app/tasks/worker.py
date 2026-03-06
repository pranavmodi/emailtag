"""Celery worker configuration."""

import logging
from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger

from app.core.config import settings

logger = logging.getLogger(__name__)

# Define a handler for the after_setup_logger signal
@after_setup_logger.connect
def setup_celery_logging(logger, **kwargs):
    """Configure Celery worker logging levels and add conversation log handler."""
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    # You can add other loggers here if needed

    # Add the ConversationLogHandler to capture logs for database storage
    # This handler buffers logs when a conversation context is active
    try:
        from app.core.conversation_log_handler import ConversationLogHandler
        conversation_handler = ConversationLogHandler(level=logging.INFO)
        logging.getLogger().addHandler(conversation_handler)
        # Also add to celery.task logger — modules using get_task_logger() log under
        # this hierarchy and Celery's worker logging setup may prevent propagation
        # to the root logger, causing task/agent logs to be silently dropped.
        logging.getLogger("celery.task").addHandler(conversation_handler)
    except Exception as e:
        # Don't fail worker startup if handler can't be added
        logging.getLogger(__name__).warning(f"Failed to add ConversationLogHandler: {e}")


@after_setup_task_logger.connect
def setup_celery_task_logging(logger, **kwargs):
    """Ensure task loggers propagate to root and have ConversationLogHandler.

    Celery configures task loggers (celery.task.*) with propagate=False,
    which prevents logs from reaching the root logger's console handler.
    Combined with worker_hijack_root_logger=False, this means task logger
    output (from get_task_logger) is silently dropped from console output.

    Fix: Enable propagation so task logs reach the root logger's handlers
    (console output), and also attach ConversationLogHandler directly for
    database capture.
    """
    # Enable propagation so task logs appear in console via root logger
    logger.propagate = True

    try:
        from app.core.conversation_log_handler import ConversationLogHandler
        # Avoid adding duplicate handlers
        if not any(isinstance(h, ConversationLogHandler) for h in logger.handlers):
            conversation_handler = ConversationLogHandler(level=logging.INFO)
            logger.addHandler(conversation_handler)
    except Exception:
        pass

celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.task_routes = {
    "app.tasks.email.process_email": {"queue": "emails"},
    "app.tasks.email.tag_email": {"queue": "tagging"},
    "app.tasks.email.orchestrate_post_ocr_processing": {"queue": "processing"},
    "app.tasks.email.perform_tagging_task": {"queue": "tagging"},
    "app.tasks.email.perform_autorespond_task": {"queue": "processing"},
    "app.tasks.pif_extraction.extract_pif_from_conversation": {"queue": "processing"},
    "app.tasks.firm_research.research_firm_task": {"queue": "processing"},
    "app.tasks.behavior_analysis.analyze_firm_behavior_task": {"queue": "processing"},
    "app.tasks.behavior_analysis.analyze_all_firms_task": {"queue": "processing"},
    "app.tasks.behavior_analysis.score_all_firms_task": {"queue": "processing"},
    "tasks.send_attachment_to_ocr": {"queue": "ocr"},
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