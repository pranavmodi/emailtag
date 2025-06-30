"""
Handles "Bill or balance Request" requests using an AI agent.

This module will contain the logic for an AI agent that processes emails tagged
as "Bill or balance Request".
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
# from agents import aio, function_tool, tool

from app.core.config import settings as app_settings_instance
from app.services import frontapp_service
from app.agents.agent_helpers import send_reply_to_front_direct, extract_patient_id_from_email_logic
# Import shared templates
from app.agents.templates.shared_templates import (
    TEMPLATE_REQUEST_PATIENT_ID,
    TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE
)
# Import bill balance templates
from app.agents.templates.bill_balance_templates import (
    COMPREHENSIVE_BILL_BALANCE_TEMPLATE,
    COMPREHENSIVE_LIEN_REMINDER_TEMPLATE,
    PATIENT_HEADER_TEMPLATE,
    SIMPLE_PATIENT_HEADER_TEMPLATE
)

# --- BEGIN: Logging ---
logger = get_task_logger(__name__)
# --- END: Logging ---

# --- BEGIN: Response Templates ---

# Main template for Bill & Balance response
BILL_BALANCE_TEMPLATE = """
{report_header}
Thank you for your request and for using Precise Imaging for your patient's imaging needs.
{bill_attachment_line}

Patient Information:
{patient_info}

Billing Status:
{billing_status_section}

Lien Status:
{lien_status_table}

To save time, you can download the bills in our portal which also contains the bill balance at the bottom.
<a href="http://precise.radflow360.com/">Access bills, appointment times, and e-sign liens (Click request login if you don't have an account)</a>

Thank you,
Precise Imaging Billing Dept.
http://www.PreciseMRI.com
"""

# Template for when liens are not signed
LIEN_REMINDER_TEMPLATE = """
Thank you for your request and for using Precise Imaging for your patient's imaging needs.
{report_header}

Patient Information:
{patient_info}

Billing Status:
Please review the lien status as we are missing signed liens which must be signed before a bill is produced.

Lien Status:
{lien_status_table}



To save time, you can download the bills in our portal which also contains the bill balance at the bottom.
Access bills, appointment times, and e-sign liens (Click request login if you don't have an account)

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""
# --- END: Response Templates ---


# --- Helper Functions for MCP Integration ---

def _create_lien_status_table(lien_statuses: List[Dict[str, Any]]) -> str:
    """Creates an HTML table for lien statuses that renders properly in email clients."""
    if not lien_statuses:
        return "No lien information available"
    
    # Create HTML table for proper email rendering
    html_parts = []
    html_parts.append('<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-family: monospace; margin: 10px 0;">')
    html_parts.append('<thead>')
    html_parts.append('<tr style="background-color: #f0f0f0; font-weight: bold;">')
    html_parts.append('<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">Lien type</th>')
    html_parts.append('<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">Patient Signature</th>')
    html_parts.append('<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">Attorney Signature</th>')
    html_parts.append('</tr>')
    html_parts.append('</thead>')
    html_parts.append('<tbody>')
    
    for lien in lien_statuses:
        lien_type = lien.get('lienType', 'Unknown')
        
        # Use the boolean flags as the source of truth for signature status
        if lien.get('hasPatientSigned', False):
            patient_date = lien.get('patientSignedLienDate', '')
            # Only show date if it exists and is not None/empty/null
            if patient_date and str(patient_date).lower() not in ['none', 'null', '']:
                # Clean up the date format if it's too long
                if len(patient_date) > 20:
                    # Try to extract just the date part (first 10 characters usually)
                    patient_date = patient_date[:10] if '/' in patient_date[:10] or '-' in patient_date[:10] else patient_date[:20]
                patient_sig = f"Signed {patient_date}"
            else:
                patient_sig = "Signed"
        else:
            patient_sig = "Not Signed"
            
        if lien.get('hasAttorneySigned', False):
            attorney_date = lien.get('attorneySignedDate', '')
            # Only show date if it exists and is not None/empty/null
            if attorney_date and str(attorney_date).lower() not in ['none', 'null', '']:
                # Clean up the date format if it's too long
                if len(attorney_date) > 20:
                    attorney_date = attorney_date[:10] if '/' in attorney_date[:10] or '-' in attorney_date[:10] else attorney_date[:20]
                attorney_sig = f"Signed {attorney_date}"
            else:
                attorney_sig = "Signed"
        else:
            attorney_sig = "Not Signed"
        
        # Add table row
        html_parts.append('<tr>')
        html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{lien_type}</td>')
        html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{patient_sig}</td>')
        html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{attorney_sig}</td>')
        html_parts.append('</tr>')
    
    html_parts.append('</tbody>')
    html_parts.append('</table>')
    
    return ''.join(html_parts)

def _create_billing_status_table(bill_balance: float, bill_status: Dict[str, Any], study_details: List[Dict[str, Any]]) -> str:
    """Creates an HTML table for billing status with study information."""
    
    # Create the billing status header
    bill_date = bill_status.get('lastBilledDate', 'unknown date') if bill_status.get('isBilled') else 'N/A'
    if bill_balance and bill_balance > 0:
        billing_header = f"The patient's current bill balance is ${bill_balance:.2f} as of {bill_date}"
    else:
        billing_header = "No billing information available yet."
    
    # Start building the HTML table
    html_parts = []
    html_parts.append(f'<p>{billing_header}</p>')
    
    if study_details:
        html_parts.append('<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-family: Arial, sans-serif; margin: 10px 0; width: 100%;">')
        html_parts.append('<thead>')
        html_parts.append('<tr style="background-color: #f0f0f0; font-weight: bold;">')
        html_parts.append('<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">STUDY DESCRIPTION</th>')
        html_parts.append('<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">STUDY DATE</th>')
        html_parts.append('<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">EXAM STATUS</th>')
        html_parts.append('<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">BILLING STATUS</th>')
        html_parts.append('</tr>')
        html_parts.append('</thead>')
        html_parts.append('<tbody>')
        
        for study in study_details:
            study_description = study.get('study_description', 'Unknown Study')
            study_date = study.get('appointment_time', 'Unknown Date')
            exam_status = study.get('status', 'Unknown Status')
            
            # Note: Current MCP doesn't provide billing amounts per study
            # This is a limitation we need to work around
            if bill_balance and bill_balance > 0 and bill_status.get('isBilled'):
                # For now, we'll indicate that billing info is available but not per-study breakdown
                billing_status = f"Part of ${bill_balance:.2f} total - See portal for breakdown"
            else:
                billing_status = "Not yet billed"
            
            html_parts.append('<tr>')
            html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{study_description}</td>')
            html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{study_date}</td>')
            html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{exam_status}</td>')
            html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{billing_status}</td>')
            html_parts.append('</tr>')
        
        html_parts.append('</tbody>')
        html_parts.append('</table>')
    else:
        html_parts.append('<p>No study information available.</p>')
    
    return ''.join(html_parts)

def _create_patient_header(patient_data: Dict[str, Any], patient_id: str) -> str:
    """Creates the patient header with full details if available."""
    patient_name = patient_data.get('patientName', '')
    dob = patient_data.get('dateOfBirth', '')
    doi = patient_data.get('dateOfInjury', '')
    
    if patient_name and dob:
        return PATIENT_HEADER_TEMPLATE.format(
            patient_id=patient_id,
            patient_name=patient_name,
            dob=dob,
            doi=doi if doi else 'N/A'
        )
    else:
        return SIMPLE_PATIENT_HEADER_TEMPLATE.format(patient_id=patient_id)

def _check_if_clarification_request(conversation_history: List[Dict[str, Any]]) -> bool:
    """
    Check if we've already sent a clarification request in this conversation.
    Returns True if we've already asked for patient details using apt status template.
    """
    for message in conversation_history:
        body = message.get('body', '').lower()
        # Check for apt status template: "Please provide the patient ID or first name, last name and date of birth."
        if ('please provide the patient id' in body and 'first name' in body and 
            'last name' in body and 'date of birth' in body and message.get('direction') == 'outbound'):
            return True
    return False


async def handle_bill_balance_request(
    front_conversation_id: str,
    current_email_content: str,
    structured_history_messages: List[Dict[str, Any]],
    settings_obj: Any = app_settings_instance
) -> Dict[str, Any]:
    """
    Main orchestrator for handling "Bill or balance Request" emails.
    Implements the 3-step logic:
    1. If single Patient ID found → auto-reply
    2. If no/multiple patients → ask for clarification (once)
    3. If still can't find → tag for human review
    """
    logger.info(f"handle_bill_balance_request called for conversation: {front_conversation_id}")
    
    # Check if we've already asked for clarification
    already_asked_for_clarification = _check_if_clarification_request(structured_history_messages)
    
    # Try to extract patient ID from the email
    patient_id = await extract_patient_id_from_email_logic(f"Subject: \n\n{current_email_content}")
    
    if not patient_id:
        if already_asked_for_clarification:
            # Step 3: We already asked for clarification, tag for human review
            logger.info(f"Patient ID still not found after clarification request for conversation {front_conversation_id}. Tagging for human review.")
            
            try:
                # Add human review tag
                frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
                
                await send_reply_to_front_direct(
                    conversation_id=front_conversation_id,
                    reply_text=TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE
                )
                
                return {"agent_handled": True, "processed_flag": True, "details": {"action": "tagged_for_human_review"}}
            except Exception as e:
                logger.error(f"Failed to tag for human review: {e}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to tag for human review: {e}"}}
        else:
            # Step 2: First time we can't find patient ID, ask for clarification
            logger.info(f"Patient ID not found for conversation {front_conversation_id}. Requesting clarification.")
            
            try:
                await send_reply_to_front_direct(
                    conversation_id=front_conversation_id,
                    reply_text=TEMPLATE_REQUEST_PATIENT_ID
                )
                
                return {"agent_handled": True, "processed_flag": True, "details": {"action": "requested_clarification"}}
            except Exception as e:
                logger.error(f"Failed to send clarification request: {e}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to send clarification: {e}"}}

    # Step 1: Patient ID found, get patient information and billing information using MCP tools
    logger.info(f"Patient ID {patient_id} found. Fetching patient and billing information via MCP tools.")
    
    try:
        # Import the MCP client function
        from app.mcp import call_mcp_tool
        
        # Add performance monitoring
        mcp_start_time = time.time()
        
        # First, get patient information (name, DOB, DOI)
        patient_info_response = await call_mcp_tool(
            tool_name="fetch_patient_info",
            arguments={"patient_id": patient_id}
        )
        
        # Get study details for billing table
        study_details_response = await call_mcp_tool(
            tool_name="fetch_study_details",
            arguments={"patient_id": patient_id}
        )
        
        # Then, call the MCP tool to get billing information
        mcp_response = await call_mcp_tool(
            tool_name="get_patient_lien_bill_balance",
            arguments={"patient_id": patient_id}
        )
        
        mcp_duration = time.time() - mcp_start_time
        logger.info(f"MCP tools completed in {mcp_duration:.2f} seconds for patient {patient_id}")
        
        # Process patient information response
        patient_header_text = f"Patient ID: {patient_id}"  # Default fallback
        if patient_info_response and isinstance(patient_info_response, dict):
            patient_data_section = patient_info_response.get('data', {})
            if patient_data_section and isinstance(patient_data_section, dict):
                patients_list = patient_data_section.get('patients', [])
                if patients_list and len(patients_list) > 0:
                    patient_info = patients_list[0]
                    first_name = patient_info.get('first_name', '').strip()
                    last_name = patient_info.get('last_name', '').strip()
                    birth_date = patient_info.get('birth_date', '')
                    doi = patient_info.get('doi', '')
                    
                    # Format name
                    if first_name and last_name:
                        full_name = f"{first_name} {last_name}"
                    elif first_name:
                        full_name = first_name
                    elif last_name:
                        full_name = last_name
                    else:
                        full_name = "Unknown"
                    
                    # Format DOB (convert from YYYY-MM-DD to MM/DD/YYYY)
                    formatted_dob = "Unknown"
                    if birth_date:
                        try:
                            date_obj = datetime.strptime(birth_date, '%Y-%m-%d')
                            formatted_dob = date_obj.strftime('%m/%d/%Y')
                        except:
                            formatted_dob = birth_date  # Use as-is if parsing fails
                    
                    # Format DOI (convert from YYYY-MM-DD to MM/DD/YYYY)
                    formatted_doi = "Unknown"
                    if doi:
                        try:
                            date_obj = datetime.strptime(doi, '%Y-%m-%d')
                            formatted_doi = date_obj.strftime('%m/%d/%Y')
                        except:
                            formatted_doi = doi  # Use as-is if parsing fails
                    
                    # Create formatted patient header
                    patient_header_text = f"{patient_id} - {full_name} - DOB: {formatted_dob} - DOI: {formatted_doi}"
                    logger.info(f"Formatted patient header: {patient_header_text}")
                else:
                    logger.warning(f"No patients found in patient info response for {patient_id}")
            else:
                logger.warning(f"Invalid data structure in patient info response for {patient_id}")
        else:
            logger.warning(f"Invalid or empty patient info response for {patient_id}")
        
        # Process study details response for billing table
        study_details_list = []
        if study_details_response and isinstance(study_details_response, dict):
            if study_details_response.get('success'):
                studies = study_details_response.get('studies', [])
                if studies and isinstance(studies, list):
                    study_details_list = studies
                    logger.info(f"Found {len(study_details_list)} studies for patient {patient_id}")
                else:
                    logger.warning(f"No studies found in study details response for patient {patient_id}")
            else:
                logger.warning(f"Study details fetch failed for patient {patient_id}: {study_details_response.get('message', 'Unknown error')}")
        else:
            logger.warning(f"Invalid study details response for patient {patient_id}")
        
        if not mcp_response or not isinstance(mcp_response, dict):
            logger.error(f"Invalid MCP response for patient {patient_id}: {mcp_response}")
            # Tag for human review on MCP error
            try:
                frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
            except Exception as tag_error:
                logger.error(f"Failed to add human review tag: {tag_error}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": "Invalid MCP tool response"}}
        
        # Log MCP response schema and structure without huge base64 data
        def get_schema_info(obj, max_depth=3, current_depth=0):
            """Get schema information about nested objects."""
            if current_depth >= max_depth:
                return f"<max_depth_reached_type_{type(obj).__name__}>"
            
            if isinstance(obj, dict):
                schema = {}
                for k, v in obj.items():
                    if k == 'bill' and isinstance(v, str) and len(v) > 100:
                        schema[k] = f"<string_length_{len(v)}_truncated>"
                    elif isinstance(v, str) and len(v) > 100:
                        schema[k] = f"<string_length_{len(v)}>"
                    elif isinstance(v, (dict, list)):
                        schema[k] = get_schema_info(v, max_depth, current_depth + 1)
                    else:
                        schema[k] = v
                return schema
            elif isinstance(obj, list):
                if len(obj) == 0:
                    return []
                elif len(obj) == 1:
                    return [get_schema_info(obj[0], max_depth, current_depth + 1)]
                else:
                    return [get_schema_info(obj[0], max_depth, current_depth + 1), f"<{len(obj)-1}_more_items>"]
            else:
                return obj
        
        schema_info = get_schema_info(mcp_response)
        logger.info(f"MCP response schema for patient {patient_id}: {schema_info}")
        logger.info(f"MCP response top-level keys for patient {patient_id}: {list(mcp_response.keys())}")
        
        # Also log the types of top-level values
        type_info = {k: type(v).__name__ + (f"_len_{len(v)}" if hasattr(v, '__len__') and not isinstance(v, (int, float)) else "") for k, v in mcp_response.items()}
        logger.info(f"MCP response value types for patient {patient_id}: {type_info}")
        
        # Check if MCP call was successful - handle both explicit success field and implicit success
        mcp_success = mcp_response.get('success')
        if mcp_success is False:  # Explicitly False
            logger.error(f"MCP tool call explicitly failed for patient {patient_id}: {mcp_response.get('error', 'Unknown error')}")
            # Tag for human review on MCP error
            try:
                frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
            except Exception as tag_error:
                logger.error(f"Failed to add human review tag: {tag_error}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"MCP tool error: {mcp_response.get('error', 'Unknown error')}"}}
        elif mcp_success is None and 'error' in mcp_response:  # No success field but has error
            logger.error(f"MCP tool call failed (no success field) for patient {patient_id}: {mcp_response.get('error', 'Unknown error')}")
            # Tag for human review on MCP error
            try:
                frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
            except Exception as tag_error:
                logger.error(f"Failed to add human review tag: {tag_error}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"MCP tool error: {mcp_response.get('error', 'Unknown error')}"}}

        # NEW: Check for business logic failures within successful transport
        # Handle case where MCP transport succeeds but business logic fails
        data_section = mcp_response.get('data', {})
        if isinstance(data_section, dict):
            response_status = data_section.get('responseStatus', '')
            if response_status == 'Fail':
                exception_info = data_section.get('exception', {})
                if isinstance(exception_info, dict):
                    error_message = exception_info.get('exceptionMessage', 'Unknown business logic error')
                    logger.error(f"MCP business logic failed for patient {patient_id}: {error_message}")
                    
                    # Enhanced error pattern matching for different business logic failures
                    error_patterns = [
                        {
                            'pattern': 'Object reference not set to an instance of an object',
                            'action': 'patient_not_found',
                            'description': 'Patient ID does not exist or has null/incomplete data'
                        },
                        {
                            'pattern': 'No patients found',
                            'action': 'patient_not_found',
                            'description': 'Patient ID not found in database'
                        },
                        {
                            'pattern': 'Invalid patient id',
                            'action': 'patient_not_found',
                            'description': 'Patient ID format is invalid'
                        },
                        {
                            'pattern': 'Patient record is inactive',
                            'action': 'patient_inactive',
                            'description': 'Patient record exists but is inactive'
                        },
                        {
                            'pattern': 'Access denied',
                            'action': 'access_denied',
                            'description': 'Insufficient permissions to access patient data'
                        },
                        {
                            'pattern': 'timeout',
                            'action': 'timeout',
                            'description': 'RadFlow API request timed out'
                        }
                    ]
                    
                    matched_pattern = None
                    for pattern_info in error_patterns:
                        if pattern_info['pattern'].lower() in error_message.lower():
                            matched_pattern = pattern_info
                            break
                    
                    if matched_pattern and matched_pattern['action'] in ['patient_not_found', 'patient_inactive']:
                        logger.info(f"Patient {patient_id} - {matched_pattern['description']}")
                        
                        # Send a polite "patient not found" response instead of erroring
                        patient_not_found_response = f"""
{patient_header_text}

Thank you for your billing inquiry.

We were unable to locate billing information for the provided Patient ID ({patient_id}) in our system. This could mean:
- The Patient ID may be incorrect or incomplete
- The patient may not have any services with our facility
- The patient record may not be set up for billing yet

Please verify the Patient ID and contact our billing department at (888) 555-1212 if you need assistance locating the correct information.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""
                        
                        await send_reply_to_front_direct(
                            conversation_id=front_conversation_id,
                            reply_text=patient_not_found_response.strip()
                        )
                        
                        return {
                            "agent_handled": True, 
                            "processed_flag": True, 
                            "details": {
                                "action": "sent_patient_not_found_response",
                                "patient_id": patient_id,
                                "reason": matched_pattern['description'],
                                "error_pattern": matched_pattern['pattern'],
                                "mcp_error": error_message,
                                "mcp_duration": mcp_duration
                            }
                        }
                    else:
                        # For other business logic errors, tag for human review
                        error_classification = matched_pattern['action'] if matched_pattern else 'unknown_business_error'
                        logger.error(f"Business logic error [{error_classification}] for patient {patient_id}: {error_message}")
                        try:
                            frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
                        except Exception as tag_error:
                            logger.error(f"Failed to add human review tag: {tag_error}")
                        return {
                            "agent_handled": False, 
                            "processed_flag": False, 
                            "details": {
                                "reason": f"MCP business logic error: {error_message}",
                                "error_classification": error_classification,
                                "mcp_duration": mcp_duration
                            }
                        }
                else:
                    logger.error(f"MCP responseStatus is 'Fail' but no exception details for patient {patient_id}")
                    try:
                        frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
                    except Exception as tag_error:
                        logger.error(f"Failed to add human review tag: {tag_error}")
                    return {"agent_handled": False, "processed_flag": False, "details": {"reason": "MCP business logic failed without details"}}

        # Parse the MCP response - check multiple possible locations for the data
        # The actual result is often nested under a 'data' key, so we check there first.
        if 'data' in mcp_response and isinstance(mcp_response.get('data'), dict):
            logger.info("Found 'data' key in MCP response, looking for 'result' inside.")
            result = mcp_response.get('data', {}).get('result', {})
        else:
            logger.info("No 'data' key in MCP response, looking for 'result' at the top level.")
            result = mcp_response.get('result', {})

        # If the result is a JSON string, parse it.
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                logger.warning(f"Result is a string but not valid JSON for patient {patient_id}: {result[:200]}")


        logger.info(f"Final result data for patient {patient_id}: {get_schema_info(result)}")
        
        if not result or not isinstance(result, dict):
            logger.error(f"No valid result data in MCP response for patient {patient_id}.")
            # Tag for human review on empty result
            try:
                frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
            except Exception as tag_error:
                logger.error(f"Failed to add human review tag: {tag_error}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": "No billing data found"}}
        
        # Extract data from MCP response with error checking
        patient_bill_balance = result.get('patientBillBalance', 0)
        patient_bill_status = result.get('patientBillStatus', {})
        lien_status_list = result.get('lienStatusList', [])
        
        # Patient data might be at top level or in a nested structure
        patient_data = result.get('patientData', {})
        if not patient_data:
            # Create minimal patient data from available fields
            patient_data = {
                'patientName': result.get('patientName', ''),
                'dateOfBirth': result.get('dateOfBirth', ''),
                'dateOfInjury': result.get('dateOfInjury', '')
            }
        
        logger.info(f"Extracted billing data for patient {patient_id}: balance={patient_bill_balance}, status={get_schema_info(patient_bill_status)}, liens={len(lien_status_list)}, studies_from_details={len(study_details_list)}")
        
        # Log lien status details for debugging
        if lien_status_list:
            for i, lien in enumerate(lien_status_list):
                logger.info(f"Lien {i}: type={lien.get('lienType')}, patient_signed={lien.get('hasPatientSigned')}, patient_date={lien.get('patientSignedLienDate')}, attorney_signed={lien.get('hasAttorneySigned')}, attorney_date={lien.get('attorneySignedDate')}")
        
        # Check if we actually have meaningful billing data
        has_billing_data = (
            patient_bill_balance is not None and patient_bill_balance > 0
        ) or (
            patient_bill_status and isinstance(patient_bill_status, dict) and patient_bill_status
        ) or (
            lien_status_list and isinstance(lien_status_list, list) and len(lien_status_list) > 0
        ) or (
            study_details_list and isinstance(study_details_list, list) and len(study_details_list) > 0
        )
        
        if not has_billing_data:
            logger.warning(f"No meaningful billing data found for patient {patient_id}. All values are empty/zero.")
            # Create patient header for no data response
            patient_header = _create_patient_header(patient_data, patient_id)
            
            # Send a response indicating no billing data available
            no_data_response = f"""
{patient_header_text}

Thank you for your billing inquiry.

Currently, there is no billing information available in our system for this patient. This could mean:
- No services have been rendered yet
- Bills have not been generated
- The patient account is not set up for billing

Please contact our billing department at (888) 555-1212 for further assistance.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""
            
            await send_reply_to_front_direct(
                conversation_id=front_conversation_id,
                reply_text=no_data_response.strip()
            )
            
            return {
                "agent_handled": True, 
                "processed_flag": True, 
                "details": {
                    "action": "sent_no_billing_data_response",
                    "patient_id": patient_id,
                    "reason": "No billing data available"
                }
            }
        
        # Check if liens are properly signed
        all_liens_signed = all(
            lien.get('hasPatientSigned', False) and lien.get('hasAttorneySigned', False)
            for lien in lien_status_list
        )
        
        # Determine if reports are requested
        include_reports = "report" in current_email_content.lower()
        
        # Build comprehensive response using new template
        attachments = []
        
        # Use the formatted patient header from MCP data
        patient_header = patient_header_text
        
        # Create sections for the comprehensive template
        billing_status_table = _create_billing_status_table(patient_bill_balance, patient_bill_status, study_details_list)
        lien_status_table = _create_lien_status_table(lien_status_list)
        
        # Determine report header and bill attachment line
        report_header = "The available final reports have been attached." if include_reports else ""
        bill_attachment_line = "A copy of the most recent bill is attached." if patient_bill_status.get("isBilled") else ""
        
        if not all_liens_signed:
            # Generate Lien Reminder response using new comprehensive template
            reply_body = COMPREHENSIVE_LIEN_REMINDER_TEMPLATE.format(
                patient_header=patient_header,
                lien_status_table=lien_status_table
            )
            subject = f"Re: {patient_id} - Lien Signature Required"
        else:
            # Generate comprehensive Bill & Balance response using new template
            reply_body = COMPREHENSIVE_BILL_BALANCE_TEMPLATE.format(
                patient_header=patient_header,
                bill_attachment_line=bill_attachment_line,
                billing_status_table=billing_status_table,
                lien_status_table=lien_status_table
            )
            subject = f"Re: {patient_id} - Billing Information"
            
            # Add bill attachment if available
            if patient_bill_status.get("bill"):
                # TODO: Handle base64 bill attachment
                # For now, we note that a bill is available but don't attach it
                pass

        # TODO: Add report attachments if requested
        if include_reports:
            # This would need additional MCP calls to get reports
            pass

        # Send the response
        await send_reply_to_front_direct(
            conversation_id=front_conversation_id,
            reply_text=reply_body
        )
        
        logger.info(f"Successfully sent comprehensive billing response for patient {patient_id} in conversation {front_conversation_id}")
        return {
            "agent_handled": True, 
            "processed_flag": True, 
            "details": {
                "action": "sent_comprehensive_billing_info",
                "patient_id": patient_id,
                "bill_balance": patient_bill_balance,
                "liens_signed": all_liens_signed,
                "studies_found": len(study_details_list),
                "attachments": len(attachments),
                "template_used": "comprehensive" if all_liens_signed else "lien_reminder"
            }
        }
        
    except asyncio.TimeoutError as e:
        logger.error(f"Timeout error during MCP call for patient {patient_id}: {e}")
        try:
            frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
        except Exception as tag_error:
            logger.error(f"Failed to add human review tag: {tag_error}")
        
        # Send user-friendly timeout response
        timeout_response = f"""
{patient_header_text}

Thank you for your billing inquiry.

We're currently experiencing delays in retrieving billing information from our system. This is likely temporary.

Please try your request again in a few minutes, or contact our billing department directly at (888) 555-1212 for immediate assistance.

Thank you for your patience,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""
        try:
            await send_reply_to_front_direct(
                conversation_id=front_conversation_id,
                reply_text=timeout_response.strip()
            )
            return {
                "agent_handled": True, 
                "processed_flag": True, 
                "details": {
                    "action": "sent_timeout_response",
                    "patient_id": patient_id,
                    "reason": "MCP timeout error"
                }
            }
        except Exception as send_error:
            logger.error(f"Failed to send timeout response: {send_error}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Timeout error and failed to send response: {e}"}}
    
    except ConnectionError as e:
        logger.error(f"Connection error during MCP call for patient {patient_id}: {e}")
        try:
            frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
        except Exception as tag_error:
            logger.error(f"Failed to add human review tag: {tag_error}")
        return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"MCP connection error: {e}"}}
    
    except Exception as e:
        logger.error(f"Unexpected error processing billing request for patient {patient_id}: {e}", exc_info=True)
        # Tag for human review on processing error
        try:
            frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
        except Exception as tag_error:
            logger.error(f"Failed to add human review tag: {tag_error}")
        return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Unexpected processing error: {e}"}}