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

    conversation_data = get_conversation_text(front_conversation_id)
    if not conversation_data or not isinstance(conversation_data, dict):
        logger.error(f"📁 ARCHIVE FAILED: No conversation data for {front_conversation_id}")
        return False

    conversation_text = conversation_data.get('text', '')
    if not conversation_text.strip():
        logger.info(f"📁 ARCHIVE SKIPPED: Empty conversation {front_conversation_id}")
        return False

    analysis_result = await are_questions_resolved_openai(conversation_text)

    # Handle structured response
    if not analysis_result.get("success", False):
        logger.error(f"📁 ARCHIVE ANALYSIS FAILED for {front_conversation_id}: {analysis_result.get('summary', 'Unknown error')}")
        return False

    all_questions_resolved = analysis_result.get("resolved", False)
    unresolved_questions = analysis_result.get("unresolved_questions", [])
    
    # Essential logging: Archive decision
    if all_questions_resolved:
        try:
            success = archive_conversation_in_front(front_conversation_id)
            if success:
                logger.info(f"📁 ARCHIVED: {front_conversation_id} - All questions resolved")
                return True
            else:
                logger.error(f"📁 ARCHIVE FAILED: Front API error for {front_conversation_id}")
                return False
        except Exception as e:
            logger.error(f"📁 ARCHIVE ERROR: {front_conversation_id} - {e}")
            return False
    else:
        logger.info(f"📁 NOT ARCHIVED: {front_conversation_id} - Unresolved: {unresolved_questions}")
        return False 