"""Webhook endpoints for FrontApp integration."""

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, List
from uuid import UUID
import asyncio
import httpx
import random
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud import email as email_crud
from app.crud import patient_conversation_data as pcd_crud
from app.crud.system_settings import system_settings_crud
from app.db.session import get_db
from app.schemas.email import EmailCreate, FrontAppWebhook, PreprocessingWebhook, EmailUpdate, Email, FrontOutboundMessageWebhook
from app.schemas.patient_conversation_data import PatientConversationDataCreate
from app.tasks.email import process_email, process_email_rx
from app.tasks.pif_extraction import extract_pif_from_conversation
from app.services.patient import fetch_patient_by_id
from app.helpers.patient_extraction import extract_and_log_patient_info
from app.services.trace_service import create_tracer, TraceLogger
from app.models.processing_trace import StepTypes, TraceSteps, TraceStatus
from app.services.frontapp_service import get_conversation_async, get_conversation_text

logger = logging.getLogger(__name__)

router = APIRouter()


class ProcessEmailRxRequest(BaseModel):
    template_name: str
    user_id: str


def verify_webhook_signature(
    request_body: bytes, signature: str = Header(None, alias="X-Front-Signature")
) -> bool:
    """
    Verify the webhook signature from FrontApp.
    
    Args:
        request_body: The raw request body
        signature: The signature from the X-Front-Signature header
        
    Returns:
        bool: True if signature is valid, False otherwise
    """
    if not signature:
        return False
    
    # Calculate expected signature
    expected_signature = hmac.new(
        settings.FRONTAPP_WEBHOOK_SECRET.encode(),
        request_body,
        hashlib.sha1
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)





@router.post("/frontapp", status_code=status.HTTP_202_ACCEPTED)
async def frontapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Webhook endpoint for FrontApp events.
    
    Args:
        request: The FastAPI request object
        db: Database session
        
    Returns:
        Dict[str, Any]: Response indicating the webhook was received
    """
    # Initialize tracer - we'll get the conversation ID after parsing
    tracer = None
    
    # Get the raw request body
    body = await request.body()
    
    try:
        # Parse the webhook payload first to get conversation ID for tracing
        payload = json.loads(body)
        webhook_data = FrontAppWebhook(**payload)
        
        # Now we can create a tracer with the conversation ID
        conversation_id = webhook_data.conversation.get("id") if webhook_data.conversation else "unknown"
        tracer = create_tracer(front_conversation_id=conversation_id)
        
        # Log webhook received
        tracer.log_step(
            step_name=TraceSteps.WEBHOOK_RECEIVED,
            step_type=StepTypes.ENTRY_POINT,
            status=TraceStatus.COMPLETED,
            input_data={
                "webhook_type": webhook_data.type,
                "conversation_id": conversation_id,
                "payload_size": len(body),
                "source_ip": request.client.host if request.client else "unknown"
            },
            output_data={
                "payload_parsed": True,
                "event_type": webhook_data.type
            }
        )
        
    except Exception as e:
        # Log parsing failure if we have a tracer
        if tracer:
            tracer.log_step(
                step_name=TraceSteps.WEBHOOK_PARSED,
                step_type=StepTypes.VALIDATION,
                status=TraceStatus.FAILED,
                error_data={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "payload_size": len(body)
                }
            )
        
        logger.error(f"Error parsing webhook payload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload format",
        )
    
    # Verify webhook signature in production (traced)
    # if not settings.DEBUG:
    #     signature = request.headers.get("X-Front-Signature")
    #     if not signature or not verify_webhook_signature(body, signature):
    #         tracer.log_step(
    #             step_name=TraceSteps.WEBHOOK_VALIDATED,
    #             step_type=StepTypes.VALIDATION,
    #             status=TraceStatus.FAILED,
    #             error_data={"error_message": "Invalid webhook signature"}
    #         )
    #         logger.warning("Invalid webhook signature")
    #         raise HTTPException(
    #             status_code=status.HTTP_401_UNAUTHORIZED,
    #             detail="Invalid signature",
    #         )
    
    # Process based on event type
    if webhook_data.type in ["inbound", "custom"]:
        tracer.log_step(
            step_name=TraceSteps.WEBHOOK_VALIDATED,
            step_type=StepTypes.VALIDATION,
            status=TraceStatus.COMPLETED,
            output_data={"event_type": webhook_data.type, "processing": True}
        )
        await process_inbound_message(db, webhook_data, tracer)
    else:
        tracer.log_step(
            step_name=TraceSteps.WEBHOOK_VALIDATED,
            step_type=StepTypes.VALIDATION,
            status=TraceStatus.SKIPPED,
            output_data={"event_type": webhook_data.type, "processing": False, "reason": "ignored_event_type"}
        )
        logger.info(f"Ignoring webhook event of type: {webhook_data.type}")
    
    return {"status": "accepted"}


async def process_inbound_message(db: AsyncSession, webhook_data: FrontAppWebhook, tracer: TraceLogger) -> None:
    """
    Process an inbound message from FrontApp.
    
    Args:
        db: Database session
        webhook_data: The webhook data from FrontApp
        tracer: Trace logger for this conversation
    """
    try:
        # Log message processing start
        with tracer.trace_step(
            step_name=TraceSteps.CONTENT_EXTRACTED,
            step_type=StepTypes.EXTRACTION,
            input_data={"message_id": webhook_data.id}
        ) as (trace_id, output_data):
            
            # Extract conversation data
            conversation_id = webhook_data.conversation.get("id")
            if not conversation_id:
                logger.warning("No conversation ID found in webhook data")
                output_data["error"] = "No conversation ID found"
                return
            
            output_data["conversation_id"] = conversation_id
        
        # Extract message data and attachments from target.data
        message = webhook_data.target.get("data", {})
        attachments = message.get("attachments", [])

        # Use the actual message author email/handle as sender for autorespond detection
        author = message.get("author") or {}
        sender = (
            author.get("email")
            or author.get("handle")
            or webhook_data.conversation.get("recipient", {}).get("handle", "unknown@example.com")
        )
        
        # Extract subject
        message_subject = message.get("subject")
        conversation_subject = webhook_data.conversation.get("subject", "")
        subject = message_subject or conversation_subject
        
        # Check if this is an autoresponse email and skip processing
        def is_autoresponse_email(content_text: str, content_body: str, sender_email: str) -> bool:
            """Detect if this is an autoresponse email that should be skipped."""
            content_to_check = f"{content_text} {content_body}"

            # Primary detection: Check for invisible marker and skip regardless of sender
            invisible_marker = settings.AUTORESPOND_INVISIBLE_MARKER
            if invisible_marker and invisible_marker in content_to_check:
                logger.info(f"🔍 Invisible marker detected in content for sender {sender_email} - treating as autorespond")
                return True

            # Fallback detection: Check for text signature (if configured)
            autoresponse_signature = settings.AUTORESPONSE_SIGNATURE
            if autoresponse_signature and autoresponse_signature in content_to_check:
                logger.info(f"🔍 Text signature detected - this is an autorespond email")
                return True

            return False
        
        # Extract recipients (to/cc) for recordkeeping
        recipients = []
        for recipient in message.get("recipients", []):
            # handle might be ID or email, prefer email if exists
            handle = recipient.get("handle", "")
            email = recipient.get("email", "")
            if email:
                recipients.append(email)
            elif "@" in handle:
                recipients.append(handle)
        
        # Extract content from the correct FrontApp fields
        # Different message types may have content in different fields
        content_body = message.get("body", "")
        content_text = message.get("text", "")
        content_html = message.get("html", "")
        
        # Log message type for debugging different content structures
        message_type = message.get("type", "unknown")
        is_inbound = message.get("is_inbound", "unknown")
        # logger.info(f"MESSAGE TYPE DEBUG - type: {message_type}, is_inbound: {is_inbound}")
        # logger.info(f"MESSAGE TYPE DEBUG - text field length: {len(content_text)}, body field length: {len(content_body)}")
        
        # Use the field that actually has content
        if content_text:
            final_content_text = content_text
        else:
            final_content_text = content_body
            
        if content_html:
            final_content_html = content_html
        else:
            final_content_html = content_body
        
        # Check for autoresponse - RE-ENABLED with invisible marker + sender domain detection
        with tracer.trace_step(
            step_name=TraceSteps.AUTORESPONSE_CHECK,
            step_type=StepTypes.BUSINESS_LOGIC,
            input_data={"sender": sender, "content_length": len(final_content_text)}
        ) as (trace_id, output_data):
            is_autoresponse = is_autoresponse_email(final_content_text, content_body, sender)
            output_data["is_autoresponse"] = is_autoresponse

            if is_autoresponse:
                logger.info(f"🤖 AUTORESPONSE DETECTED: Skipping email from {sender}")
                output_data["action"] = "skipped"
                return
            else:
                logger.info(f"✅ Processing email from {sender} (not autoresponse)")
                output_data["action"] = "processing"

        # Check for internal domain filtering
        with tracer.trace_step(
            step_name="INTERNAL_DOMAIN_CHECK",
            step_type=StepTypes.BUSINESS_LOGIC,
            input_data={"sender": sender}
        ) as (trace_id, output_data):
            # Check if internal domain filtering is enabled
            skip_internal_domains = await system_settings_crud.get_setting_value(db, "skip_internal_domains", default=False)
            output_data["skip_internal_domains_enabled"] = skip_internal_domains

            if skip_internal_domains:
                # Define internal domains to filter
                internal_domains = ["@precisemri.com", "@mediflow.com"]
                sender_lower = sender.lower()

                is_internal = any(domain in sender_lower for domain in internal_domains)
                output_data["is_internal_domain"] = is_internal

                if is_internal:
                    logger.info(f"🏢 INTERNAL DOMAIN DETECTED: Skipping email from {sender} (internal domain filtering enabled)")
                    output_data["action"] = "skipped"
                    output_data["reason"] = "internal_domain_filtered"
                    return
                else:
                    logger.info(f"✅ External email from {sender} (not internal domain)")
                    output_data["action"] = "processing"
            else:
                logger.info(f"ℹ️ Internal domain filtering DISABLED - processing email from {sender}")
                output_data["action"] = "processing"
                output_data["reason"] = "filtering_disabled"

        # Create email record
        with tracer.trace_step(
            step_name=TraceSteps.EMAIL_CREATED,
            step_type=StepTypes.DATABASE,
            input_data={
                "sender": sender,
                "subject": subject,
                "has_attachments": bool(attachments),
                "recipients_count": len(recipients)
            }
        ) as (trace_id, output_data):
            email_create = EmailCreate(
                front_message_id=webhook_data.id,
                front_conversation_id=conversation_id,
                sender=sender,
                recipients=recipients,
                subject=subject,
                content_text=final_content_text,
                content_html=final_content_html,
                has_attachments=bool(attachments),
                raw_data=webhook_data.model_dump()
            )
            
            db_email = await email_crud.create(db=db, obj_in=email_create)
            output_data["email_id"] = str(db_email.id)
            output_data["created_successfully"] = True
        
        # Log the entire conversation thread
        try:
            conversation_thread_string = await email_crud.get_conversation_content(db, front_conversation_id=conversation_id)
            # logger.info(f"Current conversation thread for {conversation_id}:\n{conversation_thread_string}")
        except Exception as e_conv_log:
            logger.error(f"Error logging conversation thread for {conversation_id}: {str(e_conv_log)}")

        # Extract and process patient IDs using the helper function (now with subject support)
        await extract_and_log_patient_info(db, final_content_text, conversation_id, db_email.id, logger, subject)

        # Check if email processing is enabled before queuing
        with tracer.trace_step(
            step_name=TraceSteps.PROCESSING_CHECK,
            step_type=StepTypes.VALIDATION,
            input_data={"email_id": str(db_email.id)}
        ) as (trace_id, output_data):
            processing_enabled = await system_settings_crud.is_email_processing_enabled(db)
            output_data["processing_enabled"] = processing_enabled

            if not processing_enabled:
                # Update email status to processing_disabled
                await email_crud.update(
                    db=db,
                    db_obj=db_email,
                    obj_in={"status": "processing_disabled"}
                )
                output_data["action"] = "disabled"
                output_data["email_status"] = "processing_disabled"
                logger.warning(
                    f"⏸️  Email processing is DISABLED. Email {db_email.id} saved but NOT queued for processing."
                )
                return

        # Queue email for processing (only if processing is enabled)
        with tracer.trace_step(
            step_name=TraceSteps.TASK_QUEUED,
            step_type=StepTypes.TASK_QUEUE,
            input_data={
                "email_id": str(db_email.id),
                "queue": "emails",
                "task": "process_email"
            }
        ) as (trace_id, output_data):
            process_email.apply_async(args=[str(db_email.id)], queue='emails')
            output_data["queued_successfully"] = True
            output_data["queue_name"] = "emails"

        # Queue PIF (Personal Injury Firm) extraction task
        # This runs in parallel with email processing to extract firm contact info
        try:
            extract_pif_from_conversation.apply_async(
                args=[conversation_id],
                queue='processing'
            )
            logger.info(f"Queued PIF extraction for conversation {conversation_id}")
        except Exception as pif_error:
            # Don't fail the webhook if PIF extraction queueing fails
            logger.warning(f"Failed to queue PIF extraction for {conversation_id}: {pif_error}")

    except Exception as e:
        logger.exception(f"Error processing inbound message: {str(e)}")


@router.post("/preprocessing", status_code=status.HTTP_202_ACCEPTED)
async def preprocessing_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Webhook endpoint for preprocessing service outputs.
    
    Args:
        request: The FastAPI request object
        db: Database session
        
    Returns:
        Dict[str, Any]: Response indicating the webhook was received
    """
    # Get the raw request body
    body = await request.body()
    
    # Verify webhook signature in production
    if not settings.DEBUG:
        signature = request.headers.get("X-Preprocessing-Signature")
        if not signature or not verify_webhook_signature(body, signature):
            logger.warning("Invalid preprocessing webhook signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )
    
    # Parse the webhook payload
    try:
        payload = json.loads(body)
        webhook_data = PreprocessingWebhook(**payload)
    except Exception as e:
        logger.error(f"Error parsing preprocessing webhook payload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload format",
        )
    
    try:
        # Get the email from database
        email = await email_crud.get(db, id=webhook_data.email_id)
        if not email:
            logger.error(f"Email {webhook_data.email_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Email not found",
            )
        
        # Update email with preprocessing results in raw_data
        update_data = {
            "raw_data": {
                **email.raw_data,
                "preprocessing": {
                    "ocr_text": webhook_data.ocr_text,
                    "cleaned_text": webhook_data.cleaned_text,
                    "cleaned_html": webhook_data.cleaned_html,
                    "extracted_entities": webhook_data.extracted_entities,
                    "confidence_score": webhook_data.confidence_score,
                    "processing_status": webhook_data.processing_status,
                    "error_message": webhook_data.error_message,
                }
            }
        }
        
        await email_crud.update(db, db_obj=email, obj_in=update_data)
        
        # If preprocessing was successful, queue the email for AI tagging
        if webhook_data.processing_status == "success":
            process_email.delay(str(email.id))
            logger.info(f"Queued email {email.id} for AI tagging after preprocessing")
        
        return {"status": "accepted", "email_id": str(email.id)}
        
    except Exception as e:
        logger.exception(f"Error processing preprocessing webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error processing webhook",
        )


# The /ocr webhook endpoint has been removed as OCR processing is now handled synchronously within the Celery task.

# --- Dummy OCR Endpoint for Testing (REMOVED) --- 
# The dummy OCR endpoint is no longer needed as the synchronous OCR flow is implemented directly in the task. 

@router.post("/frontapp/outbound", status_code=status.HTTP_202_ACCEPTED)
async def frontapp_outbound_webhook(
    request: Request,
    # db: AsyncSession = Depends(get_db) # Database not strictly needed for just logging yet
) -> Dict[str, Any]:
    """
    Webhook endpoint for outbound messages from FrontApp.
    For now, it just logs the request details.
    """
    logger.info("Received FrontApp outbound webhook request.")

    # Log headers
    headers = dict(request.headers)
    logger.info(f"Outbound Webhook Headers: {json.dumps(headers, indent=2)}")

    # Get the raw request body
    body = await request.body()
    
    # Attempt to parse and log the payload using the generic schema
    try:
        payload_dict = json.loads(body.decode())
        # Validate with Pydantic model - this will capture all fields due to extra = "allow"
        webhook_data = FrontOutboundMessageWebhook(**payload_dict) 
        logger.info(f"Parsed Outbound Webhook Payload: {webhook_data.model_dump_json(indent=2)}")
        
        # You can add more specific logging here if you identify key fields, e.n.
        # event_type = payload_dict.get("type")
        # if event_type:
        #     logger.info(f"Outbound event type: {event_type}")

    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from outbound webhook: {str(e)}")
        logger.info(f"Raw Outbound Webhook Body (on JSON error): {body.decode()}")
        # Still return 202, as we don't want Front to retry endlessly for a logging endpoint
    except Exception as e:
        logger.error(f"Error processing outbound webhook payload: {str(e)}", exc_info=True)
        logger.info(f"Raw Outbound Webhook Body (on general error): {body.decode()}")
        # Still return 202

    return {"status": "outbound_payload_logged"}


@router.post("/processemail", status_code=status.HTTP_202_ACCEPTED)
async def process_email_rx_webhook(payload: ProcessEmailRxRequest) -> Dict[str, Any]:
    """Queue placeholder RX email processing."""
    logger.info(
        "✅ Processing RX email webhook for user_id=%s template_name=%s",
        payload.user_id,
        payload.template_name,
    )
    task = process_email_rx.apply_async(
        args=[payload.template_name, payload.user_id],
        queue="processing",
    )
    logger.info(
        "📨 Queued process_email_rx task %s on processing queue for user_id=%s template_name=%s",
        task.id,
        payload.user_id,
        payload.template_name,
    )
    return {
        "status": "queued",
        "task_id": task.id,
        "template_name": payload.template_name,
        "user_id": payload.user_id,
    }


@router.post("/reprocess/{conversation_id}", status_code=status.HTTP_202_ACCEPTED)
async def reprocess_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Manually trigger processing for a conversation by ID.

    Fetches the conversation from Front API and processes it as if it were
    a new inbound message from the webhook.

    Args:
        conversation_id: The Front conversation ID to reprocess
        db: Database session

    Returns:
        Dict[str, Any]: Response with email_id and status
    """
    logger.info(f"Reprocess request received for conversation: {conversation_id}")

    # Create tracer for this reprocess request
    tracer = create_tracer(front_conversation_id=conversation_id)

    try:
        # Step 1: Fetch conversation data from Front API
        with tracer.trace_step(
            step_name="FETCH_CONVERSATION",
            step_type=StepTypes.API_CALL,
            input_data={"conversation_id": conversation_id}
        ) as (trace_id, output_data):
            conversation_data = await get_conversation_async(conversation_id)

            if not conversation_data:
                output_data["error"] = "Conversation not found in Front"
                logger.warning(f"Conversation {conversation_id} not found in Front API")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Conversation {conversation_id} not found in Front"
                )

            output_data["conversation_found"] = True
            output_data["subject"] = conversation_data.get("subject", "")

        # Step 2: Fetch conversation messages (synchronous function, run in executor)
        with tracer.trace_step(
            step_name="FETCH_MESSAGES",
            step_type=StepTypes.API_CALL,
            input_data={"conversation_id": conversation_id}
        ) as (trace_id, output_data):
            loop = asyncio.get_event_loop()
            conversation_text_data = await loop.run_in_executor(
                None, get_conversation_text, conversation_id
            )

            output_data["messages_fetched"] = True
            output_data["message_count"] = len(conversation_text_data.get("_structured_messages", []))

        # Step 3: Extract relevant data for email record
        structured_messages = conversation_text_data.get("_structured_messages", [])

        if not structured_messages:
            logger.warning(f"No messages found in conversation {conversation_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No messages found in conversation {conversation_id}"
            )

        # Get the latest message
        latest_message = structured_messages[-1] if structured_messages else {}

        # Extract sender from latest message or conversation data
        sender = (
            latest_message.get("author_email")
            or latest_message.get("author_handle")
            or conversation_data.get("recipient", {}).get("handle", "unknown@reprocess.local")
        )

        # Extract subject
        subject = conversation_data.get("subject", "")

        # Extract content from latest message
        content_text = latest_message.get("body", "")
        content_html = latest_message.get("body", "")  # Front stores HTML in body

        # Get full conversation text for context
        full_text = conversation_text_data.get("text", "")
        if full_text:
            content_text = full_text

        # Extract recipients
        recipients = []
        last_msg_details = conversation_text_data.get("last_message_details", {})
        if last_msg_details:
            recipients_to = last_msg_details.get("recipients_to", [])
            recipients_cc = last_msg_details.get("recipients_cc", [])
            if isinstance(recipients_to, list):
                recipients.extend(recipients_to)
            if isinstance(recipients_cc, list):
                recipients.extend(recipients_cc)

        # Step 4: Create email record
        with tracer.trace_step(
            step_name=TraceSteps.EMAIL_CREATED,
            step_type=StepTypes.DATABASE,
            input_data={
                "sender": sender,
                "subject": subject,
                "source": "reprocess_endpoint"
            }
        ) as (trace_id, output_data):
            email_create = EmailCreate(
                front_message_id=f"reprocess_{conversation_id}_{int(asyncio.get_event_loop().time())}",
                front_conversation_id=conversation_id,
                sender=sender,
                recipients=recipients,
                subject=subject,
                content_text=content_text,
                content_html=content_html,
                has_attachments=False,  # We don't have attachment info from this flow
                raw_data={
                    "source": "reprocess_endpoint",
                    "conversation_data": conversation_data,
                    "latest_message": latest_message,
                }
            )

            db_email = await email_crud.create(db=db, obj_in=email_create)
            output_data["email_id"] = str(db_email.id)
            output_data["created_successfully"] = True

        # Step 5: Extract patient info
        await extract_and_log_patient_info(db, content_text, conversation_id, db_email.id, logger, subject)

        # Step 6: Check if processing is enabled and queue
        with tracer.trace_step(
            step_name=TraceSteps.PROCESSING_CHECK,
            step_type=StepTypes.VALIDATION,
            input_data={"email_id": str(db_email.id)}
        ) as (trace_id, output_data):
            processing_enabled = await system_settings_crud.is_email_processing_enabled(db)
            output_data["processing_enabled"] = processing_enabled

            if not processing_enabled:
                await email_crud.update(
                    db=db,
                    db_obj=db_email,
                    obj_in={"status": "processing_disabled"}
                )
                output_data["action"] = "disabled"
                logger.warning(f"Email processing is DISABLED. Email {db_email.id} saved but NOT queued.")
                return {
                    "status": "created_but_not_queued",
                    "email_id": str(db_email.id),
                    "conversation_id": conversation_id,
                    "reason": "processing_disabled"
                }

        # Step 7: Queue for processing
        with tracer.trace_step(
            step_name=TraceSteps.TASK_QUEUED,
            step_type=StepTypes.TASK_QUEUE,
            input_data={"email_id": str(db_email.id), "queue": "emails"}
        ) as (trace_id, output_data):
            process_email.apply_async(args=[str(db_email.id)], queue='emails')
            output_data["queued_successfully"] = True

        logger.info(f"Successfully queued conversation {conversation_id} for reprocessing as email {db_email.id}")

        return {
            "status": "queued",
            "email_id": str(db_email.id),
            "conversation_id": conversation_id,
            "sender": sender,
            "subject": subject
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error reprocessing conversation {conversation_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error reprocessing conversation: {str(e)}"
        )
