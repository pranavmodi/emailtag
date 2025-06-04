"""Email processing tasks."""

import nest_asyncio # Import nest_asyncio
nest_asyncio.apply() # Apply the patch


import logging
from typing import Dict, List
from uuid import UUID
import base64 # Added for encoding
import io # Added for handling binary data
import asyncio # Add asyncio import

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from celery import Celery
from celery.utils.log import get_task_logger
import httpx

from app.core.config import settings
from app.crud.sync import email as email_crud_sync
from app.crud.sync import tag as tag_crud_sync
from app.db.session import SessionLocal
from app.db.session import AsyncSessionLocal # Add AsyncSessionLocal import
from app.services.classification_service import classify_email_tags_hierarchical, remove_conflicting_tags
from app.services.frontapp_service import add_conversation_tags, get_conversation_text, get_conversation_tags, remove_conversation_tags, create_new_conversation_for_split # Added create_new_conversation_for_split
from app.services.ocr_service import process_ocr_content # Import the new function
from app.services.autorespond_service import process_autorespond  # Add this import
from app.services.topic_analysis_service import is_new_unresolved_topic_present # Added topic analysis service
from app.tasks.worker import celery_app
from app.crud import email as email_crud
from app.models.email import Email # Added for type hinting
from app.schemas.email import EmailUpdate # Added for type hinting
from app.services.archiving_service import check_and_archive_conversation # Import the new archiving service

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.email.process_email")
def process_email(email_id: str) -> Dict:
    """
    Process an email:
    1. Validates email ID.
    2. Checks if OCR is needed based on attachments.
    3. If OCR is needed, sets status to 'pending_ocr', populates 'ocr_attachments_total',
       and dispatches 'send_attachment_to_ocr' tasks for each attachment.
    4. If OCR is not needed (no attachments or already processed),
       it directly queues 'orchestrate_post_ocr_processing'.
    """
    logger.info(f"Processing email {email_id} in new flow.")

    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}

    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found in process_email task.")
            return {"status": "error", "message": "Email not found"}

        # Assuming 'ocr_status' can be: None (not processed), 'pending_ocr', 'ocr_completed', 'ocr_error', 'ocr_skipped'
        # And Email model has 'ocr_attachments_total'
        
        needs_ocr = False
        if email_obj.has_attachments and email_obj.status not in ["ocr_completed", "ocr_error", "ocr_skipped", "pending_ocr"]: # Basic check
             # More robust: check a dedicated ocr_status field if available
             needs_ocr = True


        if needs_ocr:
            logger.info(f"Email {email_id} has attachments and requires OCR.")
            
            attachments_data = []
            try:
                # Path to attachments in raw_data might vary based on your webhook structure
                # Example path assuming FrontApp webhook structure stored in raw_data:
                if email_obj.raw_data and isinstance(email_obj.raw_data, dict):
                    target_data = email_obj.raw_data.get('target', {}).get('data', {})
                    attachments_data = target_data.get('attachments', [])
                
                if not attachments_data:
                     logger.warning(f"Email {email_id} marked with has_attachments but no attachment data found in raw_data. Skipping OCR.")
                     # Update status to indicate skipped OCR or proceed as if no attachments
                     email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="ocr_skipped")) # Example status
                     orchestrate_post_ocr_processing.apply_async(args=[email_id], queue='processing')
                     return {"status": "ocr_skipped", "email_id": email_id}

            except Exception as e:
                logger.error(f"Error accessing attachment data from raw_data for {email_id}: {e}. Skipping OCR.")
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="ocr_error")) # Mark as error
                return {"status": "error", "message": "Failed to access attachment data"}

            ocr_attachments_total = len(attachments_data)
            logger.info(f"Found {ocr_attachments_total} attachments for email {email_id}.")

            # Update email with pending_ocr status and total attachments count
            # Ensure EmailUpdate schema and Email model support ocr_attachments_total
            update_payload = EmailUpdate(
                status="pending_ocr",
                ocr_attachments_total=ocr_attachments_total,
                ocr_attachments_completed=0 # Reset completed count
            )
            email_crud_sync.update(db, db_obj=email_obj, obj_in=update_payload)
            
            for attachment in attachments_data:
                attachment_url = attachment.get("url")
                if attachment_url:
                    logger.info(f"Queueing OCR for attachment {attachment_url} for email {email_id} to 'ocr' queue")
                    # send_attachment_to_ocr.delay(email_id, attachment_url)
                    send_attachment_to_ocr.apply_async(args=[email_id, attachment_url], queue='ocr')
                else:
                    logger.warning(f"Attachment for email {email_id} is missing a URL. Decrementing total.")
                    # If an attachment has no URL, we should decrement the total count
                    # so the completion logic in send_attachment_to_ocr works correctly.
                    ocr_attachments_total -= 1
                    email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(ocr_attachments_total=ocr_attachments_total))


            if ocr_attachments_total == 0 and attachments_data: # All attachments lacked URLs
                logger.warning(f"All attachments for {email_id} lacked URLs. Skipping OCR phase.")
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="ocr_skipped"))
                # orchestrate_post_ocr_processing.delay(email_id)
                orchestrate_post_ocr_processing.apply_async(args=[email_id], queue='processing')
                return {"status": "ocr_skipped_no_urls", "email_id": email_id}
            
            return {"status": "ocr_initiated", "email_id": email_id, "attachments_queued": ocr_attachments_total}

        else:
            logger.info(f"Email {email_id} does not require OCR or OCR already handled. Proceeding to orchestration on 'processing' queue.")
            # If OCR was previously completed, status might be 'ocr_completed'.
            # If no attachments, has_attachments is false.
            # If OCR was skipped, status might be 'ocr_skipped'.
            # orchestrate_post_ocr_processing.delay(email_id)
            orchestrate_post_ocr_processing.apply_async(args=[email_id], queue='processing')
            return {"status": "processing_ocr_not_needed", "email_id": email_id}

    except Exception as e:
        logger.exception(f"Error in process_email for {email_id}: {e}")
        if db.is_active:
            db.rollback()
        # Optionally update email status to an error state here
        return {"status": "error", "message": str(e)}
    finally:
        if db.is_active:
            db.close()


@celery_app.task(name="app.tasks.email.orchestrate_post_ocr_processing")
def orchestrate_post_ocr_processing(email_id: str) -> Dict:
    """
    Orchestrates processing after OCR (or if OCR was skipped).
    1. Fetches email.
    2. Performs Topic Split Detection.
    3. Performs Archiving Check.
    4. If not split or archived, queues perform_tagging_task.
    """
    logger.info(f"Orchestrating post-OCR/skipped processing for email {email_id}")

    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id in orchestrate_post_ocr_processing: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}

    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found for orchestration")
            return {"status": "error", "message": "Email not found"}

        front_conversation_id = email_obj.front_conversation_id
        if not front_conversation_id:
            logger.error(f"Email {email_id} does not have a Front conversation ID. Cannot orchestrate.")
            # Mark as processed with an error or a specific status
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="orchestration_failed_no_front_id", is_processed=True))
            return {"status": "error", "message": "Missing Front conversation ID for orchestration"}

        # --- TOPIC SPLIT DETECTION --- (Copied and adapted from tag_email)
        is_potential_split = False
        try:
            conversation_data_for_split = get_conversation_text(front_conversation_id)
            structured_messages_for_analysis = conversation_data_for_split.get('_structured_messages', [])

            if not structured_messages_for_analysis:
                logger.warning(f"Could not retrieve structured message history for {front_conversation_id} to attempt topic split. Proceeding without split check.")
            elif len(structured_messages_for_analysis) <= 1:
                logger.info(f"Conversation {front_conversation_id} has only one or no messages. No split check needed.")
            else:
                history_for_prompt = structured_messages_for_analysis[:-1]
                transformed_history_for_analysis = []
                for msg in history_for_prompt:
                    transformed_history_for_analysis.append({
                        "sender_type": msg.get("author_role", "user"),
                        "body": msg.get("body", "")
                    })
                
                new_message_text_for_analysis = email_obj.content_text
                new_message_sender_role_for_analysis = "User"
                
                split_decision = False
                async def _run_topic_analysis_async():
                    nonlocal split_decision
                    split_decision = await is_new_unresolved_topic_present(
                        conversation_messages=transformed_history_for_analysis,
                        new_message_text=new_message_text_for_analysis,
                        new_message_sender_role=new_message_sender_role_for_analysis
                    )
                asyncio.run(_run_topic_analysis_async())
                
                if split_decision:
                    is_potential_split = True
                    logger.info(f"AI detected new unresolved topic for email {email_id} in conversation {front_conversation_id}.")
                else:
                    logger.info(f"AI analysis: No new unresolved topic for email {email_id}. Proceeding normally.")

        except Exception as e_topic_detect:
            logger.error(f"Error during topic split detection for {front_conversation_id}: {e_topic_detect}", exc_info=True)
            is_potential_split = False

        if is_potential_split:
            try:
                logger.info(f"Attempting to split message from email {email_id} (conversation {front_conversation_id}).")
                if not settings.FRONT_CHANNEL_PRIMARY_EMAIL:
                    logger.error("FRONT_CHANNEL_PRIMARY_EMAIL setting is not configured. Cannot determine 'to_handle' for split.")
                    raise ValueError("FRONT_CHANNEL_PRIMARY_EMAIL not configured.")

                new_conv_subject = f"Split: {email_obj.subject.replace('[SPLIT]', '').strip() if email_obj.subject else 'Split Conversation'}"
                new_conv_body = email_obj.content_text if email_obj.content_text else email_obj.content_html
                new_conv_sender_handle = email_obj.sender
                new_conv_sender_name = email_obj.sender
                target_channel_id_for_new_conv = settings.FRONT_CHANNEL_ID
                new_conv_metadata = {
                    "thread_ref": f"split-from-{front_conversation_id}-{email_obj.id.hex[:8]}",
                    "is_inbound": True,
                    "source_conversation_id": front_conversation_id,
                    "source_email_db_id": str(email_obj.id)
                }

                split_response = create_new_conversation_for_split(
                    channel_id=target_channel_id_for_new_conv,
                    sender_handle=new_conv_sender_handle,
                    sender_name=new_conv_sender_name,
                    to_handle=settings.FRONT_CHANNEL_PRIMARY_EMAIL,
                    subject=new_conv_subject,
                    body=new_conv_body,
                    body_format="html",
                    metadata=new_conv_metadata
                )

                if split_response and split_response.get("conversation_reference"):
                    new_front_conv_ref = split_response.get("conversation_reference")
                    logger.info(f"Successfully created new Front conversation ({new_front_conv_ref}) for split message from email {email_id}.")
                    try:
                        add_conversation_tags(front_conversation_id, ["System: Split - New Topic"])
                        logger.info(f"Tagged original conversation {front_conversation_id} for split.")
                    except Exception as tag_err:
                        logger.error(f"Failed to tag original conversation {front_conversation_id} after split: {tag_err}")
                    
                    email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="split_off", is_processed=True))
                    logger.info(f"Marked email {email_id} as 'split_off' and processed.")
                    return {"status": "success_split", "original_email_id": email_id, "new_conversation_reference": new_front_conv_ref}
                else:
                    logger.error(f"Failed to create new conversation for split (email {email_id}). API response: {split_response}")
                    # Fall through to regular processing if split failed critically (handled by not returning)

            except Exception as e_split:
                logger.error(f"Error during split attempt for email {email_id}: {e_split}", exc_info=True)
                # Fall through to process the email in the original conversation if split fails
        
        # --- END TOPIC SPLIT DETECTION ---

        # --- Check for archiving before proceeding (if not split and split didn't return) ---
        # (Copied and adapted from tag_email)
        try:
            logger.info(f"Checking if conversation {front_conversation_id} can be archived before tagging.")
            async def _run_archive_check_async():
                return await check_and_archive_conversation(front_conversation_id)
            
            was_archived = asyncio.run(_run_archive_check_async())

            if was_archived:
                logger.info(f"Conversation {front_conversation_id} was archived. Orchestration complete for this path.")
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="archived_in_orchestration", is_processed=True))
                return {"status": "success_archived_orchestration", "email_id": email_id}
            else:
                logger.info(f"Conversation {front_conversation_id} not archived. Proceeding to tagging.")
        except Exception as e_archive_check:
            logger.error(f"Error during pre-tagging archive check for {front_conversation_id}: {e_archive_check}", exc_info=True)
            # Proceed with tagging if archive check fails

        # If not split and not archived, queue for tagging
        # perform_tagging_task.delay(email_id)
        perform_tagging_task.apply_async(args=[email_id], queue='tagging')
        logger.info(f"Queued email {email_id} for tagging on 'tagging' queue.")
        return {"status": "queued_for_tagging", "email_id": email_id}

    except Exception as e:
        logger.exception(f"Error in orchestrate_post_ocr_processing for {email_id}: {str(e)}")
        if db.is_active:
            db.rollback()
        # Update email status to reflect orchestration failure
        try: # Try to update status even in exception block
            email_uuid_for_error = UUID(email_id) # Re-validate for safety
            # email_obj_for_error = email_crud_sync.get(db, id=email_uuid_for_error) # db might be closed or rolled back
            # To update status in case of failure, we might need a fresh session or a separate utility
            # For now, this error will be caught by Celery retry or marked as failed by Celery itself.
            # Consider a robust way to mark email as 'orchestration_failed' if possible.
        except: # Outer try-except for safety with UUID conversion
            pass 
        return {"status": "error", "message": str(e)}
    finally:
        if db.is_active:
            db.close()


@celery_app.task(name="app.tasks.email.perform_tagging_task")
def perform_tagging_task(email_id: str) -> Dict:
    """
    Performs email classification and tagging.
    1. Fetches email and conversation context.
    2. Classifies email for tags.
    3. Resolves tag conflicts.
    4. Applies tags to Front conversation.
    5. Updates local DB.
    6. Queues perform_autorespond_task.
    """
    logger.info(f"Performing tagging for email {email_id}")

    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id in perform_tagging_task: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}

    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found for tagging")
            return {"status": "error", "message": "Email not found"}

        front_conversation_id = email_obj.front_conversation_id
        if not front_conversation_id:
            logger.error(f"Email {email_id} has no Front conversation ID for tagging.")
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="tagging_failed_no_front_id", is_processed=True))
            return {"status": "error", "message": "Missing Front conversation ID for tagging"}

        # Fetch conversation text for classification (Adapted from tag_email)
        conversation_data = get_conversation_text(front_conversation_id)
        if not conversation_data or 'text' not in conversation_data:
            logger.error(f"Could not retrieve conversation text for {front_conversation_id}. Cannot tag.")
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="tagging_failed_no_content", is_processed=True))
            return {"status": "error", "message": "Failed to get conversation text for tagging"}

        conversation_text = conversation_data.get('text', '')
        raw_senders = conversation_data.get('senders', ['Unknown Sender'])
        raw_timestamps = conversation_data.get('timestamps', ['Unknown Timestamps'])
        
        sender_info = ", ".join(map(str, raw_senders)) if raw_senders else "Unknown Sender"
        message_times = ", ".join(map(str, raw_timestamps)) if raw_timestamps else "Unknown Timestamps"

        if not conversation_text:
            logger.warning(f"Received empty conversation text for {front_conversation_id}. Tagging might be ineffective.")
            # Decide if to proceed or mark as error. For now, let it proceed.

        # Get current tags from Front (Adapted from tag_email)
        current_front_tags = get_conversation_tags(front_conversation_id)
        if current_front_tags is None:
            logger.warning(f"Failed to retrieve current tags for {front_conversation_id}. Proceeding with empty list for conflict check.")
            current_front_tags = []

        # Classify using the hierarchical service (Adapted from tag_email)
        new_tags: List[str] = []
        async def _run_hierarchical_classification_async():
            nonlocal new_tags
            new_tags = await classify_email_tags_hierarchical(
                front_conversation_id=front_conversation_id,
                conversation_text=conversation_text,
                sender_info=sender_info,
                message_times=message_times
            )
        asyncio.run(_run_hierarchical_classification_async())

        applied_tags_to_front = False
        if not new_tags:
            logger.warning(f"Hierarchical classification returned no tags for {front_conversation_id}.")
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="tagging_completed_no_tags"))
            # No tags to apply, but still proceed to auto-respond check
        else:
            logger.info(f"Hierarchical classification for {front_conversation_id} resulted in tags: {new_tags}")
            removed_conflicts = remove_conflicting_tags(
                conversation_id=front_conversation_id,
                existing_tags=current_front_tags,
                new_tags=new_tags,
                hierarchy=settings.EMAIL_CATEGORIES 
            )
            if not removed_conflicts:
                logger.warning(f"Failed to remove conflicting tags for {front_conversation_id}. Applying new tags anyway.")

            apply_success = add_conversation_tags(front_conversation_id, new_tags)
            if apply_success:
                logger.info(f"Successfully applied tags {new_tags} to conversation {front_conversation_id}")
                applied_tags_to_front = True
                tag_objects = []
                for tag_name in new_tags:
                    tag_obj = tag_crud_sync.get_or_create_tag(db, name=tag_name)
                    tag_objects.append(tag_obj)
                email_crud_sync.update_tags(db, db_obj=email_obj, tags=tag_objects)
                logger.info(f"Updated tags in database for email {email_id}")
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="tagging_completed_applied_tags"))
            else:
                logger.error(f"Failed to apply tags {new_tags} to conversation {front_conversation_id}")
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="tagging_failed_front_apply", is_processed=True))
                # Even if Front apply fails, we might want to proceed to auto-respond or halt.
                # For now, proceed to auto-respond, but is_processed=True to avoid retries on this specific error.
        
        # Regardless of tagging outcome (unless critical error above), proceed to auto-response.
        # perform_autorespond_task.delay(email_id)
        perform_autorespond_task.apply_async(args=[email_id], queue='processing')
        logger.info(f"Queued email {email_id} for auto-response on 'processing' queue.")
        return {"status": "queued_for_autorespond", "email_id": email_id, "tags_applied_to_front": applied_tags_to_front, "determined_tags": new_tags}

    except Exception as e:
        logger.exception(f"Error in perform_tagging_task for {email_id}: {str(e)}")
        if db.is_active:
            db.rollback()
        try:
            email_uuid_for_error = UUID(email_id)
            # Consider updating status to "tagging_failed_exception" if email_obj was fetched
            # db_temp = SessionLocal()
            # temp_email_obj = email_crud_sync.get(db_temp, id=email_uuid_for_error)
            # if temp_email_obj:
            #     email_crud_sync.update(db_temp, db_obj=temp_email_obj, obj_in=EmailUpdate(status="tagging_failed_exception", is_processed=True))
            # db_temp.close()
        except: # Outer try-except for safety with UUID conversion
            pass
        return {"status": "error", "message": str(e)}
    finally:
        if db.is_active:
            db.close()


@celery_app.task(name="app.tasks.email.perform_autorespond_task")
def perform_autorespond_task(email_id: str) -> Dict:
    """
    Handles auto-response logic for an email and sets final status.
    1. Fetches email and conversation context.
    2. Checks and applies auto-response rules.
    3. Updates email status to a final state.
    """
    logger.info(f"Performing auto-response check for email {email_id}")

    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id in perform_autorespond_task: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}

    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found for auto-response.")
            return {"status": "error", "message": "Email not found"}

        front_conversation_id = email_obj.front_conversation_id
        if not front_conversation_id:
            logger.error(f"Email {email_id} has no Front conversation ID for auto-response.")
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="autorespond_failed_no_front_id", is_processed=True))
            return {"status": "error", "message": "Missing Front conversation ID for auto-response"}

        # Fetch conversation text for auto-response (can be optimized if passed from previous task)
        conversation_data = get_conversation_text(front_conversation_id) # Assuming this is still needed by process_autorespond
        if not conversation_data or 'text' not in conversation_data: # Check if process_autorespond actually needs full conv_data or just text
            logger.error(f"Could not retrieve conversation text for {front_conversation_id}. Cannot auto-respond.")
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="autorespond_failed_no_content", is_processed=True))
            return {"status": "error", "message": "Failed to get conversation text for auto-response"}
        
        conversation_text_for_autorespond = conversation_data.get('text', '')

        # --- AUTO-RESPONSE CHECK (Adapted from tag_email) ---
        auto_response_processed_flag = False # Renamed to avoid conflict if we pass a dict later
        auto_response_details = None
        try:
            logger.info(f"Checking for auto-response for conversation {front_conversation_id}.")

            async def _run_autorespond_async():
                async_db_session = AsyncSessionLocal() # process_autorespond needs async session
                try:
                    return await process_autorespond(front_conversation_id, async_db_session, conversation_text_for_autorespond)
                finally:
                    await async_db_session.close()
            
            auto_response_result = asyncio.run(_run_autorespond_async())

            if auto_response_result and auto_response_result.get("status") == "auto_response_sent":
                logger.info(f"Auto-response sent for conversation {front_conversation_id}. Details: {auto_response_result.get('details')}")
                auto_response_processed_flag = True
                auto_response_details = auto_response_result.get('details')
            elif auto_response_result and auto_response_result.get("status") == "no_auto_response_needed":
                logger.info(f"No auto-response needed for conversation {front_conversation_id}.")
            else:
                logger.warning(f"Auto-response processing for {front_conversation_id} had unexpected result: {auto_response_result}")

        except Exception as e_auto_respond:
            logger.error(f"Error during auto-response check for {front_conversation_id}: {e_auto_respond}", exc_info=True)
            # Proceed to set final status even if auto-response check fails

        # Determine final status based on tagging and auto-response outcomes
        # The status from perform_tagging_task (e.g., "tagging_completed_applied_tags", "tagging_completed_no_tags")
        # is already on email_obj.status if it was updated successfully.
        
        current_status_from_tagging = email_obj.status # This reflects the outcome of the tagging step
        final_email_status = "processed_unknown_state"

        if auto_response_processed_flag:
            if current_status_from_tagging == "tagging_completed_applied_tags":
                final_email_status = "processed_autorespond_tagged"
            elif current_status_from_tagging == "tagging_completed_no_tags":
                final_email_status = "processed_autorespond_notags"
            else: # Tagging might have failed or had a different status
                final_email_status = "processed_autorespond_tag_state_unknown"
        else: # No auto-response sent
            if current_status_from_tagging == "tagging_completed_applied_tags":
                final_email_status = "processed_tagged_no_autorespond"
            elif current_status_from_tagging == "tagging_completed_no_tags":
                final_email_status = "processed_notags_no_autorespond"
            else: # Tagging might have failed before this step, or other status
                 # If tagging failed and set is_processed=True, this task might not even run for certain failures.
                 # However, if it does, we reflect that. Or, simply use a generic processed status.
                 final_email_status = f"processed_tag_status_({current_status_from_tagging})_no_autorespond"
                 # A simpler approach if previous status is not critical for final status: just "processed"
                 # final_email_status = "processed" 

        logger.info(f"Setting final status for email {email_id} to: {final_email_status}")
        email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_email_status, is_processed=True))
        
        return {
            "status": "completed_autorespond_phase", 
            "email_id": email_id, 
            "final_db_status": final_email_status,
            "auto_response_sent": auto_response_processed_flag,
            "auto_response_details": auto_response_details
        }

    except Exception as e:
        logger.exception(f"Error in perform_autorespond_task for {email_id}: {str(e)}")
        if db.is_active:
            db.rollback()
        try:
            email_uuid_for_error = UUID(email_id)
            # Attempt to mark as failure if possible, though db session might be bad
            # update_email_status_sync(email_uuid_for_error, "autorespond_failed_exception") # Needs careful implementation
        except:
            pass
        return {"status": "error", "message": str(e)}
    finally:
        if db.is_active:
            db.close()


@celery_app.task(name="tasks.send_attachment_to_ocr", bind=True, max_retries=3, default_retry_delay=60)
def send_attachment_to_ocr(self, email_id: str, attachment_url: str):
    """
    Downloads an attachment, sends it to the synchronous OCR service,
    and updates the email record directly.
    """
    # logger.info(f"Starting OCR processing via service for attachment {attachment_url} for email {email_id}")
    
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        # logger.error(f"Invalid UUID format for email_id: {email_id}. Cannot proceed.")
        return # Abort task

    # --- Download Attachment ---
    try:
        headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
        with httpx.Client(follow_redirects=True) as client: # Ensure redirects are followed
            # logger.info(f"Downloading attachment from {attachment_url}...")
            response = client.get(attachment_url, headers=headers, timeout=120.0) # Increased timeout for download
            response.raise_for_status()
            attachment_content = response.content
            # logger.info(f"Successfully downloaded attachment for email {email_id}. Size: {len(attachment_content)} bytes.")
    except httpx.HTTPStatusError as exc:
        # logger.error(f"HTTP error downloading attachment {attachment_url} for email {email_id}: {exc.response.status_code} - {exc.response.text}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        # Consider retry for transient server errors (e.g., 5xx)
        if 500 <= exc.response.status_code < 600:
            try:
                self.retry(exc=exc)
            except Exception as retry_exc:
                # logger.error(f"Retry failed for download error: {retry_exc}")
                pass
        return # Abort after updating status
    except httpx.RequestError as exc:
        # logger.error(f"Request error downloading attachment {attachment_url} for email {email_id}: {exc}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        try:
            self.retry(exc=exc) # Retry on general request errors (network issues, etc.)
        except Exception as retry_exc:
             # logger.error(f"Retry failed for download request error: {retry_exc}")
             pass
        return # Abort after updating status
    except Exception as exc:
        # logger.exception(f"Unexpected error downloading attachment {attachment_url} for email {email_id}: {exc}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        return # Abort after updating status

    # --- Call OCR Service ---
    try:
        # logger.info(f"Calling OCR service function for email {email_id}...")
        ocr_result = process_ocr_content(attachment_content) # Call the service function

        if ocr_result is None:
            # logger.warning(f"OCR service function returned None for email {email_id}. Assuming no result.")
            # Mark as error or handle as needed - for now, let DB update handle it as potentially empty
            ocr_result = {} # Set to empty dict to avoid errors below, but DB update logic will handle empty info
        else:
             # logger.info(f"Successfully received OCR result via service function for email {email_id}.")
             # logger.debug(f"OCR Result payload: {ocr_result}")
             pass

    except httpx.HTTPStatusError as exc:
        # Raised by process_ocr_content if API returns 4xx/5xx
        # logger.error(f"HTTP error from OCR service function for email {email_id}: {exc.response.status_code} - {exc.response.text}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        # Consider retry for transient server errors (e.g., 5xx)
        if 500 <= exc.response.status_code < 600:
            try:
                self.retry(exc=exc)
            except Exception as retry_exc:
                # logger.error(f"Retry failed for OCR service HTTP error: {retry_exc}")
                pass
        return # Abort after updating status
    except httpx.RequestError as exc:
        # Raised by process_ocr_content for connection/timeout issues
        # logger.error(f"Request error from OCR service function for email {email_id}: {exc}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        try:
            self.retry(exc=exc) # Retry on general request errors
        except Exception as retry_exc:
             # logger.error(f"Retry failed for OCR service request error: {retry_exc}")
             pass
        return # Abort after updating status
    except Exception as exc:
        # Catch other exceptions from process_ocr_content (e.g., encoding, general exceptions)
        # logger.exception(f"Unexpected error calling OCR service function or processing its result for email {email_id}: {exc}")
        update_email_status_sync(email_uuid, OCR_ERROR_STATUS)
        return # Abort

    # --- Process OCR Result and Update DB ---
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            # logger.error(f"Email {email_id} not found during OCR result processing.")
            return # Cannot update non-existent email

        if email_obj.status not in ["pending_ocr", OCR_ERROR_STATUS]: # Also allow reprocessing if previous attempt failed
             # logger.warning(f"Email {email_id} is not in pending_ocr or ocr_error state (current: {email_obj.status}). Skipping update.")
             return # Avoid race conditions or double processing

        # Prepare structured result for this attachment
        attachment_ocr_data = {}
        try:
            # Assuming the structure: {"data": [{"info": {...}}], "message": "..."}
            ocr_info = ocr_result.get("data", [{}])[0].get("info", {})
            if not ocr_info:
                 # logger.warning(f"OCR result for email {email_id} lacks 'info' field or is empty. Result: {ocr_result}")
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
            # logger.error(f"Error parsing OCR result structure for email {email_id}: {parse_error}. Result: {ocr_result}")
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

        # logger.info(f"Updated email {email_id} with OCR result for attachment {attachment_url}. Completed {completed_count}/{updated_email.ocr_attachments_total} attachments.")

        # Check if all attachments are processed
        if updated_email.ocr_attachments_total is not None and completed_count >= updated_email.ocr_attachments_total:
            # Check if any attachment processing resulted in an error
            has_errors = any(result.get('error') for result in updated_email.ocr_results or [])
            final_status = OCR_ERROR_STATUS if has_errors else "ocr_completed"
            
            # logger.info(f"All OCR processing complete for email {email_id}. Setting status to {final_status} and queueing for final processing.")
            # Update status separately to ensure it happens after field updates
            email_crud_sync.update(db, db_obj=updated_email, obj_in=EmailUpdate(status=final_status))
            
            # Only queue next step if there were no errors
            if final_status == "ocr_completed":
                # process_email.delay(str(email_uuid))
                logger.info(f"OCR completed for {email_id}, queueing for post-OCR orchestration on 'processing' queue.")
                # orchestrate_post_ocr_processing.delay(str(email_uuid))
                orchestrate_post_ocr_processing.apply_async(args=[str(email_uuid)], queue='processing')
            else:
                # logger.warning(f"Skipping final processing for email {email_id} due to OCR errors.")
                pass

    except Exception as db_exc:
        # logger.exception(f"Database error processing OCR result for email {email_id}: {db_exc}")
        db.rollback()
        # Don't necessarily set to OCR_ERROR_STATUS here, could be transient DB issue
        # Consider retry?
        try:
            self.retry(exc=db_exc)
        except Exception as retry_exc:
             # logger.error(f"Retry failed for DB error: {retry_exc}")
             pass
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
        # logger.info(f"Updated status for email {email_id} to {status}") 

# Define error status constant
OCR_ERROR_STATUS = "ocr_error"

def update_email_sync(email_uuid: UUID, update_data: dict):
    """Helper function to update email fields synchronously."""
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            # logger.error(f"[update_email_sync] Email {email_uuid} not found for update.")
            return None
        
        updated_email = email_crud_sync.update(db, db_obj=email_obj, obj_in=update_data)
        # No need to commit here, update() handles it
        # db.commit()
        # db.refresh(updated_email) # Refresh is handled by update()
        # logger.info(f"[update_email_sync] Successfully updated email {email_uuid} with data: {update_data}")
        return updated_email # Return the updated object
    except Exception as e:
        # logger.exception(f"[update_email_sync] Error updating email {email_uuid}: {e}")
        db.rollback()
        return None # Indicate failure
    finally:
        db.close()

def update_email_status_sync(email_uuid: UUID, status: str):
    """Helper function to update email status synchronously."""
    update_data = {"status": status}
    updated_email = update_email_sync(email_uuid, update_data)
    if updated_email:
         # logger.info(f"[update_email_status_sync] Updated status for email {email_uuid} to {status}")
         pass
    else:
         # logger.error(f"[update_email_status_sync] Failed to update status for email {email_uuid} to {status}")
         pass 