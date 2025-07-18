"""OCR processing tasks."""

import logging
from typing import Dict
from uuid import UUID
import httpx

from sqlalchemy.orm import Session
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.crud.sync import email as email_crud_sync
from app.db.session import SessionLocal
from app.services.ocr_service import process_ocr_content
from app.schemas.email import EmailUpdate
from app.tasks.worker import celery_app

logger = get_task_logger(__name__)

# Define error status constant
OCR_ERROR_STATUS = "ocr_error"


@celery_app.task(name="tasks.send_attachment_to_ocr", bind=True, max_retries=5, default_retry_delay=60)
def send_attachment_to_ocr(self, email_id: str, attachment_url: str):
    """
    Downloads an attachment, sends it to the synchronous OCR service,
    and updates the email record directly.
    Now includes improved retry strategy and fallback processing.
    """
    logger.info(f"Starting OCR processing via service for attachment {attachment_url} for email {email_id} (attempt {self.request.retries + 1}/6)")
    
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id: {email_id}. Cannot proceed.")
        return # Abort task

    # Calculate exponential backoff delay for retries
    def get_retry_delay(retry_count):
        # Exponential backoff: 60, 120, 240, 480, 960 seconds
        return min(60 * (2 ** retry_count), 960)

    # --- Download Attachment ---
    try:
        headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
        with httpx.Client(follow_redirects=True, verify=False) as client: # Disable SSL verification for Front downloads
            logger.info(f"Downloading attachment from {attachment_url}...")
            response = client.get(attachment_url, headers=headers, timeout=120.0) # Increased timeout for download
            response.raise_for_status()
            attachment_content = response.content
            logger.info(f"Successfully downloaded attachment for email {email_id}. Size: {len(attachment_content)} bytes.")
    except httpx.HTTPStatusError as exc:
        logger.error(f"HTTP error downloading attachment {attachment_url} for email {email_id}: {exc.response.status_code} - {exc.response.text}")
        # For 4xx errors, don't retry - these are client errors
        if 400 <= exc.response.status_code < 500:
            _handle_final_ocr_failure(email_uuid, attachment_url, f"HTTP {exc.response.status_code} error downloading attachment")
            return
        # For 5xx errors, retry with exponential backoff
        if 500 <= exc.response.status_code < 600 and self.request.retries < self.max_retries:
            retry_delay = get_retry_delay(self.request.retries)
            logger.warning(f"Retrying download in {retry_delay} seconds due to server error (attempt {self.request.retries + 1}/{self.max_retries + 1})")
            try:
                self.retry(exc=exc, countdown=retry_delay)
            except Exception as retry_exc:
                logger.error(f"Retry failed for download error: {retry_exc}")
        else:
            _handle_final_ocr_failure(email_uuid, attachment_url, f"Download failed after {self.max_retries + 1} attempts: {exc}")
        return
    except httpx.RequestError as exc:
        logger.error(f"Request error downloading attachment {attachment_url} for email {email_id}: {exc}")
        if self.request.retries < self.max_retries:
            retry_delay = get_retry_delay(self.request.retries)
            logger.warning(f"Retrying download in {retry_delay} seconds due to request error (attempt {self.request.retries + 1}/{self.max_retries + 1})")
            try:
                self.retry(exc=exc, countdown=retry_delay)
            except Exception as retry_exc:
                logger.error(f"Retry failed for download request error: {retry_exc}")
        else:
            _handle_final_ocr_failure(email_uuid, attachment_url, f"Download request failed after {self.max_retries + 1} attempts: {exc}")
        return
    except Exception as exc:
        logger.exception(f"Unexpected error downloading attachment {attachment_url} for email {email_id}: {exc}")
        _handle_final_ocr_failure(email_uuid, attachment_url, f"Unexpected download error: {exc}")
        return

    # --- Call OCR Service ---
    try:
        logger.info(f"Calling OCR service function for email {email_id}...")
        ocr_result = process_ocr_content(attachment_content) # Call the service function

        if ocr_result is None:
            logger.warning(f"OCR service function returned None for email {email_id}. Assuming no result.")
            # Mark as error or handle as needed - for now, let DB update handle it as potentially empty
            ocr_result = {} # Set to empty dict to avoid errors below, but DB update logic will handle empty info
        else:
             logger.info(f"Successfully received OCR result via service function for email {email_id}.")
             logger.debug(f"OCR Result payload: {ocr_result}")

    except httpx.HTTPStatusError as exc:
        # Raised by process_ocr_content if API returns 4xx/5xx
        logger.error(f"HTTP error from OCR service function for email {email_id}: {exc.response.status_code} - {exc.response.text}")
        # For 4xx errors, don't retry - these are client errors
        if 400 <= exc.response.status_code < 500:
            _handle_final_ocr_failure(email_uuid, attachment_url, f"OCR API HTTP {exc.response.status_code} error")
            return
        # For 5xx errors or connection issues, retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = get_retry_delay(self.request.retries)
            logger.warning(f"Retrying OCR call in {retry_delay} seconds due to server error (attempt {self.request.retries + 1}/{self.max_retries + 1})")
            try:
                self.retry(exc=exc, countdown=retry_delay)
            except Exception as retry_exc:
                logger.error(f"Retry failed for OCR service HTTP error: {retry_exc}")
        else:
            _handle_final_ocr_failure(email_uuid, attachment_url, f"OCR API failed after {self.max_retries + 1} attempts: HTTP {exc.response.status_code}")
        return
    except httpx.RequestError as exc:
        # Raised by process_ocr_content for connection/timeout issues
        logger.error(f"Request error from OCR service function for email {email_id}: {exc}")
        if self.request.retries < self.max_retries:
            retry_delay = get_retry_delay(self.request.retries)
            logger.warning(f"Retrying OCR call in {retry_delay} seconds due to connection error (attempt {self.request.retries + 1}/{self.max_retries + 1})")
            try:
                self.retry(exc=exc, countdown=retry_delay)
            except Exception as retry_exc:
                logger.error(f"Retry failed for OCR service request error: {retry_exc}")
        else:
            _handle_final_ocr_failure(email_uuid, attachment_url, f"OCR connection failed after {self.max_retries + 1} attempts: {exc}")
        return
    except Exception as exc:
        # Catch other exceptions from process_ocr_content (e.g., encoding, general exceptions)
        logger.exception(f"Unexpected error calling OCR service function or processing its result for email {email_id}: {exc}")
        _handle_final_ocr_failure(email_uuid, attachment_url, f"Unexpected OCR error: {exc}")
        return

    # --- Process OCR Result and Update DB ---
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found during OCR result processing.")
            return # Cannot update non-existent email

        if email_obj.status not in ["pending_ocr", OCR_ERROR_STATUS]: # Also allow reprocessing if previous attempt failed
             logger.warning(f"Email {email_id} is not in pending_ocr or ocr_error state (current: {email_obj.status}). Skipping update.")
             return # Avoid race conditions or double processing

        # Prepare structured result for this attachment
        attachment_ocr_data = _parse_ocr_result(ocr_result, attachment_url, email_id)

        # Prepare update payload for the Email record
        update_payload = {}
        
        # Fetch current results, initialize if null
        current_ocr_results = email_obj.ocr_results or []
        
        # Append the new result dictionary
        # Consider adding logic to update if an entry for this attachment_url already exists (e.g., on retry)
        current_ocr_results.append(attachment_ocr_data)
        
        # Set the updated list in the payload
        update_payload['ocr_results'] = current_ocr_results

        # Increment completed count - crucial!
        completed_count = (email_obj.ocr_attachments_completed or 0) + 1
        update_payload['ocr_attachments_completed'] = completed_count
        
        # IMPORTANT: Preserve ocr_attachments_total to ensure completion check works
        update_payload['ocr_attachments_total'] = email_obj.ocr_attachments_total

        # Update the email record using the sync CRUD helper
        # This now updates ocr_results and ocr_attachments_completed
        updated_email = email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(**update_payload))

        logger.info(f"Updated email {email_id} with OCR result for attachment {attachment_url}. Completed {completed_count}/{updated_email.ocr_attachments_total} attachments.")

        # Check if all attachments are processed
        if updated_email.ocr_attachments_total is not None and completed_count >= updated_email.ocr_attachments_total:
            # Check if any attachment processing resulted in an error
            has_errors = any(result.get('error') for result in updated_email.ocr_results or [])
            
            if has_errors:
                final_status = "ocr_completed_with_errors"
                logger.warning(f"OCR processing complete for email {email_id} but some attachments had errors. Continuing processing anyway.")
                # Add a Front tag so humans know review is needed
                try:
                    from app.services.frontapp_service import add_conversation_tags
                    if updated_email.front_conversation_id:
                        add_conversation_tags(updated_email.front_conversation_id, ["AI: Human review required"])
                        logger.info(f"Added 'AI: Human review required' tag to conversation {updated_email.front_conversation_id} after OCR error.")
                except Exception as tag_exc:
                    logger.error(f"Failed to add AI-review tag for conversation {updated_email.front_conversation_id}: {tag_exc}")
            else:
                final_status = "ocr_completed"
                logger.info(f"OCR processing completed successfully for email {email_id}.")
            
            # Update status separately to ensure it happens after field updates
            email_crud_sync.update(db, db_obj=updated_email, obj_in=EmailUpdate(status=final_status))
            
            # IMPORTANT: Always continue processing, even with OCR errors
            # The classification and tagging should work with or without OCR data
            from app.tasks.email import orchestrate_post_ocr_processing
            logger.info(f"OCR phase complete for {email_id} (status: {final_status}), queueing for post-OCR orchestration on 'processing' queue.")
            orchestrate_post_ocr_processing.apply_async(args=[str(email_uuid)], queue='processing')

        logger.info(f"OCR task completed successfully for email {email_id}, attachment {attachment_url}")

    except Exception as db_exc:
        logger.exception(f"Database error processing OCR result for email {email_id}: {db_exc}")
        db.rollback()
        # Don't necessarily set to OCR_ERROR_STATUS here, could be transient DB issue
        # Consider retry?
        try:
            self.retry(exc=db_exc)
        except Exception as retry_exc:
             logger.error(f"Retry failed for DB error: {retry_exc}")
             pass
    finally:
        db.close()


def _parse_ocr_result(ocr_result: Dict, attachment_url: str, email_id: str) -> Dict:
    """Parse and structure OCR result data."""
    try:
        # Assuming the structure: {"data": [{"info": {...}}], "message": "..."}
        ocr_info = ocr_result.get("data", [{}])[0].get("info", {})
        if not ocr_info:
             logger.warning(f"OCR result for email {email_id} lacks 'info' field or is empty. Result: {ocr_result}")
             # Store basic info even if OCR info is empty, to mark as processed
             return {
                 "attachment_url": attachment_url, # Use URL as identifier
                 "patient_id": None,
                 "accession_nums": [],
                 "study_type": [],
                 "error": "OCR result format invalid or empty info field."
             }
        else:
            # Store the successfully extracted info
            return {
                "attachment_url": attachment_url,
                "patient_id": ocr_info.get("patient_id"),
                "accession_nums": ocr_info.get("accession_nums", []),
                "study_type": ocr_info.get("study_type", [])
                # Add any other fields from 'info' you need to store here
                # e.g., "dob": ocr_info.get("date_of_birth")
            }

    except (AttributeError, IndexError, TypeError, KeyError) as parse_error:
        logger.error(f"Error parsing OCR result structure for email {email_id}: {parse_error}. Result: {ocr_result}")
        # Store error information in the results
        return {
            "attachment_url": attachment_url,
            "error": f"Failed to parse OCR result: {parse_error}"
        }


def _update_email_sync(email_uuid: UUID, update_data: dict):
    """Helper function to update email fields synchronously."""
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"[_update_email_sync] Email {email_uuid} not found for update.")
            return None
        
        updated_email = email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(**update_data))
        logger.info(f"[_update_email_sync] Successfully updated email {email_uuid} with data: {update_data}")
        return updated_email # Return the updated object
    except Exception as e:
        logger.exception(f"[_update_email_sync] Error updating email {email_uuid}: {e}")
        db.rollback()
        return None # Indicate failure
    finally:
        db.close()


def _update_email_status_sync(email_uuid: UUID, status: str):
    """Helper function to update email status synchronously."""
    update_data = {"status": status}
    updated_email = _update_email_sync(email_uuid, update_data)
    if updated_email:
         logger.info(f"[_update_email_status_sync] Updated status for email {email_uuid} to {status}")
    else:
         logger.error(f"[_update_email_status_sync] Failed to update status for email {email_uuid} to {status}")


def _handle_final_ocr_failure(email_uuid: UUID, attachment_url: str, failure_reason: str):
    """
    Helper function to handle final OCR failure.
    Records the failure and continues with processing using fallback.
    """
    logger.error(f"Final OCR failure for email {email_uuid}, attachment {attachment_url}: {failure_reason}")
    
    # Record the OCR failure in the email's OCR results
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if email_obj:
            # Create failure record
            failure_record = {
                "attachment_url": attachment_url,
                "error": f"OCR processing failed: {failure_reason}",
                "patient_id": None,
                "accession_nums": [],
                "study_type": []
            }
            
            current_ocr_results = email_obj.ocr_results or []
            current_ocr_results.append(failure_record)
            
            completed_count = (email_obj.ocr_attachments_completed or 0) + 1
            
            update_payload = {
                'ocr_results': current_ocr_results,
                'ocr_attachments_completed': completed_count
            }
            
            updated_email = email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(**update_payload))
            
            # Always mark the Front conversation for human review immediately
            try:
                from app.services.frontapp_service import add_conversation_tags
                if email_obj.front_conversation_id:
                    add_conversation_tags(email_obj.front_conversation_id, ["AI: Human review required"])
                    logger.info(f"Added 'AI: Human review required' tag to conversation {email_obj.front_conversation_id} after OCR failure (immediate).")
            except Exception as tag_exc:
                logger.error(f"Failed to add AI-review tag for conversation {email_obj.front_conversation_id}: {tag_exc}")
            
            logger.info(f"Recorded OCR failure for {email_uuid}. Completed {completed_count}/{updated_email.ocr_attachments_total} attachments.")
            
            # Check if all attachments are processed (including failures)
            if updated_email.ocr_attachments_total is not None and completed_count >= updated_email.ocr_attachments_total:
                # IMPORTANT: Continue processing even with OCR errors
                # This is the key fix - don't let OCR failures block the entire workflow
                logger.info(f"All OCR attempts complete for email {email_uuid} (some may have failed). Continuing with email processing...")
                
                # Set status to indicate OCR completed with errors, but allow continuation
                email_crud_sync.update(db, db_obj=updated_email, obj_in=EmailUpdate(status="ocr_completed_with_errors"))

                # Add a Front tag so humans know review is needed
                try:
                    from app.services.frontapp_service import add_conversation_tags
                    if updated_email.front_conversation_id:
                        add_conversation_tags(updated_email.front_conversation_id, ["AI: Human review required"])
                        logger.info(f"Added 'AI: Human review required' tag to conversation {updated_email.front_conversation_id} after OCR failure.")
                except Exception as tag_exc:
                    logger.error(f"Failed to add AI-review tag for conversation {updated_email.front_conversation_id}: {tag_exc}")

                # Continue to next step in processing pipeline
                from app.tasks.email import orchestrate_post_ocr_processing
                logger.info(f"OCR completed (with errors) for {email_uuid}, queueing for post-OCR orchestration on 'processing' queue.")
                orchestrate_post_ocr_processing.apply_async(args=[str(email_uuid)], queue='processing')
        else:
            logger.error(f"Email {email_uuid} not found when handling OCR failure")
    except Exception as db_exc:
        logger.exception(f"Database error handling OCR failure for email {email_uuid}: {db_exc}")
        if db.is_active:
            db.rollback()
    finally:
        if db.is_active:
            db.close()


@celery_app.task(name="tasks.check_ocr_service_health")
def check_ocr_service_health() -> Dict:
    """
    Health check task for the OCR service.
    Useful for monitoring and alerting.
    """
    try:
        # Simple health check - try to connect to the OCR endpoint
        import httpx
        from app.services.ocr_service import OCR_API_URL
        
        with httpx.Client(verify=False, timeout=10.0) as client:
            # Just try to connect, don't send data
            response = client.get(OCR_API_URL.replace('/all_doc_ocr_process', '/health'), timeout=10.0)
            if response.status_code == 200:
                logger.info("OCR service health check: HEALTHY")
                return {"status": "healthy", "service": "ocr"}
            else:
                logger.warning(f"OCR service health check: UNHEALTHY (status: {response.status_code})")
                return {"status": "unhealthy", "service": "ocr", "http_status": response.status_code}
                
    except Exception as e:
        logger.error(f"OCR service health check: FAILED ({str(e)})")
        return {"status": "failed", "service": "ocr", "error": str(e)} 