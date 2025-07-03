"""Task orchestration module for email processing workflow coordination."""

import logging
from typing import Dict, List, Optional
from uuid import UUID

from celery import chain, group
from celery.utils.log import get_task_logger

from app.tasks.worker import celery_app

logger = get_task_logger(__name__)

# Task queue mappings for better resource allocation
QUEUE_MAPPINGS = {
    'process_email': 'processing',
    'orchestrate_post_ocr': 'processing', 
    'perform_tagging': 'tagging',
    'perform_autorespond': 'processing',
    'send_attachment_to_ocr': 'ocr'
}


@celery_app.task(name="app.tasks.orchestration.orchestrate_email_processing")
def orchestrate_email_processing(email_id: str, skip_ocr: bool = False) -> Dict:
    """
    High-level orchestrator for the complete email processing workflow.
    
    Args:
        email_id: UUID string of the email to process
        skip_ocr: If True, skip OCR processing (for testing or re-processing)
        
    Returns:
        Dict with orchestration status and workflow tracking info
    """
    logger.info(f"Starting email processing orchestration for {email_id}")
    
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}
    
    if skip_ocr:
        # Direct path: OCR -> Tagging -> Autorespond
        from app.tasks.email import orchestrate_post_ocr_processing
        result = orchestrate_post_ocr_processing.apply_async(
            args=[email_id], 
            queue=QUEUE_MAPPINGS['orchestrate_post_ocr']
        )
        logger.info(f"Skipped OCR for {email_id}, queued post-OCR orchestration: {result.id}")
        return {
            "status": "orchestrated_skip_ocr",
            "email_id": email_id,
            "orchestration_task_id": result.id,
            "workflow": "post_ocr_processing"
        }
    else:
        # Full path: Process -> (OCR if needed) -> Tagging -> Autorespond
        from app.tasks.email import process_email
        result = process_email.apply_async(
            args=[email_id],
            queue=QUEUE_MAPPINGS['process_email']
        )
        logger.info(f"Started full email processing for {email_id}: {result.id}")
        return {
            "status": "orchestrated_full_processing",
            "email_id": email_id,
            "orchestration_task_id": result.id,
            "workflow": "full_processing"
        }


@celery_app.task(name="app.tasks.orchestration.retry_failed_email")
def retry_failed_email(email_id: str, retry_stage: str = "full") -> Dict:
    """
    Retry processing for a failed email at a specific stage.
    
    Args:
        email_id: UUID string of the email to retry
        retry_stage: Stage to retry from ('full', 'post_ocr', 'tagging', 'autorespond')
        
    Returns:
        Dict with retry status and new task info
    """
    logger.info(f"Retrying email {email_id} from stage: {retry_stage}")
    
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}
    
    if retry_stage == "full":
        return orchestrate_email_processing(email_id, skip_ocr=False)
    elif retry_stage == "post_ocr":
        return orchestrate_email_processing(email_id, skip_ocr=True)
    elif retry_stage == "tagging":
        from app.tasks.email import perform_tagging_task
        result = perform_tagging_task.apply_async(
            args=[email_id],
            queue=QUEUE_MAPPINGS['perform_tagging']
        )
        logger.info(f"Retrying tagging for {email_id}: {result.id}")
        return {
            "status": "retrying_tagging",
            "email_id": email_id,
            "retry_task_id": result.id,
            "retry_stage": retry_stage
        }
    elif retry_stage == "autorespond":
        from app.tasks.autorespond import perform_autorespond_task
        result = perform_autorespond_task.apply_async(
            args=[email_id],
            queue=QUEUE_MAPPINGS['perform_autorespond']
        )
        logger.info(f"Retrying autorespond for {email_id}: {result.id}")
        return {
            "status": "retrying_autorespond", 
            "email_id": email_id,
            "retry_task_id": result.id,
            "retry_stage": retry_stage
        }
    else:
        logger.error(f"Invalid retry_stage: {retry_stage}")
        return {"status": "error", "message": f"Invalid retry stage: {retry_stage}"}


@celery_app.task(name="app.tasks.orchestration.batch_process_emails")
def batch_process_emails(email_ids: List[str], concurrent_limit: int = 5) -> Dict:
    """
    Process multiple emails concurrently with a limit.
    
    Args:
        email_ids: List of email UUID strings to process
        concurrent_limit: Maximum number of emails to process concurrently
        
    Returns:
        Dict with batch processing status and task group info
    """
    logger.info(f"Starting batch processing for {len(email_ids)} emails (limit: {concurrent_limit})")
    
    if not email_ids:
        return {"status": "error", "message": "No email IDs provided"}
    
    # Validate email IDs
    valid_emails = []
    for email_id in email_ids:
        try:
            UUID(email_id)
            valid_emails.append(email_id)
        except ValueError:
            logger.warning(f"Skipping invalid email ID: {email_id}")
    
    if not valid_emails:
        return {"status": "error", "message": "No valid email IDs provided"}
    
    # Process in chunks to respect concurrent limit
    chunks = [valid_emails[i:i + concurrent_limit] for i in range(0, len(valid_emails), concurrent_limit)]
    task_groups = []
    
    from app.tasks.email import process_email
    
    for chunk_idx, chunk in enumerate(chunks):
        # Create a group for each chunk
        chunk_tasks = [
            process_email.s(email_id).set(queue=QUEUE_MAPPINGS['process_email'])
            for email_id in chunk
        ]
        chunk_group = group(chunk_tasks)
        task_groups.append(chunk_group)
        logger.info(f"Created task group {chunk_idx + 1} with {len(chunk)} emails")
    
    # Execute all chunks (Celery will handle the concurrency within each group)
    group_results = []
    for group_task in task_groups:
        result = group_task.apply_async()
        group_results.append(result.id)
    
    return {
        "status": "batch_processing_started",
        "total_emails": len(valid_emails),
        "invalid_emails": len(email_ids) - len(valid_emails),
        "chunk_count": len(chunks),
        "group_task_ids": group_results,
        "concurrent_limit": concurrent_limit
    }


def get_processing_status(email_id: str) -> Dict:
    """
    Get the current processing status of an email (utility function).
    
    Args:
        email_id: UUID string of the email
        
    Returns:
        Dict with email processing status from database
    """
    try:
        from app.db.session import SessionLocal
        from app.crud.sync import email as email_crud_sync
        from uuid import UUID
        
        email_uuid = UUID(email_id)
        db = SessionLocal()
        try:
            email_obj = email_crud_sync.get(db, id=email_uuid)
            if not email_obj:
                return {"status": "not_found", "email_id": email_id}
            
            return {
                "status": "found",
                "email_id": email_id,
                "processing_status": email_obj.status,
                "is_processed": email_obj.is_processed,
                "has_attachments": email_obj.has_attachments,
                "ocr_attachments_total": getattr(email_obj, 'ocr_attachments_total', None),
                "ocr_attachments_completed": getattr(email_obj, 'ocr_attachments_completed', None),
                "created_at": email_obj.created_at.isoformat() if email_obj.created_at else None,
                "updated_at": email_obj.updated_at.isoformat() if email_obj.updated_at else None
            }
        finally:
            if db.is_active:
                db.close()
    except Exception as e:
        logger.error(f"Error getting processing status for {email_id}: {e}")
        return {"status": "error", "message": str(e), "email_id": email_id} 