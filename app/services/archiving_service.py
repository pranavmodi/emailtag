"""Service for archiving conversations."""

import logging
import os
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.services.frontapp_service import get_conversation_text, archive_conversation_in_front
from app.services.openai_service import are_questions_resolved_openai, verify_archive_decision_openai
from app.services.document_processing_service import DocumentProcessingService
from app.services.trace_service import create_tracer
from app.models.processing_trace import StepTypes, TraceStatus

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
    # Create tracer for detailed step-by-step logging
    email_id = str(email_obj.id) if email_obj and hasattr(email_obj, 'id') else None
    tracer = create_tracer(front_conversation_id, email_id)
    overall_start = datetime.utcnow()

    # Debug logging for archival detection start
    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 ARCHIVAL DETECTION START: {front_conversation_id}")
        if email_obj:
            debug_logger.debug(f"🔍 ARCHIVAL: Email object provided with attributes: {list(email_obj.__dict__.keys()) if hasattr(email_obj, '__dict__') else 'No __dict__'}")

    # Log the start of archival check
    tracer.log_step(
        step_name="archive_check_start",
        step_type=StepTypes.BUSINESS_LOGIC,
        status=TraceStatus.STARTED,
        input_data={
            "conversation_id": front_conversation_id,
            "has_email_obj": email_obj is not None,
            "has_attachments": email_obj.has_attachments if email_obj else False,
            "has_ocr_results": bool(email_obj.ocr_results) if email_obj and hasattr(email_obj, 'ocr_results') else False
        }
    )

    # FIRST CHECK: Check stored OCR results for actionable documents
    stored_check_start = datetime.utcnow()
    stored_has_actionable = False
    stored_doc_type = None
    stored_confidence = None
    stored_doc_count = 0

    if email_obj and hasattr(email_obj, 'ocr_results'):
        doc_results = email_obj.ocr_results
        if doc_results:
            stored_doc_count = len(doc_results)
            if CLASSIFICATION_DEBUG:
                debug_logger.debug(f"🔍 ARCHIVAL: Found {len(doc_results)} document processing results in stored ocr_results")

            has_actionable, doc_type, confidence = _check_for_actionable_documents(doc_results, source="stored")
            if has_actionable:
                stored_has_actionable = True
                stored_doc_type = doc_type
                stored_confidence = confidence
                logger.info(f"📁 ARCHIVE PREVENTED (STORED CHECK): {front_conversation_id} - Found {doc_type} document (confidence: {confidence:.2f})")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 ARCHIVAL BLOCKED (STORED): {front_conversation_id} - {doc_type} document prevents archiving (confidence: {confidence:.2f})")

                # Log blocked by stored documents
                tracer.log_step(
                    step_name="archive_blocked_stored_docs",
                    step_type=StepTypes.BUSINESS_LOGIC,
                    status=TraceStatus.COMPLETED,
                    input_data={"doc_count": stored_doc_count},
                    output_data={
                        "blocked": True,
                        "reason": "actionable_document_found",
                        "doc_type": doc_type,
                        "confidence": confidence,
                        "decision": "DO_NOT_ARCHIVE"
                    },
                    duration_ms=int((datetime.utcnow() - stored_check_start).total_seconds() * 1000)
                )
                return False
            else:
                logger.info(f"📁 ARCHIVE CHECK (STORED): {front_conversation_id} - No actionable documents found in stored results")

    # Log stored check result
    tracer.log_step(
        step_name="archive_check_stored_docs",
        step_type=StepTypes.BUSINESS_LOGIC,
        status=TraceStatus.COMPLETED,
        input_data={"doc_count": stored_doc_count},
        output_data={
            "has_actionable": False,
            "checked_documents": stored_doc_count,
            "result": "PASSED"
        },
        duration_ms=int((datetime.utcnow() - stored_check_start).total_seconds() * 1000)
    )

    # SECOND CHECK: Re-process latest email's attachments if it has any
    fresh_check_start = datetime.utcnow()
    fresh_doc_count = 0

    if email_obj and email_obj.has_attachments:
        logger.info(f"📁 ARCHIVE DOUBLE-CHECK: Starting fresh document processing for latest email in {front_conversation_id}")

        fresh_results = await _reprocess_attachments(email_obj)
        fresh_doc_count = len(fresh_results) if fresh_results else 0

        if fresh_results:
            has_actionable, doc_type, confidence = _check_for_actionable_documents(fresh_results, source="fresh")
            if has_actionable:
                logger.info(f"📁 ARCHIVE PREVENTED (FRESH CHECK): {front_conversation_id} - Found {doc_type} document in fresh processing (confidence: {confidence:.2f})")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 ARCHIVAL BLOCKED (FRESH): {front_conversation_id} - {doc_type} document prevents archiving (confidence: {confidence:.2f})")

                # Log blocked by fresh documents
                tracer.log_step(
                    step_name="archive_blocked_fresh_docs",
                    step_type=StepTypes.BUSINESS_LOGIC,
                    status=TraceStatus.COMPLETED,
                    input_data={"reprocessed_count": fresh_doc_count},
                    output_data={
                        "blocked": True,
                        "reason": "actionable_document_found_fresh",
                        "doc_type": doc_type,
                        "confidence": confidence,
                        "decision": "DO_NOT_ARCHIVE"
                    },
                    duration_ms=int((datetime.utcnow() - fresh_check_start).total_seconds() * 1000)
                )
                return False
            else:
                logger.info(f"📁 ARCHIVE CHECK (FRESH): {front_conversation_id} - No actionable documents found in fresh processing")
        else:
            logger.info(f"📁 ARCHIVE DOUBLE-CHECK: {front_conversation_id} - No fresh results obtained (reprocessing may have failed)")

        # Log fresh check result
        tracer.log_step(
            step_name="archive_check_fresh_docs",
            step_type=StepTypes.BUSINESS_LOGIC,
            status=TraceStatus.COMPLETED,
            input_data={"has_attachments": True},
            output_data={
                "reprocessed_count": fresh_doc_count,
                "has_actionable": False,
                "result": "PASSED"
            },
            duration_ms=int((datetime.utcnow() - fresh_check_start).total_seconds() * 1000)
        )
    else:
        logger.info(f"📁 ARCHIVE DOUBLE-CHECK: {front_conversation_id} - Latest email has no attachments, skipping fresh processing")
        tracer.log_step(
            step_name="archive_check_fresh_docs",
            step_type=StepTypes.BUSINESS_LOGIC,
            status=TraceStatus.SKIPPED,
            input_data={"has_attachments": False},
            output_data={"result": "SKIPPED_NO_ATTACHMENTS"},
            duration_ms=int((datetime.utcnow() - fresh_check_start).total_seconds() * 1000)
        )

    # Both checks passed - no actionable documents found
    logger.info(f"📁 ARCHIVE CHECKS PASSED: {front_conversation_id} - Both stored and fresh checks found no actionable documents")

    # THIRD CHECK: OpenAI conversation analysis
    openai_start = datetime.utcnow()

    conversation_data = get_conversation_text(front_conversation_id)
    if not conversation_data or not isinstance(conversation_data, dict):
        logger.error(f"📁 ARCHIVE FAILED: No conversation data for {front_conversation_id}")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 ARCHIVAL ERROR: No conversation data retrieved for {front_conversation_id}")

        tracer.log_step(
            step_name="archive_check_openai",
            step_type=StepTypes.AI_PROCESSING,
            status=TraceStatus.FAILED,
            error_data={"reason": "no_conversation_data"},
            output_data={"decision": "DO_NOT_ARCHIVE"},
            duration_ms=int((datetime.utcnow() - openai_start).total_seconds() * 1000)
        )
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

        tracer.log_step(
            step_name="archive_check_openai",
            step_type=StepTypes.AI_PROCESSING,
            status=TraceStatus.SKIPPED,
            input_data={"reason": "empty_conversation"},
            output_data={"decision": "DO_NOT_ARCHIVE"},
            duration_ms=int((datetime.utcnow() - openai_start).total_seconds() * 1000)
        )
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

        tracer.log_step(
            step_name="archive_check_openai",
            step_type=StepTypes.AI_PROCESSING,
            status=TraceStatus.FAILED,
            input_data={
                "message_count": len(structured_messages),
                "text_length": len(conversation_text)
            },
            output_data={
                "success": False,
                "error": analysis_result.get('summary', 'Unknown error'),
                "decision": "DO_NOT_ARCHIVE"
            },
            error_data={"analysis_result": analysis_result},
            duration_ms=int((datetime.utcnow() - openai_start).total_seconds() * 1000)
        )
        return False

    all_questions_resolved = analysis_result.get("resolved", False)
    unresolved_questions = analysis_result.get("unresolved_questions", [])

    # Extract parsed email chain for trace (simplified for readability)
    # Sanitize text to remove null characters that PostgreSQL can't store in JSONB
    def sanitize_text(text: str) -> str:
        if not text:
            return ""
        # Remove null characters and other problematic Unicode
        return text.replace('\x00', '').replace('\u0000', '')

    email_chain = analysis_result.get("email_chain", [])
    parsed_emails = []
    for email in email_chain:
        body = sanitize_text(email.get("body", ""))
        parsed_emails.append({
            "seq": email.get("sequence_number"),
            "from": sanitize_text(email.get("sender", "unknown")),
            "date": sanitize_text(email.get("date", "")),
            "subject": sanitize_text(email.get("subject", "")),
            "body_preview": (body[:200] + "...") if len(body) > 200 else body,
            "is_forwarded": email.get("is_forwarded_message", False)
        })

    # Log OpenAI analysis result with parsed email chain
    tracer.log_step(
        step_name="archive_check_openai",
        step_type=StepTypes.AI_PROCESSING,
        status=TraceStatus.COMPLETED,
        input_data={
            "message_count": len(structured_messages),
            "text_length": len(conversation_text)
        },
        output_data={
            "resolved": all_questions_resolved,
            "unresolved_questions": [sanitize_text(q) for q in unresolved_questions],
            "summary": sanitize_text(analysis_result.get("summary", "")),
            "latest_email_analysis": sanitize_text(analysis_result.get("latest_email_analysis", "")),
            "parsed_email_chain": parsed_emails,
            "total_emails_parsed": len(parsed_emails)
        },
        duration_ms=int((datetime.utcnow() - openai_start).total_seconds() * 1000)
    )

    if CLASSIFICATION_DEBUG:
        debug_logger.debug(f"🔍 ARCHIVAL DECISION: {front_conversation_id} - resolved: {all_questions_resolved}, unresolved: {unresolved_questions}")

    # Essential logging: Archive decision
    if all_questions_resolved:
        # FOURTH CHECK: Verification step - second opinion before archiving
        verification_start = datetime.utcnow()
        logger.info(f"📁 ARCHIVE VERIFICATION: {front_conversation_id} - Starting second-opinion verification")

        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 ARCHIVAL: Starting verification step for {front_conversation_id}")

        verification_result = await verify_archive_decision_openai(
            analysis_result.get("email_chain", []),
            analysis_result
        )

        # Log verification step
        tracer.log_step(
            step_name="archive_check_verification",
            step_type=StepTypes.AI_PROCESSING,
            status=TraceStatus.COMPLETED if verification_result.get("success") else TraceStatus.FAILED,
            input_data={
                "first_analysis_resolved": True,
                "email_count": len(analysis_result.get("email_chain", []))
            },
            output_data={
                "verified": verification_result.get("verified", False),
                "recommendation": verification_result.get("recommendation", "DO_NOT_ARCHIVE"),
                "concerns": [sanitize_text(c) for c in verification_result.get("concerns", [])],
                "summary": sanitize_text(verification_result.get("summary", ""))
            },
            duration_ms=int((datetime.utcnow() - verification_start).total_seconds() * 1000)
        )

        # Check if verification passed
        if not verification_result.get("success"):
            logger.error(f"📁 ARCHIVE VERIFICATION FAILED: {front_conversation_id} - Verification call failed")
            if CLASSIFICATION_DEBUG:
                debug_logger.debug(f"🔍 ARCHIVAL VERIFICATION ERROR: {front_conversation_id} - {verification_result}")

            tracer.log_step(
                step_name="archive_check_complete",
                step_type=StepTypes.BUSINESS_LOGIC,
                status=TraceStatus.COMPLETED,
                output_data={
                    "final_decision": "NOT_ARCHIVED",
                    "reason": "verification_call_failed",
                    "checks_passed": ["stored_docs", "fresh_docs", "openai_resolution"],
                    "checks_failed": ["verification"]
                },
                duration_ms=int((datetime.utcnow() - overall_start).total_seconds() * 1000)
            )
            return False

        if not verification_result.get("verified") or verification_result.get("recommendation") != "PROCEED_WITH_ARCHIVE":
            logger.info(f"📁 ARCHIVE BLOCKED BY VERIFICATION: {front_conversation_id} - Concerns: {verification_result.get('concerns', [])}")
            if CLASSIFICATION_DEBUG:
                debug_logger.debug(f"🔍 ARCHIVAL BLOCKED (VERIFICATION): {front_conversation_id} - {verification_result.get('summary', '')}")

            tracer.log_step(
                step_name="archive_check_complete",
                step_type=StepTypes.BUSINESS_LOGIC,
                status=TraceStatus.COMPLETED,
                output_data={
                    "final_decision": "NOT_ARCHIVED",
                    "reason": "verification_concerns",
                    "concerns": verification_result.get("concerns", []),
                    "verification_summary": verification_result.get("summary", ""),
                    "checks_passed": ["stored_docs", "fresh_docs", "openai_resolution"],
                    "checks_failed": ["verification"]
                },
                duration_ms=int((datetime.utcnow() - overall_start).total_seconds() * 1000)
            )
            return False

        logger.info(f"📁 ARCHIVE VERIFICATION PASSED: {front_conversation_id} - Proceeding with archive")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 ARCHIVAL VERIFICATION PASSED: {front_conversation_id} - {verification_result.get('summary', '')}")
        try:
            if CLASSIFICATION_DEBUG:
                debug_logger.debug(f"🔍 ARCHIVAL: Attempting to archive conversation {front_conversation_id} via Front API...")

            front_api_start = datetime.utcnow()
            success = archive_conversation_in_front(front_conversation_id)

            if success:
                logger.info(f"📁 ARCHIVED: {front_conversation_id} - All questions resolved")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 ARCHIVAL SUCCESS: {front_conversation_id} archived successfully")

                # Log successful archive
                tracer.log_step(
                    step_name="archive_executed",
                    step_type=StepTypes.API_CALL,
                    status=TraceStatus.COMPLETED,
                    output_data={
                        "archived": True,
                        "front_api_success": True,
                        "decision": "ARCHIVED"
                    },
                    duration_ms=int((datetime.utcnow() - front_api_start).total_seconds() * 1000)
                )

                # Log overall completion
                tracer.log_step(
                    step_name="archive_check_complete",
                    step_type=StepTypes.BUSINESS_LOGIC,
                    status=TraceStatus.COMPLETED,
                    output_data={
                        "final_decision": "ARCHIVED",
                        "checks_passed": ["stored_docs", "fresh_docs", "openai_resolution", "verification"],
                        "questions_resolved": True,
                        "verification_confirmed": True
                    },
                    duration_ms=int((datetime.utcnow() - overall_start).total_seconds() * 1000)
                )
                return True
            else:
                logger.error(f"📁 ARCHIVE FAILED: Front API error for {front_conversation_id}")
                if CLASSIFICATION_DEBUG:
                    debug_logger.debug(f"🔍 ARCHIVAL FRONT API ERROR: Failed to archive {front_conversation_id}")

                tracer.log_step(
                    step_name="archive_executed",
                    step_type=StepTypes.API_CALL,
                    status=TraceStatus.FAILED,
                    error_data={"reason": "front_api_error"},
                    output_data={"decision": "ARCHIVE_FAILED"},
                    duration_ms=int((datetime.utcnow() - front_api_start).total_seconds() * 1000)
                )
                return False
        except Exception as e:
            logger.error(f"📁 ARCHIVE ERROR: {front_conversation_id} - {e}")
            if CLASSIFICATION_DEBUG:
                debug_logger.debug(f"🔍 ARCHIVAL EXCEPTION: {front_conversation_id} - {str(e)}")

            tracer.log_step(
                step_name="archive_executed",
                step_type=StepTypes.API_CALL,
                status=TraceStatus.FAILED,
                error_data={"exception": str(e), "type": type(e).__name__},
                output_data={"decision": "ARCHIVE_FAILED"},
                duration_ms=int((datetime.utcnow() - overall_start).total_seconds() * 1000)
            )
            return False
    else:
        logger.info(f"📁 NOT ARCHIVED: {front_conversation_id} - Unresolved: {unresolved_questions}")
        if CLASSIFICATION_DEBUG:
            debug_logger.debug(f"🔍 ARCHIVAL NOT PERFORMED: {front_conversation_id} - unresolved questions prevent archiving")

        # Log decision not to archive
        tracer.log_step(
            step_name="archive_check_complete",
            step_type=StepTypes.BUSINESS_LOGIC,
            status=TraceStatus.COMPLETED,
            output_data={
                "final_decision": "NOT_ARCHIVED",
                "reason": "unresolved_questions",
                "unresolved_questions": unresolved_questions,
                "checks_passed": ["stored_docs", "fresh_docs"],
                "checks_failed": ["openai_resolution"]
            },
            duration_ms=int((datetime.utcnow() - overall_start).total_seconds() * 1000)
        )
        return False 