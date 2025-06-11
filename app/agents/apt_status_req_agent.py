import asyncio
import os
import json # Import json for parsing stringified JSON
import ast # Import ast for literal_eval
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta # Added for time manipulation

from openai import OpenAIError, AsyncOpenAI
from agents import Agent, Runner, ModelSettings, function_tool, OpenAIChatCompletionsModel, RunConfig
import httpx

from app.core.config import settings as app_settings_instance # Renamed to avoid conflict if settings is passed
from celery.utils.log import get_task_logger
from app.services import frontapp_service # For the actual send_reply_to_front tool
from app.mcp import default_mcp_client as mcp_client # Import default configured MCP client
# Import templates from their new location
from app.agents.templates.appointment_status_templates import (
    TEMPLATE_APPOINTMENT_FOUND_DETAILED,
    TEMPLATE_REQUEST_PATIENT_ID,
    TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE,
    TEMPLATE_APPOINTMENT_NOT_FOUND_FOR_ID,
    TEMPLATE_DB_ERROR
)
# --- BEGIN: Agent Helper Imports ---
from app.agents.agent_helpers import (
    format_conversation_history_for_agent,
    get_patient_and_study_info,
    send_fallback_reply_and_tag,
    extract_patient_id_from_email,
    send_reply_to_front
)
# --- END: Agent Helper Imports ---

logger = get_task_logger(__name__)

# --- BEGIN: Tag Constants for Appointment Status Agent ---
TAG_AI_HUMAN_REVIEW_REQUIRED = "AI: Human review required" # Centralized tag for errors/escalations
# --- END: Tag Constants ---

# --- Response Templates have been moved to app/agents/templates/appointment_status_templates.py ---

# --- BEGIN: Placeholder Static Information (Ideally from settings_obj) ---
DEFAULT_SCHEDULING_PHONE = "888-555-1212"
DEFAULT_NO_SHOW_POLICY = "**If the patient cannot make the appointment please contact us within 48 hours of the appointment to reschedule or cancel to avoid any no-show fees. Two no-shows will require a $50 no-show payment before being scheduled for a 3rd time.**"
DEFAULT_PORTAL_LINKS = {
    "bills_appointments_liens": "https://example.com/portal/bills",
    "reports_images": "https://example.com/portal/reports"
}
# --- END: Placeholder Static Information ---

# --- BEGIN: MCP Client instance ---
# The global MCP client is now imported from app.mcp
# --- END: MCP Client instance ---

# --- BEGIN: Helper Function for openai-agents SDK ---
# This function is now imported from agent_helpers
# --- END: Helper Function ---

# --- BEGIN: Reply Generation Helper ---
def _generate_response_from_template(scenario: str, data: Dict[str, Any]) -> str:
    logger.info(f"Generating reply for scenario: {scenario} with data: {data}")
    if scenario == "appointments_found" and data.get("studies"):
        studies = data.get("studies", [])
        first_study = studies[0]
        
        studies_table_rows_list = []
        for study in studies:
            # Generate HTML table rows without extra newlines
            studies_table_rows_list.append(
                f"<tr>"
                f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('study_id','N/A')}</td>"
                f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('exam_description','N/A')}</td>"
                f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('status','N/A')}</td>"
                f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('appointment_datetime_str','N/A')}</td>"
                f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('location_name','N/A')}</td>"
                f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('images_available','N/A')}</td>"
                f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('report_available','N/A')}</td>"
                f"</tr>"
            )
        studies_table_rows = "".join(studies_table_rows_list) # Join without newlines
        
        personal_injury_info_text = ""
        if data.get("is_personal_injury_case"):
            personal_injury_info_text = """<br/>
If this is also a personal injury case:<br/>
A report containing the findings of the exam will also be sent to the attorney.<br/>
A bill will be sent to the attorney once both the patient and the attorney sign all pending liens.<br/>
Please make sure to submit a negotiation offer before sending the payment.<br/>
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

# --- BEGIN: Tool Definitions using MCP Client ---
@function_tool
async def fetch_appointment_details_by_patient_id(patient_id: str, settings_obj: Optional[Any] = None) -> Dict[str, Any]:
    """
    Fetches patient demographics and appointment/study details using the shared helper.
    Transforms the data for use with response templates.
    Requires patient_id.
    'settings_obj' can be passed to get dynamic config like phone numbers, links, etc.
    """
    logger.info(f"Tool 'fetch_appointment_details_by_patient_id' called for Patient ID: {patient_id}")

    # Get static info from settings_obj or use defaults
    scheduling_phone = getattr(settings_obj, "SCHEDULING_PHONE_NUMBER", DEFAULT_SCHEDULING_PHONE)
    no_show_policy = getattr(settings_obj, "NO_SHOW_POLICY", DEFAULT_NO_SHOW_POLICY)
    portal_links = getattr(settings_obj, "PORTAL_LINKS", DEFAULT_PORTAL_LINKS)

    try:
        # 1. Fetch data using the shared helper
        mcp_results = await get_patient_and_study_info(patient_id)
        patient_result = mcp_results.get("patient_result", {})
        studies_result = mcp_results.get("study_result", {})
        
        # More robust checking of the result from the MCP tool
        if not isinstance(patient_result, dict) or "success" not in patient_result:
            logger.error(f"Invalid or malformed response from MCP patient service for patient {patient_id}. Response: {patient_result}")
            return {"status": "db_error", "message": "Received an invalid response from the patient data service.", "patient_id": patient_id}

        if not patient_result["success"]:
            error_message = patient_result.get('error', 'An unknown error occurred.') # Default error message
            logger.error(f"Failed to fetch patient details for {patient_id}: {error_message}")
            if "No patients found" in str(error_message):
                return {"status": "not_found", "message": f"No patient record found for Patient ID: {patient_id}.", "patient_id": patient_id}
            return {"status": "db_error", "message": f"Error fetching patient details: {error_message}", "patient_id": patient_id}

        # Parse patient data from MCP response
        patient_data = None
        is_personal_injury_case = False
        
        if patient_result.get("patients") and len(patient_result["patients"]) > 0:
            patient_data = patient_result["patients"][0]
            financial_type = patient_data.get("financial_type", "").lower()
            if "pi" in financial_type or "lien" in financial_type or "personal injury" in financial_type:
                is_personal_injury_case = True
        else:
            logger.warning(f"Patient details response for {patient_id} was successful but no patient data in 'patients' list.")
            return {"status": "not_found", "message": f"Patient record found for ID {patient_id}, but no detailed data available.", "patient_id": patient_id}

        # 2. Check study details from the helper
        if not isinstance(studies_result, dict) or "success" not in studies_result:
            logger.error(f"Invalid or malformed response from MCP study service for patient {patient_id}. Response: {studies_result}")
            return {"status": "db_error", "message": "Received an invalid response from the appointment data service.", "patient_id": patient_id}

        if not studies_result.get("success"):
            error_message = studies_result.get('error', 'An unknown error occurred.')
            logger.error(f"Failed to fetch study details for {patient_id}: {error_message}")
            if "No studies found" in str(error_message):
                return {"status": "not_found", "message": f"Patient ID {patient_id} found, but no appointments/studies listed.", "patient_id": patient_id}
            return {"status": "db_error", "message": f"Error fetching study details: {error_message}", "patient_id": patient_id}

        raw_studies = studies_result.get("studies", [])
        if not raw_studies:
            logger.info(f"No studies found for patient {patient_id} after successful service call.")
            return {"status": "not_found", "message": f"Patient ID {patient_id} found, but no appointments/studies listed.", "patient_id": patient_id}

        # 3. Transform Study Data for template compatibility
        transformed_studies_for_template = []
        for study in raw_studies:
            appointment_datetime_str = "Date/Time N/A"
            arrival_time_str = "N/A"
            
            service_appt_time_str = study.get("appointment_time", "")
            
            parsed_dt = None
            if service_appt_time_str:
                try:
                    # Try parsing as ISO datetime first
                    if "T" in service_appt_time_str:
                        parsed_dt = datetime.fromisoformat(service_appt_time_str.replace("Z", ""))
                    else:
                        try:
                            parsed_dt = datetime.strptime(service_appt_time_str, "%m/%d/%Y %I:%M:%S %p")
                        except ValueError:
                            try:
                                parsed_time_obj = datetime.strptime(service_appt_time_str, "%I:%M %p").time()
                                appointment_datetime_str = f"Date N/A @ {parsed_time_obj.strftime('%I:%M %p')}"
                            except ValueError:
                                appointment_datetime_str = f"{service_appt_time_str} (Could not parse fully)"

                    if parsed_dt:
                        appointment_datetime_str = parsed_dt.strftime("%m/%d/%Y @ %I:%M %p")
                        pre_arrival_min = study.get("pre_arrival_minutes", 30)
                        arrival_dt = parsed_dt - timedelta(minutes=pre_arrival_min)
                        arrival_time_str = arrival_dt.strftime("%I:%M %p")
                        
                except ValueError as e_date:
                    logger.warning(f"Could not parse appointment_time '{service_appt_time_str}' for study {study.get('authorization_number')}: {e_date}")
                    appointment_datetime_str = f"{service_appt_time_str} (Unparseable)"
            
            facility_info = study.get("facility", {})
            location_display = f"{facility_info.get('facility_name', 'N/A')} - {facility_info.get('address', 'N/A')}".strip(" -")
            if location_display == "N/A - N/A" or not location_display: location_display = "Location N/A"

            transformed_studies_for_template.append({
                "study_id": study.get("authorization_number", "N/A"),
                "exam_description": study.get("study_description", "N/A"),
                "status": study.get("status", "N/A"),
                "appointment_datetime_str": appointment_datetime_str,
                "arrival_time_str": arrival_time_str,
                "location_name": location_display,
                "images_available": "No",  # Default, not in service output
                "report_available": "No"   # Default, not in service output
            })

        if not transformed_studies_for_template:
            return {"status": "not_found", "message": f"Patient ID {patient_id} found, studies retrieved, but failed to transform any for display.", "patient_id": patient_id}

        return {
            "status": "success",
            "data": {
                "patient_id_confirmed": patient_id,
                "studies": transformed_studies_for_template,
                "is_personal_injury_case": is_personal_injury_case,
                "scheduling_phone": scheduling_phone,
                "no_show_policy": no_show_policy,
                "links": portal_links
            }
        }

    except Exception as e:
        logger.error(f"Exception in fetch_appointment_details_by_patient_id: {e}")
        return {"status": "db_error", "message": f"Exception during MCP call: {str(e)}", "patient_id": patient_id}

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

# send_reply_to_front is now imported from agent_helpers

# --- END: Tool Definitions ---

# --- BEGIN: Fallback Reply Helper ---
# This is now imported from agent_helpers
# --- END: Fallback Reply Helper ---

# --- BEGIN: Orchestrator for openai-agents SDK ---
async def handle_apt_status_request_agent_sdk(
    front_conversation_id: str,
    current_email_content: str,
    structured_history_messages: List[Dict[str, Any]],
    settings_obj: Any = app_settings_instance 
) -> Dict[str, Any]:
    """
    Handles an "Apt Status Req" using the openai-agents SDK with MCP server integration.
    Returns a dictionary with agent processing results.
    """
    logger.info(f"Initiating openai-agents SDK flow with MCP integration for Apt Status Req - Conv ID: {front_conversation_id}")

    # Initialize MCP client connection
    mcp_connected = await mcp_client.connect()
    if not mcp_connected:
        logger.error("Failed to connect to MCP server, falling back to error response")
        await send_fallback_reply_and_tag(
            front_conversation_id,
            "Our automated assistant is currently unable to connect to patient data services. A team member will review your request.",
            TAG_AI_HUMAN_REVIEW_REQUIRED
        )
        return {
            "agent_handled": False,
            "processed_flag": True,
            "details": {"reason": "MCP server connection failed. Fallback reply sent."}
        }

    formatted_history = format_conversation_history_for_agent(structured_history_messages)
    logger.info(f"Formatted conversation history: {formatted_history}")
    
    # Combine history and current email for a complete context for extraction
    full_conversation_text = f"Conversation History:\n{formatted_history}\n\nLatest User Email:\n{current_email_content}"

    instructions = f"""
You are an AI assistant for a medical imaging company, specializing in appointment status requests.
Your primary goal is to:
1.  Search the **'Entire Conversation For Extraction'** text provided below to find the Patient ID. You MUST pass this complete text block to the `extract_patient_id_from_email` tool.
2.  Fetch appointment details using `fetch_appointment_details_by_patient_id` with the extracted ID. Also pass the `settings_obj` to this tool.
3. Based on the outcome of step 2, determine the correct scenario.
4. Call the `generate_formatted_reply` tool, passing it the determined scenario and the FULL result from `fetch_appointment_details_by_patient_id` (if available), and the `extracted_patient_id` (if available).
5. Take the `reply_text` from `generate_formatted_reply`'s output.
6. Call `send_reply_to_front` with this `reply_text` and add tags ONLY IF the scenario requires escalation to a human.

Conversation ID (use for tool calls): {front_conversation_id}

**Entire Conversation For Extraction:**
---
{full_conversation_text}
---

**Scenarios & Tool Usage Flow:**

A.  **If calling `extract_patient_id_from_email` on the 'Entire Conversation For Extraction' text returns a `patient_id` (let's call it `extracted_pid`):**
    1.  Call `fetch_appointment_details_by_patient_id` with `patient_id=extracted_pid` and `settings_obj=settings_obj` (pass through from orchestrator). Let the result be `fetch_result`.
    2.  **If `fetch_result.status` is "success"** (and `fetch_result.data.studies` is not empty):
        *   Scenario for `generate_formatted_reply`: "appointments_found"
        *   Call `generate_formatted_reply` with `scenario="appointments_found"`, `fetch_details_result=fetch_result`.
        *   Take `reply_text` from its output.
        *   Call `send_reply_to_front` with this `reply_text`. (No tags needed for this success case).
    3.  **If `fetch_result.status` is "not_found"** (meaning patient ID was valid but no appointments, or patient ID itself was not found by the service):
        *   Scenario for `generate_formatted_reply`: "id_not_found_in_system"
        *   Call `generate_formatted_reply` with `scenario="id_not_found_in_system"`, `fetch_details_result=fetch_result` (which contains patient_id from input, and potentially a message from the service).
        *   Take `reply_text` from its output.
        *   Call `send_reply_to_front` with this `reply_text` and `tags_to_add=["{TAG_AI_HUMAN_REVIEW_REQUIRED}"]`.
    4.  **If `fetch_result.status` is "db_error"** (any other error from fetching/processing):
        *   Scenario for `generate_formatted_reply`: "db_error"
        *   Call `generate_formatted_reply` with `scenario="db_error"`, `fetch_details_result=fetch_result` (which contains patient_id and error message).
        *   Take `reply_text` from its output.
        *   Call `send_reply_to_front` with this `reply_text` and `tags_to_add=["{TAG_AI_HUMAN_REVIEW_REQUIRED}"]`.

B.  **If `extract_patient_id_from_email` returns NO `patient_id` after searching the 'Entire Conversation For Extraction' text:**
    1.  Review the full conversation again.
    2.  **If you have NOT asked for a Patient ID before OR the user's response is not yet in history:**
        *   Scenario for `generate_formatted_reply`: "id_missing_first_attempt"
        *   Call `generate_formatted_reply` with `scenario="id_missing_first_attempt"`, `fetch_details_result={{}}` (empty dict as no fetch was done), `extracted_patient_id=None`.
        *   Take `reply_text` from its output.
        *   Call `send_reply_to_front` with this `reply_text`. (No tag needed for first request).
    3.  **If you HAVE asked for a Patient ID before, and user STILL did not provide a usable one:**
        *   Scenario for `generate_formatted_reply`: "id_missing_second_attempt"
        *   Call `generate_formatted_reply` with `scenario="id_missing_second_attempt"`, `fetch_details_result={{}}`, `extracted_patient_id=None`.
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
            name="AppointmentStatusAgent_MCP_v1", # Updated name
            instructions=instructions,
            model=OpenAIChatCompletionsModel(
                model=settings_obj.OPENAI_MODEL_NAME if hasattr(settings_obj, 'OPENAI_MODEL_NAME') and settings_obj.OPENAI_MODEL_NAME else "gpt-4o",
                openai_client=custom_openai_client
            ),
            tools=[
                extract_patient_id_from_email,
                fetch_appointment_details_by_patient_id,
                generate_formatted_reply,
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
                    # First, try to parse it as standard JSON
                    parsed_final_output = json.loads(agent_result.final_output)
                except json.JSONDecodeError:
                    # If JSON parsing fails, it might be a string representation of a Python dict
                    logger.warning(f"JSON parsing failed for agent output. Attempting literal_eval. Output: {agent_result.final_output}")
                    try:
                        parsed_final_output = ast.literal_eval(agent_result.final_output)
                    except (ValueError, SyntaxError) as e:
                        logger.warning(f"Agent for {front_conversation_id} final_output was a string, but failed to parse as JSON or Python literal: {agent_result.final_output}. Error: {e}")
                        parsed_final_output = None
                
                if parsed_final_output and not isinstance(parsed_final_output, dict):
                    logger.warning(f"Agent for {front_conversation_id} final_output was parsed, but it is not a dictionary. Parsed Type: {type(parsed_final_output)}")
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
                await send_fallback_reply_and_tag(
                    front_conversation_id, 
                    "Our automated assistant tried to send a reply but encountered a communication issue with the final step. A team member will review your request.",
                    TAG_AI_HUMAN_REVIEW_REQUIRED
                )
                agent_outcome["agent_handled"] = False 
                agent_outcome["processed_flag"] = True 
                agent_outcome["details"] = {
                    "reason": "Agent's final tool call failed. Fallback reply sent by orchestrator.", 
                    "tool_response": parsed_final_output
                }
        elif agent_result.final_output: 
            logger.warning(f"Agent for {front_conversation_id} produced final_output, but it was not the expected dictionary format. Original Output: {agent_result.final_output}")
            await send_fallback_reply_and_tag(
                front_conversation_id,
                "Our automated assistant had an issue formatting its final response. A team member will review your request.",
                TAG_AI_HUMAN_REVIEW_REQUIRED
            )
            agent_outcome["agent_handled"] = False
            agent_outcome["processed_flag"] = True 
            agent_outcome["details"] = {
                "reason": "Agent produced unexpected final_output type or format. Fallback reply sent by orchestrator.",
                "original_final_output": str(agent_result.final_output) if len(str(agent_result.final_output)) < 200 else "Original output too long for details field"
            }
        else: 
            logger.warning(f"Agent for {front_conversation_id} completed without any final_output.")
            await send_fallback_reply_and_tag(
                front_conversation_id, 
                "Our automated assistant did not complete the processing as expected (no final output). A team member will review your request.",
                TAG_AI_HUMAN_REVIEW_REQUIRED
            )
            agent_outcome["agent_handled"] = False
            agent_outcome["processed_flag"] = True 
            agent_outcome["details"] = {"reason": "Agent completed without producing a final output. Fallback reply sent by orchestrator."}

    except Exception as e: 
        logger.error(f"Unexpected exception during openai-agents SDK orchestration or result processing for {front_conversation_id}: {e}", exc_info=True)
        await send_fallback_reply_and_tag(
            front_conversation_id, 
            "Our automated assistant encountered an unexpected internal error. A team member will review your request soon.",
            TAG_AI_HUMAN_REVIEW_REQUIRED
        )
        agent_outcome["agent_handled"] = False
        agent_outcome["processed_flag"] = True 
        agent_outcome["details"] = {"agent_error": str(e), "reason": "Unexpected agent execution error. Fallback reply sent."}
    
    finally:
        # Clean up MCP client connection
        # await mcp_client.close() # Removed this line to prevent closing the shared client
        pass

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