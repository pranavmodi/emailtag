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

logger = get_task_logger(__name__)

# --- BEGIN: Tag Constants for Appointment Status Agent ---
TAG_AI_HUMAN_REVIEW_REQUIRED = "AI: Human review required" # Centralized tag for errors/escalations
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
    if patient_id == "123456": # Mock data for testing
        return {
            "status": "success", 
            "data": {"exam_type": "MRI Brain", "appointment_date": "2024-07-15", "current_status": "Scheduled"}
        }
    elif patient_id == "PRE248509": # Specific test case from logs for "not_found"
         return {"status": "not_found", "message": f"No appointments found for Patient ID: {patient_id}."}
    elif patient_id == "654321":
        return {"status": "not_found", "message": "No appointments found for this patient ID."}
    elif patient_id == "DB_ERROR_PATIENT":
        return {"status": "db_error", "message": "Simulated database query failed."}
    else: # Default to not_found for other IDs
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
            *   Call `send_reply_to_front` with this formulated reply.
        c.  If `fetch_appointment_details_by_patient_id` result `status` is "not_found":
            *   Formulate a reply like: "We found your Patient ID: {{patient_id}}, but could not find any upcoming appointments. If you believe this is an error, please provide the approximate date and type of your exam so our team can investigate further." (Replace {{patient_id}} with the ID you have).
            *   Call `send_reply_to_front` with this formulated reply and `tags_to_add=["{TAG_AI_HUMAN_REVIEW_REQUIRED}"]`.
        d.  If `fetch_appointment_details_by_patient_id` result `status` is "db_error":
            *   Formulate a reply like: "We encountered a technical difficulty while trying to fetch your appointment details. Our team has been notified and will look into this."
            *   Call `send_reply_to_front` with this formulated reply and `tags_to_add=["{TAG_AI_HUMAN_REVIEW_REQUIRED}"]`.

    *   **If `extract_patient_id_from_email` returns NO `patient_id` (i.e., `patient_id` is null or empty)**:
        a.  **Review Conversation History**: Carefully examine the "Conversation History" provided. Determine if you (the Assistant) have previously asked for a Patient ID in this conversation, AND if the user's subsequent replies (visible in history or the "Latest User Email") did not provide a clear Patient ID that was then successfully used or found to be valid.
        b.  **If you determine you have NOT asked for a Patient ID before OR you asked but the user's response (if any) is not yet in the provided history or did not contain a clear ID**:
            *   Formulate a polite request: "To help me find your appointment status, could you please provide your Patient ID?"
            *   Call `send_reply_to_front` with this request.
        c.  **If you determine you HAVE asked for a Patient ID before, and the user's subsequent replies (in history or "Latest User Email") STILL did not yield a usable Patient ID**:
            *   Formulate an escalation message: "Thank you for the information. We're still having trouble locating your appointment details. A member of our team will personally review your request and get back to you shortly."
            *   Call `send_reply_to_front` with this message and `tags_to_add=["{TAG_AI_HUMAN_REVIEW_REQUIRED}"]`.

IMPORTANT FINAL STEP: After deciding which action to take and calling the `send_reply_to_front` tool, your job is to return ONLY the direct JSON output received from that `send_reply_to_front` tool call. Do NOT add any conversational text, summaries, or any other information around it. Your entire response for this run MUST be the JSON object that the `send_reply_to_front` tool gives back.

Remember to replace placeholders like `{{exam_type}}`, `{{appointment_date}}`, `{{current_status}}`, and `{{patient_id}}` in your formulated replies with actual values from tool outputs before calling `send_reply_to_front`.
The `send_reply_to_front` tool also accepts `tags_to_remove` if you need to clean up previous tags.
Do not ask for confirmation. Execute the described logic and make sure your final returned value is strictly the JSON output from `send_reply_to_front`.
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
            name="AppointmentStatusAgent_ConvoAware_v3",
            instructions=instructions,
            model=OpenAIChatCompletionsModel(
                model=settings_obj.OPENAI_MODEL_NAME if hasattr(settings_obj, 'OPENAI_MODEL_NAME') and settings_obj.OPENAI_MODEL_NAME else "gpt-4o", # Ensure 'gpt-4o' is used if not specified
                openai_client=custom_openai_client
            ),
            tools=[
                extract_patient_id_from_email,
                fetch_appointment_details_by_patient_id,
                send_reply_to_front,
            ],
            model_settings=ModelSettings(
                temperature=0.2 # Lower temperature for more deterministic behavior in structured tasks
            )
        )
        
        agent_run_input_context = f"Process request based on Latest User Email provided in instructions for conversation {front_conversation_id}."
        logger.info(f"Running {apt_status_agent.name} for conv {front_conversation_id}.")

        # Disable tracing for this specific run to avoid SSL errors if tracing backend is problematic
        run_config_settings = RunConfig(tracing_disabled=True)

        agent_result = await Runner.run(
            apt_status_agent, 
            input=agent_run_input_context,
            run_config=run_config_settings
        )

        # If Runner.run completes without an exception, check final_output
        parsed_final_output = None
        if agent_result.final_output:
            if isinstance(agent_result.final_output, dict):
                parsed_final_output = agent_result.final_output
            elif isinstance(agent_result.final_output, str):
                try:
                    parsed_final_output = json.loads(agent_result.final_output)
                    if not isinstance(parsed_final_output, dict):
                        # If parsing succeeds but it's not a dict (e.g. a string like "OK" was JSON encoded)
                        logger.warning(f"Agent for {front_conversation_id} final_output was a string that parsed to JSON, but not to a dictionary. Parsed: {parsed_final_output}")
                        parsed_final_output = None # Treat as invalid format
                except json.JSONDecodeError:
                    logger.warning(f"Agent for {front_conversation_id} final_output was a string, but failed to parse as JSON: {agent_result.final_output}")
                    parsed_final_output = None # Treat as invalid format
            else:
                 logger.warning(f"Agent for {front_conversation_id} final_output was neither a dict nor a string: {type(agent_result.final_output)}")
                 # parsed_final_output remains None

        if parsed_final_output: # Check if we have a valid dictionary now
            logger.info(f"Agent run for {front_conversation_id} completed. Parsed final output: {parsed_final_output}")
            
            tool_status = parsed_final_output.get("status")
            tool_message = parsed_final_output.get("message", "No message from tool's output.")

            if tool_status == "success":
                # SUCCESS case - agent handled and its final tool reported success
                agent_outcome["agent_handled"] = True
                agent_outcome["processed_flag"] = True # Reply was sent by agent's tool
                agent_outcome["details"] = {
                    "reason": "Agent successfully processed and sent reply via its designated final tool.", 
                    "tool_response": parsed_final_output
                }
                logger.info(f"Agent's final tool call successful for {front_conversation_id}: {tool_message}")
            else:
                # Agent's final tool call (e.g. send_reply_to_front) reported an error in its own status
                logger.error(f"Agent's final tool call for {front_conversation_id} reported non-success status '{tool_status}': {tool_message}")
                await _send_fallback_reply_and_tag(
                    front_conversation_id, 
                    "Our automated assistant tried to send a reply but encountered a communication issue with the final step. A team member will review your request."
                )
                agent_outcome["agent_handled"] = False # Agent logic might be fine, but final communication failed
                agent_outcome["processed_flag"] = True # Orchestrator sent a fallback reply
                agent_outcome["details"] = {
                    "reason": "Agent's final tool call failed. Fallback reply sent by orchestrator.", 
                    "tool_response": parsed_final_output
                }
        # This elif covers cases where original final_output existed but wasn't successfully parsed into a dict
        elif agent_result.final_output: 
            logger.warning(f"Agent for {front_conversation_id} produced final_output, but it was not the expected dictionary format. Original Output: {agent_result.final_output}")
            await _send_fallback_reply_and_tag(
                front_conversation_id,
                "Our automated assistant had an issue formatting its final response. A team member will review your request."
            )
            agent_outcome["agent_handled"] = False
            agent_outcome["processed_flag"] = True # Orchestrator sent a fallback reply
            agent_outcome["details"] = {
                "reason": "Agent produced unexpected final_output type or format. Fallback reply sent by orchestrator.",
                # Log the original if it's simple, otherwise a placeholder
                "original_final_output": str(agent_result.final_output) if len(str(agent_result.final_output)) < 200 else "Original output too long for details field"
            }
        else: # Agent completed, but no final_output at all.
            logger.warning(f"Agent for {front_conversation_id} completed without any final_output.")
            await _send_fallback_reply_and_tag(
                front_conversation_id, 
                "Our automated assistant did not complete the processing as expected (no final output). A team member will review your request."
            )
            agent_outcome["agent_handled"] = False
            agent_outcome["processed_flag"] = True # Orchestrator sent a fallback reply
            agent_outcome["details"] = {"reason": "Agent completed without producing a final output. Fallback reply sent by orchestrator."}

    except AgentsException as e:
        error_msg_for_log = f"AgentsException during openai-agents SDK orchestration for {front_conversation_id}: {str(e)}"
        error_details_for_outcome = str(e)
        if hasattr(e, 'run_data') and e.run_data:
            # Avoid logging overly verbose run_data directly, summarize or indicate presence
            error_msg_for_log += " | Run Data available on exception object." 
            # You might want to serialize e.run_data to string if it's useful and not too large
            # For now, keeping it simple for the 'details' field.
            # error_details_for_outcome += f" | Run Data: {str(e.run_data)}" # Could be too verbose
        logger.error(error_msg_for_log, exc_info=True) # exc_info=True will log the full traceback

        await _send_fallback_reply_and_tag(
            front_conversation_id, 
            "Our automated assistant encountered an internal SDK error. A team member will review your request shortly."
        )
        agent_outcome["agent_handled"] = False
        agent_outcome["processed_flag"] = True # Orchestrator sent a fallback reply
        agent_outcome["details"] = {"agent_error": error_details_for_outcome, "reason": "Agent execution raised an SDK exception. Fallback reply sent."}
    
    except Exception as e: # Catch any other unexpected exceptions during agent run or result processing
        logger.error(f"Unexpected exception during openai-agents SDK orchestration or result processing for {front_conversation_id}: {e}", exc_info=True)
        await _send_fallback_reply_and_tag(
            front_conversation_id, 
            "Our automated assistant encountered an unexpected internal error. A team member will review your request soon."
        )
        agent_outcome["agent_handled"] = False
        agent_outcome["processed_flag"] = True # Orchestrator sent a fallback reply
        agent_outcome["details"] = {"agent_error": str(e), "reason": "Unexpected agent execution error. Fallback reply sent."}

    # Log the final outcome from the agent orchestrator
    logger.info(f"Agent orchestration for {front_conversation_id} finished. Outcome: {agent_outcome}")
    return agent_outcome
# --- END: Orchestrator for openai-agents SDK ---


# --- BEGIN: Main Test Function (for local testing if needed) ---
# (This section is typically for local development and testing of the agent logic)
async def test_new_agent_sdk_flow():
    """Simulates an email coming in that would trigger the agent SDK flow."""
    
    # Mock settings if needed, or rely on global app_settings_instance
    class MockSDKSettings:
        OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") # Ensure this is set in your env
        OPENAI_MODEL_NAME = "gpt-4o" # Explicitly use gpt-4o for testing
        # Add any other settings your agent/tools might require from the settings_obj

    mock_settings = MockSDKSettings()
    if not mock_settings.OPENAI_API_KEY:
        print("WARNING: OPENAI_API_KEY environment variable not set. Agent test may fail.")
        # return # Optionally, exit if key is missing

    # --- Test Case 1: Patient ID present, appointment should be found (mocked) ---
    print("\n--- Test Case 1: Patient ID '123456' (Appointment Found) ---")
    test_conv_id_1 = "test_conv_apt_found_123"
    test_email_content_1 = "Hello, my Patient ID is 123456. What's my appointment status?"
    test_history_1 = [
        {"type": "message", "direction": "inbound", "author_role": "user", "body": "Previous question unrelated."},
        {"type": "message", "direction": "outbound", "author_role": "teammate", "body": "Previous assistant reply."}
    ]
    outcome1 = await handle_apt_status_request_agent_sdk(
        front_conversation_id=test_conv_id_1,
        current_email_content=test_email_content_1,
        structured_history_messages=test_history_1,
        settings_obj=mock_settings 
    )
    print(f"Test Case 1 Outcome: {outcome1}")

    # --- Test Case 2: Patient ID present, appointment NOT found (mocked) ---
    print("\n--- Test Case 2: Patient ID '654321' (Appointment Not Found) ---")
    test_conv_id_2 = "test_conv_apt_notfound_456"
    test_email_content_2 = "My PID is 654321. Any updates?"
    test_history_2 = []
    outcome2 = await handle_apt_status_request_agent_sdk(
        front_conversation_id=test_conv_id_2,
        current_email_content=test_email_content_2,
        structured_history_messages=test_history_2,
        settings_obj=mock_settings
    )
    print(f"Test Case 2 Outcome: {outcome2}")

    # --- Test Case 3: Patient ID NOT present (first attempt by agent) ---
    print("\n--- Test Case 3: Patient ID Missing (Agent Asks) ---")
    test_conv_id_3 = "test_conv_pid_missing_789"
    test_email_content_3 = "I need to know my appointment details."
    test_history_3 = []
    outcome3 = await handle_apt_status_request_agent_sdk(
        front_conversation_id=test_conv_id_3,
        current_email_content=test_email_content_3,
        structured_history_messages=test_history_3,
        settings_obj=mock_settings
    )
    print(f"Test Case 3 Outcome: {outcome3}")
    
    # --- Test Case 4: Patient ID NOT present (second attempt, after agent asked once) ---
    print("\n--- Test Case 4: Patient ID Missing Again (Agent Escalates) ---")
    test_conv_id_4 = "test_conv_pid_missing_again_012"
    test_email_content_4 = "I still don't know my Patient ID."
    test_history_4 = [ # Simulate agent already asked for ID
        {"type": "message", "direction": "inbound", "author_role": "user", "body": "I need to know my appointment details."},
        {"type": "comment", "direction": "outbound", "author_role": "teammate", "body": "To help me find your appointment status, could you please provide your Patient ID?"}, # Agent's previous request
        # Current email is test_email_content_4
    ]
    outcome4 = await handle_apt_status_request_agent_sdk(
        front_conversation_id=test_conv_id_4,
        current_email_content=test_email_content_4,
        structured_history_messages=test_history_4,
        settings_obj=mock_settings
    )
    print(f"Test Case 4 Outcome: {outcome4}")

    # --- Test Case 5: DB Error during fetch ---
    print("\n--- Test Case 5: Patient ID 'DB_ERROR_PATIENT' (DB Error) ---")
    test_conv_id_5 = "test_conv_db_error_345"
    test_email_content_5 = "My ID is DB_ERROR_PATIENT, please check."
    test_history_5 = []
    outcome5 = await handle_apt_status_request_agent_sdk(
        front_conversation_id=test_conv_id_5,
        current_email_content=test_email_content_5,
        structured_history_messages=test_history_5,
        settings_obj=mock_settings
    )
    print(f"Test Case 5 Outcome: {outcome5}")
    
    # --- Test Case 6: Real-world example from logs with PRE prefix (should be 'not_found') ---
    print("\n--- Test Case 6: Patient ID 'PRE248509' (Appointment Not Found - Real Log Example) ---")
    test_conv_id_6 = "test_conv_pre_id_notfound_678"
    test_email_content_6 = "Hello Scheduling Team,I am writing to check the status of an appointment I believe I have scheduled with your facility.My details are:Patient Name: Alex PatientPatient ID: PRE248509DOB: 01/01/1980Could you please confirm if an appointment is on file for me and, if so, provide the date, time, and any preparation instructions?This email is sent via the Python test script from: pranav@possibleminds.in. Test ID: a5f099b4-bfaf-49b5-b574-018c9d6555daThank you,Alex Patient (via Test Script)"
    test_history_6 = []
    outcome6 = await handle_apt_status_request_agent_sdk(
        front_conversation_id=test_conv_id_6,
        current_email_content=test_email_content_6,
        structured_history_messages=test_history_6,
        settings_obj=mock_settings
    )
    print(f"Test Case 6 Outcome: {outcome6}")

if __name__ == "__main__":
    # This allows running the test function directly using `python -m app.agents.apt_status_req_agent`
    # Make sure nest_asyncio is applied if running in an environment that needs it (e.g. Jupyter)
    # For simple script execution, asyncio.run should be fine.
    
    # For Celery tasks, nest_asyncio.apply() is usually at the top of the tasks.py file.
    # If running this standalone, and it's part of a larger async ecosystem (like FastAPI tests),
    # you might need to manage the event loop carefully or use pytest-asyncio.
    # For this simple test script, asyncio.run is generally okay.
    
    # Check if OPENAI_API_KEY is set
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