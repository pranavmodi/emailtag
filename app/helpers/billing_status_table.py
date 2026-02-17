"""
Helper function to generate billing status table for patient autorespond templates.

This module provides functionality to fetch and merge data from two APIs
(fetch_study_details and get_patient_lien_bill_balance) into a unified
6-column HTML billing status table for use in email templates.

Columns: Exam Description | Study Date | Exam Status | Images Available | Report Available | Billing Status
"""

import json
import logging
import re
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.agents.agent_helpers import call_mcp_tool

logger = logging.getLogger(__name__)


def _normalize_study_key(description: str, date_str: str) -> str:
    """
    Create a normalized lookup key from study description and date portion.
    Used to match studies between fetch_study_details and billing data.
    """
    desc = re.sub(r'\s+', ' ', (description or '').strip().upper())
    # Use _format_date to normalize date to MM/DD/YYYY regardless of input format
    date_part = _format_date(date_str)
    return f"{desc}|{date_part}"


def _format_date(date_str: str) -> str:
    """Format a date string to MM/DD/YYYY."""
    if not date_str:
        return 'N/A'
    date_str_stripped = date_str.strip()
    # Try full datetime formats first (before splitting)
    for fmt in ('%d %B %Y %I:%M %p', '%d %B %Y', '%m/%d/%Y %H:%M:%S', '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(date_str_stripped, fmt).strftime('%m/%d/%Y')
        except ValueError:
            continue
    # Fallback: extract date portion and try simpler formats
    date_part = date_str_stripped.split(' ')[0].split('T')[0]
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y'):
        try:
            return datetime.strptime(date_part, fmt).strftime('%m/%d/%Y')
        except ValueError:
            continue
    return date_part


def _get_billing_status_text(
    ordered_status: str,
    billing_status_raw: str,
    billing_amount: Any,
    study_date: str
) -> str:
    """
    Determine billing status text using 3-way logic:
    1. Cancelled → "Cancelled Study"
    2. Billed with amount > 0 → "$X.XX - Billed on MM/DD/YYYY"
    3. Not cancelled, amount > 0 → "Potential to be billed is $X.XX"
    4. Else → "N/A"
    """
    # Check for cancelled status
    if ordered_status and 'cancel' in ordered_status.lower():
        return "Cancelled Study"

    # Ensure billing_amount is numeric
    try:
        amount = float(billing_amount) if billing_amount is not None else 0
    except (ValueError, TypeError):
        amount = 0

    if amount > 0:
        amount_str = f"${amount:,.2f}"
        if billing_status_raw and 'BILLED' in billing_status_raw.upper():
            if study_date and study_date != 'N/A':
                return f"{amount_str} - Billed on {study_date}"
            return f"{amount_str} - Billed"
        return f"Potential to be billed is {amount_str}"

    if billing_status_raw:
        return billing_status_raw

    return "N/A"


def _build_html_table(rows: List[Dict[str, str]]) -> str:
    """Build an HTML table from row data."""
    html_parts = []
    html_parts.append('<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-family: Arial, sans-serif; margin: 10px 0; width: 100%;">')
    html_parts.append('<thead>')
    html_parts.append('<tr style="background-color: #f0f0f0; font-weight: bold;">')
    for header in ['Exam Description', 'Study Date', 'Exam Status', 'Images Available', 'Report Available', 'Billing Status']:
        html_parts.append(f'<th style="text-align: left; padding: 8px; border: 1px solid #ccc;">{header}</th>')
    html_parts.append('</tr>')
    html_parts.append('</thead>')
    html_parts.append('<tbody>')

    for row in rows:
        html_parts.append('<tr>')
        for col in ['exam_description', 'study_date', 'exam_status', 'images_available', 'report_available', 'billing_status']:
            html_parts.append(f'<td style="padding: 8px; border: 1px solid #ccc;">{row.get(col, "N/A")}</td>')
        html_parts.append('</tr>')

    html_parts.append('</tbody>')
    html_parts.append('</table>')
    return ''.join(html_parts)


def _get_error_message() -> str:
    """Return a styled fallback message when billing status table cannot be generated."""
    current_time = datetime.now().strftime("%-m/%-d/%Y %-I:%M %p")
    return (
        f'<p style="background-color: #ffeb3b; padding: 10px; border-radius: 5px;">'
        f'<em>Billing status information is currently unavailable as of {current_time}</em></p>'
    )


async def generate_billing_status_table(
    patient_id: str,
    bill_balance_data: Optional[Dict] = None
) -> str:
    """
    Generate an HTML table showing billing status per study.

    Merges data from two APIs:
    - fetch_study_details → study_description, study_date_time, ordered_status, image_count
    - get_patient_lien_bill_balance → billingStatus, billingAmount, patientBillBalance

    Args:
        patient_id: Patient ID to fetch billing data for.
        bill_balance_data: Pre-fetched bill balance data (to avoid redundant API call).
            If None, will call get_patient_lien_bill_balance internally.

    Returns:
        HTML string with billing summary header and 6-column table,
        or a styled fallback message on error.
    """
    try:
        logger.info(f"Generating billing status table for patient {patient_id}")

        # --- Fetch study details ---
        study_response = await call_mcp_tool(
            tool_name="fetch_study_details",
            arguments={"patient_id": patient_id}
        )

        studies = []
        if study_response and isinstance(study_response, dict) and study_response.get("success"):
            studies = study_response.get("studies", [])

        # --- Fetch or use pre-fetched bill balance data ---
        if bill_balance_data is None:
            bill_balance_data = await call_mcp_tool(
                tool_name="get_patient_lien_bill_balance",
                arguments={"patient_id": patient_id}
            )

        # Extract billing details from bill_balance_data
        bill_balance = 0
        billing_studies = []
        if bill_balance_data and isinstance(bill_balance_data, dict):
            # Navigate the nested response structure
            data_section = bill_balance_data.get('data', {})
            if isinstance(data_section, dict):
                result = data_section.get('result', {})
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except Exception:
                        result = {}
                if isinstance(result, dict):
                    bill_balance = result.get('patientBillBalance', 0) or 0
                    billing_studies = result.get('patientStudyDetails', []) or []
            else:
                # Try top-level result
                result = bill_balance_data.get('result', {})
                if isinstance(result, str):
                    try:
                        result = json.loads(result)
                    except Exception:
                        result = {}
                if isinstance(result, dict):
                    bill_balance = result.get('patientBillBalance', 0) or 0
                    billing_studies = result.get('patientStudyDetails', []) or []

        # Build billing lookup keyed by normalized description+date
        billing_lookup: Dict[str, Dict[str, Any]] = {}
        for bs in billing_studies:
            desc = bs.get('studyDescription', '')
            date_str = bs.get('studyDateTime', '')
            key = _normalize_study_key(desc, date_str)
            billing_lookup[key] = bs

        # Track which billing entries are matched
        matched_billing_keys = set()

        # Build table rows from study details, enriched with billing data
        table_rows: List[Dict[str, str]] = []
        for study in studies:
            study_desc = study.get('study_description', '') or 'N/A'
            raw_date = study.get('study_date_time', '')
            study_date = _format_date(raw_date)
            ordered_status = study.get('ordered_status', '') or 'N/A'
            image_count = study.get('image_count', 0) or 0
            images_available = "Yes" if image_count > 0 else "No"
            report_available = "No"  # Default — no report data from this API

            # Look up billing data
            lookup_key = _normalize_study_key(study_desc, raw_date)
            billing_entry = billing_lookup.get(lookup_key, {})
            if billing_entry:
                matched_billing_keys.add(lookup_key)

            billing_status_raw = billing_entry.get('billingStatus', '')
            billing_amount = billing_entry.get('billingAmount')

            billing_status = _get_billing_status_text(
                ordered_status, billing_status_raw, billing_amount, study_date
            )

            table_rows.append({
                'exam_description': study_desc,
                'study_date': study_date,
                'exam_status': ordered_status,
                'images_available': images_available,
                'report_available': report_available,
                'billing_status': billing_status,
            })

        # Append orphan billing entries (in bill balance but not in study details)
        for key, bs in billing_lookup.items():
            if key not in matched_billing_keys:
                desc = bs.get('studyDescription', '') or 'N/A'
                raw_date = bs.get('studyDateTime', '')
                study_date = _format_date(raw_date)
                exam_status = bs.get('examStatus', '') or 'N/A'
                billing_status_raw = bs.get('billingStatus', '')
                billing_amount = bs.get('billingAmount')

                billing_status = _get_billing_status_text(
                    exam_status, billing_status_raw, billing_amount, study_date
                )

                table_rows.append({
                    'exam_description': desc,
                    'study_date': study_date,
                    'exam_status': exam_status,
                    'images_available': 'N/A',
                    'report_available': 'N/A',
                    'billing_status': billing_status,
                })

        # Build billing summary header
        if bill_balance is not None and bill_balance > 0:
            billing_header = f"The patient's current bill balance is <b>${bill_balance:,.2f}</b>."
        else:
            billing_header = "No outstanding bill balance found."

        # Build final output
        if table_rows:
            table_html = _build_html_table(table_rows)
            return f'{billing_header}<br/><br/>{table_html}'
        else:
            return f'{billing_header}<br/><br/><p>No study details available.</p>'

    except Exception as e:
        logger.error(f"Error generating billing status table for patient {patient_id}: {e}", exc_info=True)
        return _get_error_message()
