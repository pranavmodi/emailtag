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
from app.crud.sync import processing_trace as trace_crud_sync
from app.db.session import SessionLocal
from app.db.session import AsyncSessionLocal # Add AsyncSessionLocal import
from app.services.classification_service import classify_email_tags_hierarchical, remove_conflicting_tags
from app.services.frontapp_service import add_conversation_tags, get_conversation_text, get_conversation_tags, remove_conversation_tags, create_new_conversation_for_split, send_conversation_reply # Added send_conversation_reply
from app.services.autorespond_service import process_autorespond  # Add this import
from app.services.topic_analysis_service import is_new_unresolved_topic_present # Added topic analysis service
from app.tasks.worker import celery_app
from app.crud import email as email_crud
from app.agents.agent_helpers import extract_all_patient_ids_from_email_logic
from app.models.email import Email # Added for type hinting
from app.schemas.email import EmailUpdate # Added for type hinting
from app.services.archiving_service import check_and_archive_conversation # Import the new archiving service
from app.services.trace_service import create_tracer
from app.models.processing_trace import StepTypes, TraceSteps, TraceStatus

# Import document processing task from separate module
from app.tasks.document_processing import send_attachment_to_document_processing

# Import autorespond task from separate module
from app.tasks.autorespond import perform_autorespond_task

# --------------------
# Retry helper
# --------------------
from app.exceptions import RetryableOpenAIError
from celery import Task


class TaggingTaskWithRetry(Task):
    """Celery Task base that automatically retries on transient OpenAI failures.

    After exhausting all retries, the email is marked for human review and tagged accordingly.
    """

    autoretry_for = (RetryableOpenAIError,)
    retry_backoff = True            # Exponential back-off (2s, 4s, 8s …)
    retry_backoff_max = 3600        # Cap delay at 1 hour
    retry_jitter = True             # Add jitter to avoid thundering herd
    max_retries = 5                 # After 5 attempts, fall through to on_failure

    def on_failure(self, exc, task_id, args, kwargs, einfo):  # noqa: D401 – short description style
        """Fallback executed once all retries are exhausted."""
        if isinstance(exc, RetryableOpenAIError):
            try:
                email_id = args[0] if args else kwargs.get("email_id")
                if email_id:
                    from app.db.session import SessionLocal  # Local import to avoid circular refs
                    from uuid import UUID
                    db = SessionLocal()
                    try:
                        email_obj = email_crud_sync.get(db, id=UUID(email_id))
                        if email_obj:
                            # Mark email for human review
                            email_crud_sync.update(
                                db,
                                db_obj=email_obj,
                                obj_in=EmailUpdate(
                                    status="tagging_failed_openai_unavailable",
                                    is_processed=True,
                                ),
                            )

                            # Attempt to tag conversation on Front for visibility
                            front_conv_id = email_obj.front_conversation_id
                            if front_conv_id:
                                try:
                                    add_conversation_tags(front_conv_id, ["AI: Human review required"])
                                except Exception as tag_exc:
                                    logger.error(
                                        f"Failed to add human-review tag to conversation {front_conv_id}: {tag_exc}",
                                        exc_info=True,
                                    )
                    finally:
                        if db.is_active:
                            db.close()
            except Exception as final_exc:
                logger.error(
                    f"Error while executing on_failure fallback for email: {final_exc}",
                    exc_info=True,
                )

        # Call base implementation to ensure default behaviour (e.g. logging, signals)
        super().on_failure(exc, task_id, args, kwargs, einfo)

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
    tracer = None
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found in process_email task.")
            return {"status": "error", "message": "Email not found"}
        
        # Create tracer for this conversation
        tracer = create_tracer(
            front_conversation_id=email_obj.front_conversation_id,
            email_id=email_id
        )

        # Check OCR requirements
        with tracer.trace_step(
            step_name=TraceSteps.OCR_REQUIREMENTS_CHECK,
            step_type=StepTypes.BUSINESS_LOGIC,
            input_data={
                "has_attachments": email_obj.has_attachments,
                "current_status": email_obj.status,
                "email_id": email_id
            }
        ) as (trace_id, output_data):
            needs_ocr = False
            if email_obj.has_attachments and email_obj.status not in ["ocr_completed", "ocr_completed_with_errors", "ocr_error", "ocr_skipped", "pending_ocr"]:
                needs_ocr = True
            
            output_data["needs_ocr"] = needs_ocr
            output_data["reason"] = "has_attachments_and_not_processed" if needs_ocr else "no_attachments_or_already_processed"


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
                    # send_attachment_to_ocr.delay(email_id, attachment_url)
                    send_attachment_to_document_processing.apply_async(args=[email_id, attachment_url], queue='processing')
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
            
            # Queue for orchestration
            with tracer.trace_step(
                step_name=TraceSteps.TASK_QUEUED,
                step_type=StepTypes.TASK_QUEUE,
                input_data={
                    "email_id": email_id,
                    "queue": "processing", 
                    "task": "orchestrate_post_ocr_processing"
                }
            ) as (trace_id, output_data):
                orchestrate_post_ocr_processing.apply_async(args=[email_id], queue='processing')
                output_data["queued_successfully"] = True
                output_data["next_step"] = "orchestrate_post_ocr_processing"
            
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

        # Create tracer for this conversation
        tracer = create_tracer(
            front_conversation_id=front_conversation_id,
            email_id=email_id
        )

        # --- TOPIC SPLIT DETECTION --- (Copied and adapted from tag_email)
        is_potential_split = False
        try:
            conversation_data_for_split = get_conversation_text(front_conversation_id)
            structured_messages_for_analysis = conversation_data_for_split.get('_structured_messages', [])

            if not structured_messages_for_analysis:
                logger.warning(f"Could not retrieve structured message history for {front_conversation_id} to attempt topic split. Proceeding without split check.")
            elif len(structured_messages_for_analysis) <= 1:
                pass  # No split check needed
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
                    if split_response is None:
                        logger.info(f"Conversation splitting not supported for this channel - continuing with original conversation (email {email_id})")
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
            async def _run_archive_check_async():
                return await check_and_archive_conversation(front_conversation_id, email_obj)
            
            was_archived = asyncio.run(_run_archive_check_async())

            if was_archived:
                logger.info(f"Conversation {front_conversation_id} was archived. Orchestration complete for this path.")
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="archived_in_orchestration", is_processed=True))
                return {"status": "success_archived_orchestration", "email_id": email_id}
                
        except Exception as e_archive_check:
            logger.error(f"Error during pre-tagging archive check for {front_conversation_id}: {e_archive_check}", exc_info=True)
            # Proceed with tagging if archive check fails

        # --- PATIENT ID EXTRACTION --- (NEW: Before Classification)
        # Extract patient IDs from full conversation content and store them for downstream use
        try:
            # logger.info(f"🔍 EARLY_PATIENT_ID_EXTRACTION: Starting patient ID extraction for email {email_id}")
            
            # Get full conversation content for extraction (same as archive analysis)
            conversation_data = get_conversation_text(front_conversation_id)
            if conversation_data and isinstance(conversation_data, dict):
                conversation_content = conversation_data.get('text', '')
            else:
                # Fallback to individual email content if conversation text unavailable
                conversation_content = email_obj.content_text or ""
            
            email_subject = email_obj.subject or ""
            
            # logger.info(f"🔍 EARLY_PATIENT_ID_EXTRACTION: Using conversation content ({len(conversation_content)} chars) for extraction")
            
            async def _run_patient_id_extraction_async():
                return await extract_all_patient_ids_from_email_logic(
                    email_content=conversation_content,
                    conversation_id=front_conversation_id,
                    subject=email_subject
                )
            
            with tracer.trace_step(
                step_name=TraceSteps.PATIENT_ID_EXTRACTION,
                step_type=StepTypes.AI_PROCESSING,
                input_data={
                    "email_content_length": len(conversation_content),
                    "has_subject": bool(email_subject),
                    "subject": email_subject,
                    "front_conversation_id": front_conversation_id
                }
            ) as (trace_id, output_data):
                extracted_patient_ids = asyncio.run(_run_patient_id_extraction_async())
                output_data["extracted_patient_ids"] = extracted_patient_ids
                output_data["patient_ids_count"] = len(extracted_patient_ids) if extracted_patient_ids else 0
            
            # Store extracted patient IDs in database
            if extracted_patient_ids:
                logger.info(f"🔍 EARLY_PATIENT_ID_EXTRACTION: Found patient IDs: {extracted_patient_ids}")
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(extracted_patient_ids=extracted_patient_ids))
                # logger.info(f"🔍 EARLY_PATIENT_ID_EXTRACTION: Stored patient IDs in database for email {email_id}")
            # else:
                # logger.info(f"🔍 EARLY_PATIENT_ID_EXTRACTION: No patient IDs found for email {email_id}")
                
        except Exception as e_patient_extraction:
            logger.error(f"Error during patient ID extraction for email {email_id}: {e_patient_extraction}", exc_info=True)
            # Continue with processing even if patient ID extraction fails
        
        # --- END PATIENT ID EXTRACTION ---

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


@celery_app.task(
    bind=True,
    base=TaggingTaskWithRetry,
    name="app.tasks.email.perform_tagging_task",
)
def perform_tagging_task(self, email_id: str) -> Dict:
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
        # Include document processing results if available
        document_results = email_obj.ocr_results if hasattr(email_obj, 'ocr_results') and email_obj.ocr_results else None
        new_tags = classify_email_tags_hierarchical(
            front_conversation_id=front_conversation_id,
            conversation_text=conversation_text,
            sender_info=sender_info,
            message_times=message_times,
            document_analysis_results=document_results
        )

        # --- MISSING LIEN ATTACHMENT CHECK ---
        # Check if email is classified as lien-related but missing proper lien attachments
        lien_related_tags = ['PSL', 'ASL', 'Rad Lien', 'Tech Lien', 'Lien Modified']
        is_lien_related = any(any(lien_tag.lower() in tag.lower() for lien_tag in lien_related_tags) for tag in new_tags)
        
        if is_lien_related and not any("Missing Lien Request" in str(tag) for tag in new_tags):
            logger.info(f"Email {email_id} is classified as lien-related. Checking attachment status.")
            
            # Check if email has attachments and if they contain lien documents
            has_lien_attachment = False
            
            if email_obj.has_attachments and email_obj.ocr_results:
                for ocr_result in email_obj.ocr_results:
                    if isinstance(ocr_result, dict):
                        # Check if document analysis succeeded and is a lien document
                        doc_analysis = ocr_result.get('document_analysis', {})
                        if (doc_analysis.get('success') and 
                            doc_analysis.get('data', {}).get('document_type') == 'lien'):
                            has_lien_attachment = True
                            logger.info(f"🔍 LIEN ATTACHMENT FOUND for email {email_id}")
                            break
            
            if not has_lien_attachment:
                logger.info(f"🔍 MISSING LIEN ATTACHMENT: Email {email_id} is lien-related but has no proper lien attachments. Classifying as 'Missing Lien Request'")
                new_tags = ["Missing Lien Request"]
        
        # Store original tags before OCR override for lien modification detection
        original_classification_tags = new_tags.copy() if new_tags else []
        
        # --- OCR-BASED LIEN CLASSIFICATION OVERRIDE ---
        # Check if email has OCR results and is classified under Accounts Receivable -> Liens
        # Only process if we haven't already classified as Missing Lien Request
        if (email_obj.ocr_results and 
            new_tags and 
            is_lien_related and
            not any("Missing Lien Request" in str(tag) for tag in new_tags)):
            
            logger.info(f"Email {email_id} has OCR results and is classified under Liens. Checking for OCR-based override.")
            
            try:
                # Check ALL OCR results for enhanced lien processing data and combine them
                all_enhanced_lien_data = []
                combined_lien_types = set()
                combined_signature_types = set()
                primary_patient_id = None
                
                for ocr_result in email_obj.ocr_results:
                    if isinstance(ocr_result, dict):
                        # Check for enhanced lien processing results
                        if ocr_result.get('document_analysis', {}).get('data', {}).get('enhanced_lien_analysis'):
                            enhanced_data = ocr_result['document_analysis']['data']['enhanced_lien_analysis']
                            all_enhanced_lien_data.append(enhanced_data)
                            logger.info(f"🔍 ENHANCED LIEN DATA FOUND for email {email_id}: {enhanced_data}")
                            
                            # Collect lien types from this document
                            if "LienTypes" in enhanced_data:
                                # New format with multiple lien types
                                for lien_type in enhanced_data["LienTypes"]:
                                    combined_lien_types.add(lien_type.upper())
                            elif enhanced_data.get("LienType"):
                                # Legacy format compatibility
                                combined_lien_types.add(enhanced_data["LienType"].upper())
                            
                            # Collect signature types from this document
                            signature_type = enhanced_data.get("LienSignatureType", "")
                            if signature_type in ["PSL", "ASL"]:
                                combined_signature_types.add(signature_type)
                            
                            # Use first document's patient ID as primary
                            if not primary_patient_id and enhanced_data.get("PatientID"):
                                primary_patient_id = enhanced_data["PatientID"]
                
                if all_enhanced_lien_data:
                    # Use combined enhanced lien processing data for classification
                    logger.info(f"🔍 COMBINING DATA: Found {len(all_enhanced_lien_data)} enhanced lien documents")
                    logger.info(f"🔍 Combined lien types: {list(combined_lien_types)}")
                    logger.info(f"🔍 Combined signature types: {list(combined_signature_types)}")
                    
                    determined_tags = []
                    
                    # Add signature type (PSL/ASL) - prefer ASL if both found
                    if "ASL" in combined_signature_types:
                        determined_tags.append("ASL")
                        logger.info(f"🔍 SIGNATURE TYPE DETECTED: ASL (attorney signature found)")
                    elif "PSL" in combined_signature_types:
                        determined_tags.append("PSL")
                        logger.info(f"🔍 SIGNATURE TYPE DETECTED: PSL (patient signature found)")
                    
                    # Add ALL lien types found across all documents
                    for lien_type in combined_lien_types:
                        if lien_type in ['RAD', 'RADIOLOGY']:
                            determined_tags.append('Rad Lien')
                            logger.info(f"🔍 LIEN TYPE DETECTED: Rad Lien")
                        elif lien_type in ['TECH', 'TC', 'TECHNOLOGIST']:
                            determined_tags.append('Tech Lien')
                            logger.info(f"🔍 LIEN TYPE DETECTED: Tech Lien")
                    
                    if determined_tags:
                        new_tags = determined_tags
                        logger.info(f"🔍 ENHANCED LIEN CLASSIFICATION for email {email_id}: {new_tags}")
                        logger.info(f"Applied enhanced lien tags from {len(all_enhanced_lien_data)} documents: lien_types={list(combined_lien_types)}, signature_types={list(combined_signature_types)}")
                    else:
                        logger.warning(f"🔍 ENHANCED LIEN PROCESSING completed but produced no classifiable results. Combined types: lien={list(combined_lien_types)}, signature={list(combined_signature_types)}. Keeping LLM tags: {new_tags}")
                else:
                    logger.warning(f"🔍 NO ENHANCED LIEN DATA: Email {email_id} is lien-related but enhanced processing data not found in OCR results. This should not happen if document was classified as lien. Keeping LLM tags: {new_tags}")
                    
            except Exception as e:
                logger.error(f"Error during enhanced lien type check for email {email_id}: {e}", exc_info=True)
                logger.info(f"Continuing with LLM tags due to lien analysis error: {new_tags}")
        # --- END OCR-BASED LIEN CLASSIFICATION OVERRIDE ---

        # --- LIEN MODIFICATION DETECTION ---
        # Check for lien modifications in attachments after initial classification
        lien_modifications_detected = False
        lien_modification_results = []
        
        if email_obj.has_attachments and new_tags:
            from app.services.lien_modification_service import should_check_lien_modifications, check_lien_modifications
            
            if should_check_lien_modifications(new_tags):
                logger.info(f"Email {email_id} has lien-related tags and attachments. Checking for modifications.")
                
                try:
                    # Extract attachments data from raw_data
                    attachments_data = []
                    if email_obj.raw_data and isinstance(email_obj.raw_data, dict):
                        target_data = email_obj.raw_data.get('target', {}).get('data', {})
                        attachments_data = target_data.get('attachments', [])
                    
                    if attachments_data:
                        async def _run_lien_modification_check_async():
                            nonlocal lien_modifications_detected, lien_modification_results
                            lien_modifications_detected, lien_modification_results = await check_lien_modifications(
                                email_tags=new_tags,
                                attachments_data=attachments_data
                            )
                        
                        asyncio.run(_run_lien_modification_check_async())
                        
                        # Update database with lien modification detection results
                        lien_update_payload = EmailUpdate(
                            lien_modification_checked=True,
                            lien_modifications_detected=lien_modifications_detected,
                            lien_modification_results=lien_modification_results
                        )
                        email_crud_sync.update(db, db_obj=email_obj, obj_in=lien_update_payload)
                        logger.info(f"Updated email {email_id} with lien modification detection results")
                        
                        if lien_modifications_detected:
                            logger.info(f"🔍 LIEN MODIFICATIONS DETECTED for email {email_id}! Adding 'Lien Modified' while preserving existing lien tags.")

                            # Preserve lien signature (PSL/ASL) and lien type (Rad/Tech) from
                            # either the OCR-override tags (current new_tags) OR the original
                            # classification, then add "Lien Modified".
                            lien_modified_tags = []

                            signature_candidates = new_tags + original_classification_tags
                            if any(tag == "PSL" for tag in signature_candidates):
                                lien_modified_tags.append("PSL")
                            elif any(tag == "ASL" for tag in signature_candidates):
                                lien_modified_tags.append("ASL")

                            lien_type_candidates = new_tags + original_classification_tags
                            # Support both Tech and Rad lien types (remove elif to allow both)
                            if any(tag == "Rad Lien" for tag in lien_type_candidates):
                                lien_modified_tags.append("Rad Lien")
                            if any(tag == "Tech Lien" for tag in lien_type_candidates):
                                lien_modified_tags.append("Tech Lien")

                            # Always add Lien Modified
                            lien_modified_tags.append("Lien Modified")

                            # Remove duplicates while preserving order
                            new_tags = list(dict.fromkeys(lien_modified_tags))
                            logger.info(f"Applied comprehensive lien modification tags for email {email_id}: {new_tags}")
                            logger.info(f"Original classification: {original_classification_tags}, OCR/current preserved types: {[t for t in new_tags if t in ['Rad Lien', 'Tech Lien']]}, Final: {new_tags}")
                        else:
                            logger.info(f"No lien modifications detected for email {email_id}. Keeping original tags: {new_tags}")
                    else:
                        logger.warning(f"Email {email_id} marked as having attachments but no attachment data found for lien modification check.")
                
                except Exception as e:
                    logger.error(f"Error during lien modification detection for email {email_id}: {e}", exc_info=True)
                    # Continue with original tags if modification detection fails
                    logger.info(f"Continuing with original tags due to modification detection error: {new_tags}")
        # --- END LIEN MODIFICATION DETECTION ---

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
                applied_tags_to_front = True
                final_tagging_status = "tagging_completed_applied_tags"
                # Update status; is_processed defaults to False, allowing subsequent tasks in the chain.
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_tagging_status))
                
                # Check if any case update tags were applied and add human review tag
                case_update_tags = {
                    "New Attorney", "Drop Letter", "Drop Pending", "Promise to send payment",
                    "Waiting to clear liability", "Waiting on settlement check", 
                    "Sent payment but not received", "Refund Request", "Payment on way"
                }
                
                has_case_update_tag = any(tag in case_update_tags for tag in new_tags)
                if has_case_update_tag:
                    human_review_success = add_conversation_tags(front_conversation_id, ["AI: Human review required"])
                    if human_review_success:
                        logger.info(f"Added human review tag to conversation {front_conversation_id} due to case update tags: {[tag for tag in new_tags if tag in case_update_tags]}")
                    else:
                        logger.warning(f"Failed to add human review tag to conversation {front_conversation_id} for case update tags")
                else:
                    logger.debug(f"No case update tags found in {new_tags} for conversation {front_conversation_id}")
                
                # --- INBOX ROUTING LOGIC ---
                if settings.INBOX_ROUTING_ENABLED:
                    from app.services.frontapp_service import move_conversation_to_inbox
                    
                    tag_to_inbox_mapping = settings.TAG_TO_INBOX_MAPPING
                    target_inbox_id = None
                    matched_tag = None
                    
                    # Find the first tag that matches our mapping (priority order matters)
                    for tag in new_tags:
                        if tag in tag_to_inbox_mapping:
                            target_inbox_id = tag_to_inbox_mapping[tag]
                            matched_tag = tag
                            break
                    
                    if target_inbox_id:
                        logger.info(f"📬 INBOX ROUTING: Moving conversation {front_conversation_id} to inbox {target_inbox_id} based on tag '{matched_tag}'")
                        move_success = move_conversation_to_inbox(front_conversation_id, target_inbox_id)
                        if move_success:
                            logger.info(f"✅ Successfully moved conversation {front_conversation_id} to inbox {target_inbox_id}")
                        else:
                            logger.warning(f"❌ Failed to move conversation {front_conversation_id} to inbox {target_inbox_id}")
                    else:
                        logger.debug(f"📬 INBOX ROUTING: No inbox mapping found for tags {new_tags}")
                else:
                    logger.debug(f"📬 INBOX ROUTING: Disabled (INBOX_ROUTING_ENABLED=False)")
                # --- END INBOX ROUTING LOGIC ---
            else:
                logger.error(f"Failed to apply tags {new_tags} to conversation {front_conversation_id} on Front.")
                applied_tags_to_front = False 
                final_tagging_status = "tagging_completed_front_failed" 
                # Update status to reflect Front failure; mark as 'is_processed=True' for this tagging stage
                # to prevent retries of perform_tagging_task for Front API issues,
                # but auto-response will still proceed based on local DB tags.
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_tagging_status, is_processed=True))
                
                # Even if main tag application failed, still try to add human review tag for case updates
                case_update_tags = {
                    "New Attorney", "Drop Letter", "Drop Pending", "Promise to send payment",
                    "Waiting to clear liability", "Waiting on settlement check", 
                    "Sent payment but not received", "Refund Request", "Payment on way"
                }
                
                has_case_update_tag = any(tag in case_update_tags for tag in new_tags)
                if has_case_update_tag:
                    human_review_success = add_conversation_tags(front_conversation_id, ["AI: Human review required"])
                    if human_review_success:
                        logger.info(f"Added human review tag to conversation {front_conversation_id} due to case update tags (main tagging failed): {[tag for tag in new_tags if tag in case_update_tags]}")
                    else:
                        logger.warning(f"Failed to add human review tag to conversation {front_conversation_id} for case update tags (main tagging also failed)")
        
        # --- INBOX ROUTING (for failed main tagging case) ---
        # Attempt inbox routing even if main tag application failed, based on determined tags
        if not applied_tags_to_front and settings.INBOX_ROUTING_ENABLED and new_tags:
            from app.services.frontapp_service import move_conversation_to_inbox
            
            tag_to_inbox_mapping = settings.TAG_TO_INBOX_MAPPING
            target_inbox_id = None
            matched_tag = None
            
            # Find the first tag that matches our mapping
            for tag in new_tags:
                if tag in tag_to_inbox_mapping:
                    target_inbox_id = tag_to_inbox_mapping[tag]
                    matched_tag = tag
                    break
            
            if target_inbox_id:
                logger.info(f"📬 INBOX ROUTING (after tag failure): Moving conversation {front_conversation_id} to inbox {target_inbox_id} based on determined tag '{matched_tag}'")
                move_success = move_conversation_to_inbox(front_conversation_id, target_inbox_id)
                if move_success:
                    logger.info(f"✅ Successfully moved conversation {front_conversation_id} to inbox {target_inbox_id} (despite tag application failure)")
                else:
                    logger.warning(f"❌ Failed to move conversation {front_conversation_id} to inbox {target_inbox_id} (tag application also failed)")
            else:
                logger.debug(f"📬 INBOX ROUTING (after tag failure): No inbox mapping found for determined tags {new_tags}")
        # --- END INBOX ROUTING (for failed main tagging case) ---
        
        # Regardless of tagging outcome (unless critical error above), proceed to auto-response.
        perform_autorespond_task.apply_async(args=[email_id], kwargs={'determined_tags': new_tags}, queue='processing')
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