import asyncio
import os
from typing import Optional, Dict, Any, List

from openai import OpenAIError
from agents import Agent, Runner, ModelSettings, function_tool
from app.core.config import settings as app_settings_instance # Renamed to avoid conflict if settings is passed
from celery.utils.log import get_task_logger
from app.services import frontapp_service # For the actual send_reply_to_front tool

logger = get_task_logger(__name__)

# --- BEGIN: Tag Constants for Appointment Status Agent ---
TAG_APT_STATUS_RESOLVED = "System: Apt Status - Resolved"
TAG_APT_STATUS_ID_NOT_FOUND_L1 = "System: Apt Status - Patient ID Requested L1"
TAG_APT_STATUS_DB_ERROR = "System: Apt Status - DB Error"
TAG_HUMAN_REVIEW_ID_UNMATCHED_L2 = "System: Apt Status - Human Review - ID Unmatched L2"
TAG_HUMAN_REVIEW_ID_MISSING_L2 = "System: Apt Status - Human Review - ID Missing L2"
TAG_AGENT_PROCESSING_ERROR = "System: Agent Error - Apt Status"
# --- END: Tag Constants ---


# --- BEGIN: Helper Function for openai-agents SDK ---
def _format_conversation_history_for_agent(
    structured_messages: List[Dict[str, Any]],
    max_exchanges: int = 3
) -> str:
    if not structured_messages:
        return "No relevant conversation history found."
    history_texts = []
    for msg in structured_messages:
        role = "Unknown"
        body = msg.get("body", "").strip()
        body_oneline = body.replace('\n', ' ').replace('\r', ' ')
        msg_type = msg.get("type")
        author_role = msg.get("author_role")
        direction = msg.get("direction")
        if direction == "inbound": role = "User"
        elif direction == "outbound": role = "Assistant"
        elif msg_type == "comment" and author_role == "teammate": role = "Assistant (comment)"
        elif author_role == "user": role = "User"
        if body_oneline and role != "Unknown":
            history_texts.append(f"{role}: {body_oneline}")
    if not history_texts:
        return "No relevant conversation history found after formatting."
    return "\n".join(history_texts[-(max_exchanges * 2):])
# --- END: Helper Function ---


# --- BEGIN: Tool Definitions for openai-agents SDK ---
@function_tool
async def extract_patient_id_from_email(email_content: str) -> Dict[str, Optional[str]]:
    """
    Extracts a patient ID from the given email content.
    Searches for patterns like "Patient ID: XXXX", "PID: XXXX", or a standalone 6-10 digit number.
    Returns a dictionary: {"patient_id": "extracted_id"} or {"patient_id": null} if not found.
    """
    logger.info(f"Tool 'extract_patient_id_from_email' called with content: {email_content[:100]}...")
    import re
    match = re.search(r"(patient id is|Patient ID:|PID:)\s*(\d{6,10})", email_content, re.IGNORECASE)
    if match:
        extracted_id = match.group(2)
        logger.info(f"Found patient ID: {extracted_id}")
        return {"patient_id": extracted_id}
    
    standalone_match = re.search(r"\b(\d{6,10})\b", email_content)
    if standalone_match:
        potential_id = standalone_match.group(1)
        logger.info(f"Found potential standalone patient ID: {potential_id}")
        return {"patient_id": potential_id}
        
    logger.info("No patient ID found by tool 'extract_patient_id_from_email'.")
    return {"patient_id": None}

@function_tool
async def fetch_appointment_details_by_patient_id(patient_id: str) -> Dict[str, Any]:
    """
    Fetches appointment details from the database for the given patient_id.
    Returns example structures for success, not_found, or db_error.
    """
    logger.info(f"Tool 'fetch_appointment_details_by_patient_id' called for Patient ID: {patient_id}")
    if patient_id == "123456":
        return {
            "status": "success", 
            "data": {"exam_type": "MRI Brain", "appointment_date": "2024-07-15", "current_status": "Scheduled"}
        }
    elif patient_id == "654321":
        return {"status": "not_found", "message": "No appointments found for this patient ID."}
    elif patient_id == "DB_ERROR_PATIENT":
        return {"status": "db_error", "message": "Simulated database query failed."}
    else:
        return {"status": "not_found", "message": f"No appointments found for this patient ID: {patient_id} (generic)."}

@function_tool
async def send_reply_to_front(
    conversation_id: str, 
    reply_text: str, 
    tags_to_add: Optional[List[str]] = None, 
    tags_to_remove: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sends a reply message to the specified Front conversation and optionally updates tags.
    """
    logger.info(f"Tool 'send_reply_to_front' called for conv_id {conversation_id}. Text: '{reply_text[:50]}...'. Tags to add: {tags_to_add}, Tags to remove: {tags_to_remove}")
    try:
        loop = asyncio.get_event_loop()
        reply_sent_successfully = await loop.run_in_executor(
            None, 
            frontapp_service.send_conversation_reply, 
            conversation_id, 
            reply_text
        )
        if not reply_sent_successfully:
            logger.error(f"Failed to send reply via Front for conversation {conversation_id}.")
            return {"status": "error", "message": "Front API failed to send reply."}

        if tags_to_add:
            tags_added_successfully = await loop.run_in_executor(None, frontapp_service.add_conversation_tags, conversation_id, tags_to_add)
            if not tags_added_successfully:
                logger.warning(f"Sent reply to {conversation_id} but failed to add tags: {tags_to_add}")
        if tags_to_remove:
            tags_removed_successfully = await loop.run_in_executor(None, frontapp_service.remove_conversation_tags, conversation_id, tags_to_remove)
            if not tags_removed_successfully:
                 logger.warning(f"Sent reply to {conversation_id} but failed to remove tags: {tags_to_remove}")
        
        return {"status": "success", "message": "Reply sent and tags updated."}
    except Exception as e:
        logger.error(f"Error in 'send_reply_to_front' tool for conversation {conversation_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Exception in send_reply_to_front: {str(e)}"}
# --- END: Tool Definitions ---


# --- BEGIN: Orchestrator for openai-agents SDK ---
async def handle_apt_status_request_agent_sdk(
    front_conversation_id: str,
    current_email_content: str,
    structured_history_messages: List[Dict[str, Any]],
    settings_obj: Any = app_settings_instance 
) -> Dict[str, Any]:
    """
    Handles an "Apt Status Req" using the openai-agents SDK.
    Returns a dictionary with agent processing results.
    """
    logger.info(f"Initiating openai-agents SDK flow for Apt Status Req - Conv ID: {front_conversation_id}")

    formatted_history = _format_conversation_history_for_agent(structured_history_messages)
    
    instructions = f"""
You are an AI assistant for a medical imaging company, specializing in appointment status requests.
Your primary goal is to obtain a Patient ID from the user, use it to fetch appointment details, and then inform the user. If you cannot get a Patient ID after a reasonable attempt, escalate for human review.

Conversation ID: {front_conversation_id}
Latest User Email (this is the current message you are processing):
---
{current_email_content}
---

Consider the following recent conversation history (if any, dialogue format, potentially excluding the Latest User Email content itself if it was part of history input):
---
{formatted_history}
---

Your Task & Tool Usage:

1.  **Analyze Latest User Email for Patient ID**:
    *   Call `extract_patient_id_from_email` tool with the content of the "Latest User Email".

2.  **Decision Logic Based on Patient ID Extraction**:
    *   **If `extract_patient_id_from_email` returns a `patient_id`**:
        a.  Call `fetch_appointment_details_by_patient_id` tool with the extracted `patient_id`.
        b.  If `fetch_appointment_details_by_patient_id` result `status` is "success":
            *   Formulate a reply like: "Your {{exam_type}} appointment on {{appointment_date}} is currently {{current_status}}." Fill in the placeholders using data from the tool result (e.g., result.data.exam_type).
            *   Call `send_reply_to_front` with this formulated reply and `tags_to_add=["{TAG_APT_STATUS_RESOLVED}"]`. This is your final action.
        c.  If `fetch_appointment_details_by_patient_id` result `status` is "not_found":
            *   Formulate a reply like: "We found your Patient ID: {{patient_id}}, but could not find any upcoming appointments. If you believe this is an error, please provide the approximate date and type of your exam so our team can investigate further." (Replace {{patient_id}} with the ID you have).
            *   Call `send_reply_to_front` with this formulated reply and `tags_to_add=["{TAG_HUMAN_REVIEW_ID_UNMATCHED_L2}"]`. This is your final action.
        d.  If `fetch_appointment_details_by_patient_id` result `status` is "db_error":
            *   Formulate a reply like: "We encountered a technical difficulty while trying to fetch your appointment details. Our team has been notified and will look into this."
            *   Call `send_reply_to_front` with this formulated reply and `tags_to_add=["{TAG_APT_STATUS_DB_ERROR}"]`. This is your final action.

    *   **If `extract_patient_id_from_email` returns NO `patient_id` (i.e., `patient_id` is null or empty)**:
        a.  **Review Conversation History**: Carefully examine the "Conversation History" provided. Determine if you (the Assistant) have previously asked for a Patient ID in this conversation, AND if the user's subsequent replies (visible in history or the "Latest User Email") did not provide a clear Patient ID that was then successfully used or found to be valid.
        b.  **If you determine you have NOT asked for a Patient ID before OR you asked but the user's response (if any) is not yet in the provided history or did not contain a clear ID**:
            *   Formulate a polite request: "To help me find your appointment status, could you please provide your Patient ID?"
            *   Call `send_reply_to_front` with this request and `tags_to_add=["{TAG_APT_STATUS_ID_NOT_FOUND_L1}"]`. This is your final action.
        c.  **If you determine you HAVE asked for a Patient ID before, and the user's subsequent replies (in history or "Latest User Email") STILL did not yield a usable Patient ID**:
            *   Formulate an escalation message: "Thank you for the information. We're still having trouble locating your appointment details. A member of our team will personally review your request and get back to you shortly."
            *   Call `send_reply_to_front` with this message and `tags_to_add=["{TAG_HUMAN_REVIEW_ID_MISSING_L2}"]`. This is your final action.

Remember to replace placeholders like `{{exam_type}}`, `{{appointment_date}}`, `{{current_status}}`, and `{{patient_id}}` in your formulated replies with actual values from tool outputs before calling `send_reply_to_front`.
The `send_reply_to_front` tool also accepts `tags_to_remove` (e.g., `tags_to_remove=["{TAG_APT_STATUS_ID_NOT_FOUND_L1}"]`) if you need to clean up previous tags when resolving or escalating further.
Your final output for this run MUST be the JSON result from a `send_reply_to_front` tool call.
Do not ask for confirmation. Execute the described logic and call `send_reply_to_front` as your last step.
"""
    agent_outcome = {
        "agent_handled": False, 
        "processed_flag": False, 
        "details": {"reason": "Agent process not fully completed or error before completion."}
    }

    try:
        apt_status_agent = Agent(
            name="AppointmentStatusAgent_ConvoAware_v3",
            instructions=instructions,
            tools=[
                extract_patient_id_from_email,
                fetch_appointment_details_by_patient_id,
                send_reply_to_front,
            ],
            model_settings=ModelSettings(
                model=settings_obj.OPENAI_MODEL_NAME if hasattr(settings_obj, 'OPENAI_MODEL_NAME') and settings_obj.OPENAI_MODEL_NAME else "gpt-4o",
                temperature=0.2 
            )
        )
        
        agent_run_input_context = f"Process request based on Latest User Email provided in instructions for conversation {front_conversation_id}."
        logger.info(f"Running {apt_status_agent.name} for conv {front_conversation_id}.")

        agent_result = await Runner.run(apt_status_agent, input=agent_run_input_context)

        if agent_result.error:
            logger.error(f"Agent run for {front_conversation_id} resulted in an error: {agent_result.error}")
            agent_outcome["details"] = {"agent_error": str(agent_result.error), "reason": "Agent execution failed."}
            try:
                await send_reply_to_front(
                    conversation_id=front_conversation_id,
                    reply_text="Our automated assistant encountered an issue. A team member will review your request.",
                    tags_to_add=[TAG_AGENT_PROCESSING_ERROR]
                )
                agent_outcome["processed_flag"] = True
                agent_outcome["details"]["error_reply_sent"] = True
            except Exception as e_tag:
                logger.error(f"Failed to send error reply/tag for {front_conversation_id} after agent error: {e_tag}")
                agent_outcome["details"]["error_reply_sent"] = False

        elif agent_result.final_output:
            logger.info(f"Agent run for {front_conversation_id} completed. Final output: {agent_result.final_output}")
            if isinstance(agent_result.final_output, dict) and agent_result.final_output.get("status") == "success":
                agent_outcome["agent_handled"] = True
                agent_outcome["processed_flag"] = True
                agent_outcome["details"] = {
                    "agent": apt_status_agent.name, 
                    "summary": agent_result.final_output.get("message", "Reply sent by agent.")
                }
            else:
                logger.error(f"Agent '{apt_status_agent.name}' final_output indicates failure or unexpected format: {agent_result.final_output}")
                agent_outcome["details"] = {"agent_final_output_error": str(agent_result.final_output), "reason": "Agent final output not successful."}
        else:
            logger.warning(f"Agent '{apt_status_agent.name}' did not produce final_output or error for {front_conversation_id}. History: {agent_result.history}")
            agent_outcome["details"] = {
                "agent_no_final_output": True, 
                "history": agent_result.history[-3:] if agent_result.history else [],
                "reason": "Agent completed without error but no final output."
            }

    except Exception as e_agent_orchestration:
        logger.error(f"Exception during openai-agents SDK orchestration for {front_conversation_id}: {e_agent_orchestration}", exc_info=True)
        agent_outcome["details"] = {"agent_orchestration_exception": str(e_agent_orchestration), "reason": "Critical error in agent handling logic."}
        try:
            await send_reply_to_front(
                conversation_id=front_conversation_id,
                reply_text="Our automated assistant encountered an unexpected issue. A team member will assist you shortly.",
                tags_to_add=[TAG_AGENT_PROCESSING_ERROR]
            )
            agent_outcome["processed_flag"] = True
            agent_outcome["details"]["error_reply_sent_orchestration"] = True
        except Exception as e_tag_orch:
            logger.error(f"Failed to send error reply/tag for {front_conversation_id} after agent orchestration error: {e_tag_orch}")
            agent_outcome["details"]["error_reply_sent_orchestration"] = False
            
    return agent_outcome
# --- END: Orchestrator for openai-agents SDK ---

if __name__ == "__main__":
    async def test_new_agent_sdk_flow():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(message)s')
        global logger
        logger = logging.getLogger(__name__)

        class MockSDKSettings:
            OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
            OPENAI_MODEL_NAME = "gpt-4o"
        
        if not MockSDKSettings.OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY env var not set. Cannot run new agent test.")
            return

        mock_history = [
            {"type": "message", "direction": "inbound", "author_role": "user", "body": "Can I get an update on my appointment?"},
            {"type": "comment", "author_role": "teammate", "body": "To help me find your appointment status, could you please provide your Patient ID?"} 
        ]
        
        logger.info("\n--- Testing SDK Agent: User provides ID ---")
        result1 = await handle_apt_status_request_agent_sdk(
            front_conversation_id="sdk_test_convo_1",
            current_email_content="My patient id is 123456, what is my status?",
            structured_history_messages=[],
            settings_obj=MockSDKSettings()
        )
        logger.info(f"SDK Agent Result 1: {result1}")

        await asyncio.sleep(1)

        logger.info("\n--- Testing SDK Agent: User does NOT provide ID, first time ---")
        result2 = await handle_apt_status_request_agent_sdk(
            front_conversation_id="sdk_test_convo_2",
            current_email_content="What is my appointment status?",
            structured_history_messages=[],
            settings_obj=MockSDKSettings()
        )
        logger.info(f"SDK Agent Result 2: {result2}")
        
        await asyncio.sleep(1)

        logger.info("\n--- Testing SDK Agent: User does NOT provide ID, agent asked before ---")
        result3 = await handle_apt_status_request_agent_sdk(
            front_conversation_id="sdk_test_convo_3",
            current_email_content="I don't have my patient ID right now.",
            structured_history_messages=mock_history, 
            settings_obj=MockSDKSettings()
        )
        logger.info(f"SDK Agent Result 3: {result3}")

    # To run specific tests:
    asyncio.run(test_new_agent_sdk_flow()) # For the new openai-agents SDK method
    pass 