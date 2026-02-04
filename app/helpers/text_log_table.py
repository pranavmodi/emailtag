"""
Helper function to generate text log table for patient autorespond templates.

This module provides functionality to fetch and format patient text message history
into an HTML table for use in email templates.

API Details (see docs/RADFLOW_API.md):
- Endpoint: POST https://staging-app.radflow360.com/chatbotapi/Patient/textlog?patientId={patientId}
- Auth: Basic auth (RADFLOW_CONTACT_VERIFY_AUTH env var)
- Headers: Content-Length: 0
"""

import logging
import httpx
from typing import List, Dict, Any
from datetime import datetime
from app.core.config import settings as app_settings_instance

logger = logging.getLogger(__name__)


def _get_no_text_activity_message() -> str:
    """Generate the 'no text activity' message with current timestamp."""
    current_time = datetime.now().strftime("%-m/%-d/%Y %-I:%M %p")
    return f'<p style="background-color: #ffeb3b; padding: 10px; border-radius: 5px;"><em>No text message activity found for patient as of {current_time}</em></p>'


async def generate_text_log_table(patient_id: str) -> str:
    """
    Generate HTML table showing text message history for a patient.

    Fetches text message history from RadFlow API and formats it as an HTML table with:
    - Date/Time
    - Text Type

    Args:
        patient_id: Patient ID to fetch text history for

    Returns:
        HTML table string with text history, or empty message if no texts found
    """
    if not patient_id or patient_id == "N/A":
        logger.debug("No valid patient ID provided for text log table")
        return _get_no_text_activity_message()

    try:
        logger.info(f"Generating text log table for patient {patient_id}")

        # Get auth from settings (same auth used for contactVerifyEmail)
        auth_header = app_settings_instance.RADFLOW_CONTACT_VERIFY_AUTH
        if not auth_header:
            logger.warning("RADFLOW_CONTACT_VERIFY_AUTH not configured, skipping text log")
            return _get_no_text_activity_message()

        # Build the API URL
        # Use staging URL base from the contact verify URL or default to staging
        base_url = "https://staging-app.radflow360.com/chatbotapi/Patient/textlog"
        url = f"{base_url}?patientId={patient_id}"

        # Make the API call
        # RadFlow API requires: POST method, Content-Length: 0, Basic auth
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            headers = {
                "accept": "*/*",
                "Authorization": auth_header,
                "Content-Length": "0"
            }
            response = await client.post(url, headers=headers, content="")

            if response.status_code != 200:
                logger.warning(f"RadFlow textlog API returned status {response.status_code} for patient {patient_id}")
                return _get_no_text_activity_message()

            data = response.json()

        # Check response status
        if not data.get("status") == 1 or data.get("responseStatus") != "Success":
            logger.warning(f"RadFlow textlog API unsuccessful for patient {patient_id}: {data}")
            return _get_no_text_activity_message()

        texts = data.get("result", [])

        if not texts or len(texts) == 0:
            logger.info(f"No text messages found for patient {patient_id}")
            return _get_no_text_activity_message()

        logger.info(f"Found {len(texts)} text message(s) for patient {patient_id}")

        # Generate HTML table
        table_html = _format_texts_as_html_table(texts)

        logger.info(f"Generated text log table with {len(texts)} row(s)")
        return table_html

    except Exception as e:
        logger.error(f"Error generating text log table for patient {patient_id}: {e}", exc_info=True)
        return '<p style="background-color: #ffeb3b; padding: 10px; border-radius: 5px;"><em>No recent text message history available for this patient.</em></p>'


def _format_text_type(text_type: str) -> str:
    """
    Format text type for display with human-readable labels.

    Args:
        text_type: Raw text type from API (e.g., "PatSchedRemind", "Automation")

    Returns:
        Human-readable text type
    """
    type_mapping = {
        "PatSchedRemind": "Appointment Reminder",
        "Automation": "Automated Message",
        "Manual": "Manual Message",
        "Confirmation": "Confirmation",
        "Reminder": "Reminder",
    }
    return type_mapping.get(text_type, text_type or "Unknown")


def _format_texts_as_html_table(texts: List[Dict[str, Any]]) -> str:
    """
    Format text log data as HTML table.

    Args:
        texts: List of text dictionaries with keys: patientId, dateSent, textType

    Returns:
        HTML table string
    """
    # Start table with styling
    html = """
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; font-size: 14px;">
        <thead>
            <tr style="background-color: #f2f2f2;">
                <th style="text-align: left; padding: 10px; border: 1px solid #ddd;">Date/Time</th>
                <th style="text-align: left; padding: 10px; border: 1px solid #ddd;">Message Type</th>
            </tr>
        </thead>
        <tbody>
"""

    # Sort by date descending (most recent first)
    sorted_texts = sorted(
        texts,
        key=lambda x: x.get("dateSent", ""),
        reverse=True
    )

    # Add rows for each text
    for text in sorted_texts:
        # Parse and format date/time
        date_sent = text.get("dateSent", "")
        formatted_datetime = "N/A"

        if date_sent:
            try:
                # Parse ISO format datetime
                dt = datetime.fromisoformat(date_sent.replace("Z", "+00:00"))
                formatted_datetime = dt.strftime("%m/%d/%Y %I:%M %p")
            except (ValueError, AttributeError):
                formatted_datetime = date_sent

        # Format text type
        text_type = _format_text_type(text.get("textType", ""))

        html += f"""
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;">{formatted_datetime}</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{text_type}</td>
            </tr>
"""

    # Close table
    html += """
        </tbody>
    </table>
"""

    return html
