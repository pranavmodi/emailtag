"""Service for interacting with OpenAI API."""

import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

async def are_questions_resolved_openai(conversation_text: str) -> bool:
    """
    Uses OpenAI to analyze conversation text and determine if all user questions have been addressed.

    Args:
        conversation_text: The full text of the conversation.
        # Potentially add messages_with_senders: List[Dict[str,str]] if more structure is needed

    Returns:
        bool: True if OpenAI determines all questions are resolved, False otherwise or on error.
    """
    if not settings.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not configured. Cannot analyze conversation.")
        return False

    if not conversation_text.strip():
        logger.warning("Conversation text is empty. Assuming no questions to resolve or cannot analyze.")
        return False # Or True, depending on desired behavior for empty conversations

    # More sophisticated prompt engineering might be needed here.
    # Consider providing message structure (who said what) if available.
    prompt = (
        f"Analyze the following email conversation to determine if all questions asked by the user/customer "
        f"have been adequately addressed by an agent or bot. "
        f"Respond with only 'RESOLVED' if all questions appear to be addressed, or 'UNRESOLVED' if there are pending questions or issues. "
        f"Do not add any explanation, just the single word response.\n\n"
        f"Conversation:\n{conversation_text[:15000]} # Truncate to avoid exceeding token limits, adjust as needed"
    )

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o", # Or your preferred model like gpt-3.5-turbo
        "messages": [
            {"role": "system", "content": "You are an AI assistant that analyzes email conversations. Your task is to determine if customer questions have been resolved. Respond with only RESOLVED or UNRESOLVED."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 10, # Expecting a short response (RESOLVED/UNRESOLVED)
        "temperature": 0.0, # For deterministic output
    }

    try:
        # IMPORTANT: Disabling SSL verification is a security risk and should only be done
        # in controlled development environments.
        # For production, ensure your system's CA certificates are up-to-date
        # or provide a specific CA bundle path to httpx.AsyncClient(verify=...).
        # You might also investigate using the 'certifi' package.
        async with httpx.AsyncClient(timeout=60.0, verify=False) as client: # Increased timeout & disabled SSL verify
            logger.info("Sending conversation to OpenAI for resolution analysis...")
            response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            
            completion = response.json()
            ai_response_text = completion.get('choices', [{}])[0].get('message', {}).get('content', '').strip().upper()
            logger.info(f"OpenAI response for resolution analysis: {ai_response_text}")

            if ai_response_text == "RESOLVED":
                return True
            elif ai_response_text == "UNRESOLVED":
                return False
            else:
                logger.warning(f"OpenAI returned an unexpected response: {ai_response_text}. Assuming unresolved.")
                return False

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling OpenAI: {e.response.status_code} - {e.response.text}", exc_info=True)
        return False
    except httpx.RequestError as e:
        logger.error(f"Request error calling OpenAI: {str(e)}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error during OpenAI call: {str(e)}", exc_info=True)
        return False 