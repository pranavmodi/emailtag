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
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from celery.utils.log import get_task_logger
from app.core.config import settings as app_settings_instance
from app.services import frontapp_service
from app.agents.agent_helpers import send_reply_to_front_direct, extract_patient_id_from_email_logic
from app.mcp import call_mcp_tool

# --- BEGIN: Logging ---
logger = get_task_logger(__name__)
# --- END: Logging ---

# --- BEGIN: Tag Constants ---
TAG_AI_HUMAN_REVIEW_REQUIRED = "AI: Human review required"
TAG_LIEN_MODIFIED = "Lien Modified"
RAD_LIEN_TAG = "Rad Lien"
TECH_LIEN_TAG = "Tech Lien"
# --- END: Tag Constants ---

# --- NOTE: All lien response templates are now managed via /settings/template-config ---
# Templates are fetched from database via _fetch_lien_templates_from_db()

# --- BEGIN: Helper Functions ---

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
                    "invalid_signature": settings.get("lien_reject_sig_not_valid_template", "")
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
        "invalid_signature": ""
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

        # Check if description indicates readability issues
        description = analysis_data.get("description", "").lower()
        readability_issues = ["blurry", "unclear", "unreadable", "poor quality", "distorted", "corrupted"]

        if any(issue in description for issue in readability_issues):
            logger.warning(f"Document description indicates readability issues: {description}")
            return False

    return True

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
        return f"{signature_prefix} Radiology Lien"
    elif TECH_LIEN_TAG in applied_tags:
        return f"{signature_prefix} Technologist Lien"
    else:
        return f"{signature_prefix} Lien"

async def _upload_lien_to_patient_file(patient_id: str, lien_type: str, attachment_data: Dict[str, Any]) -> bool:
    """
    Upload lien document to patient file via RadFlow API (using shared service).

    Args:
        patient_id: Patient ID to upload document for
        lien_type: Type of lien being uploaded
        attachment_data: Attachment data with URL to download

    Returns:
        True if upload successful, False otherwise
    """
    from app.services.lien_upload_service import upload_lien_to_radflow

    return await upload_lien_to_radflow(patient_id, lien_type, attachment_data)

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
            lien_status_list = result.get("lienStatusList", [])

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
                    attorney_sig_status = "Not Signed.<br/>Please eSign here"
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
    email_subject: str = None
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
    logger.info(f"Initiating {signature_type} Lien agent for conv ID: {front_conversation_id}, tags: {applied_tags}")

    # Fetch lien templates from database using unified "Lien Templates" tag
    # (All lien templates are stored under this single tag in the database)
    tag_name = "Lien Templates"
    templates = await _fetch_lien_templates_from_db(tag_name)

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

    # Check for lien modifications
    has_modifications = _check_lien_modifications(email_obj) or _has_lien_modified_tag(applied_tags)

    if has_modifications:
        logger.info(f"Lien modifications detected for conversation {front_conversation_id}. Tagging for human review.")

        try:
            # Add human review tag and lien modified tag if not already present
            tags_to_add = [TAG_AI_HUMAN_REVIEW_REQUIRED]
            if not _has_lien_modified_tag(applied_tags):
                tags_to_add.append(TAG_LIEN_MODIFIED)

            frontapp_service.add_conversation_tags(front_conversation_id, tags_to_add)

            # Send reply if template is configured
            if templates.get("modified"):
                await send_reply_to_front_direct(
                    conversation_id=front_conversation_id,
                    reply_text=templates["modified"].format(lien_type=lien_type)
                )
            else:
                logger.warning(f"Modified lien template not configured for tag '{tag_name}'. No autoresponse sent.")

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

    # Check lien readability
    if document_analysis_results and not _check_lien_readability(document_analysis_results):
        logger.info(f"Lien document unreadable for conversation {front_conversation_id}. Requesting clearer version.")

        try:
            # Send reply if template is configured
            if templates.get("unreadable"):
                await send_reply_to_front_direct(
                    conversation_id=front_conversation_id,
                    reply_text=templates["unreadable"].format(lien_type=lien_type)
                )
            else:
                logger.warning(f"Unreadable lien template not configured for tag '{tag_name}'. No autoresponse sent.")

            return {
                "agent_handled": True,
                "processed_flag": True,
                "details": {
                    "action": "requested_clearer_document",
                    "lien_type": lien_type,
                    "signature_type": signature_type
                }
            }
        except Exception as e:
            logger.error(f"Failed to request clearer document: {e}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to request clearer document: {e}"}}

    # Extract patient ID - First check if it was already extracted from document barcode
    patient_id = None

    if email_obj.extracted_patient_ids and len(email_obj.extracted_patient_ids) > 0:
        patient_id = email_obj.extracted_patient_ids[0]
        logger.info(f"🔍 LIEN AGENT: Using patient ID from document barcode: {patient_id}")
    else:
        logger.info(f"🔍 LIEN AGENT: No barcode patient ID found, attempting to extract from email text")
        patient_id = await extract_patient_id_from_email_logic(current_email_content, front_conversation_id, email_subject)

    if patient_id:
        logger.info(f"🔍 LIEN AGENT: Patient ID found: {patient_id}")
    else:
        logger.warning(f"🔍 LIEN AGENT: No patient ID found for conversation {front_conversation_id}")

    if False:  # Disabled the "patient not found" branch for testing
        logger.info(f"Patient ID not found for conversation {front_conversation_id}. Tagging for human review.")

        try:
            frontapp_service.add_conversation_tags(front_conversation_id, [TAG_AI_HUMAN_REVIEW_REQUIRED])

            # Send reply if template is configured
            if templates.get("patient_not_found"):
                await send_reply_to_front_direct(
                    conversation_id=front_conversation_id,
                    reply_text=templates["patient_not_found"].format(lien_type=lien_type)
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

    try:
        # Get patient information (needed for response template)
        patient_info_response = await call_mcp_tool(
            tool_name="fetch_patient_info",
            arguments={"patient_id": patient_id}
        )

        # Collect all split documents from ALL document analysis results
        # This handles both:
        # 1. Single PDF with multiple liens (splits within one attachment)
        # 2. Multiple separate PDFs (each with potential splits)
        all_split_documents = []
        processed_doc_indices = set()

        if document_analysis_results:
            for doc_idx, doc_result in enumerate(document_analysis_results):
                enhanced_lien_data = doc_result.get("enhanced_lien_processing", {})
                if enhanced_lien_data.get("processing_type") == "enhanced_lien_processing_split":
                    split_documents = enhanced_lien_data.get("split_documents", [])
                    if split_documents:
                        all_split_documents.extend(split_documents)
                        processed_doc_indices.add(doc_idx)
                        logger.info(f"📄 {signature_type} AGENT: Found {len(split_documents)} splits from document {doc_idx + 1}")

        # Process all split documents (from all attachments)
        upload_results = []

        if all_split_documents:
            logger.info(f"📄 {signature_type} AGENT: Processing {len(all_split_documents)} total split documents across all attachments")

            # Import upload service for split documents
            from app.services.lien_upload_service import upload_lien_pdf_bytes_to_radflow

            # Process each split document
            for i, split_doc in enumerate(all_split_documents):
                split_patient_id = split_doc.get("patient_id", "")
                split_lien_type = split_doc.get("lien_type", "")
                split_pdf_bytes = split_doc.get("pdf_bytes", b"")
                page_count = split_doc.get("page_count", 0)

                logger.info(
                    f"📄 {signature_type} AGENT: Processing split {i+1}/{len(all_split_documents)}: "
                    f"Patient={split_patient_id}, LienType={split_lien_type}, Pages={page_count}"
                )

                # Upload this split to patient file
                upload_success = await upload_lien_pdf_bytes_to_radflow(
                    patient_id=split_patient_id,
                    lien_type=split_lien_type,
                    pdf_bytes=split_pdf_bytes,
                    filename=f"lien_{split_patient_id}_{split_lien_type}_split_{i+1}.pdf",
                    signature_type=signature_type  # Pass ASL or PSL
                )

                upload_results.append({
                    "patient_id": split_patient_id,
                    "lien_type": split_lien_type,
                    "success": upload_success,
                    "page_count": page_count
                })

                if not upload_success:
                    logger.warning(f"📄 {signature_type} AGENT: Upload failed for split {i+1}")

            # Check if all uploads succeeded
            all_uploads_success = all(result["success"] for result in upload_results)
            upload_success = all_uploads_success

        else:
            # Fallback: No split documents, upload original attachments directly
            # This handles cases where documents don't need splitting (e.g., single-page liens)
            logger.info(f"📄 {signature_type} AGENT: No split documents found, uploading original attachments")

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
                    att_lien_type = lien_type  # Default to the primary lien type
                    if document_analysis_results and att_idx < len(document_analysis_results):
                        doc_analysis = document_analysis_results[att_idx].get("document_analysis", {}).get("data", {})
                        enhanced_lien = doc_analysis.get("enhanced_lien_analysis", {})
                        detected_lien_type = enhanced_lien.get("LienType", "")

                        # Normalize lien type codes to standard format
                        if detected_lien_type:
                            detected_upper = detected_lien_type.upper()
                            if detected_upper in ["TC", "TECH", "TECHNOLOGIST"]:
                                att_lien_type = "TECH"
                            elif detected_upper in ["RAD", "RADIOLOGY", "RADIOLOGIST"]:
                                att_lien_type = "RAD"
                            else:
                                att_lien_type = detected_lien_type  # Use as-is if unknown

                            logger.info(f"📄 {signature_type} AGENT: Attachment {att_idx + 1} detected as {detected_lien_type} -> normalized to {att_lien_type} lien")

                    attachment_upload_success = await _upload_lien_to_patient_file(patient_id, att_lien_type, attachment_data)

                    upload_results.append({
                        "patient_id": patient_id,
                        "lien_type": att_lien_type,
                        "success": attachment_upload_success
                    })

                    if not attachment_upload_success:
                        logger.warning(f"📄 {signature_type} AGENT: Upload failed for attachment {att_idx + 1}")

                # Check if all uploads succeeded
                all_uploads_success = all(result["success"] for result in upload_results)
                upload_success = all_uploads_success

        # If upload failed, tag for human review and notify
        if not upload_success:
            logger.warning(f"File upload failed for patient {patient_id}. Tagging for human review.")

            try:
                frontapp_service.add_conversation_tags(front_conversation_id, [TAG_AI_HUMAN_REVIEW_REQUIRED])
                await send_reply_to_front_direct(
                    conversation_id=front_conversation_id,
                    reply_text=f"We encountered an error uploading your {lien_type} to the patient file. A team member will review your submission and complete the upload manually. Thank you for your patience."
                )

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
        # Process patient information for response
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

        # Generate success response with all placeholders
        reply_body = templates["success"].format(
            lien_type=lien_type,
            patient_id=patient_id,
            patient_name=patient_name,
            dob=dob,
            doi=doi,
            lien_status_table=lien_status_table
        )

        # Send the response
        await send_reply_to_front_direct(
            conversation_id=front_conversation_id,
            reply_text=reply_body
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
                "upload_success": upload_success,
                "total_splits": len(all_split_documents) if all_split_documents else 0,
                "upload_results": upload_results
            }
        }

    except Exception as e:
        logger.error(f"Unexpected error processing {signature_type} lien for patient {patient_id}: {e}", exc_info=True)
        # Tag for human review on processing error
        try:
            frontapp_service.add_conversation_tags(front_conversation_id, [TAG_AI_HUMAN_REVIEW_REQUIRED])
            await send_reply_to_front_direct(
                conversation_id=front_conversation_id,
                reply_text=f"We encountered an error processing your {lien_type}. A team member will review your submission and get back to you shortly."
            )
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
    email_subject: str = None
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
        email_subject=email_subject
    )

async def handle_psl_lien_request(
    front_conversation_id: str,
    current_email_content: str,
    applied_tags: List[str],
    email_obj: Any,
    document_analysis_results: List[Dict[str, Any]] = None,
    settings_obj: Any = app_settings_instance,
    email_subject: str = None
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
        email_subject=email_subject
    )

# --- END: Backward Compatibility Wrappers ---
