"""Service for archiving conversations."""

import logging
import os
from app.core.config import settings
from app.services.frontapp_service import get_conversation_text, archive_conversation_in_front
from app.services.openai_service import are_questions_resolved_openai # Import OpenAI service

logger = logging.getLogger(__name__)

# Create a separate logger for detailed archival debugging (similar to classification_service)
debug_logger = logging.getLogger(f"{__name__}.debug")

# Check if detailed classification debugging is enabled
CLASSIFICATION_DEBUG = getattr(settings, 'CLASSIFICATION_DEBUG', False) or settings.DEBUG

# Set up separate file handler for classification debug logs if enabled (shared with classification service)
if CLASSIFICATION_DEBUG:
    debug_log_file = os.path.join(os.path.dirname(__file__), '../../logs/classification_debug.log')
    os.makedirs(os.path.dirname(debug_log_file), exist_ok=True)
    
    debug_handler = logging.FileHandler(debug_log_file)
    debug_handler.setLevel(logging.DEBUG)
    debug_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    debug_handler.setFormatter(debug_formatter)
    
    # Only add handler if it doesn't exist (to prevent duplicates)
    if not any(isinstance(h, logging.FileHandler) and h.baseFilename == debug_handler.baseFilename 
               for h in debug_logger.handlers):
        debug_logger.addHandler(debug_handler)
        debug_logger.setLevel(logging.DEBUG)
        debug_logger.propagate = False  # Prevent duplicate logs

async def check_and_archive_conversation(front_conversation_id: str, email_obj=None) -> bool:
    """
    Checks if a conversation can be archived and archives it if all questions are resolved.

    Args:
        front_conversation_id: The Front conversation ID.
        email_obj: Optional email object with document processing results.

    Returns:
        bool: True if the conversation was archived, False otherwise.
    """
    
    # Debug logging for archival detection start
    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 ARCHIVAL DETECTION START: {front_conversation_id}")
        if email_obj:
            debug_logger.debug(f"🔍 ARCHIVAL: Email object provided with attributes: {list(email_obj.__dict__.keys()) if hasattr(email_obj, '__dict__') else 'No __dict__'}")

    # Check for document processing results that prevent archiving
    # Document results are stored in ocr_results field
    if email_obj and hasattr(email_obj, 'ocr_results'):
        doc_results = email_obj.ocr_results
        if doc_results:
            if CLASSIFICATION_DEBUG:
                debug_logger.debug(f"🔍 ARCHIVAL: Found {len(doc_results)} document processing results in ocr_results")
            for result in doc_results:
                if isinstance(result, dict):
                    doc_analysis = result.get('document_analysis', {})
                    if doc_analysis.get('success') and doc_analysis.get('data'):
                        doc_data = doc_analysis['data']
                        doc_type = doc_data.get('document_type')
                        confidence = doc_data.get('confidence', 0.0)
                        
                        if CLASSIFICATION_DEBUG:
                            debug_logger.debug(f"🔍 ARCHIVAL: Document analysis - type: {doc_type}, confidence: {confidence:.2f}")
                        
                        # Prevent archiving for actionable document types
                        actionable_doc_types = ['rx', 'lien', 'medical_record']
                        if doc_type in actionable_doc_types and confidence > 0.7:
                            logger.info(f"📁 ARCHIVE PREVENTED: {front_conversation_id} - Found {doc_type} document (confidence: {confidence:.2f})")
                            if CLASSIFICATION_DEBUG:
                                debug_logger.debug(f"🔍 ARCHIVAL BLOCKED: {front_conversation_id} - {doc_type} document prevents archiving (confidence: {confidence:.2f})")
                            return False

    conversation_data = get_conversation_text(front_conversation_id)
    if not conversation_data or not isinstance(conversation_data, dict):
        logger.error(f"📁 ARCHIVE FAILED: No conversation data for {front_conversation_id}")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 ARCHIVAL ERROR: No conversation data retrieved for {front_conversation_id}")
        return False

    conversation_text = conversation_data.get('text', '')
    structured_messages = conversation_data.get('_structured_messages', [])
    
    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 ARCHIVAL: Retrieved conversation data:")
        debug_logger.debug(f"🔍 ARCHIVAL: - Stripped text ({len(conversation_text)} chars): {conversation_text[:200]}{'...' if len(conversation_text) > 200 else ''}")
        debug_logger.debug(f"🔍 ARCHIVAL: - Structured messages count: {len(structured_messages)}")
        for i, msg in enumerate(structured_messages):
            debug_logger.debug(f"🔍 ARCHIVAL: - Message {i+1}: ID={msg.get('id')}, Author={msg.get('author_email', msg.get('author_name', 'Unknown'))}, Body='{msg.get('body', '')[:100]}{'...' if len(msg.get('body', '')) > 100 else ''}'")
    
    if not conversation_text.strip() and not structured_messages:
        logger.info(f"📁 ARCHIVE SKIPPED: Empty conversation {front_conversation_id}")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 ARCHIVAL SKIPPED: Empty conversation text and no structured messages for {front_conversation_id}")
        return False

    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 ARCHIVAL: Sending to OpenAI for resolution analysis...")

    # Pass both stripped text and structured messages to OpenAI service
    analysis_result = await are_questions_resolved_openai(conversation_text, structured_messages)

    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 ARCHIVAL: OpenAI analysis result: {analysis_result}")

    # Handle structured response
    if not analysis_result.get("success", False):
        logger.error(f"📁 ARCHIVE ANALYSIS FAILED for {front_conversation_id}: {analysis_result.get('summary', 'Unknown error')}")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 ARCHIVAL ANALYSIS FAILED: {front_conversation_id} - {analysis_result}")
        return False

    all_questions_resolved = analysis_result.get("resolved", False)
    unresolved_questions = analysis_result.get("unresolved_questions", [])
    
    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 ARCHIVAL DECISION: {front_conversation_id} - resolved: {all_questions_resolved}, unresolved: {unresolved_questions}")
    
    # Essential logging: Archive decision
    if all_questions_resolved:
        try:
            if CLASSIFICATION_DEBUG:
                debug_logger.debug(f"🔍 ARCHIVAL: Attempting to archive conversation {front_conversation_id} via Front API...")
            success = archive_conversation_in_front(front_conversation_id)
            if success:
                logger.info(f"📁 ARCHIVED: {front_conversation_id} - All questions resolved")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 ARCHIVAL SUCCESS: {front_conversation_id} archived successfully")
                return True
            else:
                logger.error(f"📁 ARCHIVE FAILED: Front API error for {front_conversation_id}")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 ARCHIVAL FRONT API ERROR: Failed to archive {front_conversation_id}")
                return False
        except Exception as e:
            logger.error(f"📁 ARCHIVE ERROR: {front_conversation_id} - {e}")
            if CLASSIFICATION_DEBUG:
                debug_logger.debug(f"🔍 ARCHIVAL EXCEPTION: {front_conversation_id} - {str(e)}")
            return False
    else:
        logger.info(f"📁 NOT ARCHIVED: {front_conversation_id} - Unresolved: {unresolved_questions}")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 ARCHIVAL NOT PERFORMED: {front_conversation_id} - unresolved questions prevent archiving")
        return False 