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

from celery.utils.log import get_task_logger
# from agents import aio, function_tool, tool

from app.core.config import settings as app_settings_instance
from app.services import frontapp_service
from app.agents.agent_helpers import send_reply_to_front, extract_patient_id_from_email_logic

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
Access bills, appointment times, and e-sign liens (Click request login if you don't have an account)

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

How to eSign:
Patient eSign Link: {patient_esign_link}
Attorney eSign Link: {attorney_esign_link}

1. Click the eSign link above
2. Click Start at the top right
3. Sign your full name
4. Click the "Sign button and you are done

If you do not want to eSign, please click the link above and then save the document in the top right corner to manually sign and send back via email.
Learn how to quickly e-Sign or download a PDF to manually sign here

To save time, you can download the bills in our portal which also contains the bill balance at the bottom.
Access bills, appointment times, and e-sign liens (Click request login if you don't have an account)

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""

# Template for when patient ID is not found or multiple patients found
PATIENT_CLARIFICATION_TEMPLATE = """
Thank you for your request. 

To provide you with the accurate billing information, we need to verify the patient details. Could you please provide:

1. Patient ID (if available), OR
2. Patient's full first and last name, AND
3. Date of Birth (DOB) or Date of Loss (DOL)

Once we have this information, we'll be able to provide you with the billing details and any necessary documentation.

Thank you,
Precise Imaging Billing Dept.
http://www.PreciseMRI.com
"""

# Template for human review needed
HUMAN_REVIEW_TEMPLATE = """
Thank you for your request. 

We are unable to locate the patient with the information provided. Your request has been forwarded to our billing team for manual review. Someone will contact you within 1-2 business days.

Thank you,
Precise Imaging Billing Dept.
http://www.PreciseMRI.com
"""
# --- END: Response Templates ---


# --- Helper Functions for MCP Integration ---

def _create_lien_status_table(lien_statuses: List[Dict[str, Any]]) -> str:
    """Creates a formatted string table for lien statuses."""
    if not lien_statuses:
        return "No lien information available"
    
    header = "Lien Type\tPatient Signature\tAttorney Signature\n"
    rows = [header]
    
    for lien in lien_statuses:
        lien_type = lien.get('lienType', 'Unknown')
        
        if lien.get('hasPatientSigned'):
            patient_sig = f"Signed {lien.get('patientSignedLienDate', 'Unknown Date')}"
        else:
            patient_sig = "Not Signed"
            
        if lien.get('hasAttorneySigned'):
            attorney_sig = f"Signed {lien.get('attorneySignedDate', 'Unknown Date')}"
        else:
            attorney_sig = "Not Signed"
            
        rows.append(f"{lien_type}\t{patient_sig}\t{attorney_sig}")
    
    return "\n".join(rows)

def _create_billing_status_section(bill_balance: float, bill_status: Dict[str, Any]) -> str:
    """Creates the formatted string for the billing status section."""
    lines = []
    
    if bill_status.get("isBilled"):
        lines.append(f"The patient's current bill balance is ${bill_balance:.2f}")
        if bill_status.get("bill"):
            lines.append("A copy of the most recent bill is attached.")
    else:
        lines.append("No bill has been generated yet. Please check the lien status below.")
    
    return "\n".join(lines)

def _check_if_clarification_request(conversation_history: List[Dict[str, Any]]) -> bool:
    """
    Check if we've already sent a clarification request in this conversation.
    Returns True if we've already asked for patient details.
    """
    for message in conversation_history:
        body = message.get('body', '').lower()
        if ('patient id' in body and 'first and last name' in body and 
            'date of birth' in body and message.get('direction') == 'outbound'):
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
                
                await send_reply_to_front(
                    front_conversation_id=front_conversation_id,
                    body=HUMAN_REVIEW_TEMPLATE,
                    subject="Re: Billing Request - Manual Review Required"
                )
                
                return {"agent_handled": True, "processed_flag": True, "details": {"action": "tagged_for_human_review"}}
            except Exception as e:
                logger.error(f"Failed to tag for human review: {e}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to tag for human review: {e}"}}
        else:
            # Step 2: First time we can't find patient ID, ask for clarification
            logger.info(f"Patient ID not found for conversation {front_conversation_id}. Requesting clarification.")
            
            try:
                await send_reply_to_front(
                    front_conversation_id=front_conversation_id,
                    body=PATIENT_CLARIFICATION_TEMPLATE,
                    subject="Re: Billing Request - Patient Information Needed"
                )
                
                return {"agent_handled": True, "processed_flag": True, "details": {"action": "requested_clarification"}}
            except Exception as e:
                logger.error(f"Failed to send clarification request: {e}")
                return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Failed to send clarification: {e}"}}

    # Step 1: Patient ID found, get billing information using MCP tool
    logger.info(f"Patient ID {patient_id} found. Fetching billing information via MCP tool.")
    
    try:
        # Import the MCP client function
        from app.mcp import call_mcp_tool
        
        # Call the MCP tool to get billing information
        mcp_response = await call_mcp_tool(
            tool_name="mcp_precisemcp_get_patient_lien_bill_balance",
            arguments={"patient_id": patient_id}
        )
        
        if not mcp_response or not isinstance(mcp_response, dict):
            logger.error(f"Invalid MCP response for patient {patient_id}: {mcp_response}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": "Invalid MCP tool response"}}
        
        # Check if MCP call was successful
        if not mcp_response.get('success', False):
            logger.error(f"MCP tool call failed for patient {patient_id}: {mcp_response.get('error', 'Unknown error')}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"MCP tool error: {mcp_response.get('error', 'Unknown error')}"}}
        
        # Parse the MCP response - the actual tool result is in the 'result' field
        tool_result = mcp_response.get('result', {})
        if not tool_result or not isinstance(tool_result, dict):
            logger.error(f"No valid result data in MCP response for patient {patient_id}: {tool_result}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": "No billing data found"}}
        
        # The actual patient data is in the 'result' field of the tool response
        result = tool_result.get('result', {})
        if not result:
            logger.error(f"No result data in MCP response for patient {patient_id}")
            return {"agent_handled": False, "processed_flag": False, "details": {"reason": "No billing data found"}}
        
        # Extract data from MCP response
        patient_bill_balance = result.get('patientBillBalance', 0)
        patient_bill_status = result.get('patientBillStatus', {})
        lien_status_list = result.get('lienStatusList', [])
        patient_esign_link = result.get('patientEsignLink', '')
        attorney_esign_link = result.get('attorneyEsignLink', '')
        
        # Check if liens are properly signed
        all_liens_signed = all(
            lien.get('hasPatientSigned', False) and lien.get('hasAttorneySigned', False)
            for lien in lien_status_list
        )
        
        # Determine if reports are requested
        include_reports = "report" in current_email_content.lower()
        
        # Build response
        attachments = []
        patient_info = f"Patient ID: {patient_id}"
        report_header = "The available final reports have been attached." if include_reports else ""
        
        lien_status_table = _create_lien_status_table(lien_status_list)
        
        if not all_liens_signed:
            # Generate Lien Reminder response
            reply_body = LIEN_REMINDER_TEMPLATE.format(
                report_header=report_header.strip(),
                patient_info=patient_info,
                lien_status_table=lien_status_table,
                patient_esign_link=patient_esign_link,
                attorney_esign_link=attorney_esign_link
            )
            subject = f"Re: {patient_id} - Lien Signature Required"
        else:
            # Generate Bill & Balance response
            billing_status_section = _create_billing_status_section(patient_bill_balance, patient_bill_status)
            bill_attachment_line = "A copy of the most recent bill is attached." if patient_bill_status.get("isBilled") else ""
            
            reply_body = BILL_BALANCE_TEMPLATE.format(
                report_header=report_header.strip(),
                bill_attachment_line=bill_attachment_line,
                patient_info=patient_info,
                billing_status_section=billing_status_section,
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
        await send_reply_to_front(
            front_conversation_id=front_conversation_id,
            body=reply_body,
            subject=subject,
            attachments=attachments
        )
        
        logger.info(f"Successfully sent billing response for patient {patient_id} in conversation {front_conversation_id}")
        return {
            "agent_handled": True, 
            "processed_flag": True, 
            "details": {
                "action": "sent_billing_info",
                "patient_id": patient_id,
                "bill_balance": patient_bill_balance,
                "liens_signed": all_liens_signed,
                "attachments": len(attachments)
            }
        }
        
    except Exception as e:
        logger.error(f"Error processing billing request for patient {patient_id}: {e}", exc_info=True)
        return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Processing error: {e}"}} 