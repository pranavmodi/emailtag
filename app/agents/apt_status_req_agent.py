import asyncio
import os
import json
import ast # Import ast for literal_eval
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta # Added for time manipulation

# Helper function to get ordinal suffix for day
def get_day_suffix(day: int) -> str:
    """Returns the ordinal suffix for a day (st, nd, rd, th)."""
    if 10 <= day % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return suffix

from openai import OpenAIError, AsyncOpenAI
from agents import Agent, Runner, ModelSettings, function_tool, OpenAIChatCompletionsModel, RunConfig
import httpx

from app.core.config import settings as app_settings_instance # Renamed to avoid conflict if settings is passed
from celery.utils.log import get_task_logger
from app.services import frontapp_service # For the actual send_reply_to_front tool
from app.mcp import default_mcp_client as mcp_client # Import default configured MCP client
from app.db.session import AsyncSessionLocal
from app.crud.message_template import message_template_crud
from app.crud.tag_settings import tag_settings_crud
# Import templates from their locations (as fallback)
from app.agents.templates.appointment_status_templates import (
    TEMPLATE_APPOINTMENT_FOUND_DETAILED,
    TEMPLATE_APPOINTMENT_NOT_FOUND_FOR_ID,
    TEMPLATE_DB_ERROR
)
from app.agents.templates.shared_templates import (
    TEMPLATE_REQUEST_PATIENT_ID,
    TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE
)
# --- BEGIN: Agent Helper Imports ---
from app.agents.agent_helpers import (
    format_conversation_history_for_agent,
    get_patient_and_study_info,
    send_fallback_reply_and_tag,
    send_reply_to_front,
    send_reply_to_front_direct,
    send_reply_to_front_with_attachment,
    verify_sender_for_patient_access
)
# --- END: Agent Helper Imports ---

logger = get_task_logger(__name__)

# --- BEGIN: Tag Constants for Appointment Status Agent ---
TAG_AI_HUMAN_REVIEW_REQUIRED = "AI: Human review required" # Centralized tag for errors/escalations
# --- END: Tag Constants ---

# --- Response Templates have been moved to app/agents/templates/appointment_status_templates.py ---

# --- BEGIN: Placeholder Static Information (Fallback if DB fetch fails) ---
DEFAULT_SCHEDULING_PHONE = "800-558-2223"
DEFAULT_NO_SHOW_POLICY = "**If the patient cannot make the appointment please contact us within 48 hours of the appointment to reschedule or cancel to avoid any no-show fees. Two no-shows will require a $50 no-show payment before being scheduled for a 3rd time.**"
DEFAULT_PORTAL_LINKS = {
    "bills_appointments_liens": "https://example.com/portal/bills",
    "reports_images": "https://example.com/portal/reports"
}

# # Unified template (standard approach - replaces all legacy template parts)
# # COMMENTED OUT: If DB settings are missing, we should log an error instead of using a default
# DEFAULT_UNIFIED_TEMPLATE = """Dear {first_name} {last_name},<br/>
# In regards to patient ID (MRN): {patient_id_confirmed}<br/><br/>
#
# <b>How to Schedule:</b><br/><br/>
#
# <ul>
#   <li>Schedule online 24/7 via the <a href="https://app.radflow360.com/patient-portal" target="_blank">patient portal</a></li>
#   <li>Call <b>800-558-2223</b></li>
# </ul><br/>
#
# <b>Rescheduling / No Show Policy:</b><br/>
# **If the patient cannot make the appointment please contact us within 48 hours of the appointment to reschedule or cancel to avoid any no-show fees. Two no-shows will require a $50 no-show payment before being scheduled for a 3rd time.**<br/><br/>
#
# Here is a summary of the patient's exams we currently have entered into our system:<br/>
# {appointment_table}<br/>
#
# <p>Recent contact history:</p>
# {call_log_table}<br/>
#
# {personal_injury_info}
#
# <b>What You Can Access in the RadFlow 360 Portal</b><br/><br/>
#
# <ul>
#   <li>View all patient exams and status</li>
#   <li>Reports & Documents</li>
#   <li>View Images, Download, and Burn to CD</li>
#   <li>Provide Case Updates</li>
#   <li>Submit & Approve Bill Offers</li>
#   <li>Pay online via credit card and ACH</li>
# </ul><br/>
#
# <a href="https://app.radflow360.com/patient-portal" target="_blank"><b>Login or Create Your Free Account Today</b></a>"""
# --- END: Placeholder Static Information ---

# --- BEGIN: Database Settings Helper ---
async def get_tag_settings_from_db(tag_name: str = "Apt status req") -> dict:
    """
    Fetch tag settings from database.

    STANDARD APPROACH:
    - Load custom_placeholders from WORKSPACE tag (global placeholders)
    - Load unified_template from tag-specific settings

    Returns a dict with settings, falling back to defaults if not found.
    """
    try:
        async with AsyncSessionLocal() as db:
            # Load workspace custom placeholders (global)
            workspace_dict = await tag_settings_crud.get_settings_dict(db, "WORKSPACE")
            custom_placeholders = {}
            if workspace_dict and "custom_placeholders" in workspace_dict:
                custom_placeholders = workspace_dict["custom_placeholders"]
                logger.info(f"✅ Loaded {len(custom_placeholders)} custom placeholders from WORKSPACE")
            else:
                logger.warning(f"⚠️ No WORKSPACE custom placeholders found, using defaults")

            # Load tag-specific settings (unified_template only)
            settings_dict = await tag_settings_crud.get_settings_dict(db, tag_name)

            if settings_dict:
                logger.info(f"✅ Loaded settings for '{tag_name}' from database")

                return {
                    # Custom placeholders (workspace-wide, loaded from WORKSPACE tag)
                    "custom_placeholders": custom_placeholders,
                    # Unified template (tag-specific)
                    "unified_template": settings_dict.get("unified_template"),
                    # Extract specific values for backward compatibility in code
                    "scheduling_phone": custom_placeholders.get("scheduling_phone", DEFAULT_SCHEDULING_PHONE),
                    "no_show_policy": custom_placeholders.get("no_show_policy", DEFAULT_NO_SHOW_POLICY),
                    "portal_links": {
                        "bills_appointments_liens": custom_placeholders.get("bills_link", DEFAULT_PORTAL_LINKS["bills_appointments_liens"]),
                        "reports_images": custom_placeholders.get("reports_link", DEFAULT_PORTAL_LINKS["reports_images"])
                    }
                }
            else:
                logger.error(f"❌ CRITICAL: No settings found for '{tag_name}' in database! Template must be configured in /settings/template-config")
                return {
                    "custom_placeholders": custom_placeholders,  # Use workspace placeholders even if tag not found
                    "unified_template": None,  # No default - must be configured in DB
                    "scheduling_phone": custom_placeholders.get("scheduling_phone", DEFAULT_SCHEDULING_PHONE),
                    "no_show_policy": custom_placeholders.get("no_show_policy", DEFAULT_NO_SHOW_POLICY),
                    "portal_links": {
                        "bills_appointments_liens": custom_placeholders.get("bills_link", DEFAULT_PORTAL_LINKS["bills_appointments_liens"]),
                        "reports_images": custom_placeholders.get("reports_link", DEFAULT_PORTAL_LINKS["reports_images"])
                    }
                }
    except Exception as e:
        logger.error(f"❌ CRITICAL: Error fetching tag settings from database: {e}. Template must be configured in /settings/template-config", exc_info=True)
        return {
            "custom_placeholders": {},
            "unified_template": None,  # No default - must be configured in DB
            "scheduling_phone": DEFAULT_SCHEDULING_PHONE,
            "no_show_policy": DEFAULT_NO_SHOW_POLICY,
            "portal_links": DEFAULT_PORTAL_LINKS
        }
# --- END: Database Settings Helper ---

# --- BEGIN: MCP Client instance ---
# The global MCP client is now imported from app.mcp
# --- END: MCP Client instance ---

# --- BEGIN: Helper Function for openai-agents SDK ---
# This function is now imported from agent_helpers
# --- END: Helper Function ---

# --- BEGIN: Table Generation Helper ---
def _generate_appointment_table_html(studies: List[Dict[str, Any]]) -> str:
    """
    Generate HTML table for appointment/study information.

    Args:
        studies: List of study dictionaries with appointment details

    Returns:
        str: Complete HTML table with all studies
    """
    if not studies:
        return "<p>No appointments found.</p>"

    # Generate table rows
    studies_table_rows_list = []
    for study in studies:
        studies_table_rows_list.append(
            f"<tr>"
            f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('study_id','N/A')}</td>"
            f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('exam_description','N/A')}</td>"
            f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('status','N/A')}</td>"
            f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('appointment_datetime_str','N/A')}</td>"
            f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('location_name','N/A')}</td>"
            f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('mri_type','N/A')}</td>"
            f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('images_available','N/A')}</td>"
            f"<td style=\"border: 1px solid black; padding: 8px;\">{study.get('report_available','N/A')}</td>"
            f"</tr>"
        )
    studies_table_rows = "".join(studies_table_rows_list)

    # Build the complete table structure
    table_html = f"""<table border="1" style="border-collapse: collapse; width: 100%;">
<thead>
<tr>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Study ID</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Exam Description</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Status</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Study Date/Time</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Location</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">MRI Type</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Images Available</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Report Available</th>
</tr>
</thead>
<tbody>{studies_table_rows}</tbody>
</table>"""

    return table_html
# --- END: Table Generation Helper ---

# --- BEGIN: Reply Generation Helper ---
async def _generate_response_from_template(scenario: str, data: Dict[str, Any]) -> str:
    """
    Generates response from template, fetching from database first, falling back to hardcoded templates.
    """
    # Fetch templates from database with fallback to hardcoded templates
    async with AsyncSessionLocal() as db:
        template_apt_found = await message_template_crud.get_template_body(
            db, "apt_status_req_found", default=TEMPLATE_APPOINTMENT_FOUND_DETAILED
        )
        template_not_found = await message_template_crud.get_template_body(
            db, "apt_status_req_not_found", default=TEMPLATE_APPOINTMENT_NOT_FOUND_FOR_ID
        )
        template_db_error = await message_template_crud.get_template_body(
            db, "apt_status_req_db_error", default=TEMPLATE_DB_ERROR
        )

    # logger.info(f"Generating reply for scenario: {scenario} with data: {data}")
    if scenario == "appointments_found" and data.get("studies"):
        studies = data.get("studies", [])

        # Generate appointment table HTML using dedicated function
        table_html = _generate_appointment_table_html(studies)

        # Get template configuration (standard: unified template only)
        unified_template = data.get("unified_template")
        if not unified_template:
            logger.error(f"❌ CRITICAL: No unified_template configured in database for 'Apt status req'. Template must be configured in /settings/template-config")
            raise ValueError("Missing unified_template in database settings. Please configure template in /settings/template-config")

        personal_injury_template = data.get("custom_placeholders", {}).get(
            "personal_injury_info",
            "Important Information regarding personal injury cases<br/>A report containing the findings of the exam will also be sent to the attorney.<br/>A bill will be sent to the attorney once both the patient and the attorney sign all pending liens.<br/>Please make sure to submit a negotiation offer before sending the payment.<br/><br/>"
        )

        # Prepare personal injury info (conditionally included)
        personal_injury_info_text = ""
        if data.get("is_personal_injury_case"):
            personal_injury_info_text = personal_injury_template

        # Generate call log table
        from app.helpers.call_log_table import generate_call_log_table
        patient_id = data.get("patient_id_confirmed", "N/A")
        call_log_table = ""
        if patient_id != "N/A":
            call_log_table = await generate_call_log_table(patient_id)

        # Prepare all placeholder variables for logging and formatting
        first_name = data.get("first_name", "N/A")
        last_name = data.get("last_name", "N/A")
        patient_name = f"{first_name} {last_name}"

        placeholder_values = {
            "patient_id_confirmed": patient_id,
            "patient_id": patient_id,  # Add patient_id alias
            "patient_name": patient_name,  # Add patient_name for templates
            "scheduling_phone": data.get("scheduling_phone", DEFAULT_SCHEDULING_PHONE),
            "no_show_policy": data.get("no_show_policy", DEFAULT_NO_SHOW_POLICY),
            "first_name": first_name,
            "last_name": last_name,
            "dob": data.get("dob", "N/A"),
            "doi": data.get("doi", "N/A"),  # Add DOI for templates
            "address": data.get("address", "N/A"),
            "home_phone": data.get("home_phone", "N/A"),
            "cell_phone": data.get("cell_phone", "N/A"),
            "personal_injury_info": personal_injury_info_text,
            "bills_link": data.get("links", {}).get("bills_appointments_liens", "#"),
            "reports_link": data.get("links", {}).get("reports_images", "#"),
            "appointment_table": table_html,  # NEW: Add table to placeholders
            "is_personal_injury_case": data.get("is_personal_injury_case", False),
            "call_log_table": call_log_table
        }

        # Add all custom placeholders to placeholder_values
        custom_placeholders = data.get("custom_placeholders", {})
        if custom_placeholders:
            placeholder_values.update(custom_placeholders)

        # Log all placeholder values for debugging
        logger.info(f"📝 Template placeholder values for {placeholder_values['patient_id_confirmed']}:")
        logger.info(f"   Patient Info: {placeholder_values['first_name']} {placeholder_values['last_name']}, DOB: {placeholder_values['dob']}")
        logger.info(f"   Address: {placeholder_values['address']}")
        logger.info(f"   Phones: Home={placeholder_values['home_phone']}, Cell={placeholder_values['cell_phone']}")
        logger.info(f"   System: Scheduling Phone={placeholder_values['scheduling_phone']}")
        logger.info(f"   Links: Bills={placeholder_values['bills_link']}, Reports={placeholder_values['reports_link']}")
        logger.info(f"   Personal Injury Case: {placeholder_values['is_personal_injury_case']}")
        logger.info(f"   Using UNIFIED template format (standard approach)")

        # STANDARD APPROACH: Use unified template with all placeholders (custom + type-specific)
        logger.info("Formatting unified template with placeholders")
        formatted_template = unified_template.format(**placeholder_values)

        # logger.info(f"DEBUG: Generated HTML response: {formatted_template}")
        return formatted_template
    elif scenario == "id_missing_first_attempt":
        return TEMPLATE_REQUEST_PATIENT_ID
    elif scenario == "id_missing_second_attempt":
        return TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE
    elif scenario == "id_not_found_in_system":
        return template_not_found.format(patient_id=data.get("patient_id", "N/A"))
    elif scenario == "db_error":
        return template_db_error.format(patient_id=data.get("patient_id", "N/A"))
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

    # Fetch settings from database (with fallback to defaults)
    db_settings = await get_tag_settings_from_db("Apt status req")
    scheduling_phone = db_settings["scheduling_phone"]
    no_show_policy = db_settings["no_show_policy"]
    portal_links = db_settings["portal_links"]

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
        patient_demographics = {}

        if patient_result.get("patients") and len(patient_result["patients"]) > 0:
            patient_data = patient_result["patients"][0]
            financial_type = patient_data.get("financial_type", "").lower()
            if "pi" in financial_type or "lien" in financial_type or "personal injury" in financial_type:
                is_personal_injury_case = True

            # Extract patient demographics for template use
            patient_demographics = {
                "first_name": patient_data.get("first_name", "N/A"),
                "last_name": patient_data.get("last_name", "N/A"),
                "dob": patient_data.get("birth_date", "N/A"),
                "doi": patient_data.get("doi", "N/A"),  # Add DOI field
                "address": patient_data.get("address", "N/A"),
                "home_phone": patient_data.get("phone", "N/A"),
                "cell_phone": patient_data.get("phone", "N/A"),  # API may not distinguish
            }
            logger.info(f"Extracted patient demographics for {patient_id}: {patient_demographics.get('first_name')} {patient_demographics.get('last_name')}")
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
        for i, study in enumerate(raw_studies):
            appointment_datetime_str = "N/A"
            arrival_time_str = "N/A"
            
            service_appt_time_str = study.get("study_date_time", "")
            study_id_for_date_log = study.get("authorization_number", "Unknown")
            study_status = study.get("ordered_status", "N/A")
            study_image_count = study.get("image_count", 0)
            
            parsed_dt = None
            if service_appt_time_str:
                try:
                    # Try parsing as ISO datetime first
                    if "T" in service_appt_time_str:
                        parsed_dt = datetime.fromisoformat(service_appt_time_str.replace("Z", ""))
                    else:
                        try:
                            parsed_dt = datetime.strptime(service_appt_time_str, "%m/%d/%Y %I:%M:%S %p")
                        except ValueError as e1:
                            try:
                                parsed_time_obj = datetime.strptime(service_appt_time_str, "%I:%M %p").time()
                                appointment_datetime_str = f"Date N/A @ {parsed_time_obj.strftime('%I:%M %p')}"
                            except ValueError as e2:
                                # Try additional common formats
                                additional_formats = [
                                    "%d %B %Y %I:%M %p",  # 17 April 2018 01:23 PM
                                    "%d %B %Y",           # 17 April 2018 (date only)
                                    "%Y-%m-%d %H:%M:%S",  # 2024-01-15 14:30:00
                                    "%m/%d/%Y %H:%M",     # 01/15/2024 14:30
                                    "%m/%d/%Y",           # 01/15/2024
                                    "%Y-%m-%d",           # 2024-01-15
                                    "%m/%d/%y %I:%M %p",  # 01/15/24 2:30 PM
                                    "%Y-%m-%d %I:%M %p",  # 2024-01-15 2:30 PM
                                    "%B %d, %Y",          # November 23, 2019
                                    "%d-%b-%Y",           # 23-Nov-2019
                                    "%b %d, %Y",          # Nov 23, 2019
                                    "%Y-%B-%d",           # 2019-November-23
                                ]
                                
                                for fmt in additional_formats:
                                    try:
                                        parsed_dt = datetime.strptime(service_appt_time_str, fmt)
                                        break
                                    except ValueError as ef:
                                        continue
                                
                                if not parsed_dt:
                                    appointment_datetime_str = f"{service_appt_time_str} (Could not parse fully)"
                                    logger.warning(f"Could not parse study_date_time '{service_appt_time_str}' for study {study.get('authorization_number')} - all parsing attempts failed")

                    if parsed_dt:
                        # Check if we parsed a date-only value (time is 00:00:00)
                        if parsed_dt.time() == datetime.min.time():
                            # This is a date-only value, show as date with "Time TBD"
                            day_name = parsed_dt.strftime('%A')
                            month_name = parsed_dt.strftime('%B')
                            day_num = parsed_dt.day
                            year = parsed_dt.year
                            day_suffix = get_day_suffix(day_num)
                            appointment_datetime_str = f"{day_name} {month_name} {day_num}{day_suffix}, {year}<br/><br/>N/A"
                            arrival_time_str = "N/A"
                        else:
                            # This has both date and time - format as requested
                            day_name = parsed_dt.strftime('%A')
                            month_name = parsed_dt.strftime('%B')
                            day_num = parsed_dt.day
                            year = parsed_dt.year
                            day_suffix = get_day_suffix(day_num)
                            time_str = parsed_dt.strftime('%I:%M %p').lstrip('0')  # Remove leading zero from hour

                            appointment_datetime_str = f"{day_name} {month_name} {day_num}{day_suffix}, {year}<br/><br/>{time_str}"

                            pre_arrival_min = study.get("pre_arrival_minutes", 30)
                            arrival_dt = parsed_dt - timedelta(minutes=pre_arrival_min)
                            arrival_time_str = arrival_dt.strftime('%I:%M %p').lstrip('0')  # Remove leading zero
                        
                except ValueError as e_date:
                    logger.warning(f"Could not parse study_date_time '{service_appt_time_str}' for study {study.get('authorization_number')}: {e_date}")
                    appointment_datetime_str = f"{service_appt_time_str} (Unparseable)"
            
            facility_info = study.get("facility", {})
            facility_name = facility_info.get('facility_name', '').strip()
            facility_address = facility_info.get('address', '').strip()

            # Show only facility address (not facility name)
            if not facility_address or facility_address in ['N/A', 'Not Available', 'Not Available in Database']:
                location_display = "N/A"
            else:
                location_display = facility_address

            # Note: study_date_time is now used for the main Study Date/Time column (appointment_datetime_str)

            image_count = study.get("image_count", 0)
            images_available = "Yes" if image_count > 0 else "No"
            
            # Parse resources field for MRI type
            resources = study.get("resources", "")
            mri_type = "N/A"
            if resources:
                resources_upper = resources.upper()
                if "STAND" in resources_upper:
                    mri_type = "Stand Up"
                elif "OPEN" in resources_upper:
                    mri_type = "Open"
                elif "CLOSED" in resources_upper:
                    mri_type = "Closed"
            
            transformed_study = {
                "study_id": study.get("authorization_number", "N/A"),
                "exam_description": study.get("study_description", "N/A"),
                "status": study.get("ordered_status", "N/A"),
                "appointment_datetime_str": appointment_datetime_str,
                "arrival_time_str": arrival_time_str,
                "location_name": location_display,
                "mri_type": mri_type,
                "images_available": images_available,
                "report_available": "No"   # Default, not in service output
            }
            
            transformed_studies_for_template.append(transformed_study)

        if not transformed_studies_for_template:
            return {"status": "not_found", "message": f"Patient ID {patient_id} found, studies retrieved, but failed to transform any for display.", "patient_id": patient_id}

        # Log summary of study_date_time processing
        studies_with_date_time = sum(1 for study in transformed_studies_for_template if study.get('appointment_datetime_str') != 'N/A')
        studies_without_date_time = len(transformed_studies_for_template) - studies_with_date_time
        logger.info(f"Patient {patient_id}: {studies_with_date_time} studies have valid study_date_time, {studies_without_date_time} do not")

        return {
            "status": "success",
            "data": {
                "patient_id_confirmed": patient_id,
                "studies": transformed_studies_for_template,
                "is_personal_injury_case": is_personal_injury_case,
                "scheduling_phone": scheduling_phone,
                "no_show_policy": no_show_policy,
                "links": portal_links,
                # Unified template (standard approach)
                "unified_template": db_settings.get("unified_template"),  # No default - must be in DB
                # Custom placeholders (workspace-wide)
                "custom_placeholders": db_settings.get("custom_placeholders", {}),
                # Patient demographics for template placeholders
                "first_name": patient_demographics.get("first_name", "N/A"),
                "last_name": patient_demographics.get("last_name", "N/A"),
                "dob": patient_demographics.get("dob", "N/A"),
                "doi": patient_demographics.get("doi", "N/A"),  # Add DOI for templates
                "address": patient_demographics.get("address", "N/A"),
                "home_phone": patient_demographics.get("home_phone", "N/A"),
                "cell_phone": patient_demographics.get("cell_phone", "N/A")
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

    reply_text = await _generate_response_from_template(scenario, data_for_template)
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
    email_sender: str,  # Email sender for authorization verification
    settings_obj: Any = app_settings_instance,
    email_subject: str = None,  # Add email_subject parameter
    extracted_patient_ids: List[str] = None  # Add pre-extracted patient IDs parameter (list)
) -> Dict[str, Any]:
    """
    Handles an "Apt Status Req" using the openai-agents SDK with MCP server integration.
    Supports multiple patient IDs - will send separate responses for each patient.
    Returns a dictionary with agent processing results.
    """
    # Convert None to empty list for easier handling
    if extracted_patient_ids is None:
        extracted_patient_ids = []

    logger.info(f"Initiating openai-agents SDK flow with MCP integration for Apt Status Req - Conv ID: {front_conversation_id}")
    logger.info(f"🔍 MULTI-PATIENT: Processing {len(extracted_patient_ids)} patient ID(s): {extracted_patient_ids}")
    # logger.info(f"🔍 DEBUG APT_STATUS: email_subject parameter = '{email_subject}' (type: {type(email_subject)})")

    # If multiple patient IDs, process each one separately
    if len(extracted_patient_ids) > 1:
        logger.info(f"🔄 MULTI-PATIENT MODE: Processing {len(extracted_patient_ids)} patients separately")
        all_results = []

        for idx, patient_id in enumerate(extracted_patient_ids):
            logger.info(f"🔄 Processing patient {idx + 1}/{len(extracted_patient_ids)}: {patient_id}")

            # Call this same function recursively with single patient ID
            result = await handle_apt_status_request_agent_sdk(
                front_conversation_id=front_conversation_id,
                current_email_content=current_email_content,
                structured_history_messages=structured_history_messages,
                email_sender=email_sender,
                settings_obj=settings_obj,
                email_subject=email_subject,
                extracted_patient_ids=[patient_id]  # Single patient ID in list
            )
            all_results.append(result)

        # Return combined results
        all_handled = all(r.get("agent_handled", False) for r in all_results)
        all_processed = all(r.get("processed_flag", False) for r in all_results)

        # Archive the conversation after all patient responses have been sent
        if all_handled and all_processed:
            logger.info(f"📦 ARCHIVING: All {len(extracted_patient_ids)} patient responses sent successfully, archiving conversation")
            archive_success = frontapp_service.archive_conversation_in_front(front_conversation_id)
            if archive_success:
                logger.info(f"✅ ARCHIVED: Conversation {front_conversation_id} archived successfully after multi-patient responses")
            else:
                logger.warning(f"⚠️ ARCHIVE FAILED: Could not archive conversation {front_conversation_id} after multi-patient responses")

        logger.info(f"✅ MULTI-PATIENT COMPLETE: Processed {len(extracted_patient_ids)} patients")
        return {
            "agent_handled": all_handled,
            "processed_flag": all_processed,
            "details": {
                "reason": f"Processed {len(extracted_patient_ids)} patients",
                "patient_results": all_results,
                "patient_ids": extracted_patient_ids,
                "conversation_archived": all_handled and all_processed
            }
        }

    # From here on, we're processing a single patient ID (or no patient ID)
    extracted_patient_id = extracted_patient_ids[0] if extracted_patient_ids else None

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

    # --- BEGIN: SENDER VERIFICATION ---
    # Check if sender verification is enabled in settings
    sender_verification_enabled = True  # Default to enabled for security

    async with AsyncSessionLocal() as db:
        workspace_settings = await tag_settings_crud.get_settings_dict(db, "WORKSPACE")
        sender_verification_enabled = workspace_settings.get("enable_sender_verification", True)

    logger.info(f"🔐 SENDER VERIFICATION: Enabled = {sender_verification_enabled}")

    # Perform sender verification if we have a patient ID and verification is enabled
    if extracted_patient_id and sender_verification_enabled:
        logger.info(f"🔐 SENDER VERIFICATION: Checking authorization for {email_sender} to access patient {extracted_patient_id}")

        # Verify sender authorization
        verification_result = await verify_sender_for_patient_access(
            patient_id=extracted_patient_id,
            sender_email=email_sender
        )

        logger.info(f"🔐 VERIFICATION RESULT: {verification_result['message']}")
        logger.info(f"   - Authorized: {verification_result['authorized']}")
        logger.info(f"   - Role: {verification_result['role']}")
        logger.info(f"   - Status: {verification_result['verification_status']}")

        # Handle unauthorized senders
        if not verification_result["authorized"]:
            logger.warning(f"⚠️ UNAUTHORIZED ACCESS ATTEMPT:")
            logger.warning(f"   - Sender: {email_sender}")
            logger.warning(f"   - Patient: {extracted_patient_id}")
            logger.warning(f"   - Role detected: {verification_result['role']}")

            # Send HIPAA form for unauthorized access
            TEMPLATE_HIPAA_NEEDED = """Hello,

To proceed with your request for patient information, we require authorization. Please complete the attached HIPAA release form and reply to this email with the completed document.

Thank you for your cooperation."""

            hipaa_form_path = "/home/fret/work/emailtag/app/agents/templates/Medical-Release-Form.pdf"

            result = await send_reply_to_front_with_attachment(
                front_conversation_id,
                TEMPLATE_HIPAA_NEEDED,
                hipaa_form_path,
                tags_to_add=["AI handled", TAG_AI_HUMAN_REVIEW_REQUIRED]
            )

            if result.get("status") == "success":
                logger.info(f"✅ Sent HIPAA form to unauthorized sender and tagged for review")
                return {
                    "agent_handled": True,
                    "processed_flag": True,
                    "details": {
                        "action": "sender_not_authorized_hipaa_sent",
                        "sender": email_sender,
                        "patient_id": extracted_patient_id,
                        "role": verification_result["role"],
                        "verification_status": verification_result["verification_status"],
                        "reason": "Sender not authorized - HIPAA form sent"
                    }
                }
            else:
                logger.error(f"Failed to send HIPAA form with attachment: {result}")
                # Fallback to simple unauthorized message
                TEMPLATE_UNAUTHORIZED = """Hello,

We're unable to automatically provide patient information as you are not currently listed as an authorized party for this patient's case.

A team member will review your request and contact you shortly.

Thank you."""

                await send_reply_to_front_direct(
                    conversation_id=front_conversation_id,
                    reply_text=TEMPLATE_UNAUTHORIZED
                )

                frontapp_service.add_conversation_tags(
                    front_conversation_id,
                    [TAG_AI_HUMAN_REVIEW_REQUIRED]
                )

                return {
                    "agent_handled": True,
                    "processed_flag": True,
                    "details": {
                        "action": "sender_not_authorized_escalated",
                        "sender": email_sender,
                        "patient_id": extracted_patient_id,
                        "role": verification_result["role"],
                        "reason": "Sender not authorized - escalated to human review"
                    }
                }

        # Sender is authorized - log and proceed
        logger.info(f"✅ SENDER AUTHORIZED:")
        logger.info(f"   - Sender: {email_sender}")
        logger.info(f"   - Role: {verification_result['role']}")
        logger.info(f"   - Patient: {extracted_patient_id}")
        logger.info(f"   - Proceeding with appointment status request")

    elif extracted_patient_id and not sender_verification_enabled:
        logger.info(f"ℹ️ SENDER VERIFICATION DISABLED: Skipping verification for {email_sender} (testing mode)")

    else:
        logger.info(f"ℹ️ SENDER VERIFICATION SKIPPED: No patient ID available yet (will verify in follow-up)")

    # --- END: SENDER VERIFICATION ---

    formatted_history = format_conversation_history_for_agent(structured_history_messages)
    # logger.info(f"Formatted conversation history: {formatted_history}")
    
    # Combine history and current email for a complete context for extraction
    full_conversation_text = f"Conversation History:\n{formatted_history}\n\nLatest User Email:\n{current_email_content}"

    instructions = f"""
You are an AI assistant for a medical imaging company, specializing in appointment status requests.

**IMPORTANT**: Patient ID extraction has already been performed before you were called. If no patient ID was found, a deterministic "ask for patient details" response would have been sent automatically.

**PRE-EXTRACTED PATIENT ID**: {extracted_patient_id if extracted_patient_id else "None - this is a follow-up case"}

Your primary goal is to:
1. If a patient ID was provided above, use it to fetch appointment details using `fetch_appointment_details_by_patient_id`. Also pass the `settings_obj` to this tool.
2. If no patient ID was provided, this is a follow-up case where we've already asked for patient details but haven't received a valid response.
3. Based on the outcome, determine the correct scenario.
4. Call the `generate_formatted_reply` tool, passing it the determined scenario and the FULL result from `fetch_appointment_details_by_patient_id` (if available).
5. Take the `reply_text` from `generate_formatted_reply`'s output.
6. Call `send_reply_to_front` with this `reply_text` and add tags ONLY IF the scenario requires escalation to a human.

Conversation ID (use for tool calls): {front_conversation_id}
Email Subject: "{email_subject or 'No subject'}"

**Entire Conversation For Extraction:**
---
{full_conversation_text}
---

**Scenarios & Tool Usage Flow:**

A.  **If a PRE-EXTRACTED PATIENT ID was provided above:**
    1.  Call `fetch_appointment_details_by_patient_id` with the provided patient ID and `settings_obj=settings_obj` (pass through from orchestrator). Let the result be `fetch_result`.
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

B.  **If no PRE-EXTRACTED PATIENT ID was provided:**
    *   This means we've already asked for patient details previously and the user has not provided a valid patient ID.
    *   Scenario for `generate_formatted_reply`: "id_missing_second_attempt"
    *   Call `generate_formatted_reply` with `scenario="id_missing_second_attempt"`, `fetch_details_result={{}}`, `extracted_patient_id=None`.
    *   Take `reply_text` from its output.
    *   Call `send_reply_to_front` with this `reply_text` and `tags_to_add=["{TAG_AI_HUMAN_REVIEW_REQUIRED}"]`.

**IMPORTANT TOOL USAGE:**
- Use the PRE-EXTRACTED PATIENT ID provided above, do NOT attempt to extract patient IDs from the conversation text.

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
