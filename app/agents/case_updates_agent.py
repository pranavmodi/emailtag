
"""
Agent for handling Case Update related tags.

This module provides a very simple autorespond workflow for any email that has
one or more tags that fall under the "Case Updates" hierarchy (excluding those
that currently route to human-review).

It maps each supported tag to a pre-defined canned response and uses the shared
`send_reply_to_front` helper to post that reply back to the originating Front
conversation.
"""

# Standard library
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

# Third-party
from celery.utils.log import get_task_logger

# Project
from app.core.config import settings as app_settings_instance
from app.agents.agent_helpers import (
    send_reply_to_front_direct,
    extract_patient_id_from_email_logic,
)
from app.mcp import default_mcp_client as mcp_client

logger = get_task_logger(__name__)

# ---------------------------------------------------------------------------
# Supported Case-Update Tags & canned replies
# ---------------------------------------------------------------------------

CASE_UPDATE_TAG_TEMPLATES: Dict[str, str] = {
    # NOTE: Keep keys exactly as they appear in the tagging taxonomy.
    "Drop Pending": (
        "Thank you for your update. We have noted that the case is currently "
        "pending withdrawal. Please let us know once the drop has been "
        "finalised or if you require any additional documentation from us."
    ),
    "Promise to send payment": (
        "Thank you for letting us know that payment will be sent. We will "
        "continue monitoring the case and will confirm receipt as soon as it "
        "arrives."
    ),
    "Waiting to clear liability": (
        "Thank you for the update regarding liability clearance. We will keep "
        "the account on hold and await confirmation that liability has been "
        "resolved."
    ),
    "Waiting on settlement check": (
        "We appreciate the update. We will follow up once the settlement check "
        "has cleared. Please keep us informed of any developments."
    ),
    "Sent payment but not received": (
        "Thank you for informing us that payment has been sent. We will notify "
        "you once we have received and processed it."
    ),
    "Payment on way": (
        "Thank you for the update. We will confirm once the payment has been "
        "received."
    ),
}

# Map supported tags to RadFlow event IDs for logging.
# Based on MCP function validation requirements
CASE_UPDATE_TAG_EVENT_IDS: Dict[str, int] = {
    "Drop Pending": 7,  # General event requiring only notes
    "Promise to send payment": 20,  # Requires expected_payment_date
    "Waiting to clear liability": 2,  # Requires liability_expected_date
    "Waiting on settlement check": 5,  # Requires expected_payment_date
    "Sent payment but not received": 6,  # Requires payment_date_sent, check_number, check_amount
    "Payment on way": 20,  # Requires send_payment_of_estimated_date
}

# Convenience constant so that callers can easily test if a tag should trigger
# this agent.
SUPPORTED_CASE_UPDATE_TAGS = set(CASE_UPDATE_TAG_TEMPLATES.keys())

# Feature flag to disable autorespond functionality while keeping code intact
CASE_UPDATE_AUTORESPOND_ENABLED = False

# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------

async def handle_case_update_request(
    *,
    front_conversation_id: str,
    current_email_content: str,
    email_subject: str = None,
    applied_case_tags: List[str],
    structured_history_messages: List[Dict[str, Any]],
    settings_obj: Any = app_settings_instance,
) -> Dict[str, Any]:
    """Main entry-point used by *perform_autorespond_task*.

    Parameters
    ----------
    front_conversation_id:
        The Front conversation we are replying to.
    current_email_content:
        The raw text/html of the triggering email. (Currently unused but kept
        for future context aware replies.)
    email_subject:
        The subject line of the triggering email for patient extraction.
    applied_case_tags:
        List of Case-Update tags that were applied during classification.
    structured_history_messages:
        Historic messages for context (currently unused).
    settings_obj:
        Reference to the global settings module ‑ allows future dynamic config.

    Returns
    -------
    dict
        A dict matching the schema expected by *perform_autorespond_task*:
        {
            "agent_handled": bool,
            "processed_flag": bool,
            "details": dict
        }
    """
    logger.info(
        "[CaseUpdatesAgent] Called for conversation %s with tags %s",
        front_conversation_id,
        applied_case_tags,
    )

    # Find the first tag we have a canned reply for.
    chosen_tag: Optional[str] = None
    for tag in applied_case_tags:
        if tag in SUPPORTED_CASE_UPDATE_TAGS:
            chosen_tag = tag
            break

    if not chosen_tag:
        logger.warning(
            "[CaseUpdatesAgent] No supported Case-Update tags found in %s",
            applied_case_tags,
        )
        return {
            "agent_handled": False,
            "processed_flag": False,
            "details": {"reason": "No supported case-update tag present."},
        }

    # --- Patient Extraction (Always Performed) ---
    logger.info(f"🔍 DEBUG CASE_UPDATES: About to call extract_patient_id_from_email_logic")
    logger.info(f"🔍 DEBUG CASE_UPDATES: email_subject parameter = '{email_subject}' (type: {type(email_subject)})")
    logger.info(f"🔍 DEBUG CASE_UPDATES: current_email_content length = {len(current_email_content)}")
    
    patient_id = await extract_patient_id_from_email_logic(current_email_content, front_conversation_id, email_subject)
    if patient_id:
        logger.info(
            "[CaseUpdatesAgent] Extracted Patient ID: %s for conv %s",
            patient_id,
            front_conversation_id,
        )
    else:
        logger.info(
            "[CaseUpdatesAgent] No Patient ID found in conv %s",
            front_conversation_id,
        )

    # Check if autorespond (including MCP logging) is enabled via feature flag
    if not CASE_UPDATE_AUTORESPOND_ENABLED:
        logger.info(
            "[CaseUpdatesAgent] Autorespond (including MCP logging) disabled for tag '%s' in conv %s. Patient ID: %s",
            chosen_tag,
            front_conversation_id,
            patient_id or "None",
        )
        return {
            "agent_handled": True,  # Mark as handled since we processed it (just didn't perform actions)
            "processed_flag": True,
            "details": {
                "tag": chosen_tag,
                "autorespond_disabled": True,
                "mcp_logging_disabled": True,
                "patient_id": patient_id,  # Include extracted patient ID in response
            },
        }

    # --- Begin MCP Logging ---
    if patient_id:
        event_id = CASE_UPDATE_TAG_EVENT_IDS.get(chosen_tag)
        if event_id:
            if not mcp_client.is_connected:
                await mcp_client.connect()

            tool_args = {
                "patient_id": patient_id,
                "user_name": "CaseUpdatesAgent",
                "event_id": event_id,
                "notes": f"Auto-logged from email with tag: {chosen_tag}",
            }
            
            # Add required parameters based on event_id validation
            if event_id == 2:  # Waiting to clear liability
                # Provide a placeholder liability expected date (30 days from now)
                liability_date = (datetime.now() + timedelta(days=30)).strftime("%m/%d/%Y")
                tool_args["liability_expected_date"] = liability_date
            elif event_id == 5:  # Waiting on settlement check
                # Provide a placeholder expected payment date (14 days from now)
                payment_date = (datetime.now() + timedelta(days=14)).strftime("%m/%d/%Y")
                tool_args["expected_payment_date"] = payment_date
            elif event_id == 6:  # Sent payment but not received
                # Provide placeholder payment details
                payment_sent_date = (datetime.now() - timedelta(days=7)).strftime("%m/%d/%Y")
                tool_args["payment_date_sent"] = payment_sent_date
                tool_args["check_number"] = "UNKNOWN"  # Placeholder since we can't extract from email
                tool_args["check_amount"] = 1.0  # Placeholder amount (API requires > 0) since we can't extract from email
            elif event_id == 20:  # Promise to send payment or Payment on way
                # For "Promise to send payment", provide expected payment date
                # For "Payment on way", provide estimated send date
                if chosen_tag == "Promise to send payment":
                    payment_date = (datetime.now() + timedelta(days=14)).strftime("%m/%d/%Y")
                    tool_args["expected_payment_date"] = payment_date
                elif chosen_tag == "Payment on way":
                    send_date = (datetime.now() + timedelta(days=7)).strftime("%m/%d/%Y")
                    tool_args["send_payment_of_estimated_date"] = send_date
            
            logger.info(
                "[CaseUpdatesAgent] Calling 'insert_case_update_log' with args: %s",
                tool_args,
            )
            mcp_result = await mcp_client.call_tool("insert_case_update_log", tool_args)
            logger.info(
                "[CaseUpdatesAgent] 'insert_case_update_log' result: %s", mcp_result
            )
            if not mcp_result.get("success"):
                logger.error(
                    "[CaseUpdatesAgent] MCP tool 'insert_case_update_log' failed for "
                    "patient %s in conv %s. Error: %s",
                    patient_id,
                    front_conversation_id,
                    mcp_result.get("error"),
                )
        else:
            logger.warning(
                "[CaseUpdatesAgent] No Event ID mapping for tag '%s' in conv %s",
                chosen_tag,
                front_conversation_id,
            )
    else:
        logger.info(
            "[CaseUpdatesAgent] Skipping MCP log for conv %s (no patient ID found earlier).",
            front_conversation_id,
        )
    # --- End MCP Logging ---

    reply_body = CASE_UPDATE_TAG_TEMPLATES[chosen_tag]

    # Send reply via helper (runs the blocking Front call in a thread pool)
    # Note: Human review tag is added in main tagging flow for all case update emails
    send_result = await send_reply_to_front_direct(
        front_conversation_id,
        reply_body,
        tags_to_add=None,
        tags_to_remove=None,
    )

    success = send_result.get("status") == "success"
    if success:
        logger.info(
            "[CaseUpdatesAgent] Successfully sent autoresponse for tag '%s' in conv %s",
            chosen_tag,
            front_conversation_id,
        )
    else:
        logger.error(
            "[CaseUpdatesAgent] Failed to send autoresponse for tag '%s' in conv %s: %s",
            chosen_tag,
            front_conversation_id,
            send_result.get("message"),
        )

    return {
        "agent_handled": success,
        "processed_flag": success,
        "details": {
            "tag": chosen_tag,
            "send_result": send_result,
        },
    } 