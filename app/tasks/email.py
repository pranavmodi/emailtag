"""Email processing tasks."""

import nest_asyncio # Import nest_asyncio
nest_asyncio.apply() # Apply the patch

import logging
from typing import Dict, List, Any
from uuid import UUID
import asyncio # Add asyncio import

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from celery import Celery
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.crud.sync import email as email_crud_sync
from app.crud.sync import tag as tag_crud_sync
from app.db.session import SessionLocal
from app.db.session import AsyncSessionLocal # Add AsyncSessionLocal import
from app.services.classification_service import classify_email_tags_hierarchical, remove_conflicting_tags
from app.services.frontapp_service import add_conversation_tags, get_conversation_text, get_conversation_tags, remove_conversation_tags, create_new_conversation_for_split, send_conversation_reply # Added send_conversation_reply
from app.services.autorespond_service import process_autorespond  # Add this import
from app.services.topic_analysis_service import is_new_unresolved_topic_present # Added topic analysis service
from app.tasks.worker import celery_app
from app.crud import email as email_crud
from app.models.email import Email # Added for type hinting
from app.schemas.email import EmailUpdate # Added for type hinting
from app.services.archiving_service import check_and_archive_conversation # Import the new archiving service

# Import OCR task from separate module
from app.tasks.ocr import send_attachment_to_ocr

# Import autorespond task from separate module
from app.tasks.autorespond import perform_autorespond_task

logger = get_task_logger(__name__)

# Helper function to format conversation history for the agent
def _format_conversation_history_for_agent(
    structured_messages: List[Dict[str, Any]],
    max_exchanges: int = 3 # Number of recent user-assistant turn pairs
) -> str:
    if not structured_messages:
        return "No relevant conversation history found."

    history_texts = []
    # Process messages to create a simplified dialog
    for msg in structured_messages:
        role = "Unknown"
        body = msg.get("body", "").strip()
        body_oneline = body.replace('\n', ' ').replace('\r', ' ')

        msg_type = msg.get("type")
        author_role = msg.get("author_role") # e.g., user, teammate
        direction = msg.get("direction") # e.g., inbound, outbound

        if direction == "inbound": # Typically user messages
            role = "User"
        elif direction == "outbound": # Typically assistant/teammate replies sent as messages
            role = "Assistant"
        elif msg_type == "comment" and author_role == "teammate": # Comments from teammates (could be internal notes or replies)
            # We might want to distinguish AI assistant comments vs human teammate comments if possible
            # For now, let's assume outbound-like comments are from Assistant for simplicity in history.
            role = "Assistant (comment)" 
        elif author_role == "user": # Fallback for user if direction not primary determinant
            role = "User"
        
        if body_oneline and role != "Unknown":
            history_texts.append(f"{role}: {body_oneline}")

    if not history_texts:
        return "No relevant conversation history found after formatting."
    
    # Return the last few exchanges (max_exchanges * 2 lines for User/Assistant pair)
    return "\n".join(history_texts[-(max_exchanges * 2):])

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
        if email_obj.has_attachments and email_obj.status not in ["ocr_completed", "ocr_completed_with_errors", "ocr_error", "ocr_skipped", "pending_ocr"]: # Basic check
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
        final_tagging_status = "tagging_error_unknown" # Default status for logging if something unexpected happens

        if not new_tags:
            logger.warning(f"Hierarchical classification returned no tags for {front_conversation_id}.")
            final_tagging_status = "tagging_completed_no_tags"
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_tagging_status))
            # No tags to apply to DB or Front in this case. is_processed remains False by default.
        else:
            logger.info(f"Hierarchical classification for {front_conversation_id} resulted in tags: {new_tags}")

            # --- Step 1: Update tags in the local database ---
            # This ensures that email_obj in this session and any subsequent fetches within other tasks
            # (if they fetch fresh data) will see the determined tags.
            tag_objects = []
            for tag_name in new_tags:
                tag_obj = tag_crud_sync.get_or_create(db, name=tag_name)
                tag_objects.append(tag_obj)
            email_obj.tags = tag_objects # This updates the email_obj.tags relationship in the current session
            logger.info(f"Updated determined tags {new_tags} in database for email {email_id}")
            # Note: The actual commit that saves this relationship change will happen
            # during the subsequent email_crud_sync.update() calls for status updates.

            # --- Step 2: Resolve conflicts and attempt to apply tags to Front ---
            # current_front_tags were fetched earlier and represent the state on Front before our changes.
            removed_conflicts = remove_conflicting_tags(
                conversation_id=front_conversation_id,
                existing_tags=current_front_tags, 
                new_tags=new_tags,
                hierarchy=settings.EMAIL_CATEGORIES 
            )
            if not removed_conflicts:
                # This means removal from Front might have failed or wasn't needed.
                logger.warning(f"Conflict removal from Front for {front_conversation_id} reported as not successful or not performed. Proceeding to add new tags.")

            apply_success = add_conversation_tags(front_conversation_id, new_tags)
            if apply_success:
                logger.info(f"Successfully applied tags {new_tags} to conversation {front_conversation_id} on Front.")
                applied_tags_to_front = True
                final_tagging_status = "tagging_completed_applied_tags"
                # Update status; is_processed defaults to False, allowing subsequent tasks in the chain.
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_tagging_status))
            else:
                logger.error(f"Failed to apply tags {new_tags} to conversation {front_conversation_id} on Front.")
                applied_tags_to_front = False 
                final_tagging_status = "tagging_completed_front_failed" 
                # Update status to reflect Front failure; mark as 'is_processed=True' for this tagging stage
                # to prevent retries of perform_tagging_task for Front API issues,
                # but auto-response will still proceed based on local DB tags.
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_tagging_status, is_processed=True))
        
        # Regardless of tagging outcome (unless critical error above), proceed to auto-response.
        perform_autorespond_task.apply_async(args=[email_id], kwargs={'determined_tags': new_tags}, queue='processing')
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



# OCR task moved to app.tasks.ocr module

# Removed old async update_email_status function as we use sync updates now
# async def update_email_status(db: AsyncSession, email_id: str, status: str):
#    ...

# Helper function to update status (consider moving to crud)
async def update_email_status(db: AsyncSession, email_id: str, status: str):
    email = await email_crud.get(db, id=UUID(email_id))
    if email:
        await email_crud.update(db, db_obj=email, obj_in=EmailUpdate(status=status))
        # logger.info(f"Updated status for email {email_id} to {status}") 

# OCR error status constant removed - now in app.tasks.ocr module 

# Helper function to format conversation history for the agent
def _format_conversation_history_for_agent(
    structured_messages: List[Dict[str, Any]], 
    current_email_id: str, # To avoid including the current email in history
    max_exchanges: int = 5 # Number of user-assistant exchanges to include
) -> str:
    if not structured_messages:
        return "No relevant conversation history found."

    history_texts = []
    # Assuming structured_messages are ordered chronologically (oldest to newest)
    # And that each message has a unique identifier, e.g., a Front message ID if available
    # For now, we'll rely on the order and try to exclude current.
    # A more robust way would be to ensure current email_obj.raw_data has a message_id
    # and filter based on that. get_conversation_text might already exclude current one.

    # Let's assume `get_conversation_text` provides messages *before* the current one
    # or includes it, and we need to filter. For now, this formatting is illustrative.
    # A better approach might be to filter `structured_messages` to exclude the one matching `current_email_id`
    # if `structured_messages` always contains the latest message that triggered the task.
    # The `get_conversation_text` service's `_structured_messages` typically represents the whole conversation.
    
    # Simple formatting:
    relevant_messages = []
    for msg in structured_messages:
        # Heuristic: try to identify and skip the current message based on common patterns or if an ID is available.
        # This is hard without knowing the exact structure of raw_data and how current_email_id relates.
        # For this example, we'll assume structured_messages is the history PRIOR to current email.
        # If it includes current, the agent prompt needs to be aware.

        role = "User"
        if msg.get("type") == "comment" and msg.get("author_role") == "teammate": # Example: an assistant's previous reply via comment
             role = "Assistant"
        elif msg.get("direction") == "outbound": # Example: an assistant's previous reply via message
            role = "Assistant"
        # Crude mapping for user:
        elif msg.get("author_role") == "user" or msg.get("direction") == "inbound":
            role = "User"
        else: # Other types like internal comments might be filtered or labeled differently
            role = msg.get("author_role", "System")


        body = msg.get("body", "").strip()
        if body:
            # Basic sanitization of newlines for prompt clarity
            body_oneline = body.replace('\\n', ' ').replace('\\r', '')
            history_texts.append(f"{role}: {body_oneline}")

    if not history_texts:
        return "No relevant conversation history found."
        
    # Return the last few exchanges
    return "\\n".join(history_texts[- (max_exchanges * 2) :]) # *2 for user+assistant turns 