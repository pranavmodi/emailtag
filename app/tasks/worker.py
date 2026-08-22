"""Celery worker configuration."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from celery import Celery
from celery.schedules import crontab
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
    "app.tasks.email.process_email_rx": {"queue": "processing"},
    "app.tasks.email.tag_email": {"queue": "tagging"},
    "app.tasks.email.orchestrate_post_ocr_processing": {"queue": "processing"},
    "app.tasks.email.perform_tagging_task": {"queue": "tagging"},
    "app.tasks.autorespond.perform_autorespond_task": {"queue": "processing"},
    "app.tasks.bill_offer.run_bill_offer_agent_task": {"queue": "processing"},
    "app.tasks.pif_extraction.extract_pif_from_conversation": {"queue": "processing"},
    "app.tasks.firm_research.research_firm_task": {"queue": "research"},
    "app.tasks.firm_research.research_job_postings_task": {"queue": "research"},
    "app.tasks.firm_research.research_staff_task": {"queue": "research"},
    "app.tasks.firm_research.analyze_leadership_emails_task": {"queue": "research"},
    "app.tasks.firm_research.detect_vendor_stack_task": {"queue": "research"},
    "app.tasks.website_resolution.resolve_firm_website_task": {"queue": "research"},
    "app.tasks.firm_merge.run_firm_merge_task": {"queue": "research"},
    "app.tasks.firm_merge.undo_firm_merge_task": {"queue": "research"},
    "app.tasks.behavior_analysis.analyze_firm_behavior_task": {"queue": "research"},
    "app.tasks.behavior_analysis.analyze_all_firms_task": {"queue": "research"},
    "app.tasks.behavior_analysis.score_firm_task": {"queue": "research"},
    "app.tasks.behavior_analysis.score_all_firms_task": {"queue": "research"},
    "app.tasks.firm_enrichment.enrich_firm_profile_task": {"queue": "research"},
    "app.tasks.firm_enrichment.dispatch_firm_enrichment_task": {"queue": "research"},
    "app.tasks.firm_events.detect_firm_events_task": {"queue": "research"},
    "app.tasks.firm_events.detect_all_firm_events_task": {"queue": "research"},
    "app.tasks.signature_extraction.extract_signatures_task": {"queue": "research"},
    "app.tasks.inbox_audit.audit_all_inboxes": {"queue": "processing"},
    "app.tasks.inbox_audit.audit_single_inbox": {"queue": "processing"},
    "app.tasks.inbox_audit.queue_conversation_for_processing": {"queue": "processing"},
    "tasks.send_attachment_to_document_processing": {"queue": "ocr"},
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


def _la_now():
    """Return current time in America/Los_Angeles, DST-aware. Used by crontab to
    schedule daily jobs at a Pacific-time hour regardless of standard/daylight time."""
    return datetime.now(ZoneInfo("America/Los_Angeles"))


celery_app.conf.beat_schedule = {
    "daily-inbox-audit-6am-pt": {
        "task": "app.tasks.inbox_audit.audit_all_inboxes",
        "schedule": crontab(hour=6, minute=0, nowfun=_la_now),
    },
}

# Autodiscover tasks in the app package
celery_app.autodiscover_tasks(["app.tasks"])


@celery_app.task(bind=True, name="app.tasks.worker.test_task")
def test_task(self):
    """Test task to verify Celery setup."""
    logger.info("Test task fucking executed")
    return {"status": "ok"} 
