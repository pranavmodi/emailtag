"""
Handles Medical Records & Images requests using an AI agent.

This module contains the logic for an AI agent that processes emails tagged
with any Medical Records & Images tags: "Release of Records", "Image Request", 
"CD Requests", and "Reports Request". It verifies the sender's identity against 
patient records, determines the appropriate response based on the sender's role 
(attorney, doctor, etc.), and handles follow-up interactions like HIPAA form submissions.
"""
import asyncio
import os
import json
import ast
from typing import Optional, Dict, Any, List

from openai import OpenAIError, AsyncOpenAI
from agents import Agent, Runner, ModelSettings, function_tool, OpenAIChatCompletionsModel, RunConfig
import httpx

from app.core.config import settings as app_settings_instance
from celery.utils.log import get_task_logger
from app.services import frontapp_service
from app.mcp import default_mcp_client as mcp_client
# --- BEGIN: Agent Helper Imports ---
from app.agents.agent_helpers import (
    format_conversation_history_for_agent,
    get_patient_and_study_info,
    send_fallback_reply_and_tag,
    extract_patient_id_from_email,
    send_reply_to_front
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

@function_tool
async def fetch_patient_and_study_info_tool(patient_id: str) -> Dict[str, Any]:
    """
    Fetches patient and study details from the MCP server using the shared helper.
    This includes "players" associated with the case, like attorneys and doctors.
    """
    logger.info(f"Tool 'fetch_patient_and_study_info_tool' called for Patient ID: {patient_id}")
    try:
        # Use the shared helper to get raw data
        mcp_results = await get_patient_and_study_info(patient_id)
        patient_result = mcp_results.get("patient_result", {})
        study_result = mcp_results.get("study_result", {})

        if not patient_result.get("success"):
            return {"success": False, "error": f"Patient fetch failed: {patient_result.get('error', 'Unknown MCP error')}"}
        
        if not study_result.get("success"):
            return {"success": False, "error": f"Study fetch failed: {study_result.get('error', 'Unknown MCP error')}"}

        # NOTE: The structure of players is assumed here from the study_result.
        # This should be adjusted to match the actual output of the MCP tool.
        players = study_result.get("studies", [{}])[0].get("players", [])

        return {
            "success": True,
            "patient": patient_result.get("patients", [{}])[0],
            "studies": study_result.get("studies", []),
            "players": players
        }
    except Exception as e:
        logger.error(f"Exception in fetch_patient_and_study_info_tool: {e}", exc_info=True)
        return {"success": False, "error": f"Exception: {e}"}


@function_tool
async def verify_sender_identity(sender_email: str, players: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Verifies the sender's email against the list of 'players' (attorneys, doctors)
    associated with a patient's case.
    """
    logger.info(f"Tool 'verify_sender_identity' called for sender: {sender_email}")
    sender_domain = sender_email.split('@')[1] if '@' in sender_email else None

    for player in players:
        player_email = player.get("email", "").lower()
        player_role = player.get("role", "unknown").lower()

        if sender_email.lower() == player_email:
            if "attorney" in player_role:
                return {"status": "verified", "role": "attorney_on_file", "player_info": player}
            if "doctor" in player_role or "physician" in player_role:
                return {"status": "verified", "role": "doctor_on_file", "player_info": player}

    # Fallback for domain check if direct email match fails
    if sender_domain:
        for player in players:
            player_domain = player.get("domain", "").lower()
            if sender_domain == player_domain:
                # Less certain, might need human review, but can be a good hint
                 pass

    # Simple logic for now, can be expanded (e.g. check signature text)
    if "law" in sender_domain or "legal" in sender_domain:
         return {"status": "unverified", "role": "attorney_not_on_file"}

    return {"status": "unverified", "role": "unknown"}


@function_tool
async def generate_expiring_link(patient_id: str, study_id: str) -> Dict[str, str]:
    """
    Generates a secure, time-limited link for viewing reports and images.
    Placeholder: This should call a real service to generate a secure token/link.
    """
    logger.info(f"Tool 'generate_expiring_link' called for patient {patient_id}.")
    # In a real implementation, this would call a service.
    base_url = app_settings_instance.SECURE_VIEWER_URL
    # This is a mock link
    mock_token = f"token_{patient_id}_{os.urandom(8).hex()}"
    secure_link = f"{base_url}/view?token={mock_token}"
    return {"success": True, "link": secure_link}


@function_tool
async def add_consulting_physician(patient_id: str, physician_info: Dict) -> Dict[str, Any]:
    """
    Adds a physician as a consulting physician to the patient's record via HL7.
    Placeholder: This should call a real service that generates and sends an HL7 message.
    """
    logger.info(f"Tool 'add_consulting_physician' called for patient {patient_id}.")
    # In a real implementation, this would call an HL7 service.
    logger.info(f"SIMULATING: Sending HL7 message to add {physician_info.get('name')} to patient {patient_id}.")
    return {"success": True, "message": "HL7 message queued for delivery."}

# More tools for HIPAA form handling can be added here.
# For now, we will rely on the agent's logic to request the form.

@function_tool
async def generate_formatted_reply(scenario: str, data: Dict[str, Any]) -> Dict[str, str]:
    """
    Generates a formatted reply string based on the scenario and provided data.
    """
    logger.info(f"Tool 'generate_formatted_reply' called. Scenario: {scenario}")
    reply_text = _generate_response_from_template(scenario, data)
    return {"reply_text": reply_text}

# --- END: Tool Definitions ---

# --- BEGIN: Agent Orchestrator ---

async def handle_release_of_records_request(
    front_conversation_id: str,
    current_email_content: str,
    email_sender: str,
    structured_history_messages: List[Dict[str, Any]],
    settings_obj: Any = app_settings_instance
) -> Dict[str, Any]:
    """
    Orchestrates the AI agent to handle Medical Records & Images requests.
    Handles: "Release of Records", "Image Request", "CD Requests", "Reports Request".
    """
    logger.info(f"Initiating Medical Records & Images agent for conv ID: {front_conversation_id}")

    # Connect to MCP server
    if not await mcp_client.connect():
        logger.error("Failed to connect to MCP server for Medical Records agent.")
        await send_fallback_reply_and_tag(
            front_conversation_id,
            "Internal data connection error. A team member will assist you.",
            TAG_AI_HUMAN_REVIEW_REQUIRED
        )
        return {"agent_handled": False, "processed_flag": True, "details": {"reason": "MCP connection failed"}}

    full_context = f"History:\n{format_conversation_history_for_agent(structured_history_messages)}\n\nLatest Email from <{email_sender}>:\n{current_email_content}"

    instructions = f"""
You are an AI assistant processing requests for medical records. Follow these steps precisely.
Conversation ID: {front_conversation_id}
Sender Email: {email_sender}
Full Context:
---
{full_context}
---

**Your Task:**

1.  **Find Patient ID**: Call `extract_patient_id_from_email` on the 'Full Context'.
    *   If no ID is found, call `generate_formatted_reply` with scenario "request_patient_id" and send it. Your job is done.

2.  **Get Case Info**: If you have a patient ID, call `fetch_patient_and_study_info_tool`.
    *   If this fails, send a generic error and tag for human review.

3.  **Verify Sender**: Call `verify_sender_identity` with the `sender_email` and the `players` list from the previous step.

4.  **Act on Identity**:
    *   If `verify_sender_identity` returns `role: "attorney_on_file"`:
        *   Generate a reply with scenario "attorney_on_file_portal" (pass a dummy portal link for now).
        *   Send the reply.
    *   If `role: "doctor_on_file"`:
        *   Call `generate_expiring_link`.
        *   Call `add_consulting_physician` with the doctor's info.
        *   Generate a reply with scenario "doctor_on_file_link", including the secure link.
        *   Send the reply.
    *   If `role` is `attorney_not_on_file`, `doctor_not_on_file`, or `unknown`:
        *   Generate a reply with scenario "hipaa_needed".
        *   Send the reply.

5.  **CD Request Check**: Review the 'Full Context'. If a link was already sent and the user (who is a verified doctor) now insists on a CD, generate a reply for "human_review_cd_request" and add the "{TAG_AI_HUMAN_REVIEW_REQUIRED}" tag.

6.  **HIPAA Form Submission Check**: (Future logic) If the user's email contains an attachment and the history shows we were awaiting a HIPAA form, this will trigger a document analysis flow. For now, this is not implemented.

**Final Step**: After calling `send_reply_to_front`, your job is to return its direct JSON output. Do not add conversational text.
"""

    agent_outcome = {"agent_handled": False, "processed_flag": False}

    try:
        custom_httpx_client = httpx.AsyncClient(verify=False)
        custom_openai_client = AsyncOpenAI(
            api_key=settings_obj.OPENAI_API_KEY,
            http_client=custom_httpx_client
        )

        ror_agent = Agent(
            name="ReleaseOfRecordsAgent_v1",
            instructions=instructions,
            model=OpenAIChatCompletionsModel(
                model=settings_obj.AGENT_MODEL or "gpt-4o",
                openai_client=custom_openai_client
            ),
            tools=[
                extract_patient_id_from_email,
                fetch_patient_and_study_info_tool,
                verify_sender_identity,
                generate_expiring_link,
                add_consulting_physician,
                generate_formatted_reply,
                send_reply_to_front,
            ],
            model_settings=ModelSettings(temperature=0.0)
        )

        run_config = RunConfig(tracing_disabled=True)
        agent_result = await Runner.run(
            ror_agent,
            input="Process the release of records request based on the instructions.",
            run_config=run_config
        )

        final_output = agent_result.final_output
        if isinstance(final_output, str):
            try:
                final_output = json.loads(final_output)
            except json.JSONDecodeError:
                final_output = ast.literal_eval(final_output)

        if isinstance(final_output, dict) and final_output.get("status") == "success":
            agent_outcome["agent_handled"] = True
            agent_outcome["processed_flag"] = True
            agent_outcome["details"] = {"reason": "Agent successfully sent reply.", "tool_response": final_output}
        else:
            raise ValueError(f"Agent finished with non-success or invalid output: {final_output}")

    except Exception as e:
        logger.error(f"Error in Release of Records agent orchestration: {e}", exc_info=True)
        await send_fallback_reply_and_tag(
            front_conversation_id,
            "Our automated assistant encountered an error. A team member will review your request.",
            TAG_AI_HUMAN_REVIEW_REQUIRED
        )
        agent_outcome["processed_flag"] = True
        agent_outcome["details"] = {"reason": f"Agent execution error: {e}"}

    finally:
        # The MCP client is shared, so we don't close it here.
        pass

    logger.info(f"Medical Records Agent finished for {front_conversation_id}. Outcome: {agent_outcome}")
    return agent_outcome

# --- END: Agent Orchestrator --- 