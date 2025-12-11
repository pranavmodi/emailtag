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

# --- BEGIN: Response Templates ---

# Template for successful lien processing (not modified, patient found)
TEMPLATE_LIEN_PROCESSED_SUCCESS = """
Thank you for submitting the {lien_type}.

Patient ID: {patient_id}
Patient: {patient_name}
DOB: {dob}
DOI: {doi}

Your lien has been successfully uploaded to the patient file and is now on record.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""

# Template for unreadable/blurry lien document
TEMPLATE_LIEN_UNREADABLE = """
Thank you for submitting the {lien_type}.

We received your lien document, however the document appears to be unreadable due to poor image quality, blurriness, or scanning issues.

Please resend a clearer version of the lien document so we can properly process it.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""

# Template for human review (patient not found)
TEMPLATE_PATIENT_NOT_FOUND = """
Thank you for submitting the {lien_type}.

We're having trouble locating the patient record for this lien. A member of our billing team will personally review your submission and get back to you shortly.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""

# Template for modified lien (will be tagged for human review)
TEMPLATE_LIEN_MODIFIED_REVIEW = """
Thank you for submitting the {lien_type}.

We've received your lien document, however it appears to contain modifications or alterations. A member of our billing team will review this submission and get back to you shortly.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""

# --- END: Response Templates ---

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
                return {
                    "success": settings.get("lien_success_template", TEMPLATE_LIEN_PROCESSED_SUCCESS),
                    "unreadable": settings.get("lien_unreadable_template", TEMPLATE_LIEN_UNREADABLE),
                    "patient_not_found": settings.get("lien_patient_not_found_template", TEMPLATE_PATIENT_NOT_FOUND),
                    "modified": settings.get("lien_modified_template", TEMPLATE_LIEN_MODIFIED_REVIEW)
                }
    except Exception as e:
        logger.warning(f"Failed to fetch lien templates from database: {e}. Using hardcoded templates.")

    # Fallback to hardcoded templates
    return {
        "success": TEMPLATE_LIEN_PROCESSED_SUCCESS,
        "unreadable": TEMPLATE_LIEN_UNREADABLE,
        "patient_not_found": TEMPLATE_PATIENT_NOT_FOUND,
        "modified": TEMPLATE_LIEN_MODIFIED_REVIEW
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
            liens = data.get("liens", [])

            for lien in liens:
                lien_type = lien.get("lien_type", "").upper()
                patient_signed = lien.get("patient_signed", False)
                attorney_signed = lien.get("attorney_signed", False)
                patient_signed_date = lien.get("patient_signed_date", "")
                attorney_signed_date = lien.get("attorney_signed_date", "")

                # Map lien type to our standard names
                if "TECH" in lien_type or "IMAGING" in lien_type:
                    standard_type = "TECH"
                elif "RAD" in lien_type or "PROFESSIONAL" in lien_type or "REPORT" in lien_type:
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

        # Collect lien types from upload results
        for result in upload_results:
            lien_type_code = result.get("lien_type", "").upper()
            if lien_type_code in ["TECH", "TC", "TECHNOLOGIST"]:
                lien_types_to_show.add("TECH")
            elif lien_type_code in ["RAD", "RADIOLOGY"]:
                lien_types_to_show.add("RAD")

        # If no upload results, check if we have lien signatures from API
        if not lien_types_to_show and lien_signatures:
            lien_types_to_show = set(lien_signatures.keys())

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
                        try:
                            date_obj = datetime.strptime(patient_date, '%Y-%m-%d')
                            formatted_date = date_obj.strftime('%m/%d/%Y')
                        except:
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
                        try:
                            date_obj = datetime.strptime(attorney_date, '%Y-%m-%d')
                            formatted_date = date_obj.strftime('%m/%d/%Y')
                        except:
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

    # Determine tag name based on signature type
    tag_name = f"{signature_type} Lien"

    # Fetch lien templates from database
    templates = await _fetch_lien_templates_from_db(tag_name)

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

            await send_reply_to_front_direct(
                conversation_id=front_conversation_id,
                reply_text=templates["modified"].format(lien_type=lien_type)
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

    # Check lien readability
    if document_analysis_results and not _check_lien_readability(document_analysis_results):
        logger.info(f"Lien document unreadable for conversation {front_conversation_id}. Requesting clearer version.")

        try:
            await send_reply_to_front_direct(
                conversation_id=front_conversation_id,
                reply_text=templates["unreadable"].format(lien_type=lien_type)
            )

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

    # Extract patient ID from email
    patient_id = await extract_patient_id_from_email_logic(current_email_content, front_conversation_id, email_subject)

    if not patient_id:
        logger.info(f"Patient ID not found for conversation {front_conversation_id}. Tagging for human review.")

        try:
            frontapp_service.add_conversation_tags(front_conversation_id, [TAG_AI_HUMAN_REVIEW_REQUIRED])

            await send_reply_to_front_direct(
                conversation_id=front_conversation_id,
                reply_text=templates["patient_not_found"].format(lien_type=lien_type)
            )

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

        # Check if we have split documents from enhanced lien processing
        split_documents = []
        if document_analysis_results:
            for doc_result in document_analysis_results:
                enhanced_lien_data = doc_result.get("enhanced_lien_processing", {})
                if enhanced_lien_data.get("processing_type") == "enhanced_lien_processing_split":
                    split_documents = enhanced_lien_data.get("split_documents", [])
                    break

        # Process split documents if available, otherwise fall back to original attachment
        upload_results = []

        if split_documents:
            logger.info(f"📄 {signature_type} AGENT: Found {len(split_documents)} split documents to process")

            # Import upload service for split documents
            from app.services.lien_upload_service import upload_lien_pdf_bytes_to_radflow

            # Process each split document
            for i, split_doc in enumerate(split_documents):
                split_patient_id = split_doc.get("patient_id", "")
                split_lien_type = split_doc.get("lien_type", "")
                split_pdf_bytes = split_doc.get("pdf_bytes", b"")
                page_count = split_doc.get("page_count", 0)

                logger.info(
                    f"📄 {signature_type} AGENT: Processing split {i+1}/{len(split_documents)}: "
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
            # Fallback: No split documents, use original attachment upload logic
            logger.info(f"📄 {signature_type} AGENT: No split documents found, using original attachment")

            # Extract first attachment for upload
            attachment_data = {}
            if email_obj.raw_data and isinstance(email_obj.raw_data, dict):
                target_data = email_obj.raw_data.get('target', {}).get('data', {})
                attachments = target_data.get('attachments', [])
                if attachments:
                    attachment_data = attachments[0]  # Use first attachment

            upload_success = await _upload_lien_to_patient_file(patient_id, lien_type, attachment_data)

            upload_results.append({
                "patient_id": patient_id,
                "lien_type": lien_type,
                "success": upload_success
            })

        if not upload_success:
            logger.warning(f"File upload failed for patient {patient_id}, but continuing with response")

        # Process patient information for response
        patient_name = "Unknown"
        dob = "Unknown"
        doi = "Unknown"

        if patient_info_response and isinstance(patient_info_response, dict):
            if patient_info_response.get("success") and patient_info_response.get("data"):
                data = patient_info_response["data"]
                if "patients" in data and data["patients"]:
                    patient = data["patients"][0]
                    patient_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()

                    # Format DOB
                    raw_dob = patient.get('date_of_birth')
                    if raw_dob:
                        try:
                            date_obj = datetime.strptime(raw_dob, '%Y-%m-%d')
                            dob = date_obj.strftime('%m/%d/%Y')
                        except:
                            dob = raw_dob  # Use as-is if parsing fails

                    # Format DOI
                    raw_doi = patient.get('date_of_injury') or patient.get('date_of_loss')
                    if raw_doi:
                        try:
                            date_obj = datetime.strptime(raw_doi, '%Y-%m-%d')
                            doi = date_obj.strftime('%m/%d/%Y')
                        except:
                            doi = raw_doi  # Use as-is if parsing fails

        # Generate lien status table
        lien_status_table = await _generate_lien_status_table(patient_id, upload_results, signature_type)

        # Generate success response
        reply_body = templates["success"].format(
            lien_type=lien_type,
            patient_id=patient_id,
            patient_name=patient_name,
            dob=dob,
            doi=doi
        )

        # Replace {lien_status_table} placeholder with actual table
        reply_body = reply_body.replace("{lien_status_table}", lien_status_table)

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
                "total_splits": len(split_documents) if split_documents else 0,
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
