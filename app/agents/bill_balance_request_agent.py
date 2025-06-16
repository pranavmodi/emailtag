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

Billing Status:
Please review the lien status as we are missing signed liens which must be signed before a bill is produced.

Lien Status:
{lien_status_table}

How to eSign:
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
# --- END: Response Templates ---


# --- BEGIN: Placeholder Data Fetching Functions ---

async def get_patient_info(patient_id: str) -> Dict[str, Any]:
    """Placeholder to fetch patient information."""
    logger.info(f"Fetching patient info for ID: {patient_id}")
    # In a real implementation, this would query a database or another service.
    return {
        "success": True,
        "patient": {
            "name": "JESSICA VALERIE RODRIGUEZ",
            "dob": "10/09/1973",
            "doi": "03/23/2025",
            "id": patient_id
        }
    }

async def get_billing_and_lien_info(patient_id: str) -> Dict[str, Any]:
    """Placeholder to fetch billing and lien information."""
    logger.info(f"Fetching billing and lien info for Patient ID: {patient_id}")
    # This function simulates fetching financial details for a patient.
    # It can be modified to return different states, e.g., for unsigned liens.
    
    # Scenario 1: Liens signed, bill available
    return {
        "success": True,
        "liens_signed": True,
        "bill_available": True,
        "balance": "2,200.00",
        "billed_studies": [
            {
                "description": "MRI LUMBAR SPINE W/O CONTRAST",
                "date": "05/07/2025",
                "status": "SIGNED",
                "billing_status": "$2,200.00 - Billed on 05/16/2025"
            }
        ],
        "pending_studies": [
            {
                "description": "MRI HIP W/O CONTRAST - LT",
                "date": "05/27/2025",
                "status": "SCHEDULED",
                "billing_status": "Potential amount to be billed $2,200.00"
            },
            {
                "description": "MRI KNEE W/O CONTRAST - LT",
                "date": "05/30/2025",
                "status": "SCHEDULED",
                "billing_status": "Potential amount to be billed $2,200.00"
            }
        ],
        "pending_studies_total": "4,400.00",
        "lien_status": [
            {"type": "Technical Lien (Imaging)", "patient_sig": "Signed 04/25/2025", "attorney_sig": "Signed 05/16/2025"},
            {"type": "Professional lien (Report)", "patient_sig": "Signed 04/25/2025", "attorney_sig": "Signed 05/16/2025"}
        ]
    }
    
    # # Scenario 2: Liens not signed
    # return {
    #     "success": True,
    #     "liens_signed": False,
    #     "bill_available": False,
    #     "lien_status": [
    #         {"type": "Technical Lien (Imaging)", "patient_sig": "Not Signed. Please give your client this link to eSign", "attorney_sig": "Not Signed. Please eSign here"},
    #         {"type": "Professional lien (Report)", "patient_sig": "Not Signed. Please give your client this link to eSign", "attorney_sig": "Not Signed. Please eSign here"}
    #     ]
    # }

async def get_medical_report_attachments(patient_id: str) -> List[str]:
    """Placeholder to get paths of medical report PDFs."""
    logger.info(f"Fetching medical reports for Patient ID: {patient_id}")
    # This would find and return the file paths for report attachments.
    # Returning an empty list simulates no reports being available.
    return []

async def get_w9_form_attachment() -> Optional[str]:
    """Placeholder to get the path of the W9 form."""
    logger.info("Fetching W9 form path.")
    # This should point to the location of your W9 PDF.
    # For now, let's assume it's in a 'static' folder.
    w9_path = Path("static/Precise_Imaging_W9_MI_2-3-25-2.pdf")
    if w9_path.exists():
        return str(w9_path)
    logger.warning(f"W9 form not found at expected path: {w9_path}")
    return None

async def get_bill_attachment(patient_id: str) -> Optional[str]:
    """Placeholder to get the path of the latest bill PDF."""
    logger.info(f"Fetching latest bill for Patient ID: {patient_id}")
    # This would generate or find the bill PDF and return its path.
    return None # Simulate no bill attachment for now

# --- END: Placeholder Data Fetching Functions ---

def _create_lien_status_table(lien_statuses: List[Dict[str, str]]) -> str:
    """Creates a formatted string table for lien statuses."""
    header = "Lien type\tPatient Signature\tAttorney Signature\n"
    rows = [header]
    for lien in lien_statuses:
        rows.append(f"{lien['type']}\t{lien['patient_sig']}\t{lien['attorney_sig']}")
    return "\n".join(rows)

def _create_billing_status_section(billing_info: Dict[str, Any]) -> str:
    """Creates the formatted string for the billing status section."""
    lines = []
    if billing_info.get("bill_available"):
        lines.append(f"The patient's current bill balance is $ {billing_info['balance']} as of {billing_info.get('date_today', 'today')}")
        
        if billing_info.get('billed_studies'):
            lines.append("\nSTUDY DESCRIPTION\tSTUDY DATE\tEXAM STATUS\tBILLING STATUS")
            for study in billing_info['billed_studies']:
                lines.append(f"{study['description']}\t{study['date']}\t{study['status']}\t{study['billing_status']}")
        
        if billing_info.get('pending_studies'):
            lines.append(f"\nThere are pending studies that might be completed shortly")
            lines.append(f"$ {billing_info['pending_studies_total']} will be added to the bill balance once the studies below are completed:")
            lines.append("\nSTUDY DESCRIPTION\tSTUDY DATE\tEXAM STATUS\tBILLING STATUS")
            for study in billing_info['pending_studies']:
                 lines.append(f"{study['description']}\t{study['date']}\t{study['status']}\t{study['billing_status']}")
    
    return "\n".join(lines)


async def handle_bill_balance_request(
    front_conversation_id: str,
    current_email_content: str,
    structured_history_messages: List[Dict[str, Any]],
    settings_obj: Any = app_settings_instance
) -> Dict[str, Any]:
    """
    Main orchestrator for handling "Bill or balance Request" emails.
    """
    logger.info(f"handle_bill_balance_request called for conversation: {front_conversation_id}")
    
    patient_id = await extract_patient_id_from_email_logic(f"Subject: \n\n{current_email_content}")
    if not patient_id:
        logger.warning(f"Could not extract Patient ID from conversation {front_conversation_id}. Cannot proceed.")
        return {"agent_handled": False, "processed_flag": False, "details": {"reason": "Patient ID not found in email."}}

    patient_info_data = await get_patient_info(patient_id)
    if not patient_info_data.get("success"):
        logger.error(f"Failed to fetch patient info for {patient_id}.")
        return {"agent_handled": False, "processed_flag": False, "details": {"reason": "Failed to fetch patient data."}}
    patient_info = patient_info_data["patient"]
    
    billing_info = await get_billing_and_lien_info(patient_id)
    if not billing_info.get("success"):
        logger.error(f"Failed to fetch billing/lien info for {patient_id}.")
        return {"agent_handled": False, "processed_flag": False, "details": {"reason": "Failed to fetch billing/lien data."}}

    # Determine if reports are requested
    include_reports = "report" in current_email_content.lower()
    
    attachments = []
    reply_body = ""
    subject = f"Re: {patient_info.get('id', '')} - {patient_info.get('name', '')} - DOB: {patient_info.get('dob', '')} - DOI: {patient_info.get('doi', '')}"

    report_header = "The available final reports have been attached." if include_reports else ""

    lien_status_table = _create_lien_status_table(billing_info['lien_status'])

    if not billing_info.get("liens_signed"):
        # Generate Lien Reminder response
        reply_body = LIEN_REMINDER_TEMPLATE.format(
            report_header=report_header.strip(),
            lien_status_table=lien_status_table
        )
    else:
        # Generate Bill & Balance response
        billing_status_section = _create_billing_status_section(billing_info)
        bill_attachment_line = "A copy of the most recent bill is attached." if billing_info.get("bill_available") else ""

        reply_body = BILL_BALANCE_TEMPLATE.format(
            report_header=report_header.strip(),
            bill_attachment_line=bill_attachment_line,
            billing_status_section=billing_status_section,
            lien_status_table=lien_status_table
        )

        # Add W9 only if a bill is available
        if billing_info.get("bill_available"):
            w9_path = await get_w9_form_attachment()
            if w9_path:
                attachments.append(w9_path)
        
        # Add bill attachment
        bill_path = await get_bill_attachment(patient_id)
        if bill_path:
            attachments.append(bill_path)

    if include_reports:
        report_paths = await get_medical_report_attachments(patient_id)
        attachments.extend(report_paths)

    try:
        await send_reply_to_front(
            front_conversation_id=front_conversation_id,
            body=reply_body,
            subject=subject,
            attachments=attachments
        )
        logger.info(f"Successfully sent 'Bill or Balance Request' reply for conversation {front_conversation_id}")
        return {"agent_handled": True, "processed_flag": True, "details": {"reply_sent": True, "attachments": len(attachments)}}
    except Exception as e:
        logger.error(f"Failed to send reply to Front for conversation {front_conversation_id}: {e}", exc_info=True)
        return {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Front API error: {e}"}} 