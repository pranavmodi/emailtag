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
    logger.info(f"🔧 TOOL 'fetch_patient_and_study_info_tool' called for Patient ID: {patient_id}")
    try:
        # Use the shared helper to get raw data
        mcp_results = await get_patient_and_study_info(patient_id)
        patient_result = mcp_results.get("patient_result", {})
        study_result = mcp_results.get("study_result", {})

        if not patient_result.get("success"):
            return {"success": False, "error": f"Patient fetch failed: {patient_result.get('error', 'Unknown MCP error')}"}
        
        if not study_result.get("success"):
            return {"success": False, "error": f"Study fetch failed: {study_result.get('error', 'Unknown MCP error')}"}

        # Get studies data
        studies = study_result.get("studies", [])
        logger.info(f"🔧 TOOL: Found {len(studies)} studies for patient {patient_id}")
        
        result = {
            "success": True,
            "patient": patient_result.get("patients", [{}])[0],
            "studies": studies
        }
        logger.info(f"🔧 TOOL: Returning result: {result}")
        return result
    except Exception as e:
        logger.error(f"Exception in fetch_patient_and_study_info_tool: {e}", exc_info=True)
        return {"success": False, "error": f"Exception: {e}"}


@function_tool
async def compile_all_participants(patient_id: str, studies: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compiles all participants across all studies for a patient.
    Returns a comprehensive list of participants with their details.
    """
    logger.info(f"🔧 TOOL 'compile_all_participants' called for Patient ID: {patient_id}")
    logger.info(f"🔧 TOOL: Compiling participants from {len(studies)} studies")
    
    # Ensure MCP client is connected
    if not mcp_client.is_connected:
        await mcp_client.connect()

    all_participants = []
    successful_studies = 0
    failed_studies = 0

    for study in studies:
        accession_number = study.get("accessionNumber", "") or study.get("authorization_number", "")
        study_id = study.get("study_id") or study.get("id")
        logger.info(f"🔧 TOOL: Processing study {study_id} with accession: {accession_number}")
        
        if not accession_number:
            logger.warning(f"🔧 TOOL: Skipping study {study_id} - no accession number or authorization number")
            failed_studies += 1
            continue
            
        try:
            # Get participants for this specific study using accession number
            logger.info(f"🔧 TOOL: Calling get_study_participants for accession {accession_number}")
            participants_result = await mcp_client.call_tool("get_study_participants", {"accession_number": str(accession_number)})
            logger.info(f"🔧 TOOL: Participants result: {participants_result}")
            
            if participants_result.get("success") and participants_result.get("data", {}).get("result"):
                participants = participants_result["data"]["result"]
                logger.info(f"🔧 TOOL: Found {len(participants)} participants for accession {accession_number}")
                
                # Transform and add each participant
                for participant in participants:
                    participant_data = {
                        "email": participant.get("email", "").strip().lower(),
                        "role": participant.get("playerTypeName", "").lower(),
                        "type": participant.get("type", "").lower(),
                        "referrer_id": participant.get("referrerID", ""),
                        "phone": participant.get("businessPhoneNumber", ""),
                        "accession_number": accession_number,
                        "study_id": study_id,
                        "domain": participant.get("email", "").split("@")[1].lower() if "@" in participant.get("email", "") else ""
                    }
                    
                    logger.info(f"🔧 TOOL: Adding participant: {participant_data}")
                    all_participants.append(participant_data)
                
                successful_studies += 1
            else:
                logger.warning(f"🔧 TOOL: No participants found for accession {accession_number}")
                failed_studies += 1
                
        except Exception as e:
            logger.error(f"🔧 TOOL: Failed to get participants for accession {accession_number}: {e}")
            failed_studies += 1
            continue

    logger.info(f"🔧 TOOL: Compilation complete - Total participants: {len(all_participants)}, Successful studies: {successful_studies}, Failed studies: {failed_studies}")
    
    return {
        "success": True,
        "total_participants": len(all_participants),
        "participants": all_participants,
        "successful_studies": successful_studies,
        "failed_studies": failed_studies
    }


@function_tool
async def verify_sender_against_participants(sender_email: str, participants: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Verifies the sender's email against a compiled list of all participants.
    This provides efficient verification using pre-compiled participant data.
    """
    logger.info(f"🔧 TOOL 'verify_sender_against_participants' called for sender: {sender_email}")
    logger.info(f"🔧 TOOL: Checking against {len(participants)} total participants")
    sender_domain = sender_email.split('@')[1] if '@' in sender_email else None

    # First pass: Direct email matches
    for participant in participants:
        participant_email = participant.get("email", "").lower()
        participant_role = participant.get("role", "").lower()
        participant_type = participant.get("type", "").lower()
        
        logger.info(f"🔧 TOOL: Checking participant - email: {participant_email}, role: {participant_role}, type: {participant_type}")
        
        # Direct email match
        if sender_email.lower() == participant_email:
            logger.info(f"🔧 TOOL: DIRECT EMAIL MATCH found for {sender_email}")
            player_info = {
                "email": participant_email,
                "role": participant_role,
                "type": participant_type,
                "accession_number": participant.get("accession_number", ""),
                "study_id": participant.get("study_id", ""),
                "referrer_id": participant.get("referrer_id", ""),
                "phone": participant.get("phone", "")
            }
            
            # Check for attorney roles
            if "attorney" in participant_role or "law" in participant_role:
                logger.info(f"🔧 TOOL: Verified as ATTORNEY_ON_FILE")
                return {"status": "verified", "role": "attorney_on_file", "player_info": player_info}
            
            # Check for doctor/physician roles
            if any(keyword in participant_role for keyword in ["doctor", "physician", "radiologist"]) or \
               any(keyword in participant_type for keyword in ["doctor", "physician"]):
                logger.info(f"🔧 TOOL: Verified as DOCTOR_ON_FILE")
                return {"status": "verified", "role": "doctor_on_file", "player_info": player_info}

    # Second pass: Domain matches for medical professionals
    if sender_domain:
        logger.info(f"🔧 TOOL: No direct email match, checking domain matches for {sender_domain}")
        for participant in participants:
            participant_domain = participant.get("domain", "").lower()
            participant_role = participant.get("role", "").lower()
            participant_type = participant.get("type", "").lower()
            
            if sender_domain == participant_domain:
                # Domain match with doctor/physician type
                if any(keyword in participant_role for keyword in ["doctor", "physician", "radiologist"]) or \
                   any(keyword in participant_type for keyword in ["doctor", "physician"]):
                    logger.info(f"🔧 TOOL: DOMAIN MATCH found for {sender_domain}")
                    player_info = {
                        "email": participant.get("email", ""),
                        "role": participant_role,
                        "type": participant_type,
                        "accession_number": participant.get("accession_number", ""),
                        "study_id": participant.get("study_id", ""),
                        "domain": participant_domain
                    }
                    return {"status": "domain_verified", "role": "doctor_domain_match", "player_info": player_info}

    # Fallback to domain pattern matching
    logger.info(f"🔧 TOOL: No participant matches found, checking domain patterns for {sender_domain}")
    if sender_domain:
        if any(keyword in sender_domain for keyword in ["law", "legal", "attorney", "lawfirm"]):
            logger.info(f"🔧 TOOL: Domain indicates attorney_not_on_file")
            return {"status": "unverified", "role": "attorney_not_on_file"}
        
        if any(keyword in sender_domain for keyword in ["med", "clinic", "hospital", "health", "medical"]):
            logger.info(f"🔧 TOOL: Domain indicates doctor_not_on_file")
            return {"status": "unverified", "role": "doctor_not_on_file"}

    logger.info(f"🔧 TOOL: No verification possible - returning unknown")
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
    logger.info(f"Tool 'generate_formatted_reply' called. Scenario: {scenario}, Data: {data}")
    try:
        reply_text = _generate_response_from_template(scenario, data)
        logger.info(f"Generated reply text: {reply_text[:100]}...")
        return {"reply_text": reply_text}
    except Exception as e:
        logger.error(f"Error generating formatted reply for scenario {scenario}: {e}", exc_info=True)
        return {"reply_text": "A team member will review your request and get back to you shortly."}

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
    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Initiating agent for conv ID: {front_conversation_id}")
    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Email sender: {email_sender}")
    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Email content length: {len(current_email_content)} chars")
    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: History messages count: {len(structured_history_messages)}")
    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Email content preview: {current_email_content[:200]}...")

    # Connect to MCP server
    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Attempting MCP connection...")
    if not await mcp_client.connect():
        logger.error("🎯 MEDICAL_RECORDS_AGENT: Failed to connect to MCP server for Medical Records agent.")
        await send_fallback_reply_and_tag(
            front_conversation_id,
            "Internal data connection error. A team member will assist you.",
            TAG_AI_HUMAN_REVIEW_REQUIRED
        )
        return {"agent_handled": False, "processed_flag": True, "details": {"reason": "MCP connection failed"}}
    
    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: MCP connection successful")

    full_context = f"History:\n{format_conversation_history_for_agent(structured_history_messages)}\n\nLatest Email from <{email_sender}>:\n{current_email_content}"
    
    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Formatted context length: {len(full_context)} chars")
    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Context preview: {full_context[:300]}...")

    instructions = f"""
You are an AI assistant processing requests for medical records. Follow these steps precisely.
Conversation ID: {front_conversation_id}
Sender Email: {email_sender}
Full Context:
---
{full_context}
---

**Your Task:**

1.  **Find Patient ID**: Call `extract_patient_id_from_email` on the 'Full Context' with `conversation_id="{front_conversation_id}"`.
    *   If no ID is found, call `generate_formatted_reply` with scenario "request_patient_id" and send it. Your job is done.

2.  **Get Case Info**: If you have a patient ID, call `fetch_patient_and_study_info_tool`.
    *   If this fails, send a generic error and tag for human review.

3.  **Compile All Participants**: Call `compile_all_participants` with the `patient_id` and `studies` list from step 2.
    *   This will gather all participants across all studies for efficient verification.

4.  **Verify Sender**: Call `verify_sender_against_participants` with the `sender_email` and the `participants` list from step 3.
    *   This provides comprehensive verification against all study participants.

5.  **Act on Identity**:
    *   If `verify_sender_against_participants` returns `role: "attorney_on_file"`:
        *   Generate a reply with scenario "attorney_on_file_portal" (pass a dummy portal link for now).
        *   Send the reply.
    *   If `role: "doctor_on_file"`:
        *   Call `generate_expiring_link` with the patient_id and study_id from the player_info.
        *   Call `add_consulting_physician` with the doctor's info.
        *   Generate a reply with scenario "doctor_on_file_link", including the secure link.
        *   Send the reply.
    *   If `role` is `attorney_not_on_file`, `doctor_not_on_file`, or `unknown`:
        *   Generate a reply with scenario "hipaa_needed".
        *   Send the reply.

6.  **CD Request Check**: Review the 'Full Context'. If a link was already sent and the user (who is a verified doctor) now insists on a CD, generate a reply for "human_review_cd_request" and add the "{TAG_AI_HUMAN_REVIEW_REQUIRED}" tag.

7.  **HIPAA Form Submission Check**: (Future logic) If the user's email contains an attachment and the history shows we were awaiting a HIPAA form, this will trigger a document analysis flow. For now, this is not implemented.

**Final Step**: After calling `send_reply_to_front`, your job is to return its direct JSON output. Do not add conversational text.

**Error Handling**: If any step fails, call `send_reply_to_front` with a fallback message and return the result. Always return a valid JSON response from `send_reply_to_front`.
"""

    agent_outcome = {"agent_handled": False, "processed_flag": False}
    
    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Creating OpenAI client and agent...")

    try:
        custom_httpx_client = httpx.AsyncClient(verify=False)
        custom_openai_client = AsyncOpenAI(
            api_key=settings_obj.OPENAI_API_KEY,
            http_client=custom_httpx_client
        )
        
        logger.info(f"🎯 MEDICAL_RECORDS_AGENT: OpenAI client created successfully")

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
                compile_all_participants,
                verify_sender_against_participants,
                generate_expiring_link,
                add_consulting_physician,
                generate_formatted_reply,
                send_reply_to_front,
            ],
            model_settings=ModelSettings(temperature=0.0)
        )
        
        logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Agent created, starting execution...")
        logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Using model: {settings_obj.AGENT_MODEL or 'gpt-4o'}")

        run_config = RunConfig(tracing_disabled=True)
        agent_result = await Runner.run(
            ror_agent,
            input="Process the release of records request based on the instructions.",
            run_config=run_config
        )
        
        logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Agent execution completed")

        final_output = agent_result.final_output
        logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Raw output: {final_output}")
        logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Output type: {type(final_output)}")
        
        if isinstance(final_output, str):
            logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Parsing string output...")
            # Check if it's an error message that can't be parsed
            if "error occurred" in final_output.lower() or "review the request manually" in final_output.lower():
                logger.error(f"🎯 MEDICAL_RECORDS_AGENT: Agent returned error message: {final_output}")
                raise ValueError(f"Agent returned error message: {final_output}")
            
            try:
                final_output = json.loads(final_output)
                logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Successfully parsed JSON output")
            except json.JSONDecodeError:
                logger.warning(f"🎯 MEDICAL_RECORDS_AGENT: JSON parsing failed, trying literal_eval...")
                try:
                    final_output = ast.literal_eval(final_output)
                    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Successfully parsed with literal_eval")
                except (ValueError, SyntaxError):
                    logger.error(f"🎯 MEDICAL_RECORDS_AGENT: Failed to parse agent output as JSON or literal: {final_output}")
                    raise ValueError(f"Agent output is not valid JSON or literal: {final_output}")

        logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Parsed output: {final_output}")
        
        if isinstance(final_output, dict) and final_output.get("status") == "success":
            logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Agent execution successful!")
            agent_outcome["agent_handled"] = True
            agent_outcome["processed_flag"] = True
            agent_outcome["details"] = {"reason": "Agent successfully sent reply.", "tool_response": final_output}
        else:
            logger.error(f"🎯 MEDICAL_RECORDS_AGENT: Agent finished with non-success output: {final_output}")
            raise ValueError(f"Agent finished with non-success or invalid output: {final_output}")

    except Exception as e:
        logger.error(f"🎯 MEDICAL_RECORDS_AGENT: Error in agent orchestration: {e}", exc_info=True)
        logger.error(f"🎯 MEDICAL_RECORDS_AGENT: Exception type: {type(e)}")
        await send_fallback_reply_and_tag(
            front_conversation_id,
            "Our automated assistant encountered an error. A team member will review your request.",
            TAG_AI_HUMAN_REVIEW_REQUIRED
        )
        agent_outcome["processed_flag"] = True
        agent_outcome["details"] = {"reason": f"Agent execution error: {e}"}

    finally:
        # The MCP client is shared, so we don't close it here.
        logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Agent execution finished, cleaning up...")

    logger.info(f"🎯 MEDICAL_RECORDS_AGENT: Final outcome for {front_conversation_id}: {agent_outcome}")
    return agent_outcome

# --- END: Agent Orchestrator --- 