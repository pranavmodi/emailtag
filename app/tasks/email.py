"""Email processing tasks."""

import nest_asyncio # Import nest_asyncio
nest_asyncio.apply() # Apply the patch

import logging
from typing import Dict, List, Any, Optional
from uuid import UUID
from datetime import datetime
import asyncio # Add asyncio import
from contextlib import contextmanager

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
# Topic analysis imports are done dynamically within the function to avoid circular imports
from app.tasks.worker import celery_app
from app.crud import email as email_crud
from app.agents.agent_helpers import extract_all_patient_ids_from_email_logic
from app.models.email import Email # Added for type hinting
from app.schemas.email import EmailUpdate # Added for type hinting
from app.services.archiving_service import check_and_archive_conversation # Import the new archiving service
from app.services.trace_service import create_tracer
from app.models.processing_trace import StepTypes, TraceSteps, TraceStatus

# Conversation log context imports
from app.core.log_context import set_conversation_context, clear_conversation_context, add_delimiter_to_context
from app.services.conversation_log_service import flush_conversation_logs


@contextmanager
def log_context_for_conversation(front_conversation_id: str, email_id: Optional[str] = None):
    """Context manager to capture logs for a conversation.

    Sets up the log context at entry and flushes logs to the database on exit.
    This ensures all logs emitted during task execution are captured and stored.

    Args:
        front_conversation_id: The Front conversation ID.
        email_id: Optional email UUID as string.

    Yields:
        The LogContext instance for the conversation.
    """
    ctx = set_conversation_context(front_conversation_id, email_id)
    try:
        yield ctx
    finally:
        # Clear and flush logs to database
        ctx = clear_conversation_context()
        if ctx:
            flush_conversation_logs(ctx)

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
    front_conversation_id = None
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found in process_email task.")
            return {"status": "error", "message": "Email not found"}

        front_conversation_id = email_obj.front_conversation_id

        # Set up log context for capturing logs to database
        # This must be outside the with block so we can flush on exit
        log_ctx = set_conversation_context(front_conversation_id, email_id)
        add_delimiter_to_context("process_email", email_id)

        # Create tracer for this conversation
        tracer = create_tracer(
            front_conversation_id=front_conversation_id,
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
        # Flush captured logs to database
        ctx = clear_conversation_context()
        if ctx:
            flush_conversation_logs(ctx)
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

        # Set up log context for capturing logs to database
        log_ctx = set_conversation_context(front_conversation_id, email_id)
        add_delimiter_to_context("orchestrate_post_ocr_processing", email_id)

        # Create tracer for this conversation
        tracer = create_tracer(
            front_conversation_id=front_conversation_id,
            email_id=email_id
        )

        tracer.log_step(
            step_name=TraceSteps.ORCHESTRATION_STARTED,
            step_type=StepTypes.BUSINESS_LOGIC,
            status=TraceStatus.COMPLETED,
            input_data={
                "email_id": email_id,
                "front_conversation_id": front_conversation_id,
                "has_attachments": email_obj.has_attachments,
                "current_status": email_obj.status,
            }
        )

        # --- TOPIC SPLIT DETECTION --- (Uses comprehensive tag-based split detection)
        logger.info(f"🔀 TOPIC SPLIT CHECK: Starting split analysis for email {email_id} in conversation {front_conversation_id}")
        is_potential_split = False
        split_analysis_result = None

        try:
            # Import the new split detection functions
            from app.services.topic_analysis_service import (
                detect_topic_change_with_openai,
                filter_to_classification_tags
            )

            # Step 1: Get existing tags on the conversation
            logger.info(f"🔀 TOPIC SPLIT CHECK: Retrieving current tags for conversation {front_conversation_id}")
            existing_tags_objects = get_conversation_tags(front_conversation_id)

            # Extract tag names from tag objects (get_conversation_tags returns dicts, not strings)
            existing_tags = []
            if existing_tags_objects:
                for tag in existing_tags_objects:
                    if isinstance(tag, dict):
                        existing_tags.append(tag.get('name', ''))
                    else:
                        existing_tags.append(str(tag))

            logger.info(f"🔀 TOPIC SPLIT CHECK: Found {len(existing_tags)} tags on conversation: {existing_tags}")

            # Step 2: Filter to only classification tags (exclude system tags)
            classification_tags = filter_to_classification_tags(existing_tags)

            if not classification_tags:
                logger.info(f"🔀 TOPIC SPLIT CHECK: No classification tags found on conversation yet. Skipping split detection - will proceed to normal classification.")
            else:
                current_tag = classification_tags[0]  # Use the first classification tag as the reference
                logger.info(f"🔀 TOPIC SPLIT CHECK: Conversation is tagged as '{current_tag}'. Will check if new message matches this topic.")

                # Step 3: Get full conversation history
                logger.info(f"🔀 TOPIC SPLIT CHECK: Retrieving full conversation history for {front_conversation_id}")
                conversation_data_for_split = get_conversation_text(front_conversation_id)
                structured_messages_for_analysis = conversation_data_for_split.get('_structured_messages', [])

                if not structured_messages_for_analysis:
                    logger.warning(f"🔀 TOPIC SPLIT CHECK: Could not retrieve structured message history. Skipping split check.")
                else:
                    # Get all messages EXCEPT the latest one (which is the new message we're analyzing)
                    history_messages = structured_messages_for_analysis[:-1] if len(structured_messages_for_analysis) > 1 else []

                    logger.info(f"🔀 TOPIC SPLIT CHECK: Analyzing {len(history_messages)} history messages + 1 new message against tag '{current_tag}'")

                    # Prepare history for analysis
                    transformed_history = []
                    for msg in history_messages:
                        transformed_history.append({
                            "sender_type": msg.get("author_role", "user"),
                            "body": msg.get("body", ""),
                            "timestamp": msg.get("created_at", "N/A")
                        })

                    # Prepare new message metadata
                    new_message_metadata = {
                        "sender_type": "User",
                        "timestamp": datetime.utcnow().isoformat()
                    }

                    # Step 4: Call comprehensive AI split detection with full context
                    logger.info(f"🔀 TOPIC SPLIT CHECK: Calling comprehensive AI split detection with full conversation context...")

                    split_analysis_result = detect_topic_change_with_openai(
                        full_conversation_history=transformed_history,
                        current_tag=current_tag,
                        latest_message=email_obj.content_text or "",
                        latest_message_metadata=new_message_metadata,
                        tag_hierarchy=settings.EMAIL_CATEGORIES
                    )

                    # Step 5: Process the AI decision
                    if split_analysis_result.decision == "SPLIT":
                        is_potential_split = True
                        logger.info(f"✅ TOPIC SPLIT DECISION: AI recommends SPLIT (confidence: {split_analysis_result.confidence})")
                        logger.info(f"✅ TOPIC SPLIT DECISION: Rationale: {split_analysis_result.detailed_rationale}")
                        if split_analysis_result.suggested_new_tag:
                            logger.info(f"✅ TOPIC SPLIT DECISION: Suggested new tag: '{split_analysis_result.suggested_new_tag}'")
                    else:
                        logger.info(f"➡️ TOPIC SPLIT DECISION: AI recommends CONTINUE (confidence: {split_analysis_result.confidence})")
                        logger.info(f"➡️ TOPIC SPLIT DECISION: Rationale: {split_analysis_result.detailed_rationale}")
                        is_potential_split = False

        except Exception as e_topic_detect:
            logger.error(f"❌ TOPIC SPLIT ERROR: Error during topic split detection for {front_conversation_id}: {e_topic_detect}", exc_info=True)
            is_potential_split = False

        if is_potential_split:
            try:
                logger.info(f"🔀 SPLIT EXECUTION: Initiating conversation split for email {email_id} from conversation {front_conversation_id}")
                if not settings.FRONT_CHANNEL_PRIMARY_EMAIL:
                    logger.error("❌ SPLIT EXECUTION: FRONT_CHANNEL_PRIMARY_EMAIL setting is not configured. Cannot determine 'to_handle' for split.")
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

                logger.info(f"🔀 SPLIT EXECUTION: Creating new conversation with subject: '{new_conv_subject}'")
                logger.info(f"🔀 SPLIT EXECUTION: Sender: {new_conv_sender_handle}, To: {settings.FRONT_CHANNEL_PRIMARY_EMAIL}, Channel: {target_channel_id_for_new_conv}")

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
                    logger.info(f"✅ SPLIT SUCCESS: Created new Front conversation {new_front_conv_ref} for split message from email {email_id}")

                    # Tag the original conversation with system tag
                    try:
                        logger.info(f"🔀 SPLIT EXECUTION: Tagging original conversation {front_conversation_id} with 'System: Split - New Topic'")
                        add_conversation_tags(front_conversation_id, ["System: Split - New Topic"])
                        logger.info(f"✅ SPLIT SUCCESS: Tagged original conversation {front_conversation_id}")
                    except Exception as tag_err:
                        logger.error(f"❌ SPLIT ERROR: Failed to tag original conversation {front_conversation_id} after split: {tag_err}")

                    # Apply suggested tag to new conversation if valid
                    if split_analysis_result and split_analysis_result.suggested_new_tag:
                        try:
                            from app.services.topic_analysis_service import validate_and_extract_leaf_tag

                            logger.info(f"🏷️ TAG APPLICATION: AI suggested tag '{split_analysis_result.suggested_new_tag}' for new conversation")

                            # Validate and extract the leaf tag
                            validated_tag = validate_and_extract_leaf_tag(
                                split_analysis_result.suggested_new_tag,
                                settings.EMAIL_CATEGORIES
                            )

                            if validated_tag:
                                logger.info(f"🏷️ TAG APPLICATION: Applying validated tag '{validated_tag}' to new conversation {new_front_conv_ref}")
                                add_conversation_tags(new_front_conv_ref, [validated_tag])
                                logger.info(f"✅ TAG SUCCESS: Successfully tagged new conversation {new_front_conv_ref} with '{validated_tag}'")
                            else:
                                logger.warning(f"⚠️ TAG WARNING: Suggested tag '{split_analysis_result.suggested_new_tag}' is not a valid leaf tag. New conversation will be untagged.")

                        except Exception as tag_new_err:
                            logger.error(f"❌ TAG ERROR: Failed to tag new conversation {new_front_conv_ref}: {tag_new_err}", exc_info=True)
                            logger.warning(f"⚠️ TAG WARNING: New conversation {new_front_conv_ref} will remain untagged due to error")
                    else:
                        logger.warning(f"⚠️ TAG WARNING: No suggested tag available for new conversation {new_front_conv_ref}. It will remain untagged.")

                    email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="split_off", is_processed=True))
                    logger.info(f"✅ SPLIT SUCCESS: Marked email {email_id} as 'split_off' and processed. Split operation complete!")
                    return {"status": "success_split", "original_email_id": email_id, "new_conversation_reference": new_front_conv_ref}
                else:
                    if split_response is None:
                        logger.warning(f"⚠️ SPLIT WARNING: Conversation splitting not supported for this channel - continuing with original conversation (email {email_id})")
                    else:
                        logger.error(f"❌ SPLIT ERROR: Failed to create new conversation for split (email {email_id}). API response: {split_response}")
                    # Fall through to regular processing if split failed critically (handled by not returning)

            except Exception as e_split:
                logger.error(f"❌ SPLIT ERROR: Exception during split attempt for email {email_id}: {e_split}", exc_info=True)
                # Fall through to process the email in the original conversation if split fails
        
        # --- END TOPIC SPLIT DETECTION ---

        # --- Check for archiving before proceeding (if not split and split didn't return) ---
        # (Copied and adapted from tag_email)
        try:
            async def _run_archive_check_async():
                return await check_and_archive_conversation(front_conversation_id, email_obj)
            
            was_archived = asyncio.run(_run_archive_check_async())

            tracer.log_step(
                step_name=TraceSteps.ORCHESTRATION_ARCHIVE_RESULT,
                step_type=StepTypes.BUSINESS_LOGIC,
                status=TraceStatus.COMPLETED,
                output_data={
                    "was_archived": was_archived,
                }
            )

            if was_archived:
                logger.info(f"Conversation {front_conversation_id} was archived. Orchestration complete for this path.")
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="archived_in_orchestration", is_processed=True))
                return {"status": "success_archived_orchestration", "email_id": email_id}

        except Exception as e_archive_check:
            logger.error(f"Error during pre-tagging archive check for {front_conversation_id}: {e_archive_check}", exc_info=True)
            tracer.log_step(
                step_name=TraceSteps.ORCHESTRATION_ARCHIVE_RESULT,
                step_type=StepTypes.BUSINESS_LOGIC,
                status=TraceStatus.FAILED,
                error_data={
                    "error_type": type(e_archive_check).__name__,
                    "error_message": str(e_archive_check),
                }
            )
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

        tracer.log_step(
            step_name=TraceSteps.ORCHESTRATION_QUEUED_TAGGING,
            step_type=StepTypes.TASK_QUEUE,
            status=TraceStatus.COMPLETED,
            output_data={
                "email_id": email_id,
                "queue": "tagging",
            }
        )

        return {"status": "queued_for_tagging", "email_id": email_id}

    except Exception as e:
        logger.exception(f"Error in orchestrate_post_ocr_processing for {email_id}: {str(e)}")
        if db.is_active:
            db.rollback()
        # Log the failure as a trace so it's visible in the trace viewer
        try:
            import traceback as tb_module
            failure_tracer = create_tracer(
                front_conversation_id=front_conversation_id if 'front_conversation_id' in locals() else "unknown",
                email_id=email_id
            )
            failure_tracer.log_step(
                step_name=TraceSteps.ORCHESTRATION_FAILED,
                step_type=StepTypes.ERROR_HANDLING,
                status=TraceStatus.FAILED,
                error_data={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": tb_module.format_exc(),
                }
            )
        except Exception:
            logger.error(f"Failed to log orchestration failure trace for {email_id}")
        return {"status": "error", "message": str(e)}
    finally:
        # Flush captured logs to database
        ctx = clear_conversation_context()
        if ctx:
            flush_conversation_logs(ctx)
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

        # Set up log context for capturing logs to database
        log_ctx = set_conversation_context(front_conversation_id, email_id)
        add_delimiter_to_context("perform_tagging_task", email_id)

        # Fetch conversation text for classification (Adapted from tag_email)
        conversation_data = get_conversation_text(front_conversation_id)
        if not conversation_data or 'text' not in conversation_data:
            logger.error(f"Could not retrieve conversation text for {front_conversation_id}. Cannot tag.")
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="tagging_failed_no_content", is_processed=True))
            return {"status": "error", "message": "Failed to get conversation text for tagging"}

        conversation_text = conversation_data.get('text', '')
        raw_senders = conversation_data.get('senders', ['Unknown Sender'])
        raw_timestamps = conversation_data.get('timestamps', ['Unknown Timestamps'])
        raw_recipients_to = conversation_data.get('recipients_to', [])
        raw_recipients_cc = conversation_data.get('recipients_cc', [])
        structured_messages = conversation_data.get('_structured_messages', [])

        # Log structured messages extraction
        if structured_messages:
            logger.info(f"📬 EXTRACTED {len(structured_messages)} structured messages from Front API for {front_conversation_id}")
        else:
            logger.warning(f"⚠️ NO structured messages found for {front_conversation_id} - will use raw text format")

        sender_info = ", ".join(map(str, raw_senders)) if raw_senders else "Unknown Sender"
        message_times = ", ".join(map(str, raw_timestamps)) if raw_timestamps else "Unknown Timestamps"
        recipients_to_info = ", ".join([r for r in raw_recipients_to if r]) if raw_recipients_to else ""
        recipients_cc_info = ", ".join([r for r in raw_recipients_cc if r]) if raw_recipients_cc else ""

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

        # --- OTHER COMPANY LIEN SHORT-CIRCUIT ---
        other_company_name = None
        if document_results:
            for ocr_result in document_results:
                if isinstance(ocr_result, dict):
                    enhanced_lien = ocr_result.get('enhanced_lien_processing') or ocr_result.get('enhanced_lien_processing_split', {})
                    if enhanced_lien.get('other_company_detected'):
                        other_company_name = enhanced_lien.get('detected_company_name', 'Unknown')
                        break

        if other_company_name:
            logger.info(f"⚠️ OTHER COMPANY LIEN DETECTED for email {email_id}: {other_company_name}. Skipping classification.")
            new_tags = ["AI: Human review required"]
            # Add comment to conversation
            try:
                from app.services.frontapp_service import add_conversation_comment
                add_conversation_comment(
                    front_conversation_id,
                    f"This lien appears to belong to another company: {other_company_name}. Please review manually."
                )
            except Exception as e:
                logger.error(f"Failed to add other-company comment for {front_conversation_id}: {e}")
        else:
            # Normal classification flow
            new_tags = classify_email_tags_hierarchical(
                front_conversation_id=front_conversation_id,
                conversation_text=conversation_text,
                sender_info=sender_info,
                message_times=message_times,
                document_analysis_results=document_results,
                recipients_to_info=recipients_to_info,
                recipients_cc_info=recipients_cc_info,
                structured_messages=structured_messages
            )

            # --- MISSING LIEN ATTACHMENT CHECK ---
            # Check if email is classified as lien-related but missing proper lien attachments
            lien_related_tags = ['PSL', 'ASL', 'Rad Lien', 'Tech Lien', 'Lien Modified']
            is_lien_related = any(any(lien_tag.lower() in tag.lower() for lien_tag in lien_related_tags) for tag in new_tags)

            # --- PATIENT DEMO + LIEN MIXED PACKET DETECTION ---
            # If LLM classified as non-lien (e.g. Patient Demo) but OCR found actual lien data,
            # force lien processing so OCR-based override can apply lien tags
            has_patient_demo_in_ocr = False
            if not is_lien_related and email_obj.ocr_results:
                for ocr_result in email_obj.ocr_results:
                    if isinstance(ocr_result, dict):
                        enhanced_lien = ocr_result.get('document_analysis', {}).get('data', {}).get('enhanced_lien_analysis', {})
                        if enhanced_lien.get('LienTypes'):
                            logger.info(f"🔍 MIXED PACKET DETECTED for email {email_id}: LLM classified as {new_tags} "
                                        f"but OCR found lien types {enhanced_lien['LienTypes']}. Forcing lien processing.")
                            is_lien_related = True
                            # Check if patient_demo pages are present
                            if enhanced_lien.get('has_patient_demo') or any(
                                sd.get('page_type') == 'patient_demo'
                                for sd in (ocr_result.get('enhanced_lien_processing', {}).get('split_documents', []) or
                                           ocr_result.get('enhanced_lien_processing_split', {}).get('split_documents', []))
                            ):
                                has_patient_demo_in_ocr = True
                                logger.info(f"🔍 PATIENT DEMO also found in packet for email {email_id}. Will add Patient Demo tag after lien override.")
                            break

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
                            # Also check if enhanced lien analysis found lien types (mixed packets)
                            enhanced_lien = doc_analysis.get('data', {}).get('enhanced_lien_analysis', {})
                            if enhanced_lien.get('LienTypes'):
                                has_lien_attachment = True
                                logger.info(f"🔍 LIEN ATTACHMENT FOUND (via enhanced analysis) for email {email_id}")
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
                            # Add Patient Demo tag if mixed packet (patient demo + lien pages)
                            if has_patient_demo_in_ocr and "Patient Demo" not in new_tags:
                                new_tags.append("Patient Demo")
                                logger.info(f"🔍 MIXED PACKET: Added 'Patient Demo' tag alongside lien tags for email {email_id}")
                            logger.info(f"🔍 ENHANCED LIEN CLASSIFICATION for email {email_id}: {new_tags}")
                            logger.info(f"Applied enhanced lien tags from {len(all_enhanced_lien_data)} documents: lien_types={list(combined_lien_types)}, signature_types={list(combined_signature_types)}")
                        else:
                            logger.warning(f"🔍 ENHANCED LIEN PROCESSING completed but produced no classifiable lien/signature types. "
                                           f"Combined types: lien={list(combined_lien_types)}, signature={list(combined_signature_types)}. "
                                           f"Tagging for human review instead of using LLM tags: {new_tags}")
                            new_tags = ["AI: Human review required"]
                    else:
                        logger.warning(f"🔍 NO ENHANCED LIEN DATA: Email {email_id} is lien-related but enhanced processing data not found in OCR results. "
                                       f"This should not happen if document was classified as lien. Tagging for human review.")
                        new_tags = ["AI: Human review required"]

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

            # --- RX CREDENTIAL SCREENING ---
            # If email is tagged as RX and has OCR results, screen provider credentials
            if "RX" in new_tags and email_obj.ocr_results:
                try:
                    from app.services.credential_screening_service import check_rx_provider_credentials
                    from app.crud.system_settings import system_settings_crud
                    from app.db.session import AsyncSessionLocal

                    async def _run_credential_screening_async():
                        async with AsyncSessionLocal() as async_db:
                            # Check system-level kill switch first
                            screening_enabled = await system_settings_crud.get_setting_value(
                                async_db, "credential_screening_enabled", default=True
                            )
                            if not screening_enabled:
                                logger.info(f"RX credential screening disabled via system setting for email {email_id}")
                                return None

                            return await check_rx_provider_credentials(
                                email_obj.ocr_results, async_db
                            )

                    screening_result = asyncio.run(_run_credential_screening_async())

                    if screening_result and screening_result.get("requires_review"):
                        new_tags.append("credential review")
                        logger.info(
                            f"Applied 'credential review' tag for email {email_id}: "
                            f"disallowed={screening_result.get('disallowed_found', [])}, "
                            f"unknown={screening_result.get('unknown_found', [])}, "
                            f"provider={screening_result.get('provider_info', {}).get('provider_name', 'unknown')}"
                        )
                        # Post comment with credential details
                        try:
                            from app.services.frontapp_service import add_conversation_comment
                            provider_name = screening_result.get("provider_info", {}).get("provider_name", "Unknown")
                            raw_creds = screening_result.get("raw_credentials", [])
                            disallowed = screening_result.get("disallowed_found", [])
                            unknown = screening_result.get("unknown_found", [])
                            cred_display = ", ".join(raw_creds) if raw_creds else "none found"
                            parts = []
                            if disallowed:
                                parts.append(f"Disallowed: {', '.join(disallowed)}")
                            if unknown:
                                parts.append(f"Unknown: {', '.join(unknown)}")
                            screening_detail = "; ".join(parts) if parts else "no allowed credentials found"
                            comment = (
                                f"Credential review required — "
                                f"Provider: {provider_name} ({cred_display}). "
                                f"{screening_detail}. "
                                f"This referral has been held from auto-scheduling."
                            )
                            add_conversation_comment(front_conversation_id, comment)
                        except Exception as comment_err:
                            logger.error(f"Failed to add credential screening comment for {front_conversation_id}: {comment_err}")
                    elif screening_result and screening_result.get("allowed_found"):
                        logger.info(
                            f"RX credential screening passed for email {email_id}: "
                            f"allowed={screening_result.get('allowed_found', [])}"
                        )
                        # Post comment confirming credentials are valid
                        try:
                            from app.services.frontapp_service import add_conversation_comment
                            provider_name = screening_result.get("provider_info", {}).get("provider_name", "Unknown")
                            raw_creds = screening_result.get("raw_credentials", [])
                            allowed = screening_result.get("allowed_found", [])
                            cred_display = ", ".join(raw_creds) if raw_creds else "none found"
                            comment = (
                                f"Credential screening passed — "
                                f"Provider: {provider_name} ({cred_display}). "
                                f"Allowed credentials found: {', '.join(allowed)}."
                            )
                            add_conversation_comment(front_conversation_id, comment)
                        except Exception as comment_err:
                            logger.error(f"Failed to add credential screening comment for {front_conversation_id}: {comment_err}")
                    elif screening_result:
                        logger.info(
                            f"RX credential screening: no credentials extracted for email {email_id} "
                            f"(reason={screening_result.get('reason', 'unknown')})"
                        )

                except Exception as e:
                    logger.error(f"Error during RX credential screening for email {email_id}: {e}", exc_info=True)
                    logger.info(f"Continuing with original tags due to credential screening error: {new_tags}")
            # --- END RX CREDENTIAL SCREENING ---

        applied_tags_to_front = False
        final_tagging_status = "tagging_error_unknown" # Default status for logging if something unexpected happens

        if not new_tags:
            logger.warning(f"Hierarchical classification returned no tags for {front_conversation_id}.")
            final_tagging_status = "tagging_completed_no_tags"
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_tagging_status))
            # No tags to apply to DB or Front in this case. is_processed remains False by default.
        elif "No Tag" in new_tags:
            # Special handling for "No Tag" classification - skip all Front tagging and downstream processing
            logger.info(f"🚫 Email {email_id} classified as 'No Tag' (unrelated/promotional). Skipping Front tagging and downstream processing.")
            final_tagging_status = "no_tag_no_action_needed"
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_tagging_status, is_processed=True))
            # Skip Front tagging, inbox routing, case update checks, and autoresponse for "No Tag" emails
            return {"status": "no_tag_no_action", "email_id": email_id, "classification": "No Tag"}
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

                # Check if Portal Requests tag was applied and add human review tag
                if "Portal Requests" in new_tags:
                    human_review_success = add_conversation_tags(front_conversation_id, ["AI: Human review required"])
                    if human_review_success:
                        logger.info(f"Added human review tag to conversation {front_conversation_id} due to Portal Requests tag")
                    else:
                        logger.warning(f"Failed to add human review tag to conversation {front_conversation_id} for Portal Requests")

                # Check for password-protected PDF attachments and flag for human review
                if document_results:
                    password_protected_files = []
                    for doc_result in document_results:
                        if isinstance(doc_result, dict) and not doc_result.get("document_analysis", {}).get("success"):
                            error_msg = doc_result.get("document_analysis", {}).get("error", "")
                            if error_msg and ('password' in error_msg.lower() or
                                              'incorrect password' in error_msg.lower() or
                                              'encrypted' in error_msg.lower()):
                                password_protected_files.append(doc_result.get("filename", "Unknown"))
                    if password_protected_files:
                        human_review_success = add_conversation_tags(front_conversation_id, ["AI: Human review required"])
                        if human_review_success:
                            logger.info(f"Added human review tag to conversation {front_conversation_id} due to password-protected attachments: {password_protected_files}")
                        else:
                            logger.warning(f"Failed to add human review tag to conversation {front_conversation_id} for password-protected attachments")
                        try:
                            from app.services.frontapp_service import add_conversation_comment
                            filenames_str = ", ".join(password_protected_files)
                            comment = f"Password-protected attachment(s) detected: {filenames_str}. These could not be analyzed. Please review manually."
                            add_conversation_comment(front_conversation_id, comment)
                        except Exception as e:
                            logger.error(f"Failed to add password-protected PDF comment for {front_conversation_id}: {e}")

                # --- INBOX ROUTING LOGIC ---
                if settings.INBOX_ROUTING_ENABLED:
                    from app.services.frontapp_service import move_conversation_to_inbox, get_conversation

                    # Check if this conversation should be excluded from routing (test inbox)
                    TEST_CHANNEL_ID = "cha_fr79u"  # test123abc@mediflow360.com
                    should_skip_routing = False

                    try:
                        conversation_data = get_conversation(front_conversation_id)
                        if conversation_data:
                            # Check if conversation came through test channel
                            last_message = conversation_data.get("last_message", {})
                            message_channel_id = last_message.get("channel", {}).get("id") if isinstance(last_message.get("channel"), dict) else None

                            if message_channel_id == TEST_CHANNEL_ID:
                                should_skip_routing = True
                                logger.info(f"🧪 INBOX ROUTING: Skipping routing for test channel {TEST_CHANNEL_ID} (conversation {front_conversation_id})")
                    except Exception as e:
                        logger.warning(f"⚠️ Could not check conversation channel for routing exclusion: {e}")

                    if not should_skip_routing:
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

                # Check if Portal Requests tag was applied and add human review tag (main tagging failed case)
                if "Portal Requests" in new_tags:
                    human_review_success = add_conversation_tags(front_conversation_id, ["AI: Human review required"])
                    if human_review_success:
                        logger.info(f"Added human review tag to conversation {front_conversation_id} due to Portal Requests tag (main tagging failed)")
                    else:
                        logger.warning(f"Failed to add human review tag to conversation {front_conversation_id} for Portal Requests (main tagging also failed)")

                # Check for password-protected PDF attachments and flag for human review (main tagging failed case)
                if document_results:
                    password_protected_files = []
                    for doc_result in document_results:
                        if isinstance(doc_result, dict) and not doc_result.get("document_analysis", {}).get("success"):
                            error_msg = doc_result.get("document_analysis", {}).get("error", "")
                            if error_msg and ('password' in error_msg.lower() or
                                              'incorrect password' in error_msg.lower() or
                                              'encrypted' in error_msg.lower()):
                                password_protected_files.append(doc_result.get("filename", "Unknown"))
                    if password_protected_files:
                        human_review_success = add_conversation_tags(front_conversation_id, ["AI: Human review required"])
                        if human_review_success:
                            logger.info(f"Added human review tag to conversation {front_conversation_id} due to password-protected attachments (main tagging failed): {password_protected_files}")
                        else:
                            logger.warning(f"Failed to add human review tag to conversation {front_conversation_id} for password-protected attachments (main tagging also failed)")
                        try:
                            from app.services.frontapp_service import add_conversation_comment
                            filenames_str = ", ".join(password_protected_files)
                            comment = f"Password-protected attachment(s) detected: {filenames_str}. These could not be analyzed. Please review manually."
                            add_conversation_comment(front_conversation_id, comment)
                        except Exception as e:
                            logger.error(f"Failed to add password-protected PDF comment for {front_conversation_id}: {e}")

        # --- INBOX ROUTING (for failed main tagging case) ---
        # Attempt inbox routing even if main tag application failed, based on determined tags
        if not applied_tags_to_front and settings.INBOX_ROUTING_ENABLED and new_tags:
            from app.services.frontapp_service import move_conversation_to_inbox, get_conversation

            # Check if this conversation should be excluded from routing (test inbox)
            TEST_CHANNEL_ID = "cha_fr79u"  # test123abc@mediflow360.com
            should_skip_routing = False

            try:
                conversation_data = get_conversation(front_conversation_id)
                if conversation_data:
                    # Check if conversation came through test channel
                    last_message = conversation_data.get("last_message", {})
                    message_channel_id = last_message.get("channel", {}).get("id") if isinstance(last_message.get("channel"), dict) else None

                    if message_channel_id == TEST_CHANNEL_ID:
                        should_skip_routing = True
                        logger.info(f"🧪 INBOX ROUTING (after tag failure): Skipping routing for test channel {TEST_CHANNEL_ID} (conversation {front_conversation_id})")
            except Exception as e:
                logger.warning(f"⚠️ Could not check conversation channel for routing exclusion: {e}")

            if not should_skip_routing:
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

    except RetryableOpenAIError:
        # Let Celery's autoretry handle this — do NOT swallow the exception
        logger.warning(f"RetryableOpenAIError in perform_tagging_task for {email_id} — will be retried by Celery")
        if db.is_active:
            db.rollback()
        raise
    except Exception as e:
        logger.exception(f"Error in perform_tagging_task for {email_id}: {str(e)}")
        if db.is_active:
            db.rollback()
        try:
            email_uuid_for_error = UUID(email_id)
        except:
            pass
        return {"status": "error", "message": str(e)}
    finally:
        # Flush captured logs to database
        ctx = clear_conversation_context()
        if ctx:
            flush_conversation_logs(ctx)
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


@celery_app.task(name="app.tasks.email.eval_single_conversation_task")
def eval_single_conversation_task(conversation_id: str) -> Dict[str, Any]:
    """
    Celery task to evaluate classification for a single conversation.
    Runs classification WITHOUT applying tags and compares with actual tags.

    This is the async/non-blocking version that runs in Celery workers.
    """
    from app.crud.sync import email as email_crud_sync  # Use sync CRUD for Celery tasks
    from app.services.classification_service import classify_email_tags_hierarchical
    from app.services.frontapp_service import get_conversation_text
    from app.db.session import SessionLocal

    logger.info(f"🧪 EVAL TASK: Running classification for conversation {conversation_id}")

    db = SessionLocal()
    try:
        # Get conversation data from Front API
        conversation_data = get_conversation_text(conversation_id)
        if not conversation_data or "error" in conversation_data:
            logger.error(f"Failed to retrieve conversation {conversation_id} for eval")
            return {
                "conversation_id": conversation_id,
                "error": "Failed to retrieve conversation",
                "predicted_tags": [],
                "actual_tags": [],
                "exact_match": False,
                "partial_match": False,
                "accuracy": 0.0
            }

        conversation_text = conversation_data.get("text", "")
        sender_info = conversation_data.get("sender_info", {})
        message_times = conversation_data.get("message_times", {})
        recipients_to_info = conversation_data.get("recipients_to_info", {})
        recipients_cc_info = conversation_data.get("recipients_cc_info", {})
        structured_messages = conversation_data.get("_structured_messages", [])

        # Get email object to retrieve document analysis results and actual tags
        # Use load_tags=True to eagerly load tags
        email = email_crud_sync.get_by_front_conversation_id(
            db, front_conversation_id=conversation_id, load_tags=True
        )
        document_results = None
        if email and hasattr(email, 'ocr_results') and email.ocr_results:
            document_results = email.ocr_results
            logger.info(f"🧪 EVAL: Using {len(document_results)} OCR results for classification")

        # Run classification WITH document analysis (production-like)
        predicted_tags = classify_email_tags_hierarchical(
            front_conversation_id=conversation_id,
            conversation_text=conversation_text,
            sender_info=sender_info,
            message_times=message_times,
            document_analysis_results=document_results,  # ✅ Include document analysis
            recipients_to_info=recipients_to_info,
            recipients_cc_info=recipients_cc_info,
            structured_messages=structured_messages
        )

        # Get actual tags from database (already eagerly loaded)
        actual_tags = []
        if email and email.tags:
            actual_tags = [tag.name for tag in email.tags]

        # Calculate match metrics
        predicted_set = set(predicted_tags)
        actual_set = set(actual_tags)

        exact_match = predicted_set == actual_set
        partial_match = len(predicted_set & actual_set) > 0

        # Calculate accuracy (Jaccard similarity)
        if predicted_set or actual_set:
            intersection = len(predicted_set & actual_set)
            union = len(predicted_set | actual_set)
            accuracy = (intersection / union * 100) if union > 0 else 0
        else:
            accuracy = 100.0 if not predicted_set and not actual_set else 0.0

        result = {
            "conversation_id": conversation_id,
            "predicted_tags": predicted_tags,
            "actual_tags": actual_tags,
            "exact_match": exact_match,
            "partial_match": partial_match,
            "accuracy": round(accuracy, 2),
            "matching_tags": list(predicted_set & actual_set),
            "missing_tags": list(actual_set - predicted_set),
            "extra_tags": list(predicted_set - actual_set)
        }

        logger.info(f"🧪 EVAL COMPLETE: {conversation_id} | Accuracy: {accuracy:.1f}% | Match: {'Exact' if exact_match else 'Partial' if partial_match else 'None'}")
        return result

    except Exception as e:
        logger.error(f"Error evaluating conversation {conversation_id}: {e}", exc_info=True)
        return {
            "conversation_id": conversation_id,
            "error": str(e),
            "predicted_tags": [],
            "actual_tags": [],
            "exact_match": False,
            "partial_match": False,
            "accuracy": 0.0
        }
    finally:
        db.close()


@celery_app.task(name="app.tasks.email.analyze_all_tags_task", bind=True)
def analyze_all_tags_task(self, target_date_str: str, hour: Optional[int] = None) -> Dict[str, Any]:
    """
    Celery task to analyze all tags for a specific date with progress reporting.

    Args:
        self: Bound task instance for progress updates
        target_date_str: Date string in YYYY-MM-DD format
        hour: Optional hour (0-23) to filter by

    Returns:
        Dict with tag statistics
    """
    from datetime import date as date_type
    from app.crud.sync import tag as tag_crud_sync
    from app.services.frontapp_service import get_conversation_tags
    from app.db.session import SessionLocal
    import time

    target_date = date_type.fromisoformat(target_date_str)
    db = SessionLocal()

    try:
        # Update state: Fetching tags from database
        self.update_state(
            state='PROGRESS',
            meta={
                'stage': 'database',
                'message': 'Fetching tags from database...',
                'progress': 0
            }
        )

        # Get all tags and their conversations for this date/hour
        # Note: We need to implement a sync version of get_all_tags_by_date
        from sqlalchemy import select, func
        from app.models.email import Email, Tag, email_tag_association

        query = select(
            Tag.name,
            func.array_agg(Email.front_conversation_id).label('conversation_ids')
        ).select_from(email_tag_association).join(
            Tag, email_tag_association.c.tag_id == Tag.id
        ).join(
            Email, email_tag_association.c.email_id == Email.id
        ).where(
            func.date(Email.created_at) == target_date
        )

        if hour is not None:
            query = query.where(func.extract('hour', Email.created_at) == hour)

        query = query.group_by(Tag.name)

        result = db.execute(query)
        tags_data = result.fetchall()

        if not tags_data:
            return {
                'date': target_date_str,
                'total_conversations': 0,
                'total_tags': 0,
                'tag_statistics': []
            }

        # Build tag to conversations mapping
        tags_dict = {row[0]: row[1] for row in tags_data}

        # Collect all unique conversation IDs
        tag_to_conversations = {}
        all_unique_conv_ids = set()

        for tag_name, conversation_ids in tags_dict.items():
            tag_to_conversations[tag_name] = {
                'conversations_to_check': conversation_ids,
                'total_count': len(conversation_ids)
            }
            all_unique_conv_ids.update(conversation_ids)

        all_unique_conv_ids = list(all_unique_conv_ids)
        total_conversations = len(all_unique_conv_ids)

        # Update state: Starting to fetch from Front
        self.update_state(
            state='PROGRESS',
            meta={
                'stage': 'fetching',
                'message': f'Fetching tags from Front for {total_conversations} conversations...',
                'progress': 0,
                'total': total_conversations,
                'current': 0
            }
        )

        # Fetch current tags from Front for each unique conversation
        conversation_current_tags = {}
        failed_fetches = set()

        for idx, conv_id in enumerate(all_unique_conv_ids, 1):
            try:
                front_tags = get_conversation_tags(conv_id)

                if front_tags is None:
                    logger.warning(f"Could not fetch tags from Front for conversation {conv_id}")
                    conversation_current_tags[conv_id] = []
                    failed_fetches.add(conv_id)
                else:
                    tag_names = [t.get('name', '') for t in front_tags if t.get('name')]
                    conversation_current_tags[conv_id] = tag_names

                # Update progress every 5 conversations or on last one
                if idx % 5 == 0 or idx == total_conversations:
                    progress_pct = int((idx / total_conversations) * 100)
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'stage': 'fetching',
                            'message': f'Fetching conversation {idx}/{total_conversations} ({conv_id[:12]}...)',
                            'progress': progress_pct,
                            'total': total_conversations,
                            'current': idx
                        }
                    )

                # Small delay to avoid rate limits
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Error fetching tags for conversation {conv_id}: {e}")
                conversation_current_tags[conv_id] = []
                failed_fetches.add(conv_id)

        # Update state: Calculating statistics
        self.update_state(
            state='PROGRESS',
            meta={
                'stage': 'calculating',
                'message': 'Calculating statistics for all tags...',
                'progress': 95
            }
        )

        # Calculate statistics for each tag
        tag_statistics = []

        for tag_name, tag_data in tag_to_conversations.items():
            still_tagged_count = 0
            re_tagged_count = 0
            fetch_failed_count = 0

            conversations_to_check = tag_data['conversations_to_check']
            total_for_tag = tag_data['total_count']

            for conv_id in conversations_to_check:
                if conv_id in failed_fetches:
                    fetch_failed_count += 1
                    re_tagged_count += 1
                else:
                    current_tags = conversation_current_tags.get(conv_id, [])
                    if tag_name in current_tags:
                        still_tagged_count += 1
                    else:
                        re_tagged_count += 1

            still_tagged_pct = (still_tagged_count / total_for_tag * 100) if total_for_tag > 0 else 0.0
            re_tagged_pct = (re_tagged_count / total_for_tag * 100) if total_for_tag > 0 else 0.0

            tag_statistics.append({
                'tag_name': tag_name,
                'total_conversations': total_for_tag,
                'still_tagged': still_tagged_count,
                're_tagged': re_tagged_count,
                'fetch_failed': fetch_failed_count,
                'still_tagged_percentage': round(still_tagged_pct, 2),
                're_tagged_percentage': round(re_tagged_pct, 2)
            })

        # Sort by total conversations descending
        tag_statistics.sort(key=lambda x: x['total_conversations'], reverse=True)

        return {
            'date': target_date_str,
            'total_conversations': total_conversations,
            'total_tags': len(tag_statistics),
            'tag_statistics': tag_statistics
        }

    finally:
        db.close() 