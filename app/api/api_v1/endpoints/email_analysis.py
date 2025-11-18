"""Email analysis endpoints for debugging and testing."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.frontapp_service import get_conversation_text
from app.services.openai_service import extract_email_chain_openai

logger = logging.getLogger(__name__)

router = APIRouter()


class EmailChainExtractionRequest(BaseModel):
    """Request model for email chain extraction."""
    conversation_id: str


class EmailChainExtractionResponse(BaseModel):
    """Response model for email chain extraction."""
    success: bool
    conversation_id: str
    emails: list
    total_emails: int
    parsing_notes: str
    openai_prompt: str | None = None
    error: str | None = None


@router.post("/extract-email-chain", response_model=EmailChainExtractionResponse)
async def extract_email_chain(
    request: EmailChainExtractionRequest,
) -> Dict[str, Any]:
    """
    Extract individual emails from a conversation thread.

    This endpoint fetches a conversation from FrontApp and uses OpenAI
    to parse it into structured individual emails in chronological order.

    Args:
        request: Contains the Front conversation ID

    Returns:
        Structured email chain with individual emails extracted

    Raises:
        HTTPException: If conversation not found or extraction fails
    """
    try:
        # Fetch conversation text from FrontApp
        logger.info(f"Fetching conversation text for {request.conversation_id}")
        conversation_data = get_conversation_text(request.conversation_id)

        if not conversation_data or not isinstance(conversation_data, dict):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {request.conversation_id} not found or invalid"
            )

        conversation_text = conversation_data.get('text', '')
        if not conversation_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Conversation {request.conversation_id} has no text content"
            )

        # Log conversation metadata
        text_length = len(conversation_text)
        logger.info(f"📧 Conversation {request.conversation_id}: text_length={text_length} chars")

        # Log sender/recipient info if available
        senders = conversation_data.get('senders', [])
        recipients_to = conversation_data.get('recipients_to', [])
        recipients_cc = conversation_data.get('recipients_cc', [])
        logger.info(f"📧 Conversation metadata: senders={len(senders)}, recipients_to={len(recipients_to)}, recipients_cc={len(recipients_cc)}")

        # Extract email chain using OpenAI
        logger.info(f"🔍 Starting email chain extraction for {request.conversation_id}")
        extraction_result = await extract_email_chain_openai(conversation_text)

        # Log extraction results
        if extraction_result.get("success"):
            total_emails = extraction_result.get("total_emails", 0)
            emails = extraction_result.get("emails", [])
            logger.info(f"✅ Extraction successful: {total_emails} emails extracted from {request.conversation_id}")

            # Log summary of each extracted email
            for i, email in enumerate(emails, 1):
                sender = email.get('sender', 'unknown')
                subject = email.get('subject', 'no subject')
                is_forwarded = email.get('is_forwarded_message', False)
                forwarded_tag = " [FORWARDED]" if is_forwarded else ""
                logger.info(f"  📨 Email {i}/{total_emails}: From={sender}, Subject='{subject}'{forwarded_tag}")

            if extraction_result.get("parsing_notes"):
                logger.info(f"📝 Parsing notes: {extraction_result.get('parsing_notes')}")
        else:
            error = extraction_result.get("error", "Unknown error")
            logger.error(f"❌ Extraction failed for {request.conversation_id}: {error}")

        # Build response
        response = {
            "success": extraction_result.get("success", False),
            "conversation_id": request.conversation_id,
            "emails": extraction_result.get("emails", []),
            "total_emails": extraction_result.get("total_emails", 0),
            "parsing_notes": extraction_result.get("parsing_notes", ""),
            "openai_prompt": extraction_result.get("openai_prompt", None),
            "error": extraction_result.get("error", None)
        }

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting email chain for {request.conversation_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract email chain: {str(e)}"
        )
