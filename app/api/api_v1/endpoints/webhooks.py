"""Webhook endpoints for FrontApp integration."""

import hashlib
import hmac
import json
import logging
from typing import Any, Dict
import mailparser

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud import email as email_crud
from app.db.session import get_db
from app.schemas.email import EmailCreate, FrontAppWebhook
from app.tasks.email import process_email

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
    
    # Verify webhook signature in production
    if not settings.DEBUG:
        signature = request.headers.get("X-Front-Signature")
        if not signature or not verify_webhook_signature(body, signature):
            logger.warning("Invalid webhook signature")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )
    
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
    if webhook_data.type == "inbound":
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
        # Extract conversation data
        conversation_id = webhook_data.payload.get("conversation", {}).get("id")
        if not conversation_id:
            logger.error("No conversation ID in webhook payload")
            return
        
        # Check if we've already processed this conversation
        existing_email = await email_crud.get_by_front_conversation_id(
            db, front_conversation_id=conversation_id
        )
        if existing_email:
            logger.info(f"Conversation {conversation_id} already processed")
            return
        
        # Extract message data
        message = webhook_data.payload.get("message", {})
        sender = message.get("author", {}).get("email", "unknown@example.com")
        subject = message.get("subject", "")
        
        # Extract recipients
        recipients = []
        for recipient in message.get("recipients", []):
            if "email" in recipient:
                recipients.append(recipient["email"])
        
        # Extract content - both text and HTML
        content_text = message.get("text", "")
        
        # In some FrontApp payloads, HTML might be under 'body' or 'body_html'
        content_html = message.get("body", "") or message.get("body_html", "")
        
        # If we have a raw_email field, try to extract parts using mail-parser
        if "raw_email" in message and message["raw_email"]:
            try:
                email_parts = extract_email_parts(message["raw_email"])
                # Only use parsed parts if the original ones are empty
                if not content_text and email_parts["text"]:
                    content_text = email_parts["text"]
                if not content_html and email_parts["html"]:
                    content_html = email_parts["html"]
            except Exception as e:
                logger.warning(f"Error extracting email parts: {str(e)}")
            
        # Log the content for debugging
        logger.debug(f"Extracted email data - Subject: {subject}, Sender: {sender}")
        logger.debug(f"Text content length: {len(content_text)}, HTML content length: {len(content_html)}")
        
        # Create email record
        email_data = EmailCreate(
            front_conversation_id=conversation_id,
            subject=subject,
            sender=sender,
            recipients=recipients,
            content_text=content_text,
            content_html=content_html,
            raw_data=webhook_data.dict(),
        )
        
        # Save to database
        db_email = await email_crud.create(db, obj_in=email_data)
        
        # Queue processing task
        process_email.delay(str(db_email.id))
        
        logger.info(f"Queued email {db_email.id} for processing")
        
    except Exception as e:
        logger.exception(f"Error processing inbound message: {str(e)}") 