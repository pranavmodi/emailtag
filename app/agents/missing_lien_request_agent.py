"""
Handles "Missing Lien Request" requests using an AI agent.

This module contains the logic for an AI agent that processes emails tagged
as "Missing Lien Request". It performs patient lookup and provides appropriate 
eSign links for attorneys to sign liens, or requests patient identification.
"""
import asyncio
import os
import json
import ast
from typing import Optional, Dict, Any, List
import re
from pathlib import Path
import time  # For performance monitoring
from datetime import datetime  # For date formatting

from celery.utils.log import get_task_logger
from app.core.config import settings as app_settings_instance
from app.services import frontapp_service
from app.agents.agent_helpers import send_reply_to_front_direct, extract_patient_id_from_email_logic
from app.mcp import default_mcp_client as mcp_client
# Import shared templates
from app.agents.templates.shared_templates import (
    TEMPLATE_REQUEST_PATIENT_ID,
    TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE
)

# --- BEGIN: Logging ---
logger = get_task_logger(__name__)
# --- END: Logging ---

# --- BEGIN: Tag Constants ---
TAG_AI_HUMAN_REVIEW_REQUIRED = "AI: Human review required"
MISSING_LIEN_REQUEST_TAG_NAME = "Missing Lien Request"
# --- END: Tag Constants ---

# --- BEGIN: Response Templates ---

# Template for single patient found with eSign link
TEMPLATE_ESIGN_LINK_SINGLE_PATIENT = """
Thank you for your lien request.

Patient ID: {patient_id}
Patient: {patient_name}
DOB: {dob}
DOI: {doi}

Please use the following link to electronically sign the required liens for this patient:

{esign_link}

If you have any issues accessing the eSign portal, please contact our billing department at (888) 555-1212.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""

# Template for when no patient found or multiple patients found
TEMPLATE_REQUEST_PATIENT_INFO = """
Thank you for your lien request. 

To locate the correct patient and provide you with the appropriate eSign link, please provide one of the following:

1. Patient ID, OR
2. Patient's first name, last name, and date of birth (DOB), OR  
3. Patient's first name, last name, and date of loss (DOL)

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""

# Template for escalation when patient still cannot be found after additional info
TEMPLATE_ESCALATE_HUMAN_REVIEW = """
Thank you for the additional information. We're still having trouble locating the patient record to provide the appropriate lien documents.

A member of our billing team will personally review your request and get back to you shortly with the required lien information.

Thank you for your patience,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""

# --- END: Response Templates ---

# --- BEGIN: Helper Functions ---

def _check_conversation_history_for_clarification_request(structured_history_messages: List[Dict[str, Any]]) -> bool:
    """
    Check if we've already asked for patient clarification in this conversation.
    Returns True if we already asked for clarification.
    """
    if not structured_history_messages:
        return False
    
    # Look for our clarification message in the conversation history
    clarification_keywords = ["patient id", "first name", "last name", "date of birth", "date of loss"]
    
    for message in structured_history_messages:
        message_body = message.get("body", "").lower()
        direction = message.get("direction", "")
        
        # Check if this is an outbound message (from us) that contains clarification request keywords
        if direction == "outbound" and any(keyword in message_body for keyword in clarification_keywords):
            logger.info("Found previous clarification request in conversation history")
            return True
    
    return False

async def _get_esign_link_for_patient(patient_id: str) -> Optional[str]:
    """
    Generate or retrieve the eSign link for a specific patient.
    Currently returns the portal URL as a fallback since specific eSign link generation
    tools may not be available via MCP.
    """
    try:
        # For now, return the standard portal URL where attorneys can sign liens
        # In the future, this could be enhanced to generate patient-specific links
        # via MCP tools if they become available
        portal_url = "http://precise.radflow360.com/"
        logger.info(f"Using portal URL for patient {patient_id}: {portal_url}")
        return portal_url
            
    except Exception as e:
        logger.error(f"Error generating eSign link for patient {patient_id}: {e}", exc_info=True)
        return None

async def _lookup_patient_by_details(first_name: str, last_name: str, dob: str = None, dol: str = None) -> List[Dict[str, Any]]:
    """
    Lookup patient by name and DOB/DOL using existing MCP tools.
    Returns a list of matching patients.
    
    Note: This is a simplified implementation that relies on the existing
    fetch_patient_by_id tool. In a production system, you would implement
    a more sophisticated search function.
    """
    try:
        # For now, we cannot search by name/DOB directly with existing MCP tools
        # The current MCP tools only support lookup by patient_id
        # In a real implementation, you would need a proper patient search MCP tool
        logger.warning("Patient lookup by name/DOB not currently supported with existing MCP tools")
        return []
            
    except Exception as e:
        logger.error(f"Error searching for patients: {e}", exc_info=True)
        return []

# --- END: Helper Functions ---

# --- BEGIN: Main Agent Handler ---

async def handle_missing_lien_request(
    front_conversation_id: str,
    current_email_content: str,
    structured_history_messages: List[Dict[str, Any]],
    settings_obj: Any = app_settings_instance,
    email_subject: str = None
) -> Dict[str, Any]:
    """
    Orchestrates the AI agent to handle a "Missing Lien Request".
    
    Logic:
    1. If single Patient ID found: Reply with specific eSign link for attorney to sign liens
    2. No patient or multiple patients: Reply with template asking for Patient ID or name/DOB/DOL
    3. Never use the template twice - if already asked, escalate to human review
    4. If they reply and can't find a match, tag for human review
    """
    logger.info(f"Initiating Missing Lien Request agent for conv ID: {front_conversation_id}")

    # Connect to MCP server
    if not await mcp_client.connect():
        logger.error("Failed to connect to MCP server for Missing Lien Request agent.")
        try:
            frontapp_service.add_conversation_tags(front_conversation_id, [TAG_AI_HUMAN_REVIEW_REQUIRED])
            await send_reply_to_front_direct(
                front_conversation_id,
                "Internal data connection error. A team member will assist you with your lien request.",
                tags_to_add=None,
                tags_to_remove=None
            )
        except Exception as e:
            logger.error(f"Failed to send fallback reply: {e}")
        return {"agent_handled": False, "processed_flag": True, "details": {"reason": "MCP connection failed"}}

    # Check if we've already asked for clarification in this conversation
    already_asked_for_clarification = _check_conversation_history_for_clarification_request(structured_history_messages)
    
    # Extract patient ID from current email
    patient_id = await extract_patient_id_from_email_logic(current_email_content, front_conversation_id, email_subject)
    
    if not patient_id:
        # Try to extract patient details (name, DOB, DOL) from email if no patient ID
        # This is a simple regex approach - could be enhanced with NLP
        name_pattern = r'(?:patient|name):\s*([A-Za-z\s]+)'
        dob_pattern = r'(?:dob|date of birth):\s*([0-9\/\-]+)'
        dol_pattern = r'(?:dol|date of loss|date of injury|doi):\s*([0-9\/\-]+)'
        
        name_match = re.search(name_pattern, current_email_content.lower())
        dob_match = re.search(dob_pattern, current_email_content.lower())
        dol_match = re.search(dol_pattern, current_email_content.lower())
        
        if name_match and (dob_match or dol_match):
            # Try to lookup by name and DOB/DOL
            patient_name = name_match.group(1).strip()
            name_parts = patient_name.split()
            
            if len(name_parts) >= 2:
                first_name = name_parts[0]
                last_name = " ".join(name_parts[1:])
                dob = dob_match.group(1).strip() if dob_match else None
                dol = dol_match.group(1).strip() if dol_match else None
                
                logger.info(f"Attempting patient lookup by name: {first_name} {last_name}, DOB: {dob}, DOL: {dol}")
                
                matching_patients = await _lookup_patient_by_details(first_name, last_name, dob, dol)
                
                if len(matching_patients) == 1:
                    # Found exactly one patient - treat as if we had patient ID
                    patient_data = matching_patients[0]
                    patient_id = patient_data.get("patient_id") or patient_data.get("id")
                    logger.info(f"Found single patient match: {patient_id}")
                elif len(matching_patients) > 1:
                    logger.info(f"Found multiple patient matches: {len(matching_patients)}")
                    # Multiple patients found - need clarification
                    patient_id = None
                else:
                    logger.info("No patients found by name lookup")
                    patient_id = None
    
    if not patient_id:
        if already_asked_for_clarification:
            # We already asked for clarification, escalate to human review
            logger.info(f"Patient ID still not found after clarification request for conversation {front_conversation_id}. Tagging for human review.")
            
            try:
                frontapp_service.add_conversation_tags(front_conversation_id, [TAG_AI_HUMAN_REVIEW_REQUIRED])
                
                await send_reply_to_front_direct(
                    conversation_id=front_conversation_id,
                    reply_text=TEMPLATE_ESCALATE_HUMAN_REVIEW
                )
                
                return {"agent_handled": True, "processed_flag": True, "details": {"action": "tagged_for_human_review"}}
            except Exception as e:
                logger.error(f"Failed to tag for human review: {e}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to tag for human review: {e}"}}
        else:
            # First time we can't find patient ID, ask for clarification
            logger.info(f"Patient ID not found for conversation {front_conversation_id}. Requesting clarification.")
            
            try:
                await send_reply_to_front_direct(
                    conversation_id=front_conversation_id,
                    reply_text=TEMPLATE_REQUEST_PATIENT_INFO
                )
                
                return {"agent_handled": True, "processed_flag": True, "details": {"action": "requested_clarification"}}
            except Exception as e:
                logger.error(f"Failed to send clarification request: {e}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to send clarification: {e}"}}

    # Patient ID found, get patient information and eSign link
    logger.info(f"Patient ID {patient_id} found. Fetching patient information and generating eSign link.")
    
    try:
        # Get patient information using MCP tools
        from app.mcp import call_mcp_tool
        
        patient_info_response = await call_mcp_tool(
            tool_name="fetch_patient_info",
            arguments={"patient_id": patient_id}
        )
        
        # Generate eSign link (currently uses portal URL)
        esign_link = await _get_esign_link_for_patient(patient_id)
        
        if not esign_link:
            # Final fallback to portal URL
            esign_link = "http://precise.radflow360.com/"
            logger.warning(f"Could not generate eSign link for patient {patient_id}, using final fallback")
        
        # Process patient information response
        patient_header_text = f"Patient ID: {patient_id}"
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
        
        # Generate response with eSign link
        reply_body = TEMPLATE_ESIGN_LINK_SINGLE_PATIENT.format(
            patient_id=patient_id,
            patient_name=patient_name,
            dob=dob,
            doi=doi,
            esign_link=esign_link
        )
        
        # Send the response
        await send_reply_to_front_direct(
            conversation_id=front_conversation_id,
            reply_text=reply_body
        )
        
        logger.info(f"Successfully sent eSign link response for patient {patient_id} in conversation {front_conversation_id}")
        return {
            "agent_handled": True, 
            "processed_flag": True, 
            "details": {
                "action": "sent_esign_link",
                "patient_id": patient_id,
                "esign_link": esign_link
            }
        }
        
    except Exception as e:
        logger.error(f"Unexpected error processing missing lien request for patient {patient_id}: {e}", exc_info=True)
        # Tag for human review on processing error
        try:
            frontapp_service.add_conversation_tags(front_conversation_id, [TAG_AI_HUMAN_REVIEW_REQUIRED])
            await send_reply_to_front_direct(
                conversation_id=front_conversation_id,
                reply_text="We encountered an error processing your lien request. A team member will review your request and get back to you shortly."
            )
        except Exception as tag_error:
            logger.error(f"Failed to add human review tag: {tag_error}")
        return {"agent_handled": False, "processed_flag": True, "details": {"reason": f"Unexpected processing error: {e}"}}

# --- END: Main Agent Handler --- 