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
from app.helpers.billing_status_table import generate_billing_status_table
# Import shared templates
from app.agents.templates.shared_templates import (
    TEMPLATE_REQUEST_PATIENT_ID,
    TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE
)
# NOTE: Templates now come from database only, no imports needed from bill_balance_templates.py

# Database imports for fetching templates
from app.db.session import AsyncSessionLocal
from app.crud.tag_settings import tag_settings_crud

# --- BEGIN: Logging ---
logger = get_task_logger(__name__)
# --- END: Logging ---

# Tag name for bill balance templates in database
BILL_BALANCE_TAG_NAME = "Bill or Balance Request"


async def _fetch_bill_balance_templates_from_db() -> Dict[str, str]:
    """
    Fetch bill balance templates from database tag_settings.

    Returns:
        Dictionary with template keys mapped to template content
    """
    try:
        async with AsyncSessionLocal() as db:
            settings = await tag_settings_crud.get_settings_dict(db, BILL_BALANCE_TAG_NAME)
            if settings:
                return {
                    "found": settings.get("bill_balance_found_template", ""),
                    "not_found": settings.get("bill_balance_not_found_template", ""),
                    "lien_reminder": settings.get("bill_balance_lien_reminder_template", ""),
                    "no_data": settings.get("bill_balance_no_data_template", ""),
                    "request_patient_id": settings.get("bill_balance_request_patient_id_template", ""),
                    "escalation": settings.get("bill_balance_escalation_template", ""),
                    "timeout": settings.get("bill_balance_timeout_template", ""),
                }
    except Exception as e:
        logger.error(f"Failed to fetch bill balance templates from database: {e}")

    # Return empty templates if database fetch fails
    logger.warning(f"Could not load bill balance templates from database - will use hardcoded fallbacks")
    return {}

# --- BEGIN: Test Mode Support ---
BILL_BALANCE_TEST_OUTPUT_DIR = "/tmp/bill_balance_test_outputs"


async def save_test_mode_response_bill_balance(
    conversation_id: str,
    response_text: str,
    patient_id: str = None,
    response_type: str = None,
    details: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Saves the generated bill balance response to file system for test mode.
    Each patient ID gets its own response file to support multi-patient emails.

    Args:
        conversation_id: Front conversation ID
        response_text: The full formatted response message
        patient_id: Patient ID if found
        response_type: Type of response (e.g., "billing_info", "clarification_request", "not_found")
        details: Additional metadata about the response

    Returns:
        Dict with status and file path
    """
    try:
        test_dir = Path(BILL_BALANCE_TEST_OUTPUT_DIR) / conversation_id
        test_dir.mkdir(parents=True, exist_ok=True)

        # Use patient_id in filename to support multiple patients per conversation
        # If no patient_id, use timestamp to ensure uniqueness
        if patient_id:
            response_file = test_dir / f"response_{patient_id}.json"
        else:
            timestamp_suffix = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            response_file = test_dir / f"response_{timestamp_suffix}.json"

        response_data = {
            "timestamp": datetime.now().isoformat(),
            "conversation_id": conversation_id,
            "response_text": response_text,
            "patient_id": patient_id,
            "response_type": response_type,
            "details": details or {},
            "status": "test_mode_saved"
        }

        with open(response_file, "w") as f:
            json.dump(response_data, f, indent=2)

        logger.info(f"🧪 TEST MODE: Saved bill balance response to {response_file}")

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


async def send_or_save_response_bill_balance(
    conversation_id: str,
    response_text: str,
    test_mode: bool = False,
    patient_id: str = None,
    response_type: str = None,
    details: Dict[str, Any] = None
) -> None:
    """
    Either sends the response via Front API or saves to file based on test_mode.

    Args:
        conversation_id: Front conversation ID
        response_text: The full formatted response message
        test_mode: If True, save to file instead of sending
        patient_id: Patient ID if found
        response_type: Type of response
        details: Additional metadata
    """
    if test_mode:
        # Test mode: save to file
        await save_test_mode_response_bill_balance(
            conversation_id=conversation_id,
            response_text=response_text,
            patient_id=patient_id,
            response_type=response_type,
            details=details
        )
    else:
        # Normal mode: send via Front API
        await send_reply_to_front_direct(
            conversation_id=conversation_id,
            reply_text=response_text
        )
# --- END: Test Mode Support ---

# NOTE: Old BILL_BALANCE_TEMPLATE and LIEN_REMINDER_TEMPLATE removed.
# Templates are now loaded from database or fallback to bill_balance_templates.py


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
                # Extract just the date part, removing any time component
                patient_date = patient_date.split()[0] if ' ' in patient_date else patient_date
                patient_sig = f"Signed {patient_date}"
            else:
                patient_sig = "Signed"
        else:
            patient_sig = "Not Signed"

        if lien.get('hasAttorneySigned', False):
            attorney_date = lien.get('attorneySignedDate', '')
            # Only show date if it exists and is not None/empty/null
            if attorney_date and str(attorney_date).lower() not in ['none', 'null', '']:
                # Extract just the date part, removing any time component
                attorney_date = attorney_date.split()[0] if ' ' in attorney_date else attorney_date
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
    settings_obj: Any = app_settings_instance,
    email_subject: str = None,
    test_mode: bool = False,
    extracted_patient_ids: List[str] = None  # Add pre-extracted patient IDs parameter (list)
) -> Dict[str, Any]:
    """
    Main orchestrator for handling "Bill or balance Request" emails.
    Supports multiple patient IDs - will send separate responses for each patient.
    Implements the 3-step logic:
    1. If single Patient ID found → auto-reply
    2. If no/multiple patients → ask for clarification (once)
    3. If still can't find → tag for human review

    Args:
        front_conversation_id: Front conversation ID
        current_email_content: Current email body
        structured_history_messages: Conversation history
        settings_obj: Application settings
        email_subject: Email subject line
        test_mode: If True, save responses to file instead of sending via Front API
        extracted_patient_ids: Pre-extracted patient IDs (list)
    """
    logger.info(f"handle_bill_balance_request called for conversation: {front_conversation_id} (test_mode={test_mode})")

    # Convert None to empty list for easier handling
    if extracted_patient_ids is None:
        extracted_patient_ids = []

    # If multiple patient IDs, process each one separately
    if len(extracted_patient_ids) > 1:
        logger.info(f"Processing {len(extracted_patient_ids)} patients separately for bill balance")
        all_results = []

        for idx, patient_id in enumerate(extracted_patient_ids):
            logger.info(f"Processing patient {idx + 1}/{len(extracted_patient_ids)}: {patient_id}")

            # Call this same function recursively with single patient ID
            result = await handle_bill_balance_request(
                front_conversation_id=front_conversation_id,
                current_email_content=current_email_content,
                structured_history_messages=structured_history_messages,
                settings_obj=settings_obj,
                email_subject=email_subject,
                test_mode=test_mode,
                extracted_patient_ids=[patient_id]  # Single patient ID in list
            )
            all_results.append(result)

        # Return combined results
        all_handled = all(r.get("agent_handled", False) for r in all_results)
        all_processed = all(r.get("processed_flag", False) for r in all_results)

        logger.info(f"Completed processing {len(extracted_patient_ids)} patients for bill balance")
        return {
            "agent_handled": all_handled,
            "processed_flag": all_processed,
            "details": {
                "reason": f"Processed {len(extracted_patient_ids)} patients",
                "patient_results": all_results,
                "patient_ids": extracted_patient_ids
            }
        }

    # From here on, we're processing a single patient ID (or no patient ID)
    # Use pre-extracted patient ID if available, otherwise try to extract from email
    if extracted_patient_ids:
        patient_id = extracted_patient_ids[0]
        logger.info(f"Using pre-extracted patient ID: {patient_id}")
    else:
        # Fallback to extraction from email content
        patient_id = await extract_patient_id_from_email_logic(current_email_content, front_conversation_id, email_subject)

    # Check if we've already asked for clarification
    already_asked_for_clarification = _check_if_clarification_request(structured_history_messages)
    
    if not patient_id:
        if already_asked_for_clarification:
            # Step 3: We already asked for clarification, tag for human review
            logger.info(f"Patient ID still not found after clarification request for conversation {front_conversation_id}. Tagging for human review.")
            
            try:
                # Add human review tag (only in non-test mode)
                if not test_mode:
                    frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])

                await send_or_save_response_bill_balance(
                    conversation_id=front_conversation_id,
                    response_text=TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE,
                    test_mode=test_mode,
                    response_type="human_review_escalation",
                    details={"action": "tagged_for_human_review"}
                )

                return {"agent_handled": True, "processed_flag": True, "details": {"action": "tagged_for_human_review"}}
            except Exception as e:
                logger.error(f"Failed to tag for human review: {e}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to tag for human review: {e}"}}
        else:
            # Step 2: First time we can't find patient ID, ask for clarification
            logger.info(f"Patient ID not found for conversation {front_conversation_id}. Requesting clarification.")

            try:
                await send_or_save_response_bill_balance(
                    conversation_id=front_conversation_id,
                    response_text=TEMPLATE_REQUEST_PATIENT_ID,
                    test_mode=test_mode,
                    response_type="clarification_request",
                    details={"action": "requested_clarification"}
                )

                return {"agent_handled": True, "processed_flag": True, "details": {"action": "requested_clarification"}}
            except Exception as e:
                logger.error(f"Failed to send clarification request: {e}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to send clarification: {e}"}}

    # Step 1: Patient ID found, get patient information and billing information using MCP tools
    logger.info(f"Patient ID {patient_id} found. Fetching patient and billing information via MCP tools.")

    # Fetch templates from database early (needed for all response types)
    templates = await _fetch_bill_balance_templates_from_db()

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
        
        # Then, call the MCP tool to get billing information
        mcp_response = await call_mcp_tool(
            tool_name="get_patient_lien_bill_balance",
            arguments={"patient_id": patient_id}
        )
        
        mcp_duration = time.time() - mcp_start_time
        logger.info(f"MCP tools completed in {mcp_duration:.2f} seconds for patient {patient_id}")
        
        # Process patient information response - extract individual fields for template placeholders
        patient_name = "Unknown"
        formatted_dob = "Unknown"
        formatted_doi = "Unknown"

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
                        patient_name = f"{first_name} {last_name}"
                    elif first_name:
                        patient_name = first_name
                    elif last_name:
                        patient_name = last_name

                    # Format DOB (convert from YYYY-MM-DD to MM/DD/YYYY)
                    if birth_date:
                        try:
                            date_obj = datetime.strptime(birth_date, '%Y-%m-%d')
                            formatted_dob = date_obj.strftime('%m/%d/%Y')
                        except:
                            formatted_dob = birth_date  # Use as-is if parsing fails

                    # Format DOI (convert from YYYY-MM-DD to MM/DD/YYYY)
                    if doi:
                        try:
                            date_obj = datetime.strptime(doi, '%Y-%m-%d')
                            formatted_doi = date_obj.strftime('%m/%d/%Y')
                        except:
                            formatted_doi = doi  # Use as-is if parsing fails

                    logger.info(f"Patient info: {patient_id} - {patient_name} - DOB: {formatted_dob} - DOI: {formatted_doi}")
                else:
                    logger.warning(f"No patients found in patient info response for {patient_id}")
            else:
                logger.warning(f"Invalid data structure in patient info response for {patient_id}")
        else:
            logger.warning(f"Invalid or empty patient info response for {patient_id}")
        
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

                        # Use DB template for "patient not found" response
                        not_found_template = templates.get("not_found")
                        if not not_found_template:
                            logger.error(f"Missing 'bill_balance_not_found_template' in database for patient {patient_id}")
                            return {"agent_handled": False, "processed_flag": False, "details": {"reason": "Missing not_found template"}}

                        patient_not_found_response = not_found_template.format(
                            patient_id=patient_id
                        )

                        await send_or_save_response_bill_balance(
                            conversation_id=front_conversation_id,
                            response_text=patient_not_found_response.strip(),
                            test_mode=test_mode,
                            patient_id=patient_id,
                            response_type="patient_not_found",
                            details={
                                "reason": matched_pattern['description'],
                                "error_pattern": matched_pattern['pattern'],
                                "mcp_error": error_message
                            }
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
                        if not test_mode:
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
        study_details_list = result.get('patientStudyDetails', [])
        
        # Patient data might be at top level or in a nested structure
        patient_data = result.get('patientData', {})
        if not patient_data:
            # Create minimal patient data from available fields
            patient_data = {
                'patientName': result.get('patientName', ''),
                'dateOfBirth': result.get('dateOfBirth', ''),
                'dateOfInjury': result.get('dateOfInjury', '')
            }
        
        logger.info(f"Extracted billing data for patient {patient_id}: balance={patient_bill_balance}, status={get_schema_info(patient_bill_status)}, liens={len(lien_status_list)}, studies={len(study_details_list)}")
        
        # Log study details for debugging
        if study_details_list:
            logger.info(f"Found {len(study_details_list)} study details for patient {patient_id}.")
            for i, study in enumerate(study_details_list):
                logger.debug(f"Study {i+1}: {study}")
        else:
            logger.info(f"No study details found for patient {patient_id}.")

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

            # Use DB template for "no data" response
            no_data_template = templates.get("no_data")
            if not no_data_template:
                logger.error(f"Missing 'bill_balance_no_data_template' in database for patient {patient_id}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": "Missing no_data template"}}

            no_data_response = no_data_template.format(
                patient_id=patient_id,
                patient_name=patient_name,
                dob=formatted_dob,
                doi=formatted_doi
            )

            await send_or_save_response_bill_balance(
                conversation_id=front_conversation_id,
                response_text=no_data_response.strip(),
                test_mode=test_mode,
                patient_id=patient_id,
                response_type="no_billing_data",
                details={"reason": "No billing data available"}
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

        # Build comprehensive response using template (templates already fetched earlier)
        attachments = []

        # Create sections for the comprehensive template
        billing_status_table = await generate_billing_status_table(patient_id, bill_balance_data=mcp_response)
        lien_status_table = _create_lien_status_table(lien_status_list)

        # Log generated HTML tables for debugging
        logger.debug(f"Generated billing_status_table HTML for patient {patient_id}: {billing_status_table}")
        logger.debug(f"Generated lien_status_table HTML for patient {patient_id}: {lien_status_table}")

        if not all_liens_signed:
            # Generate Lien Reminder response - use DB template
            lien_reminder_template = templates.get("lien_reminder")
            if not lien_reminder_template:
                logger.error(f"Missing 'bill_balance_lien_reminder_template' in database for patient {patient_id}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": "Missing lien_reminder template"}}

            reply_body = lien_reminder_template.format(
                patient_id=patient_id,
                patient_name=patient_name,
                dob=formatted_dob,
                doi=formatted_doi,
                lien_status_table=lien_status_table,
                billing_status_table=billing_status_table
            )
            subject = f"Re: {patient_id} - Lien Signature Required"
        else:
            # Generate comprehensive Bill & Balance response - use DB template
            found_template = templates.get("found")
            if not found_template:
                logger.error(f"Missing 'bill_balance_found_template' in database for patient {patient_id}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": "Missing found template"}}

            logger.info(f"Using database template 'bill_balance_found_template' for patient {patient_id}")
            reply_body = found_template.format(
                patient_id=patient_id,
                patient_name=patient_name,
                dob=formatted_dob,
                doi=formatted_doi,
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
        await send_or_save_response_bill_balance(
            conversation_id=front_conversation_id,
            response_text=reply_body,
            test_mode=test_mode,
            patient_id=patient_id,
            response_type="comprehensive_billing_info",
            details={
                "bill_balance": patient_bill_balance,
                "liens_signed": all_liens_signed,
                "studies_found": len(study_details_list),
                "template_used": "comprehensive" if all_liens_signed else "lien_reminder"
            }
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
        if not test_mode:
            try:
                frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
            except Exception as tag_error:
                logger.error(f"Failed to add human review tag: {tag_error}")

        # Use DB template for timeout response
        timeout_template = templates.get("timeout")
        if not timeout_template:
            logger.error(f"Missing 'bill_balance_timeout_template' in database for patient {patient_id}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": "Missing timeout template"}}

        timeout_response = timeout_template.format(patient_id=patient_id)

        try:
            await send_or_save_response_bill_balance(
                conversation_id=front_conversation_id,
                response_text=timeout_response.strip(),
                test_mode=test_mode,
                patient_id=patient_id,
                response_type="timeout_error",
                details={"reason": "MCP timeout error"}
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
        if not test_mode:
            try:
                frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
            except Exception as tag_error:
                logger.error(f"Failed to add human review tag: {tag_error}")
        return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"MCP connection error: {e}"}}

    except Exception as e:
        logger.error(f"Unexpected error processing billing request for patient {patient_id}: {e}", exc_info=True)
        # Tag for human review on processing error (only in non-test mode)
        if not test_mode:
            try:
                frontapp_service.add_conversation_tags(front_conversation_id, ["AI: Human review required"])
            except Exception as tag_error:
                logger.error(f"Failed to add human review tag: {tag_error}")
        return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Unexpected processing error: {e}"}}