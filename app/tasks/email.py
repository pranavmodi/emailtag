"""Email processing tasks."""

import logging
from typing import Dict, List
from uuid import UUID
import base64 # Added for encoding
import io # Added for handling binary data

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from celery import Celery
from celery.utils.log import get_task_logger
import httpx

from app.core.config import settings
from app.crud.sync import email as email_crud_sync
from app.crud.sync import tag as tag_crud_sync
from app.db.session import SessionLocal
from app.services.classification_service import classify_email_tags_hierarchical, remove_conflicting_tags
from app.services.frontapp_service import add_conversation_tags, get_conversation_text, get_conversation_tags, remove_conversation_tags
from app.services.ocr_service import process_ocr_content # Import the new function
from app.services.autorespond_service import process_autorespond  # Add this import
from app.tasks.worker import celery_app
from app.crud import email as email_crud
from app.models.email import Email # Added for type hinting
from app.schemas.email import EmailUpdate # Added for type hinting

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.email.process_email")
def process_email(email_id: str) -> Dict:
    """
    Process an email by validating its ID and starting the classification task.

    Args:
        email_id: The UUID of the email to process

    Returns:
        Dict: Status of the processing initiation
    """
    logger.info(f"Processing email {email_id}")

    # Convert string to UUID
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}

    # Start classification/tagging task
    # Rename tag_email task to classify_email_category_task for clarity? Let's keep tag_email for now.
    tag_email.delay(email_id)

    return {"status": "processing", "email_id": email_id}


@celery_app.task(name="app.tasks.email.tag_email")
def tag_email(email_id: str) -> Dict:
    """
    Classify an email into a category and subcategory using AI analysis and apply tags.

    Args:
        email_id: The UUID of the email to classify and tag

    Returns:
        Dict: Status of the classification and tagging process
    """
    logger.info(f"Classifying email {email_id}")

    # Convert string to UUID
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id in tag_email task: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}

    # Get database session
    db = SessionLocal()
    try:
        # Get email from database using synchronous CRUD
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found for classification")
            return {"status": "error", "message": "Email not found"}

        # Get front conversation ID for analysis
        front_conversation_id = email_obj.front_conversation_id
        if not front_conversation_id:
            logger.error(f"Email {email_id} does not have a Front conversation ID. Cannot classify.")
            email_crud_sync.mark_as_processed(db, email_id=email_uuid)
            return {"status": "error", "message": "Missing Front conversation ID"}

        # Get conversation data
        conversation_data = get_conversation_text(front_conversation_id)
        if not conversation_data or not isinstance(conversation_data, dict):
            logger.error(f"Failed to get conversation data for {front_conversation_id}")
            return {"status": "error", "message": "Failed to get conversation data"}

        conversation_text = conversation_data.get('text', '')
        sender_info = ", ".join(map(str, conversation_data.get('senders', ['Unknown Sender'])))
        message_times = ", ".join(map(str, conversation_data.get('timestamps', ['Unknown Timestamps'])))

        # Get existing tags
        existing_tags_data = get_conversation_tags(front_conversation_id)
        if existing_tags_data:
            existing_tags = [tag.get('name') for tag in existing_tags_data if tag.get('name')]
            logger.info(f"Found existing tags for {front_conversation_id}: {existing_tags}")
        else:
            existing_tags = []
            logger.warning(f"Could not retrieve existing tags for {front_conversation_id} or none exist.")

        # Perform classification
        tags_to_apply = classify_email_tags_hierarchical(
            front_conversation_id=front_conversation_id,
            conversation_text=conversation_text,
            sender_info=sender_info,
            message_times=message_times
        )

        # Process auto-response if needed
        try:
            autorespond_sent = process_autorespond(front_conversation_id, conversation_text)
            if autorespond_sent:
                logger.info(f"Auto-response sent for conversation {front_conversation_id}")
                # Add auto-response tag to the list
                tags_to_apply.append("AI: Auto-responded")
        except Exception as e:
            logger.error(f"Error processing auto-response: {e}")

        # Ensure tags are unique before proceeding
        if tags_to_apply:
            unique_tags_to_apply = list(dict.fromkeys(tags_to_apply))  # Preserve order while deduplicating
            if len(unique_tags_to_apply) != len(tags_to_apply):
                logger.info(f"Removed duplicate tags. Original: {tags_to_apply}, Unique: {unique_tags_to_apply}")
                tags_to_apply = unique_tags_to_apply

        if not tags_to_apply:
            logger.error(f"Classification failed for email {email_id}. No tags determined.")
            return {"status": "error", "message": "Classification failed to determine tags"}

        logger.info(f"Email {email_id} classified with tags: {tags_to_apply}")

        # --- Explicitly remove 'Human review required' tag if applying other tags --- 
        human_review_tag = "AI: Human review required"
        if tags_to_apply != [human_review_tag] and human_review_tag in existing_tags:
            logger.info(f"Attempting to remove '{human_review_tag}' tag before applying new tags: {tags_to_apply}")
            try:
                remove_conversation_tags(front_conversation_id, [human_review_tag])
                logger.info(f"Successfully removed '{human_review_tag}' tag for conversation {front_conversation_id}.")
            except Exception as remove_hr_error:
                logger.error(f"Failed to remove '{human_review_tag}' tag for {front_conversation_id}: {remove_hr_error}. Proceeding anyway.")

        # Remove conflicting tags before adding new ones
        logger.info(f"Attempting to remove other conflicting tags for {front_conversation_id} based on hierarchy.")
        removal_success = remove_conflicting_tags(
            conversation_id=front_conversation_id,
            existing_tags=existing_tags,
            new_tags=tags_to_apply,
            hierarchy=settings.EMAIL_CATEGORIES
        )
        if not removal_success:
            logger.warning(f"Failed to remove conflicting tags for conversation {front_conversation_id}. Proceeding to add new tags anyway.")
        else:
            logger.info(f"Successfully processed conflicting tag removal for {front_conversation_id}.")

        # Create and associate tags in database
        db_tags = []
        for tag_name in tags_to_apply:
            db_tag = tag_crud_sync.get_or_create(db, name=tag_name)
            db_tags.append(db_tag)

        # Associate tags with email
        email_obj.tags = db_tags
        db.commit()

        # Update tags in FrontApp
        if email_obj.front_conversation_id:
            try:
                add_conversation_tags(
                    email_obj.front_conversation_id,
                    tags_to_apply
                )
                logger.info(f"Successfully applied tags {tags_to_apply} to Front conversation {email_obj.front_conversation_id}")
            except Exception as front_error:
                logger.error(f"Failed to update tags in Front for email {email_id}: {front_error}", exc_info=True)

        # Mark email as processed
        email_crud_sync.mark_as_processed(db, email_id=email_uuid)

        return {
            "status": "success",
            "email_id": email_id,
            "applied_tags": tags_to_apply
        }

    except Exception as e:
        logger.exception(f"Error classifying/tagging email {email_id}: {str(e)}")
        db.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        db.close()

# Define error status constant
OCR_ERROR_STATUS = "ocr_error"

def update_email_sync(email_uuid: UUID, update_data: dict):
    """Helper function to update email fields synchronously."""
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"[update_email_sync] Email {email_uuid} not found for update.")
            return None
        
        updated_email = email_crud_sync.update(db, db_obj=email_obj, obj_in=update_data)
        # No need to commit here, update() handles it
        # db.commit()
        # db.refresh(updated_email) # Refresh is handled by update()
        logger.info(f"[update_email_sync] Successfully updated email {email_uuid} with data: {update_data}")
        return updated_email # Return the updated object
    except Exception as e:
        logger.exception(f"[update_email_sync] Error updating email {email_uuid}: {e}")
        db.rollback()
        return None # Indicate failure
    finally:
        db.close()

def update_email_status_sync(email_uuid: UUID, status: str):
    """Helper function to update email status synchronously."""
    update_data = {"status": status}
    updated_email = update_email_sync(email_uuid, update_data)
    if updated_email:
         logger.info(f"[update_email_status_sync] Updated status for email {email_uuid} to {status}")
    else:
         logger.error(f"[update_email_status_sync] Failed to update status for email {email_uuid} to {status}")


@celery_app.task(name="tasks.send_attachment_to_ocr", bind=True, max_retries=3, default_retry_delay=60)
def send_attachment_to_ocr(self, email_id: str, attachment_url: str):
    """
    Downloads an attachment, sends it to the synchronous OCR service,
    and updates the email record directly.
    """
    logger.info(f"Starting OCR processing via service for attachment {attachment_url} for email {email_id}")
    
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id: {email_id}. Cannot proceed.")
        return # Abort task

    # --- Download Attachment ---
    try:
        headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
        with httpx.Client(follow_redirects=True) as client: # Ensure redirects are followed
            logger.info(f"Downloading attachment from {attachment_url}...")
            response = client.get(attachment_url, headers=headers, timeout=120.0) # Increased timeout for download
            response.raise_for_status()
            attachment_content = response.content
            logger.info(f"Successfully downloaded attachment for email {email_id}. Size: {len(attachment_content)} bytes.")
    except httpx.HTTPStatusError as exc:
        logger.error(f"HTTP error downloading attachment {attachment_url} for email {email_id}: {exc.response.status_code} - {exc.response.text}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        # Consider retry for transient server errors (e.g., 5xx)
        if 500 <= exc.response.status_code < 600:
            try:
                self.retry(exc=exc)
            except Exception as retry_exc:
                logger.error(f"Retry failed for download error: {retry_exc}")
        return # Abort after updating status
    except httpx.RequestError as exc:
        logger.error(f"Request error downloading attachment {attachment_url} for email {email_id}: {exc}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        try:
            self.retry(exc=exc) # Retry on general request errors (network issues, etc.)
        except Exception as retry_exc:
             logger.error(f"Retry failed for download request error: {retry_exc}")
        return # Abort after updating status
    except Exception as exc:
        logger.exception(f"Unexpected error downloading attachment {attachment_url} for email {email_id}: {exc}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        return # Abort after updating status

    # --- Call OCR Service ---
    try:
        logger.info(f"Calling OCR service function for email {email_id}...")
        ocr_result = process_ocr_content(attachment_content) # Call the service function

        if ocr_result is None:
            # Handle cases where process_ocr_content returns None (e.g., empty content)
            logger.warning(f"OCR service function returned None for email {email_id}. Assuming no result.")
            # Mark as error or handle as needed - for now, let DB update handle it as potentially empty
            ocr_result = {} # Set to empty dict to avoid errors below, but DB update logic will handle empty info
        else:
             logger.info(f"Successfully received OCR result via service function for email {email_id}.")
             logger.debug(f"OCR Result payload: {ocr_result}")

    except httpx.HTTPStatusError as exc:
        # Raised by process_ocr_content if API returns 4xx/5xx
        logger.error(f"HTTP error from OCR service function for email {email_id}: {exc.response.status_code} - {exc.response.text}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        # Consider retry for transient server errors (e.g., 5xx)
        if 500 <= exc.response.status_code < 600:
            try:
                self.retry(exc=exc)
            except Exception as retry_exc:
                logger.error(f"Retry failed for OCR service HTTP error: {retry_exc}")
        return # Abort after updating status
    except httpx.RequestError as exc:
        # Raised by process_ocr_content for connection/timeout issues
        logger.error(f"Request error from OCR service function for email {email_id}: {exc}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        try:
            self.retry(exc=exc) # Retry on general request errors
        except Exception as retry_exc:
             logger.error(f"Retry failed for OCR service request error: {retry_exc}")
        return # Abort after updating status
    except Exception as exc:
        # Catch other exceptions from process_ocr_content (e.g., encoding, general exceptions)
        logger.exception(f"Unexpected error calling OCR service function or processing its result for email {email_id}: {exc}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        return # Abort

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
        attachment_ocr_data = {}
        try:
            # Assuming the structure: {"data": [{"info": {...}}], "message": "..."}
            ocr_info = ocr_result.get("data", [{}])[0].get("info", {})
            if not ocr_info:
                 logger.warning(f"OCR result for email {email_id} lacks 'info' field or is empty. Result: {ocr_result}")
                 # Store basic info even if OCR info is empty, to mark as processed
                 attachment_ocr_data = {
                     "attachment_url": attachment_url, # Use URL as identifier
                     "patient_id": None,
                     "accession_nums": [],
                     "study_type": [],
                     "error": "OCR result format invalid or empty info field."
                 }
            else:
                # Store the successfully extracted info
                attachment_ocr_data = {
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
            attachment_ocr_data = {
                "attachment_url": attachment_url,
                "error": f"Failed to parse OCR result: {parse_error}"
            }
            # Don't set global OCR_ERROR_STATUS here, let completion check handle it

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

        # Update the email record using the sync CRUD helper
        # This now updates ocr_results and ocr_attachments_completed
        updated_email = email_crud_sync.update(db, db_obj=email_obj, obj_in=update_payload)

        logger.info(f"Updated email {email_id} with OCR result for attachment {attachment_url}. Completed {completed_count}/{updated_email.ocr_attachments_total} attachments.")

        # Check if all attachments are processed
        if updated_email.ocr_attachments_total is not None and completed_count >= updated_email.ocr_attachments_total:
            # Check if any attachment processing resulted in an error
            has_errors = any(result.get('error') for result in updated_email.ocr_results or [])
            final_status = OCR_ERROR_STATUS if has_errors else "ocr_completed"
            
            logger.info(f"All OCR processing complete for email {email_id}. Setting status to {final_status} and queueing for final processing.")
            # Update status separately to ensure it happens after field updates
            email_crud_sync.update_status(db, email_id=email_uuid, status=final_status)
            
            # Only queue next step if there were no errors
            if final_status == "ocr_completed":
                process_email.delay(str(email_uuid))
            else:
                logger.warning(f"Skipping final processing for email {email_id} due to OCR errors.")

    except Exception as db_exc:
        logger.exception(f"Database error processing OCR result for email {email_id}: {db_exc}")
        db.rollback()
        # Don't necessarily set to OCR_ERROR_STATUS here, could be transient DB issue
        # Consider retry?
        try:
            self.retry(exc=db_exc)
        except Exception as retry_exc:
             logger.error(f"Retry failed for DB error: {retry_exc}")
    finally:
        db.close()

# Removed old async update_email_status function as we use sync updates now
# async def update_email_status(db: AsyncSession, email_id: str, status: str):
#    ...

# Helper function to update status (consider moving to crud)
async def update_email_status(db: AsyncSession, email_id: str, status: str):
    email = await email_crud.get(db, id=email_id)
    if email:
        update_data = {"status": status}
        await email_crud.update(db, db_obj=email, obj_in=update_data)
        logger.info(f"Updated status for email {email_id} to {status}") 