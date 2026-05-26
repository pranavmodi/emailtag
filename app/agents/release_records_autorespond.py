"""
Handles Medical Records & Images requests using an AI agent.

This module contains the logic for an AI agent that processes emails tagged
with any Medical Records & Images tags: "Release of Records", "Image Request",
"CD Requests", and "Reports Request". It verifies the sender's identity using
the full verification flow which includes:
1. RadFlow contacts database check (known attorneys, doctors, etc.)
2. Study participants verification

Based on the sender's verified role (attorney, doctor, known_contact, etc.),
it determines the appropriate response and handles follow-up interactions
like HIPAA form submissions for unauthorized senders.
"""
import asyncio
import os
import json
import ast
from typing import Optional, Dict, Any, List


from app.core.config import settings as app_settings_instance
from celery.utils.log import get_task_logger
from app.services import frontapp_service
from app.mcp import default_mcp_client as mcp_client
# --- BEGIN: Agent Helper Imports ---
from app.agents.agent_helpers import (
    format_conversation_history_for_agent,
    get_patient_and_study_info,
    handle_unauthorized_sender,
    send_fallback_reply_and_tag,
    extract_all_patient_ids_from_email_logic,
    send_reply_to_front_direct,
    send_reply_to_front_with_attachment,
    verify_sender_for_patient_access
)
# --- END: Agent Helper Imports ---

# --- BEGIN: Logging ---
logger = get_task_logger(__name__)
# --- END: Logging ---

# --- BEGIN: Tag Constants ---
TAG_AI_HUMAN_REVIEW_REQUIRED = "AI: Human review required"

# --- END: Tag Constants ---

# --- BEGIN: Response Templates (for Medical Records & Images) ---
# For simplicity, templates are defined here. They can be moved to a separate file.

TEMPLATE_HIPAA_NEEDED = """
Hello,

To proceed with your request for medical records, we require a completed HIPAA release form. Please fill out the attached form and reply to this email with the completed document.

Thank you for your cooperation.
"""

TEMPLATE_ATTORNEY_ON_FILE_PORTAL = """
Hello,

You can access the records for this case via your portal. Here is the link:
{attorney_portal_link}

If you have any issues, please let us know.

Thank you.
"""

TEMPLATE_DOCTOR_ON_FILE_LINK = """
Hello Dr. {doctor_name},

Here is a secure, 30-day link to view the requested images and reports:
{secure_link}

You can also access information for all your referred patients through our physician portal. If you need assistance with your portal access, please let us know.

Thank you.
"""

TEMPLATE_HIPAA_RECEIVED_LINK = """
Hello,

Thank you for providing the HIPAA release form.

Here is a secure, 30-day link to view the requested images and reports:
{secure_link}

You can create a permanent account to access records in the future here: {account_creation_link}

Thank you.
"""

TEMPLATE_HIPAA_INVALID = """
Hello,

We received the HIPAA form, but it appears to be incomplete or unsigned.
Reason: {reason}

Please review the form, ensure all fields are filled correctly and it is signed, and send it back to us.

Thank you.
"""

TEMPLATE_REQUEST_PATIENT_ID = """
Hello,

To help you with your request for medical records, could you please provide the Patient ID?

Thank you.
"""

TEMPLATE_HUMAN_REVIEW_CD_REQUEST = "A team member will review your request for a CD and get back to you shortly."
# --- END: Response Templates ---


# --- BEGIN: Helper Functions ---

def _generate_response_from_template(scenario: str, data: Dict[str, Any]) -> str:
    """Generates a reply from a template based on the scenario."""
    logger.info(f"Generating reply for scenario: {scenario}")
    if scenario == "hipaa_needed":
        return TEMPLATE_HIPAA_NEEDED
    elif scenario == "attorney_on_file_portal":
        return TEMPLATE_ATTORNEY_ON_FILE_PORTAL.format(attorney_portal_link=data.get("portal_link", "#"))
    elif scenario == "doctor_on_file_link":
        return TEMPLATE_DOCTOR_ON_FILE_LINK.format(doctor_name=data.get("doctor_name", ""), secure_link=data.get("secure_link", "#"))
    elif scenario == "hipaa_received_link":
        return TEMPLATE_HIPAA_RECEIVED_LINK.format(secure_link=data.get("secure_link", "#"), account_creation_link=data.get("account_link", "#"))
    elif scenario == "hipaa_invalid":
        return TEMPLATE_HIPAA_INVALID.format(reason=data.get("reason", "Not specified"))
    elif scenario == "request_patient_id":
        return TEMPLATE_REQUEST_PATIENT_ID
    elif scenario == "human_review_cd_request":
        return TEMPLATE_HUMAN_REVIEW_CD_REQUEST
    else:
        logger.warning(f"Unknown scenario for reply generation: {scenario}")
        return "A team member will review your request and get back to you shortly."

# --- END: Helper Functions ---


# --- BEGIN: Tool Definitions ---

async def fetch_patient_and_study_info_tool(patient_id: str) -> Dict[str, Any]:
    """
    Fetches patient and study details from the MCP server using the shared helper.
    """
    try:
        mcp_results = await get_patient_and_study_info(patient_id)
        patient_result = mcp_results.get("patient_result", {})
        study_result = mcp_results.get("study_result", {})

        if not patient_result.get("success"):
            return {"success": False, "error": f"Patient fetch failed: {patient_result.get('error', 'Unknown MCP error')}"}
        
        if not study_result.get("success"):
            return {"success": False, "error": f"Study fetch failed: {study_result.get('error', 'Unknown MCP error')}"}

        studies = study_result.get("studies", [])
        
        return {
            "success": True,
            "patient": patient_result.get("patients", [{}])[0],
            "studies": studies
        }
    except Exception as e:
        logger.error(f"Exception in fetch_patient_and_study_info_tool: {e}", exc_info=True)
        return {"success": False, "error": f"Exception: {e}"}





# --- END: Tool Definitions ---

# --- BEGIN: Agent Orchestrator ---

async def handle_release_of_records_request(
    front_conversation_id: str,
    current_email_content: str,
    email_sender: str,
    structured_history_messages: List[Dict[str, Any]],
    settings_obj: Any = app_settings_instance,
    email_obj: Any = None
) -> Dict[str, Any]:
    """
    Handles Medical Records & Images requests using direct conditional logic.
    Handles: "Release of Records", "Image Request", "CD Requests", "Reports Request".
    """
    # Connect to MCP server
    if not await mcp_client.connect():
        logger.error("Failed to connect to MCP server for Medical Records request.")
        await send_fallback_reply_and_tag(
            front_conversation_id,
            "Internal data connection error. A team member will assist you.",
            TAG_AI_HUMAN_REVIEW_REQUIRED
        )
        return {"agent_handled": False, "processed_flag": True, "details": {"reason": "MCP connection failed"}}

    # Check for pre-extracted patient IDs from document processing
    if not email_obj or not hasattr(email_obj, 'extracted_patient_ids') or not email_obj.extracted_patient_ids:
        logger.info("No pre-extracted patient IDs found in database - cannot proceed with autorespond")
        return {"agent_handled": False, "processed_flag": False, "details": {"reason": "No patient ID in database, autorespond not applicable"}}
    
    patient_ids = email_obj.extracted_patient_ids
    patient_id = patient_ids[0]
    logger.info(f"Using pre-extracted patient ID for Medical Records request: {patient_id}")
    
    # Get patient and study info
    mcp_results = await get_patient_and_study_info(patient_id)
    patient_result = mcp_results.get("patient_result", {})
    study_result = mcp_results.get("study_result", {})

    if not patient_result.get("success") or not study_result.get("success"):
        logger.error("Failed to fetch patient/study data from MCP - tagging for human review without sending message")
        await send_fallback_reply_and_tag(
            front_conversation_id,
            "",  # Don't send any message to user on MCP errors
            TAG_AI_HUMAN_REVIEW_REQUIRED
        )
        return {"agent_handled": False, "processed_flag": True, "details": {"reason": "Patient/study fetch failed - tagged for human review"}}
    
    studies = study_result.get("studies", [])
    patient_info = patient_result.get("patients", [{}])[0]

    # Verify sender using full verification flow (includes RadFlow contact check)
    verification_result = await verify_sender_for_patient_access(patient_id, email_sender, studies)

    if verification_result.get("verification_status") == "error":
        logger.error("Failed to verify sender - tagging for human review without sending message")
        await send_fallback_reply_and_tag(
            front_conversation_id,
            "",  # Don't send any message to user on verification errors
            TAG_AI_HUMAN_REVIEW_REQUIRED
        )
        return {"agent_handled": False, "processed_flag": True, "details": {"reason": "Sender verification failed - tagged for human review"}}

    agent_outcome = {"agent_handled": False, "processed_flag": False}

    try:
        is_authorized = verification_result.get("authorized", False)
        verification_role = verification_result.get("role", "unknown")
        player_info = verification_result.get("player_info", {})

        logger.info(f"Sender verification result: authorized={is_authorized}, role={verification_role}, status={verification_result.get('verification_status')}")

        # Handle unauthorized senders - use universal WORKSPACE-based denial response
        if not is_authorized:
            return await handle_unauthorized_sender(
                conversation_id=front_conversation_id,
                sender_email=email_sender,
                patient_id=patient_id,
                verification_result=verification_result,
            )
        
        # Handle doctor on file case
        if verification_role == "doctor_on_file":
            # Check for CD request in conversation history first
            history_text = format_conversation_history_for_agent(structured_history_messages)
            if "cd" in current_email_content.lower() and ("link" in history_text.lower() or "secure" in history_text.lower()):
                await send_fallback_reply_and_tag(
                    front_conversation_id,
                    TEMPLATE_HUMAN_REVIEW_CD_REQUEST,
                    TAG_AI_HUMAN_REVIEW_REQUIRED
                )
                agent_outcome["agent_handled"] = True
                agent_outcome["processed_flag"] = True
                agent_outcome["details"] = {"reason": "CD request after link sent, escalated to human review"}
                return agent_outcome

            # Send normal doctor response with secure link
            base_url = app_settings_instance.SECURE_VIEWER_URL or "https://viewer.precisemri.com"
            mock_token = f"token_{patient_id}_{os.urandom(8).hex()}"
            secure_link = f"{base_url}/view?token={mock_token}"
            doctor_name = player_info.get("email", "").split("@")[0] if player_info.get("email") else "Doctor"

            reply_text = TEMPLATE_DOCTOR_ON_FILE_LINK.format(
                doctor_name=doctor_name,
                secure_link=secure_link
            )

        # Handle attorney on file case OR known contact from RadFlow database
        # Known contacts are typically attorneys verified in RadFlow's contact system
        elif verification_role in ["attorney_on_file", "known_contact"]:
            portal_link = app_settings_instance.ATTORNEY_PORTAL_URL or "https://app.radflow360.com/"
            reply_text = TEMPLATE_ATTORNEY_ON_FILE_PORTAL.format(attorney_portal_link=portal_link)

        # Handle other authorized cases (e.g., domain_verified) - escalate to human review
        else:
            logger.info(f"Authorized sender with unhandled role '{verification_role}' - escalating to human review")
            await send_fallback_reply_and_tag(
                front_conversation_id,
                "A team member will review your request and assist you shortly.",
                TAG_AI_HUMAN_REVIEW_REQUIRED
            )
            agent_outcome["agent_handled"] = True
            agent_outcome["processed_flag"] = True
            agent_outcome["details"] = {"reason": f"Authorized sender with role '{verification_role}' escalated to human review"}
            return agent_outcome
        
        # Send the response for attorney/doctor on file cases
        result = await send_reply_to_front_direct(
            front_conversation_id,
            reply_text,
            tags_to_add=["AI handled"]
        )
        
        if result.get("status") == "success":
            agent_outcome["agent_handled"] = True
            agent_outcome["processed_flag"] = True
            agent_outcome["details"] = {"reason": "Successfully sent reply", "response": result}
        else:
            logger.error(f"Failed to send reply: {result}")
            raise ValueError(f"Failed to send reply: {result}")

    except Exception as e:
        logger.error(f"Error processing Medical Records request: {e}", exc_info=True)
        await send_fallback_reply_and_tag(
            front_conversation_id,
            "Our automated assistant encountered an error. A team member will review your request.",
            TAG_AI_HUMAN_REVIEW_REQUIRED
        )
        agent_outcome["processed_flag"] = True
        agent_outcome["details"] = {"reason": f"Processing error: {e}"}

    return agent_outcome

# --- END: Agent Orchestrator --- 