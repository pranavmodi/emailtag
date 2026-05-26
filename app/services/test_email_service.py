"""Service for sending test emails via SMTP.

This service provides functionality to send test emails using scenarios
from the client evaluation test suite.
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import make_msgid
from typing import Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# SMTP configuration from environment
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
DEFAULT_RECIPIENT_EMAIL = os.getenv("DEFAULT_RECIPIENT_EMAIL")

# Project root for finding attachment files
PROJECT_ROOT = Path(__file__).parent.parent.parent


def check_smtp_config() -> dict:
    """Check if SMTP configuration is available.

    Returns:
        Dict with smtp_configured bool and recipient_email if configured
    """
    smtp_configured = all([SMTP_HOST, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD])
    return {
        "smtp_configured": smtp_configured,
        "recipient_email": DEFAULT_RECIPIENT_EMAIL,
        "smtp_host": SMTP_HOST if smtp_configured else None,
    }


def get_scenarios_by_type() -> dict:
    """Load test scenarios grouped by type.

    Returns:
        Dict with scenarios grouped by type and type metadata
    """
    try:
        from scripts.evals.scenarios_client_evals import CLIENT_EVAL_SCENARIOS
    except ImportError:
        logger.error("Could not import CLIENT_EVAL_SCENARIOS from scripts.evals.scenarios_client_evals")
        return {"scenarios": {}, "types": {}}

    # Group scenarios by type based on expected_tags
    scenarios_by_type: dict = {}

    # Define type mappings based on expected_tags
    type_mappings = {
        "apt_status": ["Apt status req"],
        "scheduling": ["Schedule Request", "RX", "Cancel Request", "Reschedule Request"],
        "lien_asl": ["ASL"],
        "lien_psl": ["PSL"],
        "lien_modified": ["Lien Modified"],
        "bill_balance": ["Bill or balance Request"],
        "medical_records": ["Release of Records", "Reports Request", "Image Request", "CD Requests"],
        "case_updates": ["Sent payment but not received", "Drop Letter", "New Attorney", "Promise to send payment"],
        "patient_demo": ["Patient Demo"],
        "other": [],
    }

    # Reverse mapping: tag -> type
    tag_to_type = {}
    for type_key, tags in type_mappings.items():
        for tag in tags:
            tag_to_type[tag] = type_key

    for scenario_key, scenario in CLIENT_EVAL_SCENARIOS.items():
        # Skip multi-step scenarios for now
        if scenario.get("is_multi_step"):
            continue

        expected_tags = scenario.get("expected_tags", [])

        # Determine the type based on expected tags
        scenario_type = "other"
        for tag in expected_tags:
            if tag in tag_to_type:
                scenario_type = tag_to_type[tag]
                break

        # Check for lien types more specifically
        if "ASL" in expected_tags:
            scenario_type = "lien_asl"
        elif "PSL" in expected_tags:
            scenario_type = "lien_psl"
        elif "Lien Modified" in expected_tags:
            scenario_type = "lien_modified"

        if scenario_type not in scenarios_by_type:
            scenarios_by_type[scenario_type] = {}

        # Build scenario info
        scenarios_by_type[scenario_type][scenario_key] = {
            "key": scenario_key,
            "description": scenario.get("description", ""),
            "subject": scenario.get("subject", ""),
            "expected_tags": expected_tags,
            "has_attachments": "attachments" in scenario and len(scenario["attachments"]) > 0,
            "type": scenario_type,
        }

    # Type labels for UI
    type_labels = {
        "apt_status": "Appointment Status",
        "scheduling": "Scheduling",
        "lien_asl": "Attorney Signed Liens (ASL)",
        "lien_psl": "Patient Signed Liens (PSL)",
        "lien_modified": "Modified Liens",
        "bill_balance": "Bill/Balance Requests",
        "medical_records": "Medical Records",
        "case_updates": "Case Updates",
        "patient_demo": "Patient Demographics",
        "other": "Other",
    }

    return {
        "scenarios": scenarios_by_type,
        "types": type_labels,
    }


def send_test_email(scenario_key: str, recipient_email: Optional[str] = None) -> dict:
    """Send a test email for a given scenario.

    Args:
        scenario_key: The key of the scenario to send
        recipient_email: Optional override for recipient email

    Returns:
        Dict with status and message
    """
    # Check SMTP configuration
    if not all([SMTP_HOST, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD]):
        return {
            "scenario_key": scenario_key,
            "status": "failed",
            "message": "SMTP configuration incomplete. Check SMTP_HOST, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD environment variables."
        }

    # Get recipient
    target_email = recipient_email or DEFAULT_RECIPIENT_EMAIL
    if not target_email:
        return {
            "scenario_key": scenario_key,
            "status": "failed",
            "message": "No recipient email configured. Set DEFAULT_RECIPIENT_EMAIL in environment."
        }

    # Load scenario
    try:
        from scripts.evals.scenarios_client_evals import CLIENT_EVAL_SCENARIOS
    except ImportError:
        return {
            "scenario_key": scenario_key,
            "status": "failed",
            "message": "Could not import scenarios module."
        }

    if scenario_key not in CLIENT_EVAL_SCENARIOS:
        return {
            "scenario_key": scenario_key,
            "status": "failed",
            "message": f"Scenario '{scenario_key}' not found."
        }

    scenario = CLIENT_EVAL_SCENARIOS[scenario_key]

    # Skip multi-step scenarios
    if scenario.get("is_multi_step"):
        return {
            "scenario_key": scenario_key,
            "status": "failed",
            "message": "Multi-step scenarios are not supported via UI."
        }

    try:
        smtp_port = int(SMTP_PORT)
    except ValueError:
        return {
            "scenario_key": scenario_key,
            "status": "failed",
            "message": f"Invalid SMTP_PORT: {SMTP_PORT}"
        }

    # Build email
    subject = scenario["subject"]
    body_html = scenario["body_html"]

    # Generate unique test ID
    import uuid
    unique_id = str(uuid.uuid4())[:8]
    body_html = body_html.replace("{UNIQUE_TEST_ID}", unique_id)

    msg = MIMEMultipart()
    msg_id = make_msgid(domain=SENDER_EMAIL.split('@')[1] if SENDER_EMAIL and '@' in SENDER_EMAIL else 'localhost')
    msg['Message-ID'] = msg_id
    msg['Subject'] = subject
    msg['From'] = SENDER_EMAIL
    msg['To'] = target_email
    msg.attach(MIMEText(body_html, 'html'))

    # Handle attachments
    if 'attachments' in scenario:
        for attachment_item in scenario['attachments']:
            if isinstance(attachment_item, str):
                attachment_file = attachment_item
                attachment_filename = os.path.basename(attachment_file)
            elif isinstance(attachment_item, dict):
                attachment_file = attachment_item.get('filepath', attachment_item.get('filename', ''))
                attachment_filename = attachment_item.get('filename', os.path.basename(attachment_file))
            else:
                continue

            # Try to find the file
            possible_paths = [
                PROJECT_ROOT / attachment_file,
                PROJECT_ROOT / "scripts" / "evals" / attachment_file,
                PROJECT_ROOT / "scripts" / attachment_file,
                Path(attachment_file),
            ]

            attachment_found = False
            for potential_path in possible_paths:
                if potential_path.exists():
                    try:
                        with open(potential_path, "rb") as f:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(f.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename="{attachment_filename}"',
                        )
                        msg.attach(part)
                        attachment_found = True
                        logger.info(f"Attached file: {potential_path}")
                        break
                    except Exception as e:
                        logger.warning(f"Error attaching file {potential_path}: {e}")
                        continue

            if not attachment_found:
                logger.warning(f"Attachment file not found: {attachment_file}")

    # Send email
    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, smtp_port) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, target_email, msg.as_string())
        else:
            with smtplib.SMTP(SMTP_HOST, smtp_port) as server:
                server.ehlo()
                if smtp_port == 587:
                    server.starttls()
                    server.ehlo()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, target_email, msg.as_string())

        logger.info(f"Test email sent successfully for scenario {scenario_key} to {target_email}")
        return {
            "scenario_key": scenario_key,
            "status": "success",
            "message": f"Email sent to {target_email}",
            "test_id": unique_id,
        }

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication Error: {e}")
        return {
            "scenario_key": scenario_key,
            "status": "failed",
            "message": f"SMTP authentication failed: {e}"
        }
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP Connect Error: {e}")
        return {
            "scenario_key": scenario_key,
            "status": "failed",
            "message": f"Failed to connect to SMTP server: {e}"
        }
    except Exception as e:
        logger.error(f"Error sending test email: {e}")
        return {
            "scenario_key": scenario_key,
            "status": "failed",
            "message": f"Error sending email: {str(e)}"
        }
