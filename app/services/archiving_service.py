"""Service for archiving conversations."""

import logging
import os
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.services.frontapp_service import get_conversation_text, archive_conversation_in_front
from app.services.openai_service import are_questions_resolved_openai # Import OpenAI service
from app.services.document_processing_service import DocumentProcessingService

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


async def _reprocess_attachments(email_obj) -> List[Dict[str, Any]]:
    """
    Re-download and re-process all attachments from the LATEST email only to get fresh document analysis.

    This function only processes attachments from the most recent email in the conversation,
    not all emails in the conversation history.

    Args:
        email_obj: The latest email object with raw_data containing attachment information

    Returns:
        List of fresh document processing results from the latest email's attachments only
    """
    fresh_results = []

    if not email_obj or not email_obj.has_attachments:
        logger.info(f"📁 ARCHIVE DOUBLE-CHECK: Latest email in {email_obj.front_conversation_id if email_obj else 'unknown'} has no attachments to reprocess")
        return fresh_results

    try:
        # Extract attachment URLs from raw_data (latest email only)
        target_data = email_obj.raw_data.get('target', {}).get('data', {})
        attachments_data = target_data.get('attachments', [])

        if not attachments_data:
            logger.info(f"📁 ARCHIVE DOUBLE-CHECK: No attachment data found in raw_data for latest email in {email_obj.front_conversation_id}")
            return fresh_results

        logger.info(f"📁 ARCHIVE DOUBLE-CHECK: Found {len(attachments_data)} attachments in LATEST EMAIL to reprocess for conversation {email_obj.front_conversation_id}")

        # Process each attachment
        service = DocumentProcessingService()

        for i, attachment in enumerate(attachments_data):
            attachment_url = attachment.get("url")
            if not attachment_url:
                logger.warning(f"📁 ARCHIVE DOUBLE-CHECK: Attachment {i+1} missing URL, skipping")
                continue

            filename = attachment_url.split('/')[-1] if '/' in attachment_url else f'attachment_{i+1}'

            try:
                # Download attachment
                headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
                async with httpx.AsyncClient(follow_redirects=True, verify=False, timeout=120.0) as client:
                    response = await client.get(attachment_url, headers=headers)
                    response.raise_for_status()
                    attachment_content = response.content

                logger.info(f"📁 ARCHIVE DOUBLE-CHECK: Downloaded attachment {filename} ({len(attachment_content)} bytes)")

                # Process document
                processing_result = await service.process_document(attachment_content, filename)
                fresh_results.append(processing_result)

                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 ARCHIVE DOUBLE-CHECK: Processed {filename}: {processing_result}")

                logger.info(f"📁 ARCHIVE DOUBLE-CHECK: Processed attachment {filename} - status: {processing_result.get('processing_status')}")

            except httpx.HTTPError as e:
                logger.error(f"📁 ARCHIVE DOUBLE-CHECK: Failed to download {filename}: {e}")
                continue
            except Exception as e:
                logger.error(f"📁 ARCHIVE DOUBLE-CHECK: Error processing {filename}: {e}")
                continue

        logger.info(f"📁 ARCHIVE DOUBLE-CHECK: Successfully reprocessed {len(fresh_results)} attachments from latest email in conversation {email_obj.front_conversation_id}")
        return fresh_results

    except Exception as e:
        logger.error(f"📁 ARCHIVE DOUBLE-CHECK: Error in _reprocess_attachments: {e}")
        return fresh_results


def _check_for_actionable_documents(doc_results: List[Dict[str, Any]], source: str = "stored") -> tuple[bool, Optional[str], Optional[float]]:
    """
    Check a list of document processing results for actionable document types.

    Args:
        doc_results: List of document processing results
        source: Source of the results ("stored" or "fresh") for logging

    Returns:
        Tuple of (has_actionable, doc_type, confidence)
    """
    actionable_doc_types = ['rx', 'lien', 'medical_record', 'case_update']

    for result in doc_results:
        if isinstance(result, dict):
            doc_analysis = result.get('document_analysis', {})
            if doc_analysis.get('success') and doc_analysis.get('data'):
                doc_data = doc_analysis['data']
                doc_type = doc_data.get('document_type')
                confidence = doc_data.get('confidence', 0.0)

                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 ARCHIVE CHECK ({source}): Document analysis - type: {doc_type}, confidence: {confidence:.2f}")

                # Check if document is actionable
                if doc_type in actionable_doc_types and confidence > 0.7:
                    return True, doc_type, confidence

    return False, None, None


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

    # FIRST CHECK: Check stored OCR results for actionable documents
    stored_has_actionable = False
    if email_obj and hasattr(email_obj, 'ocr_results'):
        doc_results = email_obj.ocr_results
        if doc_results:
            if CLASSIFICATION_DEBUG:
                debug_logger.debug(f"🔍 ARCHIVAL: Found {len(doc_results)} document processing results in stored ocr_results")

            has_actionable, doc_type, confidence = _check_for_actionable_documents(doc_results, source="stored")
            if has_actionable:
                logger.info(f"📁 ARCHIVE PREVENTED (STORED CHECK): {front_conversation_id} - Found {doc_type} document (confidence: {confidence:.2f})")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 ARCHIVAL BLOCKED (STORED): {front_conversation_id} - {doc_type} document prevents archiving (confidence: {confidence:.2f})")
                return False
            else:
                logger.info(f"📁 ARCHIVE CHECK (STORED): {front_conversation_id} - No actionable documents found in stored results")

    # SECOND CHECK: Re-process latest email's attachments if it has any
    if email_obj and email_obj.has_attachments:
        logger.info(f"📁 ARCHIVE DOUBLE-CHECK: Starting fresh document processing for latest email in {front_conversation_id}")

        fresh_results = await _reprocess_attachments(email_obj)

        if fresh_results:
            has_actionable, doc_type, confidence = _check_for_actionable_documents(fresh_results, source="fresh")
            if has_actionable:
                logger.info(f"📁 ARCHIVE PREVENTED (FRESH CHECK): {front_conversation_id} - Found {doc_type} document in fresh processing (confidence: {confidence:.2f})")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 ARCHIVAL BLOCKED (FRESH): {front_conversation_id} - {doc_type} document prevents archiving (confidence: {confidence:.2f})")
                return False
            else:
                logger.info(f"📁 ARCHIVE CHECK (FRESH): {front_conversation_id} - No actionable documents found in fresh processing")
        else:
            logger.info(f"📁 ARCHIVE DOUBLE-CHECK: {front_conversation_id} - No fresh results obtained (reprocessing may have failed)")
    else:
        logger.info(f"📁 ARCHIVE DOUBLE-CHECK: {front_conversation_id} - Latest email has no attachments, skipping fresh processing")

    # Both checks passed - no actionable documents found
    logger.info(f"📁 ARCHIVE CHECKS PASSED: {front_conversation_id} - Both stored and fresh checks found no actionable documents")

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