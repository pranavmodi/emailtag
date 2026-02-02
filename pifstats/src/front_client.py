"""Front API client for fetching conversation data."""

import logging
import re
from typing import Dict, List, Optional, Any

import httpx

from .config import settings

logger = logging.getLogger(__name__)


def get_headers() -> Dict[str, str]:
    """Get headers for Front API requests."""
    return {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a conversation from Front.

    Args:
        conversation_id: The Front conversation ID

    Returns:
        The conversation data or None if not found
    """
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}"

    try:
        with httpx.Client(verify=False, timeout=30.0) as client:
            response = client.get(url, headers=get_headers())
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error getting conversation {conversation_id}: {e.response.status_code}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error getting conversation {conversation_id}: {str(e)}")
        return None


def get_conversation_messages(conversation_id: str) -> List[Dict[str, Any]]:
    """
    Get all messages from a Front conversation.

    Args:
        conversation_id: The Front conversation ID

    Returns:
        List of message dictionaries in chronological order
    """
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/messages"

    try:
        with httpx.Client(verify=False, timeout=30.0) as client:
            response = client.get(url, headers=get_headers())
            response.raise_for_status()
            data = response.json()
            messages = data.get("_results", [])
            # Reverse to get chronological order (Front returns newest first)
            messages.reverse()
            return messages
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error getting messages for {conversation_id}: {e.response.status_code}")
        return []
    except httpx.RequestError as e:
        logger.error(f"Request error getting messages for {conversation_id}: {str(e)}")
        return []


def clean_html(html_content: str) -> str:
    """Remove HTML tags from content."""
    if not html_content:
        return ""
    return re.sub(r'<[^>]*>', '', html_content).strip()


def search_front_conversations(query: str, limit: int = 25) -> List[Dict[str, Any]]:
    """
    Search Front conversations by a free-text query.

    Uses the Front API search endpoint which searches subjects and message bodies.

    Args:
        query: The search query string
        limit: Maximum number of results to return

    Returns:
        List of conversation dicts with id, subject, recipients, created_at
    """
    from urllib.parse import quote

    encoded_query = quote(query)
    url = f"{settings.FRONT_API_BASE_URL}/conversations/search/{encoded_query}"

    try:
        with httpx.Client(verify=False, timeout=30.0) as client:
            response = client.get(url, headers=get_headers())
            response.raise_for_status()
            data = response.json()
            results = data.get("_results", [])

            conversations = []
            for conv in results[:limit]:
                recipients = []
                for recipient in conv.get("recipients", []):
                    handle = recipient.get("handle")
                    if handle:
                        recipients.append(handle)

                conversations.append({
                    "conversation_id": conv.get("id", ""),
                    "subject": conv.get("subject", ""),
                    "recipients": recipients,
                    "created_at": conv.get("created_at"),
                })

            logger.info(f"Front search for '{query}' returned {len(conversations)} conversations")
            return conversations
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error searching Front conversations for '{query}': {e.response.status_code}")
        return []
    except httpx.RequestError as e:
        logger.error(f"Request error searching Front conversations for '{query}': {str(e)}")
        return []


def get_conversation_with_messages(conversation_id: str) -> Dict[str, Any]:
    """
    Get a conversation with all its messages formatted for entity extraction.

    Args:
        conversation_id: The Front conversation ID

    Returns:
        Dictionary containing conversation metadata and formatted message text
    """
    conversation = get_conversation(conversation_id)
    messages = get_conversation_messages(conversation_id)

    if not conversation:
        logger.warning(f"Could not fetch conversation {conversation_id}")
        return {
            "conversation_id": conversation_id,
            "subject": "",
            "messages": [],
            "full_text": "",
            "participants": [],
        }

    # Extract participant emails from conversation
    participants = []
    recipients = conversation.get("recipients", [])
    for recipient in recipients:
        handle = recipient.get("handle")
        if handle:
            participants.append(handle)

    # Process messages
    processed_messages = []
    full_text_parts = []

    for msg in messages:
        raw_body = msg.get("body", "")
        cleaned_body = clean_html(raw_body)

        # Extract sender info - author can be None for some messages
        author = msg.get("author") or {}
        sender_email = author.get("email") or author.get("handle") or "Unknown"
        sender_name = ""
        if author.get("first_name") or author.get("last_name"):
            sender_name = f"{author.get('first_name', '')} {author.get('last_name', '')}".strip()

        # Extract recipients
        to_recipients = []
        cc_recipients = []
        for recipient in msg.get("recipients", []):
            role = recipient.get("role", "")
            handle = recipient.get("handle", "")
            if role == "to" and handle:
                to_recipients.append(handle)
            elif role == "cc" and handle:
                cc_recipients.append(handle)

        processed_msg = {
            "sender_email": sender_email,
            "sender_name": sender_name,
            "to": to_recipients,
            "cc": cc_recipients,
            "subject": msg.get("subject", ""),
            "body": cleaned_body,
            "created_at": msg.get("created_at"),
        }
        processed_messages.append(processed_msg)

        # Build full text for LLM
        text_part = f"From: {sender_email}"
        if sender_name:
            text_part += f" ({sender_name})"
        text_part += f"\nTo: {', '.join(to_recipients) if to_recipients else 'N/A'}"
        if cc_recipients:
            text_part += f"\nCC: {', '.join(cc_recipients)}"
        if msg.get("subject"):
            text_part += f"\nSubject: {msg.get('subject')}"
        text_part += f"\n\n{cleaned_body}\n"
        text_part += "\n" + "-" * 50 + "\n"
        full_text_parts.append(text_part)

    return {
        "conversation_id": conversation_id,
        "subject": conversation.get("subject", ""),
        "messages": processed_messages,
        "full_text": "\n".join(full_text_parts),
        "participants": participants,
    }
