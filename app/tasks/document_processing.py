"""Document processing tasks using OpenAI-based document analysis."""

import logging
from typing import Dict
from uuid import UUID
import httpx

from sqlalchemy.orm import Session
from sqlalchemy import text
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.crud.sync import email as email_crud_sync
from app.db.session import SessionLocal
from app.services.document_processing_service import DocumentProcessingService
from app.schemas.email import EmailUpdate
from app.tasks.worker import celery_app

logger = get_task_logger(__name__)

# Define error status constant
DOCUMENT_ERROR_STATUS = "document_processing_error"


@celery_app.task(name="tasks.send_attachment_to_document_processing", bind=True, 
                 max_retries=3, 
                 default_retry_delay=60)
def send_attachment_to_document_processing(self, email_id: str, attachment_url: str):
    """
    Downloads an attachment, processes it with document processing service,
    and updates the email record directly.
    """
    logger.info(f"Starting document processing for attachment {attachment_url} for email {email_id} (attempt {self.request.retries + 1}/4)")
    
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id: {email_id}. Cannot proceed.")
        return

    # Calculate exponential backoff delay for retries
    def get_retry_delay(retry_count):
        delay = 60 * (2 ** retry_count)
        return min(delay, 960)

    # --- Download Attachment ---
    try:
        headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
        with httpx.Client(follow_redirects=True, verify=False) as client:
            logger.info(f"Downloading attachment from {attachment_url}...")
            response = client.get(attachment_url, headers=headers, timeout=120.0)
            response.raise_for_status()
            attachment_content = response.content
            logger.info(f"Successfully downloaded attachment for email {email_id}. Size: {len(attachment_content)} bytes.")
    except httpx.HTTPStatusError as exc:
        logger.error(f"HTTP error downloading attachment {attachment_url} for email {email_id}: {exc.response.status_code} - {exc.response.text}")
        if 400 <= exc.response.status_code < 500:
            _handle_final_document_processing_failure(email_uuid, attachment_url, f"HTTP {exc.response.status_code} error downloading attachment")
            return
        if 500 <= exc.response.status_code < 600 and self.request.retries < 3:
            retry_delay = get_retry_delay(self.request.retries)
            logger.warning(f"Retrying download in {retry_delay} seconds due to server error (attempt {self.request.retries + 1}/4)")
            try:
                self.retry(exc=exc, countdown=retry_delay)
            except Exception as retry_exc:
                logger.error(f"Retry failed for download error: {retry_exc}")
        else:
            _handle_final_document_processing_failure(email_uuid, attachment_url, f"Download failed after 4 attempts: {exc}")
        return
    except Exception as exc:
        logger.exception(f"Unexpected error downloading attachment {attachment_url} for email {email_id}: {exc}")
        _handle_final_document_processing_failure(email_uuid, attachment_url, f"Unexpected download error: {exc}")
        return

    # --- Process Document ---
    try:
        logger.info(f"Processing document for email {email_id}...")
        
        # Extract filename from URL
        filename = attachment_url.split('/')[-1] if '/' in attachment_url else 'attachment'
        
        # Use document processing service
        import asyncio
        service = DocumentProcessingService()
        processing_result = asyncio.run(service.process_document(attachment_content, filename))

        logger.info(f"📄 DOCUMENT PROCESSING RESULT for email {email_id}:")
        logger.info(f"📄 Full result: {processing_result}")
        
        if not processing_result.get("processing_status") == "completed":
            logger.warning(f"Document processing incomplete for email {email_id}. Status: {processing_result.get('processing_status')}")
        else:
            logger.info(f"✅ Successfully processed document for email {email_id}")
            
            # Log structured analysis results if available
            doc_analysis = processing_result.get("document_analysis", {})
            if doc_analysis.get("success"):
                analysis_data = doc_analysis.get("data", {})
                logger.info(f"📋 Document Type: {analysis_data.get('document_type', 'unknown')}")
                logger.info(f"📋 Description: {analysis_data.get('description', 'N/A')}")
                logger.info(f"📋 Patient ID: {analysis_data.get('patient_id', 'Not found')}")
                logger.info(f"📋 Confidence: {analysis_data.get('confidence', 0.0):.2f}")
            else:
                logger.warning(f"❌ Document analysis failed: {doc_analysis.get('error', 'Unknown error')}")

    except Exception as exc:
        logger.exception(f"Unexpected error processing document for email {email_id}: {exc}")
        _handle_final_document_processing_failure(email_uuid, attachment_url, f"Unexpected processing error: {exc}")
        return

    # --- Process Results and Update DB ---
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found during document processing result update.")
            return

        if email_obj.status not in ["pending_ocr", "pending_document_processing", DOCUMENT_ERROR_STATUS]:
             logger.warning(f"Email {email_id} is not in pending processing state (current: {email_obj.status}). Skipping update.")
             return

        # Parse processing result for structured data
        attachment_data = _parse_document_processing_result(processing_result, attachment_url, email_id)

        # Update document processing results
        current_processing_results = email_obj.ocr_results or []  # Reuse existing field
        current_processing_results.append(attachment_data)
        
        update_payload = {'ocr_results': current_processing_results}

        # Use atomic database-level increment
        db.execute(
            text("UPDATE email SET ocr_attachments_completed = COALESCE(ocr_attachments_completed, 0) + 1 WHERE id = :email_id"),
            {"email_id": str(email_uuid)}
        )
        db.commit()
        
        # Get updated email object
        updated_email_with_count = email_crud_sync.get(db, id=email_uuid)
        if not updated_email_with_count:
            logger.error(f"Email {email_id} not found after atomic count update.")
            return
            
        completed_count = updated_email_with_count.ocr_attachments_completed
        
        # Update with processing results
        updated_email = email_crud_sync.update(db, db_obj=updated_email_with_count, obj_in=EmailUpdate(**update_payload))

        logger.info(f"Updated email {email_id} with document processing result for attachment {attachment_url}. Completed {completed_count}/{updated_email.ocr_attachments_total} attachments.")

        # Add comment to Front conversation if patient ID found
        if attachment_data.get('patient_id') and updated_email.front_conversation_id:
            patient_id = attachment_data['patient_id']
            logger.info(f"Document processing found patient ID {patient_id} for email {email_id}, adding comment to conversation.")
            try:
                from app.services.frontapp_service import add_conversation_comment
                comment_text = f"Bot found patient id {patient_id} via document processing"
                add_conversation_comment(updated_email.front_conversation_id, comment_text)
                logger.info(f"Added document processing patient ID comment to conversation {updated_email.front_conversation_id}: {comment_text}")
            except Exception as e:
                logger.error(f"Failed to add document processing patient ID comment to conversation {updated_email.front_conversation_id}: {e}", exc_info=True)

        # Check if all attachments are processed and trigger orchestration if complete
        logger.info(f"Checking document processing completion for email {email_id}: {completed_count}/{updated_email.ocr_attachments_total}")
        _check_document_processing_completion_and_trigger_orchestration(updated_email, completed_count, email_id, str(email_uuid))

        logger.info(f"Document processing task completed successfully for email {email_id}, attachment {attachment_url}")

    except Exception as db_exc:
        logger.exception(f"Database error processing document result for email {email_id}: {db_exc}")
        db.rollback()
        try:
            self.retry(exc=db_exc)
        except Exception as retry_exc:
             logger.error(f"Retry failed for DB error: {retry_exc}")
    finally:
        db.close()


def _parse_document_processing_result(processing_result: Dict, attachment_url: str, email_id: str) -> Dict:
    """Parse and structure document processing result data."""
    try:
        # Extract relevant information from structured document analysis
        document_analysis = processing_result.get("document_analysis", {})
        
        # Extract structured data
        patient_id = None
        doc_type = None
        description = ""
        
        if document_analysis.get("success"):
            analysis_data = document_analysis.get("data", {})
            patient_id = analysis_data.get("patient_id")
            doc_type = analysis_data.get("document_type")
            description = analysis_data.get("description", "")
        
        return {
            "attachment_url": attachment_url,
            "patient_id": patient_id,
            "document_type": doc_type,
            "description": description,
            "document_analysis": document_analysis,
            "processing_status": processing_result.get("processing_status")
        }

    except Exception as parse_error:
        logger.error(f"Error parsing document processing result for email {email_id}: {parse_error}. Result: {processing_result}")
        return {
            "attachment_url": attachment_url,
            "error": f"Failed to parse processing result: {parse_error}"
        }


def _check_document_processing_completion_and_trigger_orchestration(updated_email, completed_count: int, email_id: str, email_uuid_str: str):
    """
    Check if all document processing is complete and trigger orchestration.
    """
    if updated_email.ocr_attachments_total is None:
        logger.warning(f"Email {email_id} has no ocr_attachments_total set. Cannot determine completion.")
        return
        
    if completed_count < updated_email.ocr_attachments_total:
        logger.info(f"Email {email_id}: Document processing progress {completed_count}/{updated_email.ocr_attachments_total} - waiting for more attachments.")
        return
        
    # All attachments are complete
    logger.info(f"All document processing complete for email {email_id} ({completed_count}/{updated_email.ocr_attachments_total})")
    
    # Check if any processing resulted in an error
    has_errors = any(result.get('error') for result in updated_email.ocr_results or [])
    
    if has_errors:
        final_status = "document_processing_completed_with_errors"
        logger.warning(f"Document processing complete for email {email_id} but some attachments had errors. Continuing processing anyway.")
        try:
            from app.services.frontapp_service import add_conversation_tags
            if updated_email.front_conversation_id:
                add_conversation_tags(updated_email.front_conversation_id, ["AI: Human review required"])
                logger.info(f"Added 'AI: Human review required' tag to conversation {updated_email.front_conversation_id} after processing error.")
        except Exception as tag_exc:
            logger.error(f"Failed to add AI-review tag for conversation {updated_email.front_conversation_id}: {tag_exc}")
    else:
        final_status = "document_processing_completed"
        logger.info(f"Document processing completed successfully for email {email_id}.")
    
    # Update status and trigger next phase
    try:
        db = SessionLocal()
        try:
            email_obj = email_crud_sync.get(db, id=UUID(email_uuid_str))
            if email_obj and email_obj.status not in ["document_processing_completed", "document_processing_completed_with_errors"]:
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_status))
                logger.info(f"Updated email {email_id} status to {final_status}")
                
                from app.tasks.email import orchestrate_post_ocr_processing
                logger.info(f"Document processing phase complete for {email_id} (status: {final_status}), queueing for post-processing orchestration.")
                orchestrate_post_ocr_processing.apply_async(args=[email_uuid_str], queue='processing')
            else:
                logger.info(f"Email {email_id} already marked as processing complete ({email_obj.status if email_obj else 'not found'}). Skipping duplicate orchestration.")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error updating status and triggering orchestration for email {email_id}: {e}", exc_info=True)


def _handle_final_document_processing_failure(email_uuid: UUID, attachment_url: str, failure_reason: str):
    """
    Helper function to handle final document processing failure.
    """
    logger.error(f"Final document processing failure for email {email_uuid}, attachment {attachment_url}: {failure_reason}")
    
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if email_obj:
            # Create failure record
            failure_record = {
                "attachment_url": attachment_url,
                "error": f"Document processing failed: {failure_reason}",
                "patient_id": None,
                "extracted_text": "",
                "processing_status": "failed"
            }
            
            current_results = email_obj.ocr_results or []
            current_results.append(failure_record)
            
            # Atomic increment for completion count
            db.execute(
                text("UPDATE email SET ocr_attachments_completed = COALESCE(ocr_attachments_completed, 0) + 1 WHERE id = :email_id"),
                {"email_id": str(email_uuid)}
            )
            db.commit()
            
            # Get updated email object
            updated_email_state = email_crud_sync.get(db, id=email_uuid)
            if not updated_email_state:
                logger.error(f"Email {email_uuid} not found after atomic count update in failure handler.")
                return
                
            completed_count = updated_email_state.ocr_attachments_completed
            
            # Update processing results
            update_payload = {'ocr_results': current_results}
            updated_email = email_crud_sync.update(db, db_obj=updated_email_state, obj_in=EmailUpdate(**update_payload))
            
            # Mark for human review
            try:
                from app.services.frontapp_service import add_conversation_tags
                if email_obj.front_conversation_id:
                    add_conversation_tags(email_obj.front_conversation_id, ["AI: Human review required"])
                    logger.info(f"Added 'AI: Human review required' tag to conversation {email_obj.front_conversation_id} after processing failure.")
            except Exception as tag_exc:
                logger.error(f"Failed to add AI-review tag for conversation {email_obj.front_conversation_id}: {tag_exc}")
            
            logger.info(f"Recorded document processing failure for {email_uuid}. Completed {completed_count}/{updated_email.ocr_attachments_total} attachments.")
            
            # Check if all attachments are processed
            _check_document_processing_completion_and_trigger_orchestration(updated_email, completed_count, str(email_uuid), str(email_uuid))
        else:
            logger.error(f"Email {email_uuid} not found when handling document processing failure")
    except Exception as db_exc:
        logger.exception(f"Database error handling document processing failure for email {email_uuid}: {db_exc}")
        if db.is_active:
            db.rollback()
    finally:
        if db.is_active:
            db.close()


# Legacy function name for backward compatibility
send_attachment_to_ocr = send_attachment_to_document_processing