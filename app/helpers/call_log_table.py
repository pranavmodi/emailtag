"""
Helper function to generate call log table for patient autorespond templates.

This module provides functionality to fetch and format patient call history
into an HTML table for use in email templates.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime
from app.agents.agent_helpers import call_mcp_tool

logger = logging.getLogger(__name__)


async def generate_call_log_table(patient_id: str, phone_number: str = None) -> str:
    """
    Generate HTML table showing call history for a patient.

    Fetches call history from RadFlow API and formats it as an HTML table with:
    - Date/Time
    - Phone Number
    - Inbound/Outbound
    - Disposition

    Args:
        patient_id: Patient ID to fetch call history for
        phone_number: Optional phone number to filter calls (if not provided, uses patient's phone)

    Returns:
        HTML table string with call history, or empty string if no calls found
    """
    try:
        logger.info(f"📞 Generating call log table for patient {patient_id}")

        # Fetch call history from RadFlow API via MCP tool
        call_log_response = await call_mcp_tool(
            tool_name="get_patient_call_log",
            arguments={"patient_id": patient_id}
        )

        if not call_log_response or not isinstance(call_log_response, dict):
            logger.warning(f"📞 No valid call log response for patient {patient_id}")
            return '<p style="background-color: #ffeb3b; padding: 10px; border-radius: 5px;"><em>No recent call history available for this patient.</em></p>'

        # Extract call log data
        call_log_data = call_log_response.get("content", [])

        if isinstance(call_log_data, list) and len(call_log_data) > 0:
            # Parse the first content item which should contain the call log
            if isinstance(call_log_data[0], dict) and "text" in call_log_data[0]:
                import json
                try:
                    call_log_json = json.loads(call_log_data[0]["text"])
                    calls = call_log_json.get("calls", [])
                except json.JSONDecodeError:
                    logger.error(f"📞 Failed to parse call log JSON for patient {patient_id}")
                    return '<p style="background-color: #ffeb3b; padding: 10px; border-radius: 5px;"><em>No recent call history available for this patient.</em></p>'
            else:
                calls = call_log_data
        else:
            logger.info(f"📞 No call history found for patient {patient_id}")
            return "<p><em>No recent call history available for this patient.</em></p>"

        if not calls or len(calls) == 0:
            logger.info(f"📞 No calls in call log for patient {patient_id}")
            return "<p><em>No recent call history available for this patient.</em></p>"

        logger.info(f"📞 Found {len(calls)} call(s) for patient {patient_id}")

        # Filter by phone number if provided
        if phone_number:
            calls = [call for call in calls if call.get("phone_number") == phone_number]
            logger.info(f"📞 Filtered to {len(calls)} call(s) for phone {phone_number}")

        if not calls:
            return "<p><em>No recent call history available for this patient.</em></p>"

        # Generate HTML table
        table_html = _format_calls_as_html_table(calls)

        logger.info(f"✅ Generated call log table with {len(calls)} row(s)")
        return table_html

    except Exception as e:
        logger.error(f"Error generating call log table for patient {patient_id}: {e}", exc_info=True)
        return "<p><em>No recent call history available for this patient.</em></p>"


def _format_calls_as_html_table(calls: List[Dict[str, Any]]) -> str:
    """
    Format call log data as HTML table.

    Args:
        calls: List of call dictionaries with keys: date_time, phone_number, direction, disposition

    Returns:
        HTML table string
    """
    # Start table with styling
    html = """
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; font-size: 14px;">
        <thead>
            <tr style="background-color: #f2f2f2;">
                <th style="text-align: left; padding: 10px; border: 1px solid #ddd;">Date/Time</th>
                <th style="text-align: left; padding: 10px; border: 1px solid #ddd;">Phone #</th>
                <th style="text-align: center; padding: 10px; border: 1px solid #ddd;">Direction</th>
                <th style="text-align: left; padding: 10px; border: 1px solid #ddd;">Disposition</th>
            </tr>
        </thead>
        <tbody>
"""

    # Add rows for each call
    for call in calls:
        # Parse and format date/time
        date_time_str = call.get("date_time", call.get("datetime", "N/A"))
        try:
            # Try to parse and format the datetime
            if date_time_str != "N/A":
                dt = datetime.fromisoformat(date_time_str.replace("Z", "+00:00"))
                formatted_datetime = dt.strftime("%m/%d/%Y %I:%M %p")
            else:
                formatted_datetime = date_time_str
        except (ValueError, AttributeError):
            formatted_datetime = date_time_str

        phone_number = call.get("phone_number", call.get("phone", "N/A"))
        direction = call.get("direction", "N/A")
        disposition = call.get("disposition", call.get("status", "N/A"))

        # Determine direction display and icon
        if direction.lower() == "inbound":
            direction_display = "⬅️ Inbound"
            direction_color = "#4CAF50"  # Green
        elif direction.lower() == "outbound":
            direction_display = "➡️ Outbound"
            direction_color = "#2196F3"  # Blue
        else:
            direction_display = direction
            direction_color = "#666"  # Gray

        html += f"""
            <tr>
                <td style="padding: 8px; border: 1px solid #ddd;">{formatted_datetime}</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{phone_number}</td>
                <td style="padding: 8px; border: 1px solid #ddd; text-align: center; color: {direction_color}; font-weight: bold;">{direction_display}</td>
                <td style="padding: 8px; border: 1px solid #ddd;">{disposition}</td>
            </tr>
"""

    # Close table
    html += """
        </tbody>
    </table>
"""

    return html
