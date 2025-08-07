"""Service for archiving conversations."""

import logging
from app.core.config import settings
from app.services.frontapp_service import get_conversation_text, archive_conversation_in_front
from app.services.openai_service import are_questions_resolved_openai # Import OpenAI service

logger = logging.getLogger(__name__)

async def check_and_archive_conversation(front_conversation_id: str) -> bool:
    """
    Checks if a conversation can be archived and archives it if all questions are resolved.

    Args:
        front_conversation_id: The Front conversation ID.

    Returns:
        bool: True if the conversation was archived, False otherwise.
    """
    logger.info(f"Checking if conversation {front_conversation_id} can be archived.")

    conversation_data = get_conversation_text(front_conversation_id)
    if not conversation_data or not isinstance(conversation_data, dict):
        logger.error(f"Failed to get conversation data for {front_conversation_id} in archiving check.")
        return False

    conversation_text = conversation_data.get('text', '')
    # Consider passing more structured data like `conversation_data.get('senders')` 
    # or the raw messages if `are_questions_resolved_openai` is adapted for it.

    if not conversation_text.strip():
        logger.info(f"Conversation text for {front_conversation_id} is empty. Skipping OpenAI analysis, not archiving.")
        return False

    logger.info(f"Sending conversation {front_conversation_id} to OpenAI for resolution analysis.")
    analysis_result = await are_questions_resolved_openai(conversation_text)
    logger.info(f"OpenAI analysis for {front_conversation_id} completed. Result: {analysis_result}")

    # Handle structured response
    if not analysis_result.get("success", False):
        logger.error(f"OpenAI analysis failed for {front_conversation_id}: {analysis_result.get('summary', 'Unknown error')}")
        return False

    all_questions_resolved = analysis_result.get("resolved", False)
    unresolved_questions = analysis_result.get("unresolved_questions", [])
    analysis_summary = analysis_result.get("summary", "No summary provided")
    
    logger.info(f"OpenAI analysis summary for {front_conversation_id}: {analysis_summary}")
    if unresolved_questions:
        logger.info(f"Unresolved questions found for {front_conversation_id}: {unresolved_questions}")

    if all_questions_resolved:
        try:
            logger.info(f"Attempting to archive conversation {front_conversation_id} as all questions appear resolved.")
            success = archive_conversation_in_front(front_conversation_id)
            if success:
                logger.info(f"Successfully archived conversation {front_conversation_id}.")
                return True
            else:
                logger.error(f"Failed to archive conversation {front_conversation_id} via Front API even after AI indicated resolution.")
                return False
        except Exception as e:
            logger.error(f"Error during archiving conversation {front_conversation_id} after AI analysis: {e}", exc_info=True)
            return False
    else:
        logger.info(f"Conversation {front_conversation_id} not archived as OpenAI analysis indicated questions might still be pending.")
        if unresolved_questions:
            logger.info(f"Specific unresolved questions preventing archival: {unresolved_questions}")
        return False 