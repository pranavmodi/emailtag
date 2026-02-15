"""
Unified Lien Agent - Handles both ASL (Attorney Signed) and PSL (Patient Signed) Lien requests.

This module contains the logic for an AI agent that processes emails tagged
as "ASL > Rad Lien", "ASL > Tech Lien", "PSL > Rad Lien", or "PSL > Tech Lien".
It checks for lien modifications, verifies readability, and either uploads to
patient file or requests human review.
"""
import asyncio
import os
import json
import httpx
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from datetime import datetime

from celery.utils.log import get_task_logger
from app.core.config import settings as app_settings_instance
from app.services import frontapp_service
from app.agents.agent_helpers import (
    send_reply_to_front_direct,
    extract_patient_id_from_email_logic,
    get_patient_and_study_info,
    compile_study_participants,
    _append_autoresponse_signature,
)
from app.mcp import call_mcp_tool
from collections import defaultdict

# --- BEGIN: Logging ---
logger = get_task_logger(__name__)
# --- END: Logging ---

# --- BEGIN: Tag Constants ---
TAG_AI_HUMAN_REVIEW_REQUIRED = "AI: Human review required"
TAG_LIEN_MODIFIED = "Lien Modified"
TAG_PATIENT_DEMO = "Patient Demo"  # Tag for patient demographic documents
RAD_LIEN_TAG = "Rad Lien"
TECH_LIEN_TAG = "Tech Lien"
# --- END: Tag Constants ---

# --- BEGIN: Westfax Constants ---
WESTFAX_SENDER_EMAIL = "westfaxff@westfax.com"
# --- END: Westfax Constants ---

# --- BEGIN: Test Mode Constants ---
LIEN_TEST_UPLOAD_DIR = "/tmp/lien_test_uploads"
# --- END: Test Mode Constants ---


def _tag_for_human_review(conversation_id: str, additional_tags: List[str] = None) -> bool:
    """
    Tag conversation for human review and unassign it.

    Args:
        conversation_id: The Front conversation ID
        additional_tags: Optional list of additional tags to add alongside the human review tag

    Returns:
        bool: True if both operations succeeded, False otherwise
    """
    tags_to_add = [TAG_AI_HUMAN_REVIEW_REQUIRED]
    if additional_tags:
        tags_to_add.extend(additional_tags)

    tag_success = frontapp_service.add_conversation_tags(conversation_id, tags_to_add)
    unassign_success = frontapp_service.unassign_conversation(conversation_id)

    if not tag_success:
        logger.warning(f"Failed to add human review tag to conversation {conversation_id}")
    if not unassign_success:
        logger.warning(f"Failed to unassign conversation {conversation_id}")

    return tag_success and unassign_success


# --- NOTE: All lien response templates are now managed via /settings/template-config ---
# Templates are fetched from database via _fetch_lien_templates_from_db()

# --- BEGIN: Helper Functions ---


class _SafeFormatDict(defaultdict):
    """A defaultdict that returns the key wrapped in braces for missing keys.
    Used for safe template formatting so unknown placeholders like {patient_id}
    don't raise KeyError — they are left as-is in the output."""

    def __missing__(self, key):
        return "{" + key + "}"


def _safe_format_template(template: str, max_iterations: int = 10, **kwargs) -> str:
    """
    Format a template string with nested placeholder resolution.

    Performs multiple passes until no more replacements are made or max iterations reached.
    This allows placeholders within placeholder values to be resolved.

    Example: If {greeting} = "Hello {patient_name}" and {patient_name} = "Jane Smith",
    the result will be "Hello Jane Smith" after two passes.

    Args:
        template: The template string with placeholders
        max_iterations: Maximum number of passes to prevent infinite loops (default: 10)
        **kwargs: Placeholder key-value pairs

    Returns:
        The template with all nested placeholders resolved, unknown placeholders left intact
    """
    result = template
    for _ in range(max_iterations):
        previous = result
        safe = _SafeFormatDict(str, **kwargs)
        try:
            result = result.format_map(safe)
        except (KeyError, ValueError) as e:
            # If formatting fails, return what we have
            logger.warning(f"Template formatting error during nested resolution: {e}")
            break

        if result == previous:
            break  # No more replacements made

    return result


async def _build_rejection_placeholder_values(
    patient_id: Optional[str],
    lien_type: str,
    signature_type: str,
    custom_placeholders: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Build a full set of placeholder values for rejection templates.
    Fetches patient info and lien status table when patient_id is available.
    Returns a dict suitable for template formatting.
    """
    values: Dict[str, str] = {
        "lien_type": lien_type or "",
        "patient_id": patient_id or "",
        "patient_name": "",
        "dob": "",
        "doi": "",
        "lien_status_table": "",
        "call_log_table": "",
        "text_log_table": "",
        "billing_status_table": "",
    }

    if patient_id:
        try:
            # Fetch patient info
            patient_info_response = await call_mcp_tool(
                tool_name="fetch_patient_info",
                arguments={"patient_id": patient_id}
            )

            if patient_info_response and isinstance(patient_info_response, dict):
                data_section = patient_info_response.get('data', {})
                if data_section and isinstance(data_section, dict):
                    patients_list = data_section.get('patients', [])
                    if patients_list and len(patients_list) > 0:
                        patient = patients_list[0]
                        first_name = patient.get('first_name', '').strip()
                        last_name = patient.get('last_name', '').strip()
                        if first_name and last_name:
                            values["patient_name"] = f"{first_name} {last_name}"
                        elif first_name:
                            values["patient_name"] = first_name
                        elif last_name:
                            values["patient_name"] = last_name

                        raw_dob = patient.get('birth_date')
                        if raw_dob:
                            try:
                                date_obj = datetime.strptime(raw_dob, '%Y-%m-%d')
                                values["dob"] = date_obj.strftime('%m/%d/%Y')
                            except Exception:
                                values["dob"] = raw_dob

                        raw_doi = patient.get('doi')
                        if raw_doi:
                            try:
                                date_obj = datetime.strptime(raw_doi, '%Y-%m-%d')
                                values["doi"] = date_obj.strftime('%m/%d/%Y')
                            except Exception:
                                values["doi"] = raw_doi

            # Generate lien status table (no upload results for rejections)
            values["lien_status_table"] = await _generate_lien_status_table(patient_id, [], signature_type)

            # Generate call log table
            from app.helpers.call_log_table import generate_call_log_table
            values["call_log_table"] = await generate_call_log_table(patient_id)

            # Generate text log table
            from app.helpers.text_log_table import generate_text_log_table
            values["text_log_table"] = await generate_text_log_table(patient_id)

            # Generate billing status table
            from app.helpers.billing_status_table import generate_billing_status_table
            values["billing_status_table"] = await generate_billing_status_table(patient_id)

        except Exception as e:
            logger.warning(f"Failed to fetch patient info for rejection template: {e}")

    # Merge custom workspace placeholders
    if custom_placeholders:
        values.update(custom_placeholders)

    return values


async def _fetch_custom_placeholders_from_db() -> Dict[str, str]:
    """
    Fetch workspace custom placeholders from database tag_settings.

    Returns:
        Dictionary of custom placeholder key-value pairs
    """
    try:
        from app.crud.tag_settings import tag_settings_crud
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            # Load workspace custom placeholders (global)
            workspace_settings = await tag_settings_crud.get_settings_dict(db, "WORKSPACE")

            if workspace_settings and "custom_placeholders" in workspace_settings:
                custom_placeholders = workspace_settings["custom_placeholders"]
                logger.info(f"✅ Loaded {len(custom_placeholders)} custom placeholders from WORKSPACE")
                return custom_placeholders
            else:
                logger.warning(f"⚠️ No WORKSPACE custom placeholders found")
                return {}

    except Exception as e:
        logger.error(f"❌ Error fetching custom placeholders: {e}")
        return {}

async def _fetch_lien_templates_from_db(tag_name: str) -> Dict[str, str]:
    """
    Fetch lien templates from database tag_settings.

    Args:
        tag_name: Tag name to fetch settings for ("ASL Lien" or "PSL Lien")

    Returns:
        Dictionary with template keys mapped to template content
    """
    try:
        from app.crud.tag_settings import tag_settings_crud
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            tag_settings = await tag_settings_crud.get_by_tag_name(db, tag_name)

            if tag_settings and tag_settings.settings:
                settings = tag_settings.settings
                # Use exact key names from frontend template-config
                return {
                    "success": settings.get("lien_success_template", ""),
                    "unreadable": settings.get("lien_reject_not_readable_template", ""),
                    "patient_not_found": settings.get("lien_patient_not_found_template", ""),
                    "modified": settings.get("lien_reject_no_changes_template", ""),
                    "invalid_signature": settings.get("lien_reject_sig_not_valid_template", ""),
                    # New specific templates for conditional language
                    "cover_letter_conditional": settings.get("lien_reject_cover_letter_conditional_template", ""),
                    "email_conditional": settings.get("lien_reject_email_conditional_template", "")
                }
    except Exception as e:
        logger.error(f"Failed to fetch lien templates from database: {e}")

    # Return empty templates if database fetch fails - this should not happen in production
    logger.error(f"Could not load lien templates for tag '{tag_name}' - templates will be empty!")
    return {
        "success": "",
        "unreadable": "",
        "patient_not_found": "",
        "modified": "",
        "invalid_signature": "",
        "cover_letter_conditional": "",
        "email_conditional": ""
    }

def _check_lien_readability(document_analysis_results: List[Dict[str, Any]]) -> bool:
    """
    Check if lien documents are readable based on OCR confidence and analysis results.

    Args:
        document_analysis_results: List of document analysis results

    Returns:
        True if lien is readable, False if unreadable/blurry
    """
    if not document_analysis_results:
        return False

    for doc_result in document_analysis_results:
        # Check if document analysis succeeded
        if not doc_result.get("document_analysis", {}).get("success"):
            logger.warning("Document analysis failed - considering unreadable")
            return False

        # Check analysis confidence
        analysis_data = doc_result.get("document_analysis", {}).get("data", {})
        confidence = analysis_data.get("confidence", 0.0)

        # If confidence is very low, document might be unreadable
        if confidence < 0.3:  # 30% threshold for readability
            logger.warning(f"Low analysis confidence ({confidence}) - document may be unreadable")
            return False

        # Check if description indicates the document is truly unreadable
        # Note: "blurry" is acceptable - only flag if document is completely unreadable
        description = analysis_data.get("description", "").lower()
        unreadable_issues = ["unreadable", "illegible", "corrupted", "cannot read"]

        if any(issue in description for issue in unreadable_issues):
            logger.warning(f"Document description indicates unreadable: {description}")
            return False

    return True

def _check_signature_placement(document_analysis_results: List[Dict[str, Any]]) -> bool:
    """
    Check if signatures are placed inside designated signature boxes.

    Args:
        document_analysis_results: List of document analysis results containing signature data

    Returns:
        True if all signatures are properly placed, False if any are outside boxes
    """
    if not document_analysis_results:
        # No documents to check - consider valid
        return True

    for doc_result in document_analysis_results:
        # Get enhanced lien processing data which contains signature placement info
        enhanced_lien_data = doc_result.get("enhanced_lien_processing", {})

        # Check if we have signature placement data from each split document
        split_documents = enhanced_lien_data.get("split_documents", [])

        for split_doc in split_documents:
            # Check signature placement validity for this document/page
            signature_data = split_doc.get("signature_data", {})

            if signature_data:
                placement_valid = signature_data.get("placement_valid", True)
                placement_issues = signature_data.get("placement_issues", [])

                if not placement_valid or placement_issues:
                    logger.warning(f"⚠️ SIGNATURE PLACEMENT: Signature(s) COMPLETELY OUTSIDE box - {placement_issues}")
                    return False

    # All signatures are properly placed
    return True

def _check_document_quality(email_obj: Any) -> Tuple[bool, str]:
    """
    Check document quality from lien modification detection results.

    Args:
        email_obj: Email database object with lien modification detection results

    Returns:
        Tuple of (is_readable: bool, quality: str)
        - is_readable: True if quality is GOOD or BLURRY, False only if UNREADABLE
        - quality: "GOOD", "BLURRY", or "UNREADABLE"
    """
    if not hasattr(email_obj, 'lien_modification_results') or not email_obj.lien_modification_results:
        # No modification detection results - assume readable
        logger.info("📄 QUALITY: No modification detection results, assuming GOOD quality")
        return (True, "GOOD")

    # lien_modification_results is a list of detection results per attachment
    for result in email_obj.lien_modification_results:
        # Extract quality from the result
        document_quality = result.get("document_quality", "GOOD")

        # Only flag as unreadable if quality is UNREADABLE (BLURRY is acceptable)
        if document_quality == "UNREADABLE":
            logger.warning(f"📄 QUALITY: Document is UNREADABLE - requesting clearer scan")
            return (False, document_quality)

    # All attachments have acceptable quality (GOOD or BLURRY)
    logger.info("📄 QUALITY: All documents assessed as readable (GOOD or BLURRY)")
    return (True, "GOOD")

def _check_duplicate_barcodes(document_analysis_results: List[Dict[str, Any]]) -> Tuple[bool, bool]:
    """
    Check if duplicate barcodes were detected across multiple pages.

    Args:
        document_analysis_results: List of document analysis results

    Returns:
        Tuple of (has_duplicate_barcodes, duplicates_are_spanish_copies)
    """
    if not document_analysis_results:
        return False, False

    for doc_result in document_analysis_results:
        enhanced_lien_data = doc_result.get("enhanced_lien_processing", {})
        has_duplicate_barcodes = enhanced_lien_data.get("has_duplicate_barcodes", False)

        if has_duplicate_barcodes:
            duplicates_are_spanish_copies = enhanced_lien_data.get("duplicates_are_spanish_copies", False)
            spanish_page_indices = enhanced_lien_data.get("spanish_page_indices", [])
            logger.warning("⚠️ DUPLICATE BARCODES: Same barcode found on multiple pages")
            if duplicates_are_spanish_copies:
                logger.info(f"📄 DUPLICATE BARCODES: Duplicates are English+Spanish lien copies (Spanish pages: {spanish_page_indices})")
            return True, duplicates_are_spanish_copies

    return False, False


def _score_split_document(split_doc: Dict[str, Any], signature_type: str = "ASL") -> int:
    """
    Score a split document based on quality indicators.

    Higher score = better quality document. Used for deduplication to keep
    the best copy when multiple identical liens exist.

    Scoring criteria:
    - Signature placement valid: +20 points
    - No placement issues: +10 points (minus 5 per issue)
    - Required signature present: +15 points
    - Signature inside box: +10 points
    - Has signature data at all: +5 points

    Args:
        split_doc: Split document dictionary with signature_data
        signature_type: "ASL" or "PSL" to determine which signature to check

    Returns:
        Integer score (higher is better)
    """
    score = 0
    signature_data = split_doc.get("signature_data", {})

    # No signature data = lowest priority
    if not signature_data:
        return score

    # Has signature data
    score += 5

    # Signature placement validity (+20 if valid)
    if signature_data.get("placement_valid", False):
        score += 20

    # Placement issues (start with +10, subtract 5 per issue)
    placement_issues = signature_data.get("placement_issues", [])
    issue_penalty = len(placement_issues) * 5
    score += max(0, 10 - issue_penalty)

    # Check for required signature based on type
    if signature_type.upper() == "ASL":
        # Attorney Signed Lien - need attorney signature
        if signature_data.get("attorney_signature_present", False):
            score += 15
        if signature_data.get("attorney_signature_inside_box", False):
            score += 10
    else:
        # Patient Signed Lien - need patient signature
        if signature_data.get("patient_signature_present", False):
            score += 15
        if signature_data.get("patient_signature_inside_box", False):
            score += 10

    return score


async def _regenerate_split_documents(
    attachment_url: str,
    split_metadata: List[Dict[str, Any]],
    max_retries: int = 3
) -> List[Dict[str, Any]]:
    """
    Download attachment and regenerate split PDFs from saved metadata.

    Args:
        attachment_url: Front API URL to download the attachment
        split_metadata: List of split document metadata (without pdf_bytes)
        max_retries: Maximum number of retry attempts for network errors

    Returns:
        List of split documents with pdf_bytes populated
    """
    try:
        logger.info(f"🔄 Downloading attachment to regenerate {len(split_metadata)} splits: {attachment_url}")

        # Download original attachment with retry logic for network errors
        headers = {"Authorization": f"Bearer {app_settings_instance.FRONT_AUTH_TOKEN}"}
        original_pdf_bytes = None
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
                    response = await client.get(attachment_url, headers=headers, timeout=120.0)
                    response.raise_for_status()
                    original_pdf_bytes = response.content
                    break  # Success, exit retry loop
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.NetworkError) as e:
                last_error = e
                if attempt < max_retries:
                    retry_delay = 5 * (2 ** attempt)  # 5s, 10s, 20s exponential backoff
                    logger.warning(
                        f"🔄 Network error downloading attachment (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"❌ Network error after {max_retries + 1} attempts: {e}")
                    raise

        if original_pdf_bytes is None:
            raise last_error or Exception("Failed to download attachment")

        logger.info(f"✅ Downloaded {len(original_pdf_bytes)} bytes from {attachment_url}")

        # Import PDF splitter
        from app.services.lien.pdf_splitter import PDFSplitter

        # Convert metadata to page groupings format
        page_groupings = []
        for split_meta in split_metadata:
            page_groupings.append({
                "pages": split_meta.get("original_pages", []),
                "patient_id": split_meta.get("patient_id", ""),
                "lien_type": split_meta.get("lien_type", ""),
                "page_type": split_meta.get("page_type", "lien"),  # Preserve page_type for patient_demo
                "doc_type_id": split_meta.get("doc_type_id", ""),  # Preserve doc_type_id for patient_demo
                "signature_type": split_meta.get("signature_type", ""),
                "signature_data": split_meta.get("signature_data", {}),
                # Bilingual duplicate metadata for Spanish lien handling
                "is_bilingual_duplicate": split_meta.get("is_bilingual_duplicate", False),
                "english_pages": split_meta.get("english_pages", []),
                "spanish_pages": split_meta.get("spanish_pages", [])
            })

        # Re-split the PDF
        splitter = PDFSplitter()
        split_documents = splitter.split_pdf_by_groups(original_pdf_bytes, page_groupings)

        logger.info(f"✅ Re-generated {len(split_documents)} split documents with pdf_bytes")
        return split_documents

    except Exception as e:
        logger.error(f"Failed to regenerate split documents from {attachment_url}: {e}", exc_info=True)
        return []

async def _check_duplicate_lien_type(patient_id: str, lien_type: str, signature_type: str) -> Tuple[bool, str]:
    """
    Check if patient already has the exact same lien type in RadFlow.

    Args:
        patient_id: Patient ID (e.g., "PRE123456")
        lien_type: Lien type being uploaded ("TECH" or "RAD")
        signature_type: Signature type being uploaded ("ASL" or "PSL")

    Returns:
        Tuple of (has_duplicate: bool, reason: str)
    """
    try:
        logger.info(f"🔍 DUPLICATE CHECK: Checking for existing {lien_type} {signature_type} lien for patient {patient_id}")

        # Fetch existing liens from RadFlow
        lien_status_response = await call_mcp_tool(
            tool_name="get_patient_lien_bill_balance",
            arguments={"patient_id": patient_id}
        )

        if not lien_status_response or not lien_status_response.get("success"):
            logger.warning("⚠️ DUPLICATE CHECK: Could not fetch lien status, allowing upload")
            return (False, "Could not fetch lien status")

        # Parse existing liens
        data = lien_status_response.get("data", {})
        result = data.get("result", {})
        lien_status_list = result.get("lienStatusList", [])

        for lien in lien_status_list:
            existing_lien_type = lien.get("lienType", "").upper()
            patient_signed = lien.get("hasPatientSigned", False)
            attorney_signed = lien.get("hasAttorneySigned", False)

            # Map to standard lien type
            standard_lien_type = None
            if "TECH" in existing_lien_type or "IMAGING" in existing_lien_type:
                standard_lien_type = "TECH"
            elif "RAD" in existing_lien_type or "PROFESSIONAL" in existing_lien_type or "MEDICAL" in existing_lien_type or "RADIOLOGIST" in existing_lien_type:
                standard_lien_type = "RAD"

            if not standard_lien_type:
                continue

            # Determine existing signature type
            existing_signature_type = None
            if attorney_signed:
                existing_signature_type = "ASL"
            elif patient_signed:
                existing_signature_type = "PSL"

            # Check for exact match (same lien type AND same signature type)
            if standard_lien_type == lien_type and existing_signature_type == signature_type:
                reason = f"Patient already has {lien_type} {signature_type} lien in RadFlow"
                logger.warning(f"⚠️ DUPLICATE LIEN: {reason}")
                return (True, reason)

        logger.info(f"✅ DUPLICATE CHECK: No exact duplicate found, allowing upload")
        return (False, "No duplicate found")

    except Exception as e:
        logger.error(f"Error checking for duplicate lien type: {e}", exc_info=True)
        # On error, allow upload (don't block on technical failure)
        return (False, f"Error during duplicate check: {e}")

def _check_lien_modifications(email_obj: Any) -> bool:
    """
    Check if lien has modifications based on email processing results.

    Args:
        email_obj: Email database object with lien modification detection results

    Returns:
        True if modifications detected, False otherwise
    """
    # Check if lien modification detection was run and found modifications
    if hasattr(email_obj, 'lien_modifications_detected') and email_obj.lien_modifications_detected:
        logger.info("Lien modifications detected in email processing")
        return True

    return False

def _has_lien_modified_tag(applied_tags: List[str]) -> bool:
    """Check if 'Lien Modified' tag is present in applied tags."""
    return TAG_LIEN_MODIFIED in applied_tags

def _determine_lien_type(applied_tags: List[str], signature_type: str) -> str:
    """
    Determine lien type based on tags and signature type.

    Args:
        applied_tags: List of applied tags
        signature_type: "ASL" or "PSL"

    Returns:
        Full lien type string
    """
    signature_prefix = "Attorney Signed" if signature_type == "ASL" else "Patient Signed"

    if RAD_LIEN_TAG in applied_tags:
        return f"{signature_prefix} Radiologist Lien"
    elif TECH_LIEN_TAG in applied_tags:
        return f"{signature_prefix} Technologist Lien"
    else:
        return f"{signature_prefix} Lien"

async def _upload_lien_to_patient_file(patient_id: str, lien_type: str, attachment_data: Dict[str, Any], conversation_id: str = None) -> bool:
    """
    Upload lien document to patient file via RadFlow API (using shared service).

    Args:
        patient_id: Patient ID to upload document for
        lien_type: Type of lien being uploaded
        attachment_data: Attachment data with URL to download
        conversation_id: Front conversation ID (for test mode file organization)

    Returns:
        True if upload successful, False otherwise
    """
    from app.services.lien_upload_service import upload_lien_to_radflow

    return await upload_lien_to_radflow(patient_id, lien_type, attachment_data, conversation_id)

async def _generate_lien_status_table(patient_id: str, upload_results: List[Dict[str, Any]], signature_type: str = "ASL") -> str:
    """
    Generate HTML table showing lien signature status for patient.

    Fetches real-time lien signature status from RadFlow API and displays it in a formatted table.

    Args:
        patient_id: Patient ID to fetch lien status for
        upload_results: List of upload results from split documents
        signature_type: "ASL" or "PSL" to determine which signature column to show

    Returns:
        HTML table string with lien status information
    """
    try:
        logger.info(f"📊 Generating lien status table for patient {patient_id} (signature_type: {signature_type})")

        # Fetch actual lien status from RadFlow API via MCP tool
        lien_status_response = await call_mcp_tool(
            tool_name="get_patient_lien_bill_balance",
            arguments={"patient_id": patient_id}
        )

        # Parse lien status from MCP response
        lien_signatures = {}  # Map of lien_type -> {"patient_signed": bool, "attorney_signed": bool, "patient_date": str, "attorney_date": str}

        if lien_status_response and lien_status_response.get("success"):
            data = lien_status_response.get("data", {})
            result = data.get("result", {})
            patient_esign_link = result.get("patientEsignLink")
            attorney_esign_link = result.get("attorneyEsignLink")
            lien_status_list = result.get("lienStatusList") or []

            for lien in lien_status_list:
                lien_type = lien.get("lienType", "").upper()
                patient_signed = lien.get("hasPatientSigned", False)
                attorney_signed = lien.get("hasAttorneySigned", False)
                patient_signed_date = lien.get("patientSignedLienDate", "")
                attorney_signed_date = lien.get("attorneySignedDate", "")

                # Map lien type to our standard names
                if "TECH" in lien_type or "IMAGING" in lien_type:
                    standard_type = "TECH"
                elif "RAD" in lien_type or "PROFESSIONAL" in lien_type or "MEDICAL" in lien_type or "RADIOLOGIST" in lien_type:
                    standard_type = "RAD"
                else:
                    continue

                lien_signatures[standard_type] = {
                    "patient_signed": patient_signed,
                    "attorney_signed": attorney_signed,
                    "patient_date": patient_signed_date,
                    "attorney_date": attorney_signed_date
                }

            logger.info(f"📊 Fetched lien status from RadFlow: {lien_signatures}")
        else:
            logger.warning(f"📊 Could not fetch lien status from RadFlow, using upload results as fallback")

        # Build table rows
        rows = []
        lien_types_to_show = set()

        # PRIORITY 1: Use lien signatures from API (most accurate source)
        if lien_signatures:
            lien_types_to_show = set(lien_signatures.keys())
            logger.info(f"📊 Using lien types from RadFlow API: {lien_types_to_show}")
        else:
            # FALLBACK: Collect lien types from upload results
            for result in upload_results:
                lien_type_code = result.get("lien_type", "").upper()
                if lien_type_code in ["TECH", "TC", "TECHNOLOGIST"]:
                    lien_types_to_show.add("TECH")
                elif lien_type_code in ["RAD", "RADIOLOGY"]:
                    lien_types_to_show.add("RAD")
            logger.info(f"📊 Using lien types from upload results: {lien_types_to_show}")

        # Generate rows for each lien type
        for lien_type_code in sorted(lien_types_to_show):
            # Map lien type code to display name
            if lien_type_code == "TECH":
                lien_display_name = "Technical Lien (Imaging)"
            elif lien_type_code == "RAD":
                lien_display_name = "Professional Lien (Report)"
            else:
                continue

            # Get signature status from API or fallback to upload results
            if lien_type_code in lien_signatures:
                sig_info = lien_signatures[lien_type_code]

                # Format patient signature status
                if sig_info["patient_signed"]:
                    patient_date = sig_info["patient_date"]
                    if patient_date:
                        # Try multiple date formats (MCP returns "MM/DD/YYYY HH:MM:SS" format)
                        try:
                            # Try "MM/DD/YYYY HH:MM:SS" format first
                            date_obj = datetime.strptime(patient_date.split()[0], '%m/%d/%Y')
                            formatted_date = date_obj.strftime('%m/%d/%Y')
                        except:
                            try:
                                # Try "YYYY-MM-DD" format
                                date_obj = datetime.strptime(patient_date, '%Y-%m-%d')
                                formatted_date = date_obj.strftime('%m/%d/%Y')
                            except:
                                # Use as-is if both fail
                                formatted_date = patient_date
                        patient_sig_status = f"Signed {formatted_date}"
                    else:
                        patient_sig_status = "Signed"
                else:
                    if patient_esign_link:
                        patient_sig_status = f'Not Signed.<br/><a href="{patient_esign_link}" target="_blank">Please eSign here</a>'
                    else:
                        patient_sig_status = "Not Signed"

                # Format attorney signature status
                if sig_info["attorney_signed"]:
                    attorney_date = sig_info["attorney_date"]
                    if attorney_date:
                        # Try multiple date formats (MCP returns "MM/DD/YYYY HH:MM:SS" format)
                        try:
                            # Try "MM/DD/YYYY HH:MM:SS" format first
                            date_obj = datetime.strptime(attorney_date.split()[0], '%m/%d/%Y')
                            formatted_date = date_obj.strftime('%m/%d/%Y')
                        except:
                            try:
                                # Try "YYYY-MM-DD" format
                                date_obj = datetime.strptime(attorney_date, '%Y-%m-%d')
                                formatted_date = date_obj.strftime('%m/%d/%Y')
                            except:
                                # Use as-is if both fail
                                formatted_date = attorney_date
                        attorney_sig_status = f"Signed {formatted_date}"
                    else:
                        attorney_sig_status = "Signed"
                else:
                    if attorney_esign_link:
                        attorney_sig_status = f'Not Signed.<br/><a href="{attorney_esign_link}" target="_blank">Please eSign here</a>'
                    else:
                        attorney_sig_status = "Not Signed"
            else:
                # Fallback: use upload success as indicator
                upload_result = next((r for r in upload_results if r.get("lien_type", "").upper() in [lien_type_code, f"{lien_type_code}OLOGIST"]), None)
                if upload_result and upload_result.get("success"):
                    today = datetime.now().strftime("%m/%d/%Y")
                    patient_sig_status = f"Signed {today}"
                    attorney_sig_status = f"Signed {today}"
                else:
                    patient_sig_status = "Not Signed"
                    attorney_sig_status = "Not Signed"

            row = f"""<tr>
<td style="border: 1px solid black; padding: 8px;">{lien_display_name}</td>
<td style="border: 1px solid black; padding: 8px;">{patient_sig_status}</td>
<td style="border: 1px solid black; padding: 8px;">{attorney_sig_status}</td>
</tr>"""
            rows.append(row)

        # If no rows generated, return empty string
        if not rows:
            logger.info(f"📊 No lien data available for table generation")
            return ""

        # Build complete table
        table = f"""<table border="1" style="border-collapse: collapse; width: 100%; margin-top: 10px;">
<thead>
<tr>
<th style="border: 1px solid black; padding: 8px; text-align: left; background-color: #f0f0f0;">Lien Type</th>
<th style="border: 1px solid black; padding: 8px; text-align: left; background-color: #f0f0f0;">Patient Signature</th>
<th style="border: 1px solid black; padding: 8px; text-align: left; background-color: #f0f0f0;">Attorney Signature</th>
</tr>
</thead>
<tbody>
{''.join(rows)}
</tbody>
</table>"""

        logger.info(f"✅ Generated lien status table with {len(rows)} row(s)")
        return table

    except Exception as e:
        logger.error(f"Error generating lien status table: {e}", exc_info=True)
        return ""


async def save_test_mode_response(
    conversation_id: str,
    response_text: str,
    tags_to_add: Optional[List[str]] = None,
    lien_type: str = None,
    signature_type: str = None
) -> Dict[str, Any]:
    """
    Saves the generated lien autorespond message to file system for test mode.

    Args:
        conversation_id: Front conversation ID
        response_text: The full formatted response message
        tags_to_add: List of tags that would be applied
        lien_type: "Rad Lien" or "Tech Lien"
        signature_type: "ASL" or "PSL"

    Returns:
        Dict with status and file path
    """
    try:
        test_dir = Path(LIEN_TEST_UPLOAD_DIR) / conversation_id
        test_dir.mkdir(parents=True, exist_ok=True)

        response_file = test_dir / "response.json"

        response_data = {
            "timestamp": datetime.now().isoformat(),
            "conversation_id": conversation_id,
            "response_text": response_text,
            "tags_to_add": tags_to_add or [],
            "lien_type": lien_type,
            "signature_type": signature_type,
            "status": "test_mode_saved"
        }

        with open(response_file, "w") as f:
            json.dump(response_data, f, indent=2)

        logger.info(f"🧪 TEST MODE: Saved response to {response_file}")

        return {
            "status": "success",
            "file_path": str(response_file),
            "message": "Response saved to file (test mode)"
        }

    except Exception as e:
        logger.error(f"Error saving test mode response: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to save response: {str(e)}"
        }


async def fetch_attorney_and_case_manager_from_participants(patient_id: str) -> Dict[str, Any]:
    """
    Fetches study participants for a patient and extracts the attorney email
    and case manager notification preferences.

    Args:
        patient_id: The patient ID (e.g., "PRE123456")

    Returns:
        Dictionary with:
            attorney_email: str or None
            notify_case_manager: bool
            case_manager_email: str or None
    """
    result = {
        "attorney_email": None,
        "notify_case_manager": False,
        "case_manager_email": None
    }

    try:
        # Get patient and study info
        patient_study_info = await get_patient_and_study_info(patient_id)

        study_result = patient_study_info.get("study_result", {})
        if not study_result.get("success", False):
            logger.warning(f"Failed to fetch study info for patient {patient_id}: {study_result.get('error', 'Unknown')}")
            return result

        # Extract studies list from the response
        studies = []
        study_data = study_result.get("data", {})
        if isinstance(study_data, dict):
            studies = study_data.get("studies", []) or study_data.get("result", [])
        elif isinstance(study_data, list):
            studies = study_data

        if not studies:
            logger.warning(f"No studies found for patient {patient_id}")
            return result

        # Compile participants across all studies
        participants_result = await compile_study_participants(patient_id, studies)

        if not participants_result.get("success") or not participants_result.get("participants"):
            logger.warning(f"No participants found for patient {patient_id}")
            return result

        participants = participants_result["participants"]
        logger.info(f"🔍 WESTFAX: Found {len(participants)} participants for patient {patient_id}")

        # Log raw participant data for debugging new fields
        for p in participants:
            logger.info(f"🔍 WESTFAX PARTICIPANT: role={p.get('role')}, email={p.get('email')}, "
                        f"notifyCaseManager={p.get('notifyCaseManager', 'N/A')}, "
                        f"caseManagerEmail={p.get('caseManagerEmail', 'N/A')}")

        # Find attorney participant
        for participant in participants:
            role = (participant.get("role") or "").lower()
            if "attorney" in role and participant.get("email"):
                result["attorney_email"] = participant["email"]
                logger.info(f"✅ WESTFAX: Found attorney email: {result['attorney_email']} (role: {role})")

                # Check for case manager fields on the participant
                if participant.get("notifyCaseManager"):
                    result["notify_case_manager"] = True
                    result["case_manager_email"] = participant.get("caseManagerEmail")
                break

        # Also check at the study/response level for case manager fields
        # (in case Malhar added them at the study level rather than participant level)
        if result["attorney_email"] and not result["notify_case_manager"]:
            for study in studies:
                if study.get("notifyCaseManager"):
                    result["notify_case_manager"] = True
                    result["case_manager_email"] = study.get("caseManagerEmail")
                    logger.info(f"✅ WESTFAX: Found case manager info at study level: "
                                f"notify={result['notify_case_manager']}, email={result['case_manager_email']}")
                    break

        if not result["attorney_email"]:
            logger.warning(f"⚠️ WESTFAX: No attorney found in participants for patient {patient_id}")

    except Exception as e:
        logger.error(f"Error fetching attorney/case manager for patient {patient_id}: {e}", exc_info=True)

    return result


async def send_or_save_response(
    conversation_id: str,
    response_text: str,
    tags_to_add: Optional[List[str]] = None,
    test_mode: bool = False,
    lien_type: str = None,
    signature_type: str = None,
    to_recipients: Optional[List[str]] = None,
    cc_recipients: Optional[List[str]] = None
) -> None:
    """
    Either sends the response via Front API or saves to file based on test_mode.

    Args:
        conversation_id: Front conversation ID
        response_text: The full formatted response message
        tags_to_add: List of tags to add (for both send and save)
        test_mode: If True, save to file instead of sending
        lien_type: "Rad Lien" or "Tech Lien" (for test mode metadata)
        signature_type: "ASL" or "PSL" (for test mode metadata)
        to_recipients: Optional explicit recipient list (overrides default reply-all)
        cc_recipients: Optional CC recipient list (used with to_recipients)
    """
    if test_mode:
        # Test mode: save to file (include recipient override info in metadata)
        await save_test_mode_response(
            conversation_id=conversation_id,
            response_text=response_text,
            tags_to_add=tags_to_add,
            lien_type=lien_type,
            signature_type=signature_type
        )
        if to_recipients:
            logger.info(f"🧪 TEST MODE: Would send to {to_recipients} (cc: {cc_recipients}) instead of default reply-all")
    elif to_recipients:
        # Directed reply mode: send to explicit recipients
        logger.info(f"📧 Sending directed reply for {conversation_id} to {to_recipients} (cc: {cc_recipients})")
        final_reply_text = _append_autoresponse_signature(response_text)

        reply_sent = await asyncio.to_thread(
            frontapp_service.send_conversation_reply_to_recipients,
            conversation_id,
            final_reply_text,
            to_recipients,
            cc_recipients
        )

        if not reply_sent:
            logger.error(f"Failed to send directed reply for conversation {conversation_id}")
            return

        # Add tags (same as send_reply_to_front_direct)
        if tags_to_add is None:
            tags_to_add = []
        else:
            tags_to_add = list(tags_to_add)
        if "AI handled" not in tags_to_add:
            tags_to_add.append("AI handled")
        await asyncio.to_thread(frontapp_service.add_conversation_tags, conversation_id, tags_to_add)
    else:
        # Normal mode: send via Front API (reply-all)
        await send_reply_to_front_direct(
            conversation_id=conversation_id,
            reply_text=response_text,
            tags_to_add=tags_to_add
        )

# --- END: Helper Functions ---

# --- BEGIN: Main Agent Handler ---

async def handle_lien_request(
    front_conversation_id: str,
    current_email_content: str,
    applied_tags: List[str],
    email_obj: Any,
    signature_type: str,
    document_analysis_results: List[Dict[str, Any]] = None,
    settings_obj: Any = app_settings_instance,
    email_subject: str = None,
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Unified agent to handle both ASL and PSL lien submissions (Rad Lien or Tech Lien).

    Logic:
    1. Check if lien was modified (strikethrough, crossed out, etc.)
       a. If modified, tag for human review and add "Lien Modified" tag
       b. If not modified, proceed to next steps
    2. If no patient found: Tag for human review
    3. If lien is unreadable (blurry/poor quality): Reply with confluence template
    4. If all checks pass: Upload to patient file and reply with success template

    Args:
        front_conversation_id: Front conversation ID
        current_email_content: Current email content
        applied_tags: List of tags applied to this email
        email_obj: Email database object
        signature_type: "ASL" for Attorney Signed, "PSL" for Patient Signed
        document_analysis_results: Results from document analysis
        settings_obj: Settings object
        email_subject: Email subject line

    Returns:
        Dictionary with agent handling results
    """
    logger.info(f"═══════════════════════════════════════════════════════════════════════════════")
    logger.info(f"📋 {signature_type} LIEN AGENT START: Conversation {front_conversation_id}")
    logger.info(f"   Tags: {applied_tags}")
    logger.info(f"   Test Mode: {test_mode}")
    logger.info(f"   Document Analysis Results: {len(document_analysis_results) if document_analysis_results else 0} document(s)")
    logger.info(f"═══════════════════════════════════════════════════════════════════════════════")

    # Detect Westfax sender - liens from Westfax should reply to the attorney, not back to Westfax
    is_westfax_sender = (
        email_obj.sender
        and email_obj.sender.lower().strip() == WESTFAX_SENDER_EMAIL
    )
    if is_westfax_sender:
        logger.info(f"📠 WESTFAX DETECTED: Sender is {email_obj.sender} - will look up attorney for reply")

    # Step 1: Analyze email content for conditional language
    # DISABLED: Email conditional language check disabled per user request
    # Only PDF/attachment conditional language checks are active
    from app.services.lien.cover_letter_detector import CoverLetterDetector
    cover_letter_detector = CoverLetterDetector()
    # email_analysis = await cover_letter_detector.analyze_email_content(current_email_content)
    email_analysis = {"has_conditional_language": False}  # Skip email content check

    # Fetch lien templates from database using unified "Lien Templates" tag
    # (All lien templates are stored under this single tag in the database)
    tag_name = "Lien Templates"
    templates = await _fetch_lien_templates_from_db(tag_name)

    # Fetch workspace custom placeholders (global placeholders available to all templates)
    custom_placeholders = await _fetch_custom_placeholders_from_db()

    # Validate that templates were loaded
    if not templates.get("success"):
        logger.error(f"CRITICAL: Lien success template not configured for tag '{tag_name}'. Please configure templates in /settings/template-config")
        return {
            "agent_handled": False,
            "processed_flag": False,
            "details": {"error": "Templates not configured"}
        }

    # Determine lien type from tags
    lien_type = _determine_lien_type(applied_tags, signature_type)

    # Extract patient ID early so rejection templates can use it
    patient_id = None
    if email_obj.extracted_patient_ids and len(email_obj.extracted_patient_ids) > 0:
        patient_id = email_obj.extracted_patient_ids[0]
        logger.info(f"🔍 LIEN AGENT: Early patient ID from document barcode: {patient_id}")
    else:
        logger.info(f"🔍 LIEN AGENT: No barcode patient ID found early, attempting email text extraction")
        patient_id = await extract_patient_id_from_email_logic(current_email_content, front_conversation_id, email_subject)
        if patient_id:
            logger.info(f"🔍 LIEN AGENT: Early patient ID from email text: {patient_id}")

    # Build placeholder values for rejection templates (patient info, lien status table, etc.)
    rejection_placeholders = await _build_rejection_placeholder_values(
        patient_id=patient_id,
        lien_type=lien_type,
        signature_type=signature_type,
        custom_placeholders=custom_placeholders
    )

    # Step 2: Check email content for conditional language
    if email_analysis.get("has_conditional_language", False):
        logger.warning(f"⚠️ EMAIL CONDITIONAL LANGUAGE: Detected in email content for conversation {front_conversation_id}")
        conditional_phrases = email_analysis.get("conditional_phrases_found", [])
        logger.warning(f"   Conditional phrases: {conditional_phrases}")

        try:
            # Add human review tag, lien modified tag, and unassign
            tags_to_add = [TAG_AI_HUMAN_REVIEW_REQUIRED, TAG_LIEN_MODIFIED]
            _tag_for_human_review(front_conversation_id, additional_tags=[TAG_LIEN_MODIFIED])

            # Add comment to conversation describing the modification (no autorespond)
            comment_text = "Lien modification detected: The email body contains conditional language regarding the lien. This lien requires human review before processing."
            if conditional_phrases:
                phrases_list = ", ".join(conditional_phrases[:3])
                comment_text += f" Detected phrases: {phrases_list}"
            frontapp_service.add_conversation_comment(front_conversation_id, comment_text)

            # In test mode, save to sandbox so the conversation appears in the sandbox UI
            if test_mode:
                await save_test_mode_response(
                    conversation_id=front_conversation_id,
                    response_text=comment_text,
                    tags_to_add=tags_to_add,
                    lien_type=lien_type,
                    signature_type=signature_type
                )

            return {
                "agent_handled": True,
                "processed_flag": True,
                "details": {
                    "action": "tagged_for_human_review_email_conditional_language",
                    "lien_type": lien_type,
                    "signature_type": signature_type,
                    "conditional_phrases": conditional_phrases
                }
            }
        except Exception as e:
            logger.error(f"Failed to handle email conditional language: {e}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to handle email conditional language: {e}"}}

    # Step 3: Check document attachments for cover letters with conditional language
    has_cover_letter_with_conditions = False
    cover_letter_phrases = []

    if document_analysis_results:
        for doc_result in document_analysis_results:
            # Check both enhanced_lien_processing and enhanced_lien_processing_split
            enhanced_data = doc_result.get("enhanced_lien_processing_split", doc_result.get("enhanced_lien_processing", {}))
            if enhanced_data.get("has_cover_letter_with_conditions", False):
                has_cover_letter_with_conditions = True
                cover_letter_phrases.extend(enhanced_data.get("conditional_phrases_found", []))

    if has_cover_letter_with_conditions:
        logger.warning(f"⚠️ COVER LETTER CONDITIONAL LANGUAGE: Detected in attachments for conversation {front_conversation_id}")
        logger.warning(f"   Conditional phrases: {cover_letter_phrases}")

        try:
            # Add human review tag, lien modified tag, and unassign
            tags_to_add = [TAG_AI_HUMAN_REVIEW_REQUIRED, TAG_LIEN_MODIFIED]
            _tag_for_human_review(front_conversation_id, additional_tags=[TAG_LIEN_MODIFIED])

            # Add comment to conversation describing the modification (no autorespond)
            comment_text = "Lien modification detected: The attached cover letter contains conditional language. This lien requires human review before processing."
            if cover_letter_phrases:
                phrases_list = ", ".join(cover_letter_phrases[:3])
                comment_text += f" Detected phrases: {phrases_list}"
            frontapp_service.add_conversation_comment(front_conversation_id, comment_text)

            # In test mode, save to sandbox so the conversation appears in the sandbox UI
            if test_mode:
                await save_test_mode_response(
                    conversation_id=front_conversation_id,
                    response_text=comment_text,
                    tags_to_add=tags_to_add,
                    lien_type=lien_type,
                    signature_type=signature_type
                )

            return {
                "agent_handled": True,
                "processed_flag": True,
                "details": {
                    "action": "tagged_for_human_review_cover_letter_conditions",
                    "lien_type": lien_type,
                    "signature_type": signature_type,
                    "conditional_phrases": cover_letter_phrases
                }
            }
        except Exception as e:
            logger.error(f"Failed to handle cover letter conditional language: {e}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to handle cover letter conditional language: {e}"}}

    # Step 4: Check if lien belongs to another company (not Precise Imaging)
    other_company_detected = False
    detected_company_name = None

    if document_analysis_results:
        for doc_result in document_analysis_results:
            # Check both enhanced_lien_processing and enhanced_lien_processing_split
            enhanced_data = doc_result.get("enhanced_lien_processing_split", doc_result.get("enhanced_lien_processing", {}))
            if enhanced_data.get("other_company_detected"):
                other_company_detected = True
                detected_company_name = enhanced_data.get("detected_company_name", "Unknown")
                break

    if other_company_detected:
        logger.warning(f"⚠️ OTHER COMPANY LIEN: Detected lien from '{detected_company_name}' for conversation {front_conversation_id}")

        try:
            # Add human review tag and unassign (no autoresponse for errors)
            _tag_for_human_review(front_conversation_id)

            # Add comment explaining why human review is needed
            comment_text = f"Other company lien detected: This lien appears to be from '{detected_company_name}', not Precise Imaging. Please review and handle accordingly."
            frontapp_service.add_conversation_comment(front_conversation_id, comment_text)

            return {
                "agent_handled": True,
                "processed_flag": True,
                "details": {
                    "action": "tagged_for_human_review_other_company",
                    "detected_company": detected_company_name,
                    "lien_type": lien_type,
                    "signature_type": signature_type
                }
            }
        except Exception as e:
            logger.error(f"Failed to handle other company lien: {e}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to handle other company lien: {e}"}}

    # Check for lien modifications (strikethrough)
    has_modifications = _check_lien_modifications(email_obj) or _has_lien_modified_tag(applied_tags)

    if has_modifications:
        logger.info(f"Lien modifications detected for conversation {front_conversation_id}. Tagging for human review.")

        try:
            # Add human review tag, lien modified tag if not already present, and unassign
            additional_tags = [TAG_LIEN_MODIFIED] if not _has_lien_modified_tag(applied_tags) else None
            tags_to_add = [TAG_AI_HUMAN_REVIEW_REQUIRED] + (additional_tags or [])
            _tag_for_human_review(front_conversation_id, additional_tags=additional_tags)

            # Add comment to conversation describing the modification (no autorespond)
            # Build a descriptive comment from the modification results if available
            comment_text = "Lien modification detected: The attached document appears to contain strikethroughs, crossed-out text, or other modifications. This lien requires human review before processing."
            if hasattr(email_obj, 'lien_modification_results') and email_obj.lien_modification_results:
                for mod_result in email_obj.lien_modification_results:
                    if mod_result.get("modifications_detected"):
                        strikethrough_data = mod_result.get("strikethrough_data", {})
                        instances = strikethrough_data.get("strikethrough_text", [])
                        if instances:
                            details = []
                            for inst in instances:
                                text = inst.get("text", "").strip()
                                if text and len(text.split()) >= 4:
                                    details.append(text)
                            if details:
                                detail_text = "; ".join(details[:3])
                                comment_text += f" Struck-through text found: {detail_text}"
                        break
            frontapp_service.add_conversation_comment(front_conversation_id, comment_text)

            # In test mode, save to sandbox so the conversation appears in the sandbox UI
            if test_mode:
                await save_test_mode_response(
                    conversation_id=front_conversation_id,
                    response_text=comment_text,
                    tags_to_add=tags_to_add,
                    lien_type=lien_type,
                    signature_type=signature_type
                )

            return {
                "agent_handled": True,
                "processed_flag": True,
                "details": {
                    "action": "tagged_for_human_review_modified",
                    "lien_type": lien_type,
                    "signature_type": signature_type
                }
            }
        except Exception as e:
            logger.error(f"Failed to handle modified lien: {e}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to handle modified lien: {e}"}}

    # Check signature placement validity
    signature_placement_valid = _check_signature_placement(document_analysis_results)
    if not signature_placement_valid:
        logger.info(f"Signature placement invalid for conversation {front_conversation_id}. Requesting properly signed lien.")

        try:
            # Add human review tag and unassign
            _tag_for_human_review(front_conversation_id)

            # Add comment explaining why human review is needed
            comment_text = f"Invalid signature placement: The {signature_type} {lien_type} lien signature does not appear to be in the correct location. Please review the document and verify signature placement."
            frontapp_service.add_conversation_comment(front_conversation_id, comment_text)

            # Send reply if template is configured
            if templates.get("invalid_signature"):
                await send_or_save_response(
                    conversation_id=front_conversation_id,
                    response_text=_safe_format_template(templates["invalid_signature"], **rejection_placeholders),
                    tags_to_add=None,
                    test_mode=test_mode,
                    lien_type=lien_type,
                    signature_type=signature_type
                )
            else:
                logger.warning(f"Invalid signature template not configured for tag '{tag_name}'. No autoresponse sent.")

            return {
                "agent_handled": True,
                "processed_flag": True,
                "details": {
                    "action": "tagged_for_human_review_signature_placement",
                    "lien_type": lien_type,
                    "signature_type": signature_type
                }
            }
        except Exception as e:
            logger.error(f"Failed to handle invalid signature placement: {e}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to handle invalid signature placement: {e}"}}

    # Check document quality (BLURRY/UNREADABLE check)
    is_readable, quality_status = _check_document_quality(email_obj)
    if not is_readable:
        logger.info(f"Document quality poor ({quality_status}) for conversation {front_conversation_id}. Requesting clearer scan.")

        try:
            # Add human review tag and unassign
            _tag_for_human_review(front_conversation_id)

            # Add comment explaining why human review is needed
            comment_text = f"Poor document quality: The attached lien document is {quality_status.lower()}. A clearer scan may be needed."
            frontapp_service.add_conversation_comment(front_conversation_id, comment_text)

            # Send unreadable template
            if templates.get("unreadable"):
                await send_or_save_response(
                    conversation_id=front_conversation_id,
                    response_text=_safe_format_template(templates["unreadable"], **rejection_placeholders),
                    tags_to_add=None,
                    test_mode=test_mode,
                    lien_type=lien_type,
                    signature_type=signature_type
                )
            else:
                logger.warning(f"Unreadable template not configured for tag '{tag_name}'. No autoresponse sent.")

            return {
                "agent_handled": True,
                "processed_flag": True,
                "details": {
                    "action": "tagged_for_human_review_poor_quality",
                    "lien_type": lien_type,
                    "signature_type": signature_type,
                    "quality": quality_status
                }
            }
        except Exception as e:
            logger.error(f"Failed to handle poor document quality: {e}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to handle poor document quality: {e}"}}

    # Check for duplicate barcodes
    has_duplicate_barcodes, duplicates_are_spanish_copies = _check_duplicate_barcodes(document_analysis_results)
    logger.info(f"📄 DUPLICATE CHECK: has_duplicate_barcodes={has_duplicate_barcodes}, duplicates_are_spanish_copies={duplicates_are_spanish_copies}")
    if has_duplicate_barcodes:
        # For ASL liens, allow processing when duplicates are just English+Spanish copies
        # of the same lien. The dedup logic already prefers the English page, so the
        # Spanish copy is dropped and only the English version gets uploaded.
        if duplicates_are_spanish_copies and signature_type == "ASL":
            logger.info(
                f"📄 SPANISH COPY BYPASS: Duplicate barcodes are English+Spanish copies for ASL lien "
                f"in conversation {front_conversation_id}. Allowing normal processing — "
                f"dedup will select the English version for upload."
            )
        else:
            logger.info(f"Duplicate barcodes detected for conversation {front_conversation_id}. Tagging for human review.")

            try:
                # Add human review tag and unassign (no autoresponse for errors)
                _tag_for_human_review(front_conversation_id)

                # Add comment explaining why human review is needed
                comment_text = f"Duplicate barcodes detected: Multiple lien documents with the same barcode were found in this email. Please review to determine which document should be processed."
                frontapp_service.add_conversation_comment(front_conversation_id, comment_text)

                return {
                    "agent_handled": True,
                    "processed_flag": True,
                    "details": {
                        "action": "tagged_for_human_review_duplicate_barcodes",
                        "lien_type": lien_type,
                        "signature_type": signature_type
                    }
                }
            except Exception as e:
                logger.error(f"Failed to handle duplicate barcodes: {e}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to handle duplicate barcodes: {e}"}}

    # NOTE: _check_lien_readability is DISABLED as of 2026-01-15
    # Reason: Redundant with _check_document_quality() which uses AI vision to assess quality.
    # _check_lien_readability checks OCR confidence and analysis success, but this was causing
    # false positives (flagging documents as unreadable when they were actually readable).
    # The _check_document_quality() function (called earlier) now handles quality assessment
    # and only flags documents as unreadable if BOTH AI vision runs return "UNREADABLE".
    # Keeping this code in case we need to re-enable for edge cases.
    #
    # if document_analysis_results and not _check_lien_readability(document_analysis_results):
    #     logger.info(f"Lien document unreadable for conversation {front_conversation_id}. Requesting clearer version.")
    #
    #     try:
    #         # Send reply if template is configured
    #         if templates.get("unreadable"):
    #             await send_or_save_response(
    #                 conversation_id=front_conversation_id,
    #                 response_text=_safe_format_template(templates["unreadable"], **rejection_placeholders),
    #                 tags_to_add=None,
    #                 test_mode=test_mode,
    #                 lien_type=lien_type,
    #                 signature_type=signature_type
    #             )
    #         else:
    #             logger.warning(f"Unreadable lien template not configured for tag '{tag_name}'. No autoresponse sent.")
    #
    #         return {
    #             "agent_handled": True,
    #             "processed_flag": True,
    #             "details": {
    #                 "action": "requested_clearer_document",
    #                 "lien_type": lien_type,
    #                 "signature_type": signature_type
    #             }
    #         }
    #     except Exception as e:
    #         logger.error(f"Failed to request clearer document: {e}")
    #         return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to request clearer document: {e}"}}

    # patient_id was already extracted early (before rejection checks)
    if patient_id:
        logger.info(f"🔍 LIEN AGENT: Patient ID available for processing: {patient_id}")
    else:
        logger.warning(f"🔍 LIEN AGENT: No patient ID found for conversation {front_conversation_id}")

    if False:  # Disabled the "patient not found" branch for testing
        logger.info(f"Patient ID not found for conversation {front_conversation_id}. Tagging for human review.")

        try:
            _tag_for_human_review(front_conversation_id)

            # Send reply if template is configured
            if templates.get("patient_not_found"):
                await send_or_save_response(
                    conversation_id=front_conversation_id,
                    response_text=_safe_format_template(templates["patient_not_found"], **rejection_placeholders),
                    tags_to_add=None,
                    test_mode=test_mode,
                    lien_type=lien_type,
                    signature_type=signature_type
                )
            else:
                logger.warning(f"Patient not found template not configured for tag '{tag_name}'. No autoresponse sent.")

            return {
                "agent_handled": True,
                "processed_flag": True,
                "details": {
                    "action": "tagged_for_human_review_no_patient",
                    "lien_type": lien_type,
                    "signature_type": signature_type
                }
            }
        except Exception as e:
            logger.error(f"Failed to handle missing patient: {e}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to handle missing patient: {e}"}}

    # Patient found - proceed with lien processing
    logger.info(f"Patient ID {patient_id} found. Processing {lien_type} for conversation {front_conversation_id}.")

    # Check for duplicate lien type (exact match of lien type AND signature type)
    if patient_id:
        has_duplicate_lien, duplicate_reason = await _check_duplicate_lien_type(patient_id, lien_type, signature_type)
        if has_duplicate_lien:
            logger.info(f"Duplicate lien type detected for conversation {front_conversation_id}. {duplicate_reason}. Tagging for human review.")

            try:
                # Add human review tag and unassign
                _tag_for_human_review(front_conversation_id)

                # Add comment to Front conversation
                comment_text = f"{duplicate_reason}. Please review and handle accordingly."
                frontapp_service.add_conversation_comment(front_conversation_id, comment_text)

                return {
                    "agent_handled": True,
                    "processed_flag": True,
                    "details": {
                        "action": "tagged_for_human_review_duplicate_lien_type",
                        "lien_type": lien_type,
                        "signature_type": signature_type,
                        "reason": duplicate_reason
                    }
                }
            except Exception as e:
                logger.error(f"Failed to handle duplicate lien type: {e}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to handle duplicate lien type: {e}"}}

    try:
        # Get patient information (needed for response template)
        patient_info_response = await call_mcp_tool(
            tool_name="fetch_patient_info",
            arguments={"patient_id": patient_id}
        )

        # Collect split metadata from ALL document analysis results
        # This handles both:
        # 1. Single PDF with multiple liens (splits within one attachment)
        # 2. Multiple separate PDFs (each with potential splits)
        splits_by_url = {}  # Map attachment_url -> list of split metadata
        processed_doc_indices = set()

        if document_analysis_results:
            for doc_idx, doc_result in enumerate(document_analysis_results):
                enhanced_lien_data = doc_result.get("enhanced_lien_processing", {})
                if enhanced_lien_data.get("processing_type") == "enhanced_lien_processing_split":
                    split_metadata = enhanced_lien_data.get("split_documents", [])
                    if split_metadata:
                        attachment_url = doc_result.get("attachment_url", "")
                        if attachment_url:
                            if attachment_url not in splits_by_url:
                                splits_by_url[attachment_url] = []
                            splits_by_url[attachment_url].extend(split_metadata)
                            processed_doc_indices.add(doc_idx)
                            logger.info(f"📄 {signature_type} AGENT: Found {len(split_metadata)} split metadata from document {doc_idx + 1}")

        # Regenerate split documents with pdf_bytes by downloading attachments
        all_split_documents = []
        if splits_by_url:
            logger.info(f"📄 {signature_type} AGENT: Regenerating splits from {len(splits_by_url)} attachment(s)")

            for attachment_url, split_meta_list in splits_by_url.items():
                regenerated_splits = await _regenerate_split_documents(attachment_url, split_meta_list)
                all_split_documents.extend(regenerated_splits)

            logger.info(f"📄 {signature_type} AGENT: Successfully regenerated {len(all_split_documents)} split documents with pdf_bytes")

        # Handle bilingual duplicates (English + Spanish pages with same barcode)
        # ASL: Filter to English pages only (attorney only signs English)
        # PSL: Keep all pages merged into single PDF (patient may sign both)
        if all_split_documents:
            from app.services.lien.pdf_splitter import PDFSplitter

            processed_splits = []
            for split_doc in all_split_documents:
                is_bilingual = split_doc.get("is_bilingual_duplicate", False)

                if is_bilingual and signature_type == "ASL":
                    # ASL: Re-split to only include English pages
                    english_pages = split_doc.get("english_pages", [])
                    if english_pages:
                        logger.info(
                            f"📄 ASL BILINGUAL: Filtering to English pages only for "
                            f"Patient={split_doc.get('patient_id')}, LienType={split_doc.get('lien_type')}. "
                            f"Keeping pages {english_pages}, dropping Spanish pages {split_doc.get('spanish_pages', [])}"
                        )
                        # Re-extract only English pages from the PDF
                        splitter = PDFSplitter()
                        # Map original page indices to current PDF page indices
                        # The pdf_bytes contains pages at indices corresponding to original_pages
                        original_pages = split_doc.get("original_pages", [])
                        # Find which indices in the current PDF correspond to English pages
                        english_indices_in_split = [
                            i for i, orig_page in enumerate(original_pages)
                            if orig_page in english_pages
                        ]
                        if english_indices_in_split:
                            english_only_bytes = splitter.extract_pages(
                                split_doc.get("pdf_bytes", b""),
                                english_indices_in_split
                            )
                            split_doc["pdf_bytes"] = english_only_bytes
                            split_doc["original_pages"] = english_pages
                            split_doc["page_count"] = len(english_pages)
                            split_doc["is_bilingual_duplicate"] = False  # No longer bilingual after filtering
                            processed_splits.append(split_doc)
                        else:
                            logger.warning(f"📄 ASL BILINGUAL: No English pages found, skipping split")
                    else:
                        logger.warning(
                            f"📄 ASL BILINGUAL: No english_pages metadata, keeping original split for "
                            f"Patient={split_doc.get('patient_id')}"
                        )
                        processed_splits.append(split_doc)
                elif is_bilingual and signature_type == "PSL":
                    # PSL: Keep all pages merged (English + Spanish in single PDF)
                    logger.info(
                        f"📄 PSL BILINGUAL: Keeping merged English+Spanish PDF for "
                        f"Patient={split_doc.get('patient_id')}, LienType={split_doc.get('lien_type')}. "
                        f"Pages: English={split_doc.get('english_pages', [])}, Spanish={split_doc.get('spanish_pages', [])}"
                    )
                    processed_splits.append(split_doc)
                else:
                    # Not bilingual, keep as-is
                    processed_splits.append(split_doc)

            all_split_documents = processed_splits

            # Log summary of bilingual processing
            bilingual_count = sum(1 for s in all_split_documents if s.get("is_bilingual_duplicate", False))
            logger.info(f"📄 BILINGUAL PROCESSING COMPLETE: {len(all_split_documents)} splits after processing, {bilingual_count} still marked bilingual")

        # Deduplicate split documents by (patient_id, page_type, lien_type, doc_type_id)
        # When duplicates exist, keep the one with the highest quality score
        # This prevents uploading the same lien multiple times and ensures we keep the best copy
        if all_split_documents:
            # Group splits by their dedup key
            splits_by_key: Dict[tuple, List[Dict[str, Any]]] = {}

            for split_doc in all_split_documents:
                patient_id = split_doc.get("patient_id", "")
                page_type = split_doc.get("page_type", "lien")
                lien_type = split_doc.get("lien_type", "")
                doc_type_id = split_doc.get("doc_type_id", "")

                dedup_key = (patient_id, page_type, lien_type, doc_type_id)

                if dedup_key not in splits_by_key:
                    splits_by_key[dedup_key] = []
                splits_by_key[dedup_key].append(split_doc)

            # For each group, keep the best quality document
            deduplicated_splits = []
            duplicates_removed = 0

            for dedup_key, split_group in splits_by_key.items():
                patient_id, page_type, lien_type, doc_type_id = dedup_key

                if len(split_group) == 1:
                    # No duplicates for this key
                    deduplicated_splits.append(split_group[0])
                else:
                    # Multiple copies - score each and keep the best
                    scored_splits = [
                        (split_doc, _score_split_document(split_doc, signature_type))
                        for split_doc in split_group
                    ]
                    # Sort by score descending
                    scored_splits.sort(key=lambda x: x[1], reverse=True)

                    best_split, best_score = scored_splits[0]
                    deduplicated_splits.append(best_split)
                    duplicates_removed += len(split_group) - 1

                    # Log the selection
                    all_scores = [s[1] for s in scored_splits]
                    logger.info(
                        f"📄 {signature_type} AGENT: Found {len(split_group)} copies of "
                        f"Patient={patient_id}, PageType={page_type}, LienType={lien_type or 'N/A'} — "
                        f"scores={all_scores}, keeping best (score={best_score})"
                    )

            if duplicates_removed > 0:
                logger.info(
                    f"📄 {signature_type} AGENT: Deduplication removed {duplicates_removed} duplicate(s), "
                    f"{len(deduplicated_splits)} unique split(s) remaining"
                )

            all_split_documents = deduplicated_splits

        # Process all split documents (from all attachments)
        upload_results = []
        has_patient_demo = False
        has_liens = False
        all_unique_patient_ids = set()

        if all_split_documents:
            logger.info(f"📄 {signature_type} AGENT: Processing {len(all_split_documents)} unique split documents")

            # Import upload services for split documents
            from app.services.lien_upload_service import upload_lien_pdf_bytes_to_radflow, upload_patient_demo_to_radflow

            # Process each split document
            for i, split_doc in enumerate(all_split_documents):
                split_patient_id = split_doc.get("patient_id", "")
                split_lien_type = split_doc.get("lien_type", "")
                split_page_type = split_doc.get("page_type", "lien")  # "lien" or "patient_demo"
                split_doc_type_id = split_doc.get("doc_type_id", "")
                split_pdf_bytes = split_doc.get("pdf_bytes", b"")
                page_count = split_doc.get("page_count", 0)

                # Track unique patient IDs for consolidated response
                if split_patient_id and split_patient_id.startswith("PRE"):
                    all_unique_patient_ids.add(split_patient_id)

                if split_page_type == "patient_demo":
                    # Handle patient demo document
                    has_patient_demo = True
                    logger.info(
                        f"📄 {signature_type} AGENT: Processing patient demo {i+1}/{len(all_split_documents)}: "
                        f"Patient={split_patient_id}, DocTypeID={split_doc_type_id}, Pages={page_count}"
                    )

                    # Upload patient demo document
                    upload_success = await upload_patient_demo_to_radflow(
                        patient_id=split_patient_id,
                        pdf_bytes=split_pdf_bytes,
                        filename=f"patient_demo_{i+1}.pdf",
                        doc_type_id=split_doc_type_id,
                        conversation_id=front_conversation_id
                    )

                    upload_results.append({
                        "patient_id": split_patient_id,
                        "page_type": "patient_demo",
                        "doc_type_id": split_doc_type_id,
                        "lien_type": "",
                        "success": upload_success,
                        "page_count": page_count
                    })

                    if not upload_success:
                        logger.warning(f"📄 {signature_type} AGENT: Upload failed for patient demo {i+1}")
                else:
                    # Handle lien document
                    # Skip splits with empty lien_type — these are mis-classified pages
                    # (e.g. patient_demo pages marked as page_type=lien in mixed packets)
                    if not split_lien_type:
                        logger.warning(
                            f"📄 {signature_type} AGENT: Skipping split {i+1}/{len(all_split_documents)} — "
                            f"page_type is 'lien' but lien_type is empty (Patient={split_patient_id}). "
                            f"This may be a mis-classified page in a mixed packet."
                        )
                        continue

                    has_liens = True
                    logger.info(
                        f"📄 {signature_type} AGENT: Processing lien split {i+1}/{len(all_split_documents)}: "
                        f"Patient={split_patient_id}, LienType={split_lien_type}, Pages={page_count}"
                    )

                    # Upload this split to patient file
                    upload_success = await upload_lien_pdf_bytes_to_radflow(
                        patient_id=split_patient_id,
                        lien_type=split_lien_type,
                        pdf_bytes=split_pdf_bytes,
                        filename=f"split_{i+1}.pdf",
                        signature_type=signature_type,  # Pass ASL or PSL
                        conversation_id=front_conversation_id  # For test mode file organization
                    )

                    upload_results.append({
                        "patient_id": split_patient_id,
                        "page_type": "lien",
                        "lien_type": split_lien_type,
                        "success": upload_success,
                        "page_count": page_count
                    })

                    if not upload_success:
                        logger.warning(f"📄 {signature_type} AGENT: Upload failed for split {i+1}")

            # Check if all uploads succeeded
            all_uploads_success = all(result["success"] for result in upload_results)
            upload_success = all_uploads_success

            # Add Patient Demo tag if patient demo documents were detected
            if has_patient_demo:
                logger.info(f"📄 {signature_type} AGENT: Patient demo documents detected, adding 'Patient Demo' tag")
                try:
                    frontapp_service.add_conversation_tags(front_conversation_id, [TAG_PATIENT_DEMO])
                except Exception as tag_error:
                    logger.warning(f"Failed to add Patient Demo tag: {tag_error}")

        else:
            # Fallback: No split documents, upload original attachments directly
            # This handles cases where documents don't need splitting (e.g., single-page liens)
            logger.info(f"📄 {signature_type} AGENT: No split documents found, uploading original attachments")

            # Initialize tracking variables for fallback case
            has_patient_demo = False
            has_liens = True  # Assume liens for fallback (original behavior)
            all_unique_patient_ids = set()
            if patient_id:
                all_unique_patient_ids.add(patient_id)

            # Get all attachments from email
            attachments = []
            if email_obj.raw_data and isinstance(email_obj.raw_data, dict):
                target_data = email_obj.raw_data.get('target', {}).get('data', {})
                attachments = target_data.get('attachments', [])

            if not attachments:
                logger.error(f"📄 {signature_type} AGENT: No attachments found in email")
                upload_success = False
            else:
                # Upload ALL attachments (not just the first one)
                logger.info(f"📄 {signature_type} AGENT: Uploading {len(attachments)} attachment(s)")

                for att_idx, attachment_data in enumerate(attachments):
                    # Determine lien type from document analysis if available
                    att_lien_type_short = "TECH"  # Default short code
                    if document_analysis_results and att_idx < len(document_analysis_results):
                        doc_analysis = document_analysis_results[att_idx].get("document_analysis", {}).get("data", {})
                        enhanced_lien = doc_analysis.get("enhanced_lien_analysis", {})
                        detected_lien_type = enhanced_lien.get("LienType", "")

                        # Normalize lien type codes to standard format
                        if detected_lien_type:
                            detected_upper = detected_lien_type.upper()
                            if detected_upper in ["TC", "TECH", "TECHNOLOGIST"]:
                                att_lien_type_short = "TECH"
                            elif detected_upper in ["RAD", "RADIOLOGY", "RADIOLOGIST"]:
                                att_lien_type_short = "RAD"
                            else:
                                att_lien_type_short = "TECH"  # Default fallback

                            logger.info(f"📄 {signature_type} AGENT: Attachment {att_idx + 1} detected as {detected_lien_type} -> normalized to {att_lien_type_short} lien")

                    # Convert short code to full lien type name for upload function
                    # The _upload_lien_to_patient_file function expects full names like "Attorney Signed Technologist Lien"
                    if att_lien_type_short == "TECH":
                        if signature_type == "PSL":
                            att_lien_type_full = "Patient Signed Technologist Lien"
                        else:  # ASL
                            att_lien_type_full = "Attorney Signed Technologist Lien"
                    elif att_lien_type_short == "RAD":
                        if signature_type == "PSL":
                            att_lien_type_full = "Patient Signed Radiologist Lien"
                        else:  # ASL
                            att_lien_type_full = "Attorney Signed Radiologist Lien"
                    else:
                        att_lien_type_full = lien_type  # Fallback to original

                    attachment_upload_success = await _upload_lien_to_patient_file(patient_id, att_lien_type_full, attachment_data, front_conversation_id)

                    upload_results.append({
                        "patient_id": patient_id,
                        "page_type": "lien",
                        "lien_type": att_lien_type_short,  # Store short code for table generation
                        "success": attachment_upload_success
                    })

                    if not attachment_upload_success:
                        logger.warning(f"📄 {signature_type} AGENT: Upload failed for attachment {att_idx + 1}")

                # Check if all uploads succeeded
                all_uploads_success = all(result["success"] for result in upload_results)
                upload_success = all_uploads_success

        # If upload failed, tag for human review and unassign (no autoresponse for errors)
        if not upload_success:
            logger.warning(f"File upload failed for patient {patient_id}. Tagging for human review.")

            try:
                _tag_for_human_review(front_conversation_id)

                # Add comment explaining why human review is needed
                comment_text = f"Upload failed: Failed to upload {signature_type} {lien_type} lien to patient file (Patient ID: {patient_id}). The RadFlow upload API returned an error. Please manually upload the lien document."
                frontapp_service.add_conversation_comment(front_conversation_id, comment_text)

                return {
                    "agent_handled": True,
                    "processed_flag": True,
                    "details": {
                        "action": "tagged_for_human_review_upload_failed",
                        "patient_id": patient_id,
                        "lien_type": lien_type,
                        "signature_type": signature_type,
                        "upload_success": False,
                        "reason": "RadFlow upload failed"
                    }
                }
            except Exception as tag_error:
                logger.error(f"Failed to add human review tag after upload failure: {tag_error}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Upload failed and couldn't tag for review: {tag_error}"}}

        # Upload succeeded - proceed with success response
        # Check for standalone patient demo (no liens)
        if has_patient_demo and not has_liens:
            logger.info(f"📄 {signature_type} AGENT: Standalone patient demo detected - sending acknowledgment")

            # For standalone patient demo, send a simple acknowledgment
            # No need to generate lien status table
            patient_demo_response = "Thank you for submitting the patient demographic document(s). The document(s) have been uploaded to the patient file."

            # Add patient IDs to the response
            if all_unique_patient_ids:
                patient_demo_response += f"\n\nPatient ID(s): {', '.join(sorted(all_unique_patient_ids))}"

            await send_or_save_response(
                conversation_id=front_conversation_id,
                response_text=patient_demo_response,
                tags_to_add=None,
                test_mode=test_mode,
                lien_type="Patient Demo",
                signature_type=""
            )

            logger.info(f"Successfully processed standalone patient demo for conversation {front_conversation_id}")
            return {
                "agent_handled": True,
                "processed_flag": True,
                "details": {
                    "action": "patient_demo_processed_successfully",
                    "patient_ids": list(all_unique_patient_ids),
                    "has_patient_demo": True,
                    "has_liens": False,
                    "upload_success": upload_success,
                    "total_splits": len(all_split_documents) if all_split_documents else 0,
                    "upload_results": upload_results
                }
            }

        # Process patient information for response
        # For multiple patients, we need to handle them in a consolidated response
        unique_patient_ids = list(all_unique_patient_ids) if all_unique_patient_ids else ([patient_id] if patient_id else [])

        # Wait for RadFlow to update signature status after document upload
        # RadFlow needs approximately 5 minutes to process uploaded documents and update signature status
        if unique_patient_ids:
            # Assign conversation to AI bot during the wait so human agents don't pick it up
            # Only assign in production mode — sandbox should not touch conversation assignment
            if test_mode:
                logger.info(f"🧪 SANDBOX: Skipping bot assignment for conversation {front_conversation_id} (test/sandbox mode)")
            else:
                from app.core.config import settings as app_settings
                if app_settings.FRONT_BOT_TEAMMATE_ID:
                    frontapp_service.assign_conversation(front_conversation_id, app_settings.FRONT_BOT_TEAMMATE_ID)
                else:
                    logger.warning(f"FRONT_BOT_TEAMMATE_ID not configured — cannot assign conversation {front_conversation_id} during RadFlow wait")

            if test_mode:
                logger.info(f"⏳ Skipping 5-minute RadFlow wait (test/sandbox mode) for {len(unique_patient_ids)} patient(s)")
            else:
                logger.info(f"⏳ Waiting 5 minutes for RadFlow to update signature status for {len(unique_patient_ids)} patient(s)...")
                await asyncio.sleep(300)  # 5 minutes = 300 seconds

        # Generate consolidated response for multiple patients
        if len(unique_patient_ids) > 1:
            logger.info(f"📄 {signature_type} AGENT: Generating consolidated response for {len(unique_patient_ids)} patients")

            response_sections = []

            for pid in sorted(unique_patient_ids):
                # Fetch patient info for each patient
                pid_info_response = await call_mcp_tool(
                    tool_name="fetch_patient_info",
                    arguments={"patient_id": pid}
                )

                pid_patient_name = "Unknown"
                pid_dob = "Unknown"
                pid_doi = "Unknown"

                if pid_info_response and isinstance(pid_info_response, dict):
                    data_section = pid_info_response.get('data', {})
                    if data_section and isinstance(data_section, dict):
                        patients_list = data_section.get('patients', [])
                        if patients_list and len(patients_list) > 0:
                            patient = patients_list[0]
                            first_name = patient.get('first_name', '').strip()
                            last_name = patient.get('last_name', '').strip()
                            if first_name and last_name:
                                pid_patient_name = f"{first_name} {last_name}"
                            elif first_name:
                                pid_patient_name = first_name
                            elif last_name:
                                pid_patient_name = last_name

                            raw_dob = patient.get('birth_date')
                            if raw_dob:
                                try:
                                    date_obj = datetime.strptime(raw_dob, '%Y-%m-%d')
                                    pid_dob = date_obj.strftime('%m/%d/%Y')
                                except:
                                    pid_dob = raw_dob

                            raw_doi = patient.get('doi')
                            if raw_doi:
                                try:
                                    date_obj = datetime.strptime(raw_doi, '%Y-%m-%d')
                                    pid_doi = date_obj.strftime('%m/%d/%Y')
                                except:
                                    pid_doi = raw_doi

                # Filter upload results for this patient
                pid_upload_results = [r for r in upload_results if r.get("patient_id") == pid]

                # Generate lien status table for this patient
                pid_lien_status_table = await _generate_lien_status_table(pid, pid_upload_results, signature_type)

                # Build section for this patient
                section = f"""<h3>Patient: {pid_patient_name} ({pid})</h3>
<p><strong>DOB:</strong> {pid_dob} | <strong>DOI:</strong> {pid_doi}</p>
{pid_lien_status_table}"""
                response_sections.append(section)

            # Combine all patient sections
            consolidated_body = "<hr>".join(response_sections)

            # Add header message
            header = f"<p>Thank you for your submission. We have processed documents for {len(unique_patient_ids)} patients.</p>"
            if has_patient_demo:
                header += "<p><em>Note: Patient demographic documents have also been uploaded.</em></p>"

            reply_body = header + "<hr>" + consolidated_body

            # For Westfax liens, look up attorney for each patient and collect recipients
            westfax_to = None
            westfax_cc = None
            if is_westfax_sender:
                logger.info(f"📠 WESTFAX MULTI-PATIENT: Looking up attorneys for {len(unique_patient_ids)} patients")
                all_attorney_emails = set()
                all_cm_emails = set()
                for pid in unique_patient_ids:
                    atty_info = await fetch_attorney_and_case_manager_from_participants(pid)
                    if atty_info["attorney_email"]:
                        all_attorney_emails.add(atty_info["attorney_email"])
                    if atty_info["notify_case_manager"] and atty_info["case_manager_email"]:
                        all_cm_emails.add(atty_info["case_manager_email"])

                if all_attorney_emails:
                    westfax_to = list(all_attorney_emails)
                    westfax_cc = list(all_cm_emails) if all_cm_emails else None
                    logger.info(f"📠 WESTFAX MULTI-PATIENT: Directing reply to attorneys: {westfax_to}, cc: {westfax_cc}")
                else:
                    logger.info(f"📠 WESTFAX MULTI-PATIENT: No attorney emails found for any patient. Lien uploaded successfully, no notification will be sent.")

            # Send the consolidated response
            await send_or_save_response(
                conversation_id=front_conversation_id,
                response_text=reply_body,
                tags_to_add=None,
                test_mode=test_mode,
                lien_type=lien_type,
                signature_type=signature_type,
                to_recipients=westfax_to,
                cc_recipients=westfax_cc
            )

            logger.info(f"Successfully processed {lien_type} for {len(unique_patient_ids)} patients in conversation {front_conversation_id}")
            return {
                "agent_handled": True,
                "processed_flag": True,
                "details": {
                    "action": "lien_processed_successfully_multi_patient",
                    "patient_ids": unique_patient_ids,
                    "lien_type": lien_type,
                    "signature_type": signature_type,
                    "has_patient_demo": has_patient_demo,
                    "upload_success": upload_success,
                    "total_splits": len(all_split_documents) if all_split_documents else 0,
                    "upload_results": upload_results
                }
            }

        # Single patient response (original logic)
        patient_name = "Unknown"
        dob = "Unknown"
        doi = "Unknown"

        if patient_info_response and isinstance(patient_info_response, dict):
            data_section = patient_info_response.get('data', {})
            if data_section and isinstance(data_section, dict):
                patients_list = data_section.get('patients', [])
                if patients_list and len(patients_list) > 0:
                    patient = patients_list[0]

                    # Extract and format patient name
                    first_name = patient.get('first_name', '').strip()
                    last_name = patient.get('last_name', '').strip()
                    if first_name and last_name:
                        patient_name = f"{first_name} {last_name}"
                    elif first_name:
                        patient_name = first_name
                    elif last_name:
                        patient_name = last_name
                    else:
                        patient_name = "Unknown"

                    # Format DOB (field is 'birth_date' not 'date_of_birth')
                    raw_dob = patient.get('birth_date')
                    if raw_dob:
                        try:
                            date_obj = datetime.strptime(raw_dob, '%Y-%m-%d')
                            dob = date_obj.strftime('%m/%d/%Y')
                        except:
                            dob = raw_dob  # Use as-is if parsing fails

                    # Format DOI (field is 'doi' not 'date_of_injury')
                    raw_doi = patient.get('doi')
                    if raw_doi:
                        try:
                            date_obj = datetime.strptime(raw_doi, '%Y-%m-%d')
                            doi = date_obj.strftime('%m/%d/%Y')
                        except:
                            doi = raw_doi  # Use as-is if parsing fails
                else:
                    logger.warning(f"No patients found in patient info response for {patient_id}")
            else:
                logger.warning(f"Invalid data structure in patient info response for {patient_id}")

        # Generate lien status table
        lien_status_table = await _generate_lien_status_table(patient_id, upload_results, signature_type)

        # Generate call log table
        from app.helpers.call_log_table import generate_call_log_table
        call_log_table = await generate_call_log_table(patient_id)

        # Generate text log table
        from app.helpers.text_log_table import generate_text_log_table
        text_log_table = await generate_text_log_table(patient_id)

        # Generate billing status table
        from app.helpers.billing_status_table import generate_billing_status_table
        billing_status_table = await generate_billing_status_table(patient_id)

        # Prepare all placeholders for template formatting
        placeholder_values = {
            "lien_type": lien_type,
            "patient_id": patient_id,
            "patient_name": patient_name,
            "dob": dob,
            "doi": doi,
            "lien_status_table": lien_status_table,
            "call_log_table": call_log_table,
            "text_log_table": text_log_table,
            "billing_status_table": billing_status_table
        }

        # Merge in custom placeholders from workspace settings
        if custom_placeholders:
            placeholder_values.update(custom_placeholders)
            logger.info(f"📝 Merged {len(custom_placeholders)} custom placeholders into template")

        # Generate success response with nested placeholder resolution
        reply_body = _safe_format_template(templates["success"], **placeholder_values)

        # Add note about patient demo if present
        if has_patient_demo:
            reply_body += "<br/><p><em>Note: Patient demographic documents have also been uploaded.</em></p>"

        # For Westfax liens, look up attorney to direct the reply
        westfax_to = None
        westfax_cc = None
        if is_westfax_sender:
            logger.info(f"📠 WESTFAX SINGLE-PATIENT: Looking up attorney for patient {patient_id}")
            atty_info = await fetch_attorney_and_case_manager_from_participants(patient_id)
            if atty_info["attorney_email"]:
                westfax_to = [atty_info["attorney_email"]]
                if atty_info["notify_case_manager"] and atty_info["case_manager_email"]:
                    westfax_cc = [atty_info["case_manager_email"]]
                logger.info(f"📠 WESTFAX SINGLE-PATIENT: Directing reply to attorney: {westfax_to}, cc: {westfax_cc}")
            else:
                logger.info(f"📠 WESTFAX SINGLE-PATIENT: No attorney email found for patient {patient_id}. Lien uploaded successfully, no notification will be sent.")

        # Send the response
        await send_or_save_response(
            conversation_id=front_conversation_id,
            response_text=reply_body,
            tags_to_add=None,
            test_mode=test_mode,
            lien_type=lien_type,
            signature_type=signature_type,
            to_recipients=westfax_to,
            cc_recipients=westfax_cc
        )

        logger.info(f"Successfully processed {lien_type} for patient {patient_id} in conversation {front_conversation_id}")
        return {
            "agent_handled": True,
            "processed_flag": True,
            "details": {
                "action": "lien_processed_successfully",
                "patient_id": patient_id,
                "lien_type": lien_type,
                "signature_type": signature_type,
                "has_patient_demo": has_patient_demo,
                "upload_success": upload_success,
                "total_splits": len(all_split_documents) if all_split_documents else 0,
                "upload_results": upload_results
            }
        }

    except Exception as e:
        logger.error(f"Unexpected error processing {signature_type} lien for patient {patient_id}: {e}", exc_info=True)
        # Tag for human review and unassign on processing error (no autoresponse for errors)
        try:
            _tag_for_human_review(front_conversation_id)

            # Add comment explaining the error
            comment_text = f"Processing error: An unexpected error occurred while processing this {signature_type} {lien_type} lien. Error: {str(e)[:200]}"
            frontapp_service.add_conversation_comment(front_conversation_id, comment_text)
        except Exception as tag_error:
            logger.error(f"Failed to add human review tag: {tag_error}")
        return {"agent_handled": False, "processed_flag": True, "details": {"reason": f"Unexpected processing error: {e}"}}

# --- END: Main Agent Handler ---

# --- BEGIN: Backward Compatibility Wrappers ---

async def handle_asl_lien_request(
    front_conversation_id: str,
    current_email_content: str,
    applied_tags: List[str],
    email_obj: Any,
    document_analysis_results: List[Dict[str, Any]] = None,
    settings_obj: Any = app_settings_instance,
    email_subject: str = None,
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Backward compatibility wrapper for ASL lien requests.
    Calls the unified handle_lien_request with signature_type="ASL".
    """
    return await handle_lien_request(
        front_conversation_id=front_conversation_id,
        current_email_content=current_email_content,
        applied_tags=applied_tags,
        email_obj=email_obj,
        signature_type="ASL",
        document_analysis_results=document_analysis_results,
        settings_obj=settings_obj,
        email_subject=email_subject,
        test_mode=test_mode
    )

async def handle_psl_lien_request(
    front_conversation_id: str,
    current_email_content: str,
    applied_tags: List[str],
    email_obj: Any,
    document_analysis_results: List[Dict[str, Any]] = None,
    settings_obj: Any = app_settings_instance,
    email_subject: str = None,
    test_mode: bool = False
) -> Dict[str, Any]:
    """
    Backward compatibility wrapper for PSL lien requests.
    Calls the unified handle_lien_request with signature_type="PSL".
    """
    return await handle_lien_request(
        front_conversation_id=front_conversation_id,
        current_email_content=current_email_content,
        applied_tags=applied_tags,
        email_obj=email_obj,
        signature_type="PSL",
        document_analysis_results=document_analysis_results,
        settings_obj=settings_obj,
        email_subject=email_subject,
        test_mode=test_mode
    )

# --- END: Backward Compatibility Wrappers ---
