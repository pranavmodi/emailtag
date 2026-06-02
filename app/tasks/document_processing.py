"""Document processing tasks using OpenAI-based document analysis."""

import logging
from typing import Dict, Optional
from uuid import UUID
import httpx

from sqlalchemy.orm import Session
from sqlalchemy import text
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.core.log_context import set_conversation_context, clear_conversation_context, add_delimiter_to_context
from app.crud.sync import email as email_crud_sync
from app.db.session import SessionLocal
from app.services.conversation_log_service import flush_conversation_logs
from app.services.document_processing_service import DocumentProcessingService
from app.schemas.email import EmailUpdate
from app.tasks.worker import celery_app

logger = get_task_logger(__name__)

# Define error status constant
DOCUMENT_ERROR_STATUS = "document_processing_error"


@celery_app.task(name="tasks.send_attachment_to_document_processing", bind=True, 
                 max_retries=3, 
                 default_retry_delay=60)
def send_attachment_to_document_processing(
    self,
    email_id: str,
    attachment_url: str,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
):
    """
    Downloads an attachment, processes it with document processing service,
    and updates the email record directly.
    """

    filename = _resolve_attachment_filename(attachment_url, filename, content_type)
    logger.info(f"🔄 DOCUMENT PROCESSING START: {filename} for email {email_id}")

    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id: {email_id}. Cannot proceed.")
        return

    # Look up front_conversation_id for log capture
    front_conversation_id = None
    try:
        db_lookup = SessionLocal()
        try:
            email_for_ctx = email_crud_sync.get(db_lookup, id=email_uuid)
            if email_for_ctx:
                front_conversation_id = email_for_ctx.front_conversation_id
        finally:
            db_lookup.close()
    except Exception as ctx_exc:
        logger.warning(f"⚠️ LOG CONTEXT SETUP FAILED for email {email_id}: {ctx_exc} — document processing logs will not be captured in trace")

    # Set up conversation log context so all logs (including barcode detection) are captured
    log_ctx = None
    if front_conversation_id:
        log_ctx = set_conversation_context(front_conversation_id, email_id)
        add_delimiter_to_context(f"send_attachment_to_document_processing | email: {email_id}")

    try:
        _do_document_processing(self, email_id, email_uuid, attachment_url, filename)
    finally:
        if log_ctx:
            log_ctx = clear_conversation_context()
            if log_ctx:
                flush_conversation_logs(log_ctx)


def _resolve_attachment_filename(
    attachment_url: str,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
) -> str:
    """Prefer Front attachment filename, falling back to URL plus content-type hint."""
    resolved = filename or (attachment_url.split('/')[-1] if '/' in attachment_url else 'attachment')
    if "." in resolved:
        return resolved

    extension_by_content_type = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-excel": ".xls",
        "text/plain": ".txt",
    }
    extension = extension_by_content_type.get((content_type or "").split(";")[0].strip().lower())
    return f"{resolved}{extension}" if extension else resolved


def _do_document_processing(self, email_id: str, email_uuid: UUID, attachment_url: str, filename: str):
    """Inner function containing the actual document processing logic."""

    # Calculate exponential backoff delay for retries
    def get_retry_delay(retry_count):
        delay = 60 * (2 ** retry_count)
        return min(delay, 960)

    # --- Download Attachment ---
    try:
        headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
        with httpx.Client(follow_redirects=True, verify=False) as client:
            response = client.get(attachment_url, headers=headers, timeout=120.0)
            response.raise_for_status()
            attachment_content = response.content
    except httpx.HTTPStatusError as exc:
        logger.error(f"HTTP error downloading attachment {attachment_url} for email {email_id}: {exc.response.status_code} - {exc.response.text}")
        if 400 <= exc.response.status_code < 500:
            _handle_final_document_processing_failure(email_uuid, attachment_url, f"HTTP {exc.response.status_code} error downloading attachment")
            return
        if 500 <= exc.response.status_code < 600 and self.request.retries < 3:
            retry_delay = get_retry_delay(self.request.retries)
            logger.warning(f"Retrying download in {retry_delay} seconds due to server error (attempt {self.request.retries + 1}/4)")
            try:
                self.retry(exc=exc, countdown=retry_delay)
            except Exception as retry_exc:
                logger.error(f"Retry failed for download error: {retry_exc}")
        else:
            _handle_final_document_processing_failure(email_uuid, attachment_url, f"Download failed after 4 attempts: {exc}")
        return
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as exc:
        # Network connectivity errors (DNS failures, connection refused, timeouts)
        error_msg = str(exc)
        logger.error(f"Network error downloading attachment {attachment_url} for email {email_id}: {error_msg}")
        if self.request.retries < self.max_retries:
            retry_delay = get_retry_delay(self.request.retries)
            logger.warning(f"🔄 Retrying download in {retry_delay}s due to network error (attempt {self.request.retries + 1}/{self.max_retries + 1}): {error_msg}")
            try:
                self.retry(exc=exc, countdown=retry_delay)
            except self.MaxRetriesExceededError:
                logger.error(f"Max retries exceeded for network error: {error_msg}")
                _handle_final_document_processing_failure(email_uuid, attachment_url, f"Network error after {self.max_retries + 1} attempts: {error_msg}")
        else:
            _handle_final_document_processing_failure(email_uuid, attachment_url, f"Network error after {self.max_retries + 1} attempts: {error_msg}")
        return
    except Exception as exc:
        logger.exception(f"Unexpected error downloading attachment {attachment_url} for email {email_id}: {exc}")
        _handle_final_document_processing_failure(email_uuid, attachment_url, f"Unexpected download error: {exc}")
        return

    # --- Process Document ---
    try:
        # Use document processing service
        import asyncio
        service = DocumentProcessingService()
        processing_result = asyncio.run(service.process_document(attachment_content, filename))

        # Log processing shape without dumping extracted document text/PHI.
        result_summary = _processing_result_log_summary(processing_result)

        # If enhanced lien processing exists, add a summary without pdf_bytes
        if 'enhanced_lien_processing' in processing_result:
            enhanced_data = processing_result['enhanced_lien_processing']
            enhanced_summary = {k: v for k, v in enhanced_data.items() if k != 'split_documents'}
            if 'split_documents' in enhanced_data:
                split_docs_summary = []
                for doc in enhanced_data['split_documents']:
                    split_docs_summary.append({
                        k: v for k, v in doc.items() if k != 'pdf_bytes'
                    })
                enhanced_summary['split_documents'] = split_docs_summary
            result_summary['enhanced_lien_processing'] = enhanced_summary

        logger.info(f"📄 DOCUMENT PROCESSING RESULT for email {email_id}:")
        logger.info(f"📄 Result summary: {result_summary}")
        
        if not processing_result.get("processing_status") == "completed":
            logger.warning(f"Document processing incomplete for email {email_id}. Status: {processing_result.get('processing_status')}")
        else:
            logger.info(f"✅ Successfully processed document for email {email_id}")
            
            # Log structured analysis results if available
            doc_analysis = processing_result.get("document_analysis", {})
            if doc_analysis.get("success"):
                analysis_data = doc_analysis.get("data", {})
                doc_type = analysis_data.get('document_type', 'unknown')
                description = analysis_data.get('description', 'N/A')
                confidence = analysis_data.get('confidence', 0.0)
                
                logger.info(f"📋 Document Type: {doc_type} (confidence: {confidence:.2f})")
                logger.info(f"📋 Classification Reason: {description}")
                logger.info(f"📋 Patient ID: {analysis_data.get('patient_id', 'Not found')}")
                
                # Clear explanation of why it was classified as lien or other
                if doc_type == 'lien':
                    logger.info(f"🏷️ LIEN DETECTED in {filename}: Document identified as lien based on content analysis")
                elif doc_type == 'other':
                    logger.info(f"🏷️ NON-LIEN DOCUMENT in {filename}: Classified as '{doc_type}' - {description}")
                else:
                    logger.info(f"🏷️ DOCUMENT CLASSIFICATION in {filename}: Type '{doc_type}' - {description}")
            else:
                logger.warning(f"❌ Document analysis failed: {doc_analysis.get('error', 'Unknown error')}")

    except Exception as exc:
        logger.exception(f"Unexpected error processing document for email {email_id}: {exc}")
        _handle_final_document_processing_failure(email_uuid, attachment_url, f"Unexpected processing error: {exc}")
        return

    # --- Process Results and Update DB ---
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found during document processing result update.")
            return

        if email_obj.status not in ["pending_ocr", "pending_document_processing", DOCUMENT_ERROR_STATUS]:
             logger.warning(f"Email {email_id} is not in pending processing state (current: {email_obj.status}). Skipping update.")
             return

        # Parse processing result for structured data
        attachment_data = _parse_document_processing_result(processing_result, attachment_url, email_id)

        # Update document processing results
        current_processing_results = email_obj.ocr_results or []  # Reuse existing field
        current_processing_results.append(attachment_data)
        
        update_payload = {'ocr_results': current_processing_results}

        # Use atomic database-level increment
        db.execute(
            text("UPDATE email SET ocr_attachments_completed = COALESCE(ocr_attachments_completed, 0) + 1 WHERE id = :email_id"),
            {"email_id": str(email_uuid)}
        )
        db.commit()
        
        # Get updated email object
        updated_email_with_count = email_crud_sync.get(db, id=email_uuid)
        if not updated_email_with_count:
            logger.error(f"Email {email_id} not found after atomic count update.")
            return
            
        completed_count = updated_email_with_count.ocr_attachments_completed
        
        # Update with processing results
        updated_email = email_crud_sync.update(db, db_obj=updated_email_with_count, obj_in=EmailUpdate(**update_payload))


        # Add comments to Front conversation for all patient IDs found
        patient_ids_to_add = []
        
        # Check for single patient ID (legacy)
        if attachment_data.get('patient_id'):
            patient_ids_to_add.append(attachment_data['patient_id'])
        
        # Check for multiple patient IDs from enhanced lien analysis
        enhanced_lien_analysis = attachment_data.get('document_analysis', {}).get('data', {}).get('enhanced_lien_analysis', {})
        if enhanced_lien_analysis.get('PatientIDs'):
            # Add all patient IDs from barcode analysis, avoiding duplicates
            for pid in enhanced_lien_analysis['PatientIDs']:
                if pid and pid not in patient_ids_to_add:
                    patient_ids_to_add.append(pid)
        
        # Update extracted_patient_ids in database if patient IDs were found
        if patient_ids_to_add:
            logger.info(f"Document processing found {len(patient_ids_to_add)} patient ID(s) for email {email_id}: {patient_ids_to_add}")
            
            # Merge with existing extracted_patient_ids from email content extraction
            existing_patient_ids = updated_email.extracted_patient_ids or []
            all_patient_ids = list(existing_patient_ids)  # Start with existing IDs
            
            # Add new patient IDs from document processing, avoiding duplicates
            for pid in patient_ids_to_add:
                if pid not in all_patient_ids:
                    all_patient_ids.append(pid)
            
            # Update database with combined patient IDs
            if all_patient_ids != existing_patient_ids:
                logger.info(f"Updating database extracted_patient_ids for email {email_id}: {all_patient_ids}")
                email_crud_sync.update(db, db_obj=updated_email, obj_in=EmailUpdate(extracted_patient_ids=all_patient_ids))
            
            # Add comments to Front conversation
            if updated_email.front_conversation_id:
                try:
                    from app.services.frontapp_service import add_multiple_patient_ids_comment_safe
                    add_multiple_patient_ids_comment_safe(updated_email.front_conversation_id, patient_ids_to_add, "document processing")
                except Exception as e:
                    logger.error(f"Failed to add document processing patient ID comments to conversation {updated_email.front_conversation_id}: {e}", exc_info=True)

        # Check for unreadable barcodes that need human review
        enhanced_lien_data = attachment_data.get('enhanced_lien_processing', {})
        unreadable_barcode_pages = enhanced_lien_data.get('unreadable_barcode_pages', [])
        if unreadable_barcode_pages and updated_email.front_conversation_id:
            try:
                from app.services.frontapp_service import add_conversation_tags, add_conversation_comment
                # Build a human-readable comment describing which pages had unreadable barcodes
                page_details = []
                for page_info in unreadable_barcode_pages:
                    page_num = page_info.get("page_number", "?")
                    lien_subtype = page_info.get("lien_subtype", "UNKNOWN")
                    page_details.append(f"Page {page_num} ({lien_subtype} lien)")
                pages_str = ", ".join(page_details)
                comment = (
                    f"⚠️ Human review required: Barcode expected but could not be read on {pages_str} "
                    f"in attachment {filename}. The affected page(s) could not be processed automatically."
                )
                add_conversation_comment(updated_email.front_conversation_id, comment)
                add_conversation_tags(updated_email.front_conversation_id, ["AI: Human review required"])
                logger.warning(
                    f"⚠️ UNREADABLE BARCODE REVIEW: Flagged conversation {updated_email.front_conversation_id} "
                    f"for human review - {pages_str} in {filename}"
                )
            except Exception as review_exc:
                logger.error(
                    f"Failed to flag unreadable barcode for human review on conversation "
                    f"{updated_email.front_conversation_id}: {review_exc}"
                )

        # Check if all attachments are processed and trigger orchestration if complete
        _check_document_processing_completion_and_trigger_orchestration(updated_email, completed_count, email_id, str(email_uuid))

        logger.info(f"✅ DOCUMENT PROCESSING COMPLETE: {filename} for email {email_id}")

    except Exception as db_exc:
        logger.exception(f"Database error processing document result for email {email_id}: {db_exc}")
        db.rollback()
        try:
            self.retry(exc=db_exc)
        except Exception as retry_exc:
             logger.error(f"Retry failed for DB error: {retry_exc}")
    finally:
        db.close()


def _parse_document_processing_result(processing_result: Dict, attachment_url: str, email_id: str) -> Dict:
    """Parse and structure document processing result data."""
    try:
        # Extract relevant information from structured document analysis
        document_analysis = processing_result.get("document_analysis", {})
        
        # Extract structured data
        patient_id = None
        doc_type = None
        description = ""
        
        if document_analysis.get("success"):
            analysis_data = document_analysis.get("data", {})
            patient_id = analysis_data.get("patient_id")
            doc_type = analysis_data.get("document_type")
            description = analysis_data.get("description", "")
        
        result_dict = {
            "attachment_url": attachment_url,
            "filename": processing_result.get("filename") or "",
            "detected_type": processing_result.get("detected_type") or processing_result.get("document_type"),
            "file_size": processing_result.get("file_size"),
            "patient_id": patient_id,
            "document_type": doc_type,
            "description": description,
            "document_analysis": document_analysis,
            "processing_status": processing_result.get("processing_status")
        }

        for key in ("text_content", "extracted_text", "ocr_text", "content", "summary"):
            if processing_result.get(key):
                result_dict[key] = processing_result[key]

        pages = processing_result.get("pages") or processing_result.get("page_results")
        if pages:
            result_dict["pages"] = pages

        # Include enhanced lien processing data if available (excluding pdf_bytes for JSON serialization)
        if "enhanced_lien_processing" in processing_result:
            enhanced_data = processing_result["enhanced_lien_processing"]
            # Create a copy without pdf_bytes in split_documents
            enhanced_clean = {k: v for k, v in enhanced_data.items() if k != 'split_documents'}

            # Add split_documents without pdf_bytes
            if 'split_documents' in enhanced_data:
                split_docs_clean = []
                for doc in enhanced_data['split_documents']:
                    doc_clean = {k: v for k, v in doc.items() if k != 'pdf_bytes'}
                    split_docs_clean.append(doc_clean)
                enhanced_clean['split_documents'] = split_docs_clean

            result_dict["enhanced_lien_processing"] = enhanced_clean

        # Include provider credential analysis for RX documents
        if "provider_credential_analysis" in processing_result:
            result_dict["provider_credential_analysis"] = processing_result["provider_credential_analysis"]

        return result_dict

    except Exception as parse_error:
        logger.error(f"Error parsing document processing result for email {email_id}: {parse_error}. Result: {processing_result}")
        return {
            "attachment_url": attachment_url,
            "error": f"Failed to parse processing result: {parse_error}"
        }


def _processing_result_log_summary(processing_result: Dict) -> Dict:
    """Summarize document processing output without logging extracted PHI text."""
    text_keys = {"text_content", "extracted_text", "ocr_text", "content", "summary"}
    summary = {
        key: value
        for key, value in processing_result.items()
        if key not in text_keys and key not in {"enhanced_lien_processing", "page_results", "pages"}
    }
    for key in text_keys:
        if processing_result.get(key):
            summary[f"{key}_chars"] = len(str(processing_result[key]))
    pages = processing_result.get("pages") or processing_result.get("page_results") or []
    if isinstance(pages, list):
        summary["page_count"] = len(pages)
        summary["page_text_chars"] = sum(len(str(page.get("text") or "")) for page in pages if isinstance(page, dict))
    return summary


def _check_document_processing_completion_and_trigger_orchestration(updated_email, completed_count: int, email_id: str, email_uuid_str: str):
    """
    Check if all document processing is complete and trigger orchestration.
    """
    if updated_email.ocr_attachments_total is None:
        logger.warning(f"Email {email_id} has no ocr_attachments_total set. Cannot determine completion.")
        return
        
    if completed_count < updated_email.ocr_attachments_total:
        return
    
    # Check if any processing resulted in an error
    has_errors = any(result.get('error') for result in updated_email.ocr_results or [])
    
    if has_errors:
        final_status = "document_processing_completed_with_errors"
        try:
            from app.services.frontapp_service import add_conversation_tags
            if updated_email.front_conversation_id:
                add_conversation_tags(updated_email.front_conversation_id, ["AI: Human review required"])
        except Exception as tag_exc:
            logger.error(f"Failed to add AI-review tag for conversation {updated_email.front_conversation_id}: {tag_exc}")
    else:
        final_status = "document_processing_completed"
    
    # Update status and trigger next phase
    try:
        db = SessionLocal()
        try:
            email_obj = email_crud_sync.get(db, id=UUID(email_uuid_str))
            if email_obj and email_obj.status not in ["document_processing_completed", "document_processing_completed_with_errors"]:
                email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_status))
                
                from app.tasks.email import orchestrate_post_ocr_processing
                orchestrate_post_ocr_processing.apply_async(args=[email_uuid_str], queue='processing')
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error updating status and triggering orchestration for email {email_id}: {e}", exc_info=True)


def _handle_final_document_processing_failure(email_uuid: UUID, attachment_url: str, failure_reason: str):
    """
    Helper function to handle final document processing failure.
    """
    logger.error(f"Final document processing failure for email {email_uuid}, attachment {attachment_url}: {failure_reason}")
    
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if email_obj:
            # Create failure record
            failure_record = {
                "attachment_url": attachment_url,
                "error": f"Document processing failed: {failure_reason}",
                "patient_id": None,
                "extracted_text": "",
                "processing_status": "failed"
            }
            
            current_results = email_obj.ocr_results or []
            current_results.append(failure_record)
            
            # Atomic increment for completion count
            db.execute(
                text("UPDATE email SET ocr_attachments_completed = COALESCE(ocr_attachments_completed, 0) + 1 WHERE id = :email_id"),
                {"email_id": str(email_uuid)}
            )
            db.commit()
            
            # Get updated email object
            updated_email_state = email_crud_sync.get(db, id=email_uuid)
            if not updated_email_state:
                logger.error(f"Email {email_uuid} not found after atomic count update in failure handler.")
                return
                
            completed_count = updated_email_state.ocr_attachments_completed
            
            # Update processing results
            update_payload = {'ocr_results': current_results}
            updated_email = email_crud_sync.update(db, db_obj=updated_email_state, obj_in=EmailUpdate(**update_payload))
            
            # Mark for human review
            try:
                from app.services.frontapp_service import add_conversation_tags
                if email_obj.front_conversation_id:
                    add_conversation_tags(email_obj.front_conversation_id, ["AI: Human review required"])
                    logger.info(f"Added 'AI: Human review required' tag to conversation {email_obj.front_conversation_id} after processing failure.")
            except Exception as tag_exc:
                logger.error(f"Failed to add AI-review tag for conversation {email_obj.front_conversation_id}: {tag_exc}")
            
            
            # Check if all attachments are processed
            _check_document_processing_completion_and_trigger_orchestration(updated_email, completed_count, str(email_uuid), str(email_uuid))
        else:
            logger.error(f"Email {email_uuid} not found when handling document processing failure")
    except Exception as db_exc:
        logger.exception(f"Database error handling document processing failure for email {email_uuid}: {db_exc}")
        if db.is_active:
            db.rollback()
    finally:
        if db.is_active:
            db.close()


# Legacy function name for backward compatibility
send_attachment_to_ocr = send_attachment_to_document_processing
