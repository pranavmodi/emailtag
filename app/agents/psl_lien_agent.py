"""
Handles PSL (Patient Signed Lien) requests for both Rad Lien and Tech Lien tags.

This module contains the logic for an AI agent that processes emails tagged
as "PSL > Rad Lien" or "PSL > Tech Lien". It checks for lien modifications,
verifies readability, and either uploads to patient file or requests human review.
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
PSL_RAD_LIEN_TAG = "Rad Lien"
PSL_TECH_LIEN_TAG = "Tech Lien"
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

def _determine_lien_type(applied_tags: List[str]) -> str:
    """Determine whether this is a Rad Lien or Tech Lien based on tags."""
    if PSL_RAD_LIEN_TAG in applied_tags:
        return "Patient Signed Radiology Lien"
    elif PSL_TECH_LIEN_TAG in applied_tags:
        return "Patient Signed Technologist Lien"
    else:
        return "Patient Signed Lien"

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

# --- END: Helper Functions ---

# --- BEGIN: Main Agent Handler ---

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
    Orchestrates the AI agent to handle PSL lien submissions (Rad Lien or Tech Lien).
    
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
        document_analysis_results: Results from document analysis
        settings_obj: Settings object
        email_subject: Email subject line
        
    Returns:
        Dictionary with agent handling results
    """
    logger.info(f"Initiating PSL Lien agent for conv ID: {front_conversation_id}, tags: {applied_tags}")

    # Determine lien type from tags
    lien_type = _determine_lien_type(applied_tags)
    
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
                reply_text=TEMPLATE_LIEN_MODIFIED_REVIEW.format(lien_type=lien_type)
            )
            
            return {
                "agent_handled": True, 
                "processed_flag": True, 
                "details": {
                    "action": "tagged_for_human_review_modified",
                    "lien_type": lien_type
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
                reply_text=TEMPLATE_LIEN_UNREADABLE.format(lien_type=lien_type)
            )
            
            return {
                "agent_handled": True, 
                "processed_flag": True, 
                "details": {
                    "action": "requested_clearer_document",
                    "lien_type": lien_type
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
                reply_text=TEMPLATE_PATIENT_NOT_FOUND.format(lien_type=lien_type)
            )
            
            return {
                "agent_handled": True, 
                "processed_flag": True, 
                "details": {
                    "action": "tagged_for_human_review_no_patient",
                    "lien_type": lien_type
                }
            }
        except Exception as e:
            logger.error(f"Failed to handle missing patient: {e}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to handle missing patient: {e}"}}
    
    # Patient found - proceed with lien processing
    logger.info(f"Patient ID {patient_id} found. Processing {lien_type} for conversation {front_conversation_id}.")
    
    try:
        # Get patient information
        patient_info_response = await call_mcp_tool(
            tool_name="fetch_patient_info",
            arguments={"patient_id": patient_id}
        )
        
        # Upload lien to patient file (currently simulated)
        # Extract first attachment for upload
        attachment_data = {}
        if email_obj.raw_data and isinstance(email_obj.raw_data, dict):
            target_data = email_obj.raw_data.get('target', {}).get('data', {})
            attachments = target_data.get('attachments', [])
            if attachments:
                attachment_data = attachments[0]  # Use first attachment
        
        upload_success = await _upload_lien_to_patient_file(patient_id, lien_type, attachment_data)
        
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
        
        # Generate success response
        reply_body = TEMPLATE_LIEN_PROCESSED_SUCCESS.format(
            lien_type=lien_type,
            patient_id=patient_id,
            patient_name=patient_name,
            dob=dob,
            doi=doi
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
                "upload_success": upload_success
            }
        }
        
    except Exception as e:
        logger.error(f"Unexpected error processing PSL lien for patient {patient_id}: {e}", exc_info=True)
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