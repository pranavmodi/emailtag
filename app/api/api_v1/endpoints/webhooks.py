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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud import email as email_crud
from app.crud import patient_conversation_data as pcd_crud
from app.db.session import get_db
from app.schemas.email import EmailCreate, FrontAppWebhook, PreprocessingWebhook, EmailUpdate, Email, FrontOutboundMessageWebhook
from app.schemas.patient_conversation_data import PatientConversationDataCreate
from app.tasks.email import process_email, send_attachment_to_ocr
from app.services.patient import fetch_patient_by_id
from app.helpers.patient_extraction import extract_and_log_patient_info

logger = logging.getLogger(__name__)

router = APIRouter()


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


def extract_email_parts(raw_email: str) -> Dict[str, str]:
    """
    Extract parts from a raw email using mail-parser.
    
    Args:
        raw_email: Raw email content
        
    Returns:
        Dict[str, str]: Dictionary containing text and html parts
    """
    try:
        parsed_mail = mailparser.parse_from_string(raw_email)
        return {
            "text": parsed_mail.body,
            "html": parsed_mail.body_html or ""
        }
    except Exception as e:
        logger.error(f"Error parsing raw email: {str(e)}")
        return {"text": "", "html": ""}


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
    # Get the raw request body
    body = await request.body()
    # logger.info(f"Received raw FrontApp webhook request: {body.decode()}")
    logger.info(f"Received raw FrontApp webhook request")

    
    # Verify webhook signature in production
    # if not settings.DEBUG:
    #     signature = request.headers.get("X-Front-Signature")
    #     if not signature or not verify_webhook_signature(body, signature):
    #         logger.warning("Invalid webhook signature")
    #         raise HTTPException(
    #             status_code=status.HTTP_401_UNAUTHORIZED,
    #             detail="Invalid signature",
    #         )
    
    # Parse the webhook payload
    try:
        payload = json.loads(body)
        webhook_data = FrontAppWebhook(**payload)
    except Exception as e:
        logger.error(f"Error parsing webhook payload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload format",
        )
    
    # Process based on event type
    if webhook_data.type in ["inbound", "custom"]:
        await process_inbound_message(db, webhook_data)
    else:
        logger.info(f"Ignoring webhook event of type: {webhook_data.type}")
    
    return {"status": "accepted"}


async def process_inbound_message(db: AsyncSession, webhook_data: FrontAppWebhook) -> None:
    """
    Process an inbound message from FrontApp.
    
    Args:
        db: Database session
        webhook_data: The webhook data from FrontApp
    """
    try:
        logger.info(f"Processing inbound message: {webhook_data.id}")
        # Extract conversation data
        conversation_id = webhook_data.conversation.get("id")
        if not conversation_id:
            logger.warning("No conversation ID found in webhook data")
            return
        
        # Extract message data and attachments from target.data
        message = webhook_data.target.get("data", {})
        attachments = message.get("attachments", [])
        sender = webhook_data.conversation.get("recipient", {}).get("handle", "unknown@example.com")
        subject = message.get("subject") or webhook_data.conversation.get("subject", "")
        
        # Extract recipients
        recipients = []
        for recipient in message.get("recipients", []):
            # handle might be ID or email, prefer email if exists
            handle = recipient.get("handle", "")
            if "@" in handle: 
                recipients.append(handle)
            elif recipient.get("email"): # Check if email field exists
                recipients.append(recipient["email"])
        
        # Extract content
        content_text = message.get("text", "")
        content_html = message.get("html", "")
        
        # Create email record with raw webhook data
        email_create = EmailCreate(
            front_message_id=webhook_data.id,
            front_conversation_id=conversation_id,
            sender=sender,
            recipients=recipients,
            subject=subject,
            content_text=content_text,
            content_html=content_html,
            has_attachments=bool(attachments),
            raw_data=webhook_data.model_dump()  # Include the complete webhook data
        )
        
        db_email = await email_crud.create(db=db, obj_in=email_create)
        logger.info(f"Created email record with ID: {db_email.id}")
        
        # Log the entire conversation thread
        try:
            conversation_thread_string = await email_crud.get_conversation_content(db, front_conversation_id=conversation_id)
            logger.info(f"Current conversation thread for {conversation_id}:\n{conversation_thread_string}")
        except Exception as e_conv_log:
            logger.error(f"Error logging conversation thread for {conversation_id}: {str(e_conv_log)}")

        # Extract and process patient IDs using the helper function
        await extract_and_log_patient_info(db, content_text, conversation_id, db_email.id, logger)

        # If attachments exist, queue OCR tasks, otherwise queue standard processing
        if attachments:
            logger.info(f"Email {db_email.id} has {len(attachments)} attachments. Queuing for OCR.")
            for attachment in attachments:
                # Assuming attachment object has a 'url' key
                attachment_url = attachment.get("url")
                if attachment_url:
                    send_attachment_to_ocr.delay(str(db_email.id), attachment_url)
                else:
                    logger.warning(f"Attachment for email {db_email.id} is missing a URL. Skipping OCR.")
                    # Optionally, decrement ocr_attachments_total here or handle differently
        else:
            # Queue standard processing task if no attachments
            process_email.delay(str(db_email.id))
            logger.info(f"Queued email {db_email.id} for standard processing (no attachments)")
        
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