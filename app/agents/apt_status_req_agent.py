import asyncio
import os
import json # Import json for parsing stringified JSON
from typing import Optional, Dict, Any, List

from openai import OpenAIError, AsyncOpenAI
from agents import Agent, Runner, ModelSettings, function_tool, OpenAIChatCompletionsModel, RunConfig
import httpx

from app.core.config import settings as app_settings_instance # Renamed to avoid conflict if settings is passed
from celery.utils.log import get_task_logger
from app.services import frontapp_service # For the actual send_reply_to_front tool
# Import templates from their new location
from app.agents.templates.appointment_status_templates import (
    TEMPLATE_APPOINTMENT_FOUND_DETAILED,
    TEMPLATE_REQUEST_PATIENT_ID,
    TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE,
    TEMPLATE_APPOINTMENT_NOT_FOUND_FOR_ID,
    TEMPLATE_DB_ERROR
)

logger = get_task_logger(__name__)

# --- BEGIN: Tag Constants for Appointment Status Agent ---
TAG_AI_HUMAN_REVIEW_REQUIRED = "AI: Human review required" # Centralized tag for errors/escalations
# --- END: Tag Constants ---

# --- Response Templates have been moved to app/agents/templates/appointment_status_templates.py ---


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

# --- BEGIN: Reply Generation Helper ---
def _generate_response_from_template(scenario: str, data: Dict[str, Any]) -> str:
    logger.info(f"Generating reply for scenario: {scenario} with data: {data}")
    if scenario == "appointments_found" and data.get("studies"):
        studies = data.get("studies", [])
        first_study = studies[0]
        
        studies_table_rows_list = []
        for study in studies:
            studies_table_rows_list.append(
                f"{study.get('study_id','N/A')} | {study.get('exam_description','N/A')} | {study.get('status','N/A')} | {study.get('appointment_datetime_str','N/A')} | {study.get('location_name','N/A')} | {study.get('images_available','N/A')} | {study.get('report_available','N/A')}"
            )
        studies_table_rows = "\n".join(studies_table_rows_list)
        
        personal_injury_info_text = ""
        if data.get("is_personal_injury_case"):
            personal_injury_info_text = """
If this is also a personal injury case:
A report containing the findings of the exam will also be sent to the attorney.
A bill will be sent to the attorney once both the patient and the attorney sign all pending liens.
Please make sure to submit a negotiation offer before sending the payment.
"""
        return TEMPLATE_APPOINTMENT_FOUND_DETAILED.format(
            patient_id_confirmed=data.get("patient_id_confirmed", "N/A"),
            first_study_id=first_study.get("study_id", "N/A"),
            first_exam_description=first_study.get("exam_description", "N/A"),
            first_appointment_datetime_str=first_study.get("appointment_datetime_str", "N/A"),
            first_arrival_time_str=first_study.get("arrival_time_str", "N/A"),
            first_location_name=first_study.get("location_name", "N/A"),
            scheduling_phone=data.get("scheduling_phone", "N/A"),
            no_show_policy=data.get("no_show_policy", "N/A"),
            studies_table_rows=studies_table_rows,
            personal_injury_info=personal_injury_info_text,
            bills_link=data.get("links", {}).get("bills_appointments_liens", "#"),
            reports_link=data.get("links", {}).get("reports_images", "#")
        )
    elif scenario == "id_missing_first_attempt":
        return TEMPLATE_REQUEST_PATIENT_ID
    elif scenario == "id_missing_second_attempt":
        return TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE
    elif scenario == "id_not_found_in_system":
        return TEMPLATE_APPOINTMENT_NOT_FOUND_FOR_ID.format(patient_id=data.get("patient_id", "N/A"))
    elif scenario == "db_error":
        return TEMPLATE_DB_ERROR.format(patient_id=data.get("patient_id", "N/A"))
    else:
        logger.warning(f"Unknown scenario or missing data for reply generation: {scenario}")
        return "We are looking into your request and will get back to you shortly."

# --- END: Reply Generation Helper ---

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
    # Updated regex to capture optional alphabetic prefixes (e.g., PRE, PX) and ensure whole word matching for the ID part.
    match = re.search(r"(patient id is|Patient ID:|PID:)\s*([A-Z_]{0,5}\d{6,10})\b", email_content, re.IGNORECASE)
    if match:
        extracted_id = match.group(2) # Group 2 now captures the full ID (prefix + numbers)
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
    if patient_id == "123456": # Mock data for testing (simple success)
        return {
            "status": "success", 
            "data": {
                "patient_id_confirmed": "123456",
                "studies": [{
                    "study_id": "SINGLE123", "exam_description": "MRI Brain", 
                    "status": "Scheduled", "appointment_datetime_str": "2024-07-15 @ 03:00 PM",
                    "arrival_time_str": "02:45 PM", 
                    "location_name": "Main Imaging Center",
                    "images_available": "No", "report_available": "No"
                }],
                "is_personal_injury_case": False,
                "scheduling_phone": "800-555-1212",
                "no_show_policy": "**Standard no-show policy applies.**",
                "links": {"bills_appointments_liens": "#internal", "reports_images": "#internal"}
            }
        }
    elif patient_id == "PRE1079637": # Detailed case for template
        return {
            "status": "success",
            "data": {
                "patient_id_confirmed": "PRE1079637",
                "studies": [
                    {
                        "study_id": "RAM1030696", "exam_description": "MRI THORACIC SPINE W/O CONTRAST",
                        "status": "SCHEDULED", "appointment_datetime_str": "05/22/2025 @ 05:30 PM",
                        "arrival_time_str": "05:15 PM", 
                        "location_name": "1550 Pepper Dr. Suite G El Centro CA 92243",
                        "images_available": "No", "report_available": "No"
                    },
                    {
                        "study_id": "RAM1030697", "exam_description": "MRI LUMBAR SPINE W/O CONTRAST",
                        "status": "SCHEDULED", "appointment_datetime_str": "05/22/2025 @ 06:05 PM",
                        "arrival_time_str": "05:50 PM",
                        "location_name": "1550 Pepper Dr. Suite G El Centro CA 92243",
                        "images_available": "No", "report_available": "No"
                    }
                ],
                "is_personal_injury_case": True,
                "scheduling_phone": "818-629-1169",
                "no_show_policy": "**If the patient cannot make the appointment please contact us within 48 hours of the appointment to reschedule or cancel to avoid any no-show fees. Two no-shows will require a $50 no-show payment before being scheduled for a 3rd time.**",
                "links": {
                    "bills_appointments_liens": "https://example.com/portal/access_bills", # Placeholder
                    "reports_images": "https://example.com/portal/access_reports" # Placeholder
                }
            }
        }
    elif patient_id == "654321" or patient_id == "PRE248509": # PRE248509 from previous logs, now explicitly 'not_found'
         return {"status": "not_found", "message": f"No appointments found for Patient ID: {patient_id}.", "patient_id": patient_id}
    elif patient_id == "DB_ERROR_PATIENT":
        return {"status": "db_error", "message": "Simulated database query failed.", "patient_id": patient_id}
    else: # Default to not_found for other IDs
        return {"status": "not_found", "message": f"No appointments found for this patient ID: {patient_id} (generic).", "patient_id": patient_id}

@function_tool
async def generate_formatted_reply(scenario: str, fetch_details_result: Dict[str, Any], extracted_patient_id: Optional[str] = None) -> Dict[str, str]:
    """
    Generates a formatted reply string based on the scenario and data from fetching appointment details.
    'scenario' can be: "appointments_found", "id_missing_first_attempt", "id_missing_second_attempt", 
                         "id_not_found_in_system", "db_error".
    'fetch_details_result' is the full dictionary output from 'fetch_appointment_details_by_patient_id' tool.
    'extracted_patient_id' is the patient_id obtained from 'extract_patient_id_from_email' tool, used if fetch_details_result might not have it (e.g. initial fetch failed).
    """
    logger.info(f"Tool 'generate_formatted_reply' called. Scenario: {scenario}")
    
    data_for_template = {}
    if scenario == "appointments_found":
        data_for_template = fetch_details_result.get("data", {})
    elif scenario in ["id_not_found_in_system", "db_error"]:
        # These scenarios expect patient_id to be in the top level of fetch_details_result or passed via extracted_patient_id
        data_for_template = {"patient_id": fetch_details_result.get("patient_id") or extracted_patient_id}
    # For id_missing scenarios, 'data' might be empty or not strictly needed by the template
    # but we pass it along in case templates evolve.
    
    reply_text = _generate_response_from_template(scenario, data_for_template)
    logger.info(f"Generated reply text: {reply_text[:200]}...") # Log snippet
    return {"reply_text": reply_text}

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
        if tags_to_remove: # This part of the tool can remain for generic use, even if agent prompt changes
            tags_removed_successfully = await loop.run_in_executor(None, frontapp_service.remove_conversation_tags, conversation_id, tags_to_remove)
            if not tags_removed_successfully:
                 logger.warning(f"Sent reply to {conversation_id} but failed to remove tags: {tags_to_remove}")
        
        return {"status": "success", "message": "Reply sent and tags (if any) updated."}
    except Exception as e:
        logger.error(f"Error in 'send_reply_to_front' tool for conversation {conversation_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"Exception in send_reply_to_front: {str(e)}"}
# --- END: Tool Definitions ---


# --- BEGIN: Fallback Reply Helper ---
async def _send_fallback_reply_and_tag(
    conversation_id: str, 
    reply_text: str,
    tag_to_add: str = TAG_AI_HUMAN_REVIEW_REQUIRED # Changed default tag
):
    """Sends a fallback reply to Front and adds an error tag."""
    logger.info(f"Sending fallback reply for conversation {conversation_id} due to agent error/issue. Text: '{reply_text}'")
    try:
        loop = asyncio.get_event_loop()
        
        # Send reply
        reply_sent = await loop.run_in_executor(
            None,
            frontapp_service.send_conversation_reply,
            conversation_id,
            reply_text
        )
        if not reply_sent:
            logger.error(f"Failed to send fallback error reply message for {conversation_id} via frontapp_service.")
        else:
            logger.info(f"Successfully sent fallback error reply for {conversation_id}.")
        
        # Add error tag
        if tag_to_add:
            tags_added = await loop.run_in_executor(
                None, 
                frontapp_service.add_conversation_tags, 
                conversation_id, 
                [tag_to_add]
            )
            if not tags_added:
                logger.warning(f"Failed to add error tag {tag_to_add} for {conversation_id} after sending fallback reply.")
            else:
                logger.info(f"Successfully added error tag {tag_to_add} for {conversation_id}.")

    except Exception as ex_fallback:
        logger.error(f"Exception during sending fallback reply/tag for {conversation_id}: {ex_fallback}", exc_info=True)
# --- END: Fallback Reply Helper ---


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
    logger.info(f"Formatted conversation history: {formatted_history}")
    
    instructions = f"""
You are an AI assistant for a medical imaging company, specializing in appointment status requests.
Your primary goal is to:
1. Extract a Patient ID using `extract_patient_id_from_email`.
2. Fetch appointment details using `fetch_appointment_details_by_patient_id` with the extracted ID.
3. Based on the outcome of step 2, determine the correct scenario.
4. Call the `generate_formatted_reply` tool, passing it the determined scenario and the FULL result from `fetch_appointment_details_by_patient_id` (if available), and the `extracted_patient_id` (if available).
5. Take the `reply_text` from `generate_formatted_reply`'s output.
6. Call `send_reply_to_front` with this `reply_text` and add tags ONLY IF the scenario requires escalation to a human.

Conversation ID: {front_conversation_id}
Latest User Email:
---
{current_email_content}
---
Conversation History (if any):
---
{formatted_history}
---

**Scenarios & Tool Usage Flow:**

A.  **If `extract_patient_id_from_email` returns a `patient_id` (let's call it `extracted_pid`):**
    1.  Call `fetch_appointment_details_by_patient_id` with `extracted_pid`. Let the result be `fetch_result`.
    2.  **If `fetch_result.status` is "success"**:
        *   Scenario for `generate_formatted_reply`: "appointments_found"
        *   Call `generate_formatted_reply` with `scenario="appointments_found"`, `fetch_details_result=fetch_result`.
        *   Take `reply_text` from its output.
        *   Call `send_reply_to_front` with this `reply_text`. (No tags needed for this success case).
    3.  **If `fetch_result.status` is "not_found"**:
        *   Scenario for `generate_formatted_reply`: "id_not_found_in_system"
        *   Call `generate_formatted_reply` with `scenario="id_not_found_in_system"`, `fetch_details_result=fetch_result` (which contains patient_id).
        *   Take `reply_text` from its output.
        *   Call `send_reply_to_front` with this `reply_text` and `tags_to_add=["{TAG_AI_HUMAN_REVIEW_REQUIRED}"]`.
    4.  **If `fetch_result.status` is "db_error"**:
        *   Scenario for `generate_formatted_reply`: "db_error"
        *   Call `generate_formatted_reply` with `scenario="db_error"`, `fetch_details_result=fetch_result` (which contains patient_id).
        *   Take `reply_text` from its output.
        *   Call `send_reply_to_front` with this `reply_text` and `tags_to_add=["{TAG_AI_HUMAN_REVIEW_REQUIRED}"]`.

B.  **If `extract_patient_id_from_email` returns NO `patient_id`:**
    1.  Review Conversation History.
    2.  **If you have NOT asked for a Patient ID before OR the user's response is not yet in history:**
        *   Scenario for `generate_formatted_reply`: "id_missing_first_attempt"
        *   Call `generate_formatted_reply` with `scenario="id_missing_first_attempt"`, `fetch_details_result={{}}` (empty dict as no fetch was done).
        *   Take `reply_text` from its output.
        *   Call `send_reply_to_front` with this `reply_text`. (No tag needed for first request).
    3.  **If you HAVE asked for a Patient ID before, and user STILL did not provide a usable one:**
        *   Scenario for `generate_formatted_reply`: "id_missing_second_attempt"
        *   Call `generate_formatted_reply` with `scenario="id_missing_second_attempt"`, `fetch_details_result={{}}`.
        *   Take `reply_text` from its output.
        *   Call `send_reply_to_front` with this `reply_text` and `tags_to_add=["{TAG_AI_HUMAN_REVIEW_REQUIRED}"]`.

**IMPORTANT FINAL STEP:** After calling `send_reply_to_front`, your job is to return ONLY the direct JSON output received from that `send_reply_to_front` tool call. Do NOT add any conversational text, summaries, or any other information around it. Your entire response for this run MUST be the JSON object that the `send_reply_to_front` tool gives back.

Do not ask for confirmation. Execute the described logic.
"""
    agent_outcome = {
        "agent_handled": False, 
        "processed_flag": False, 
        "details": {"reason": "Agent process not fully completed or error before completion."}
    }

    try:
        # Create an httpx client with SSL verification disabled
        custom_httpx_client = httpx.AsyncClient(verify=False)
        # Create an OpenAI client with the custom httpx client
        custom_openai_client = AsyncOpenAI(
            api_key=settings_obj.OPENAI_API_KEY if hasattr(settings_obj, 'OPENAI_API_KEY') else os.environ.get("OPENAI_API_KEY"),
            http_client=custom_httpx_client
        )

        apt_status_agent = Agent(
            name="AppointmentStatusAgent_ConvoAware_v4_Templated", # Updated name
            instructions=instructions,
            model=OpenAIChatCompletionsModel(
                model=settings_obj.OPENAI_MODEL_NAME if hasattr(settings_obj, 'OPENAI_MODEL_NAME') and settings_obj.OPENAI_MODEL_NAME else "gpt-4o",
                openai_client=custom_openai_client
            ),
            tools=[
                extract_patient_id_from_email,
                fetch_appointment_details_by_patient_id,
                generate_formatted_reply, # Added new tool
                send_reply_to_front,
            ],
            model_settings=ModelSettings(
                temperature=0.1 # Further reduced temperature for stricter adherence to tool use
            )
        )
        
        agent_run_input_context = f"Process request based on Latest User Email provided in instructions for conversation {front_conversation_id}."
        logger.info(f"Running {apt_status_agent.name} for conv {front_conversation_id}.")

        run_config_settings = RunConfig(tracing_disabled=True)
        agent_result = await Runner.run(
            apt_status_agent, 
            input=agent_run_input_context,
            run_config=run_config_settings
        )

        parsed_final_output = None
        if agent_result.final_output:
            if isinstance(agent_result.final_output, dict):
                parsed_final_output = agent_result.final_output
            elif isinstance(agent_result.final_output, str):
                try:
                    parsed_final_output = json.loads(agent_result.final_output)
                    if not isinstance(parsed_final_output, dict):
                        logger.warning(f"Agent for {front_conversation_id} final_output was a string that parsed to JSON, but not to a dictionary. Parsed: {parsed_final_output}")
                        parsed_final_output = None 
                except json.JSONDecodeError:
                    logger.warning(f"Agent for {front_conversation_id} final_output was a string, but failed to parse as JSON: {agent_result.final_output}")
                    parsed_final_output = None
            else:
                 logger.warning(f"Agent for {front_conversation_id} final_output was neither a dict nor a string: {type(agent_result.final_output)}")

        if parsed_final_output: 
            logger.info(f"Agent run for {front_conversation_id} completed. Parsed final output: {parsed_final_output}")
            tool_status = parsed_final_output.get("status")
            tool_message = parsed_final_output.get("message", "No message from tool's output.")

            if tool_status == "success":
                agent_outcome["agent_handled"] = True
                agent_outcome["processed_flag"] = True 
                agent_outcome["details"] = {
                    "reason": "Agent successfully processed and sent reply via its designated final tool.", 
                    "tool_response": parsed_final_output
                }
                logger.info(f"Agent's final tool call successful for {front_conversation_id}: {tool_message}")
            else:
                logger.error(f"Agent's final tool call for {front_conversation_id} reported non-success status '{tool_status}': {tool_message}")
                await _send_fallback_reply_and_tag(
                    front_conversation_id, 
                    "Our automated assistant tried to send a reply but encountered a communication issue with the final step. A team member will review your request."
                )
                agent_outcome["agent_handled"] = False 
                agent_outcome["processed_flag"] = True 
                agent_outcome["details"] = {
                    "reason": "Agent's final tool call failed. Fallback reply sent by orchestrator.", 
                    "tool_response": parsed_final_output
                }
        elif agent_result.final_output: 
            logger.warning(f"Agent for {front_conversation_id} produced final_output, but it was not the expected dictionary format. Original Output: {agent_result.final_output}")
            await _send_fallback_reply_and_tag(
                front_conversation_id,
                "Our automated assistant had an issue formatting its final response. A team member will review your request."
            )
            agent_outcome["agent_handled"] = False
            agent_outcome["processed_flag"] = True 
            agent_outcome["details"] = {
                "reason": "Agent produced unexpected final_output type or format. Fallback reply sent by orchestrator.",
                "original_final_output": str(agent_result.final_output) if len(str(agent_result.final_output)) < 200 else "Original output too long for details field"
            }
        else: 
            logger.warning(f"Agent for {front_conversation_id} completed without any final_output.")
            await _send_fallback_reply_and_tag(
                front_conversation_id, 
                "Our automated assistant did not complete the processing as expected (no final output). A team member will review your request."
            )
            agent_outcome["agent_handled"] = False
            agent_outcome["processed_flag"] = True 
            agent_outcome["details"] = {"reason": "Agent completed without producing a final output. Fallback reply sent by orchestrator."}

    except AgentsException as e:
        error_msg_for_log = f"AgentsException during openai-agents SDK orchestration for {front_conversation_id}: {str(e)}"
        error_details_for_outcome = str(e)
        if hasattr(e, 'run_data') and e.run_data:
            error_msg_for_log += " | Run Data available on exception object." 
        logger.error(error_msg_for_log, exc_info=True) 

        await _send_fallback_reply_and_tag(
            front_conversation_id, 
            "Our automated assistant encountered an internal SDK error. A team member will review your request shortly."
        )
        agent_outcome["agent_handled"] = False
        agent_outcome["processed_flag"] = True 
        agent_outcome["details"] = {"agent_error": error_details_for_outcome, "reason": "Agent execution raised an SDK exception. Fallback reply sent."}
    
    except Exception as e: 
        logger.error(f"Unexpected exception during openai-agents SDK orchestration or result processing for {front_conversation_id}: {e}", exc_info=True)
        await _send_fallback_reply_and_tag(
            front_conversation_id, 
            "Our automated assistant encountered an unexpected internal error. A team member will review your request soon."
        )
        agent_outcome["agent_handled"] = False
        agent_outcome["processed_flag"] = True 
        agent_outcome["details"] = {"agent_error": str(e), "reason": "Unexpected agent execution error. Fallback reply sent."}

    logger.info(f"Agent orchestration for {front_conversation_id} finished. Outcome: {agent_outcome}")
    return agent_outcome
# --- END: Orchestrator for openai-agents SDK ---


# --- BEGIN: Main Test Function (for local testing if needed) ---
# (This section is typically for local development and testing of the agent logic)
async def test_new_agent_sdk_flow():
    """Simulates an email coming in that would trigger the agent SDK flow."""
    
    class MockSDKSettings:
        OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") 
        OPENAI_MODEL_NAME = "gpt-4o" 

    mock_settings = MockSDKSettings()
    if not mock_settings.OPENAI_API_KEY:
        print("WARNING: OPENAI_API_KEY environment variable not set. Agent test may fail.")

    async def run_test_case(case_name, conv_id, email_content, history, expected_to_handle=True):
        print(f"\n--- Test Case: {case_name} ---")
        outcome = await handle_apt_status_request_agent_sdk(
            front_conversation_id=conv_id,
            current_email_content=email_content,
            structured_history_messages=history,
            settings_obj=mock_settings 
        )
        print(f"Outcome for {case_name}: {outcome}")
        if expected_to_handle and not outcome.get("agent_handled"):
            print(f"WARNING: {case_name} was expected to be handled by agent but was not.")
        elif not expected_to_handle and outcome.get("agent_handled"):
             print(f"INFO: {case_name} was not expected to be handled by agent and was not (or agent chose not to).")


    await run_test_case(
        "Patient ID '123456' (Simple Appointment Found)", "test_conv_simple_found",
        "Hello, my Patient ID is 123456. Status?", [], True
    )
    await run_test_case(
        "Patient ID 'PRE1079637' (Detailed Appointment Found)", "test_conv_detailed_found",
        "My ID is PRE1079637. Check appointment.", [], True
    )
    await run_test_case(
        "Patient ID '654321' (Appointment Not Found)", "test_conv_apt_notfound",
        "My PID is 654321. Any updates?", [], True 
    )
    await run_test_case(
        "Patient ID 'PRE248509' (Appointment Not Found - from logs)", "test_conv_pre248509_notfound",
        "Patient ID: PRE248509. Check status.", [], True
    )
    await run_test_case(
        "Patient ID Missing (Agent Asks)", "test_conv_pid_missing",
        "I need to know my appointment details.", [], True 
    )
    
    history_agent_asked = [
        {"type": "message", "direction": "inbound", "author_role": "user", "body": "I need to know my appointment details."},
        {"type": "comment", "direction": "outbound", "author_role": "teammate", "body": TEMPLATE_REQUEST_PATIENT_ID}, 
    ]
    await run_test_case(
        "Patient ID Missing Again (Agent Escalates)", "test_conv_pid_missing_again",
        "I still don\'t know my Patient ID.", history_agent_asked, True
    )
    await run_test_case(
        "Patient ID 'DB_ERROR_PATIENT' (DB Error)", "test_conv_db_error",
        "My ID is DB_ERROR_PATIENT, please check.", [], True
    )


if __name__ == "__main__":
    if not os.environ.get("OPENAI_API_KEY"):
        print("********************************************************************************")
        print("WARNING: OPENAI_API_KEY environment variable is not set.")
        print("The agent test flow requires an OpenAI API key to interact with the LLM.")
        print("Please set the OPENAI_API_KEY environment variable before running this test.")
        print("Example: export OPENAI_API_KEY='your_key_here'")
        print("********************************************************************************")
    else:
        print("Attempting to run test_new_agent_sdk_flow()...")
        try:
            asyncio.run(test_new_agent_sdk_flow())
        except RuntimeError as e:
            if "cannot be called from a running event loop" in str(e):
                print("Asyncio loop already running. Applying nest_asyncio and retrying.")
                import nest_asyncio
                nest_asyncio.apply()
                asyncio.run(test_new_agent_sdk_flow())
            else:
                raise 