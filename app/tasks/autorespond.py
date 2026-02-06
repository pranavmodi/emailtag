"""Auto-response and agent orchestration tasks."""

import logging
import asyncio
from typing import Dict, List, Any
from uuid import UUID

from sqlalchemy.orm import Session
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.crud.sync import email as email_crud_sync
from app.crud.system_settings import system_settings_crud
from app.db.session import SessionLocal, AsyncSessionLocal
from app.schemas.email import EmailUpdate
from app.tasks.worker import celery_app
from app.services.frontapp_service import add_conversation_tags, get_conversation_text

# Conversation log context imports
from app.core.log_context import set_conversation_context, clear_conversation_context
from app.services.conversation_log_service import flush_conversation_logs

# Agent imports
from app.agents.apt_status_req_agent import handle_apt_status_request_agent_sdk
from app.agents.release_records_autorespond import handle_release_of_records_request
from app.agents.bill_balance_request_agent import handle_bill_balance_request
from app.agents.case_updates_agent import handle_case_update_request
from app.agents.missing_lien_request_agent import handle_missing_lien_request
# Unified lien agent (replaces separate ASL/PSL agents, but keeps backward compatibility wrappers)
from app.agents.lien_agent import handle_asl_lien_request, handle_psl_lien_request
from app.agents.agent_helpers import extract_patient_id_from_email_logic

logger = get_task_logger(__name__)

# Tag constants for auto-response logic
APT_STATUS_REQ_TAG_NAME = "Apt status req"
RELEASE_OF_RECORDS_TAG_NAME = "Release of Records"
IMAGE_REQUEST_TAG_NAME = "Image Request"
CD_REQUESTS_TAG_NAME = "CD Requests"
REPORTS_REQUEST_TAG_NAME = "Reports Request"
BILL_OR_BALANCE_REQUEST_TAG_NAME = "Bill or balance Request"
MISSING_LIEN_REQUEST_TAG_NAME = "Missing Lien Request"
RAD_LIEN_TAG_NAME = "Rad Lien"
TECH_LIEN_TAG_NAME = "Tech Lien"
PSL_TAG_NAME = "PSL"
ASL_TAG_NAME = "ASL"

# Medical Records & Images tags that should use the Release of Records agent
MEDICAL_RECORDS_TAGS = {
    RELEASE_OF_RECORDS_TAG_NAME,
    IMAGE_REQUEST_TAG_NAME,
    CD_REQUESTS_TAG_NAME,
    REPORTS_REQUEST_TAG_NAME,
}

# Human review tags
BILL_OFFER_TAG_NAME = "Bill Offer"
PENDING_APPROVAL_TAG_NAME = "Pending Approval"
NEW_ATTORNEY_TAG_NAME = "New Attorney"
DROP_LETTER_TAG_NAME = "Drop Letter"
INCORRECT_PATIENT_INFO_TAG_NAME = "Incorrect patient info"
INCORRECT_STUDY_INFO_TAG_NAME = "Incorrect study info"
REFUND_REQUEST_TAG_NAME = "Refund Request"
HUMAN_REVIEW_TAG_NAME = "AI: Human review required"

TAGS_REQUIRING_HUMAN_REVIEW = {
    BILL_OFFER_TAG_NAME,
    PENDING_APPROVAL_TAG_NAME,
    NEW_ATTORNEY_TAG_NAME,
    DROP_LETTER_TAG_NAME,
    INCORRECT_PATIENT_INFO_TAG_NAME,
    INCORRECT_STUDY_INFO_TAG_NAME,
    REFUND_REQUEST_TAG_NAME,
}

# Case update tags
CASE_UPDATE_TAGS = {
    "Drop Pending",
    "Promise to send payment",
    "Waiting to clear liability",
    "Waiting on settlement check",
    "Sent payment but not received",
    "Payment on way",
}


@celery_app.task(name="app.tasks.autorespond.perform_autorespond_task")
def perform_autorespond_task(email_id: str, determined_tags: List[str] = None) -> Dict:
    """
    Performs auto-response processing including:
    1. Human review tag checking
    2. Agent orchestration for specific tag types
    3. Final status determination
    """
    if determined_tags is not None:
        pass

    # Helper function to check autorespond settings from database
    async def _check_autorespond_enabled(autorespond_type: str) -> bool:
        """Check if a specific autorespond type is enabled in database settings."""
        async with AsyncSessionLocal() as async_db:
            return await system_settings_crud.is_autorespond_enabled(async_db, autorespond_type)

    async def _check_global_autorespond_enabled() -> bool:
        """Check if global autorespond master switch is enabled."""
        async with AsyncSessionLocal() as async_db:
            return await system_settings_crud.get_setting_value(
                async_db, "global_autorespond_enabled", default=True
            )

    # Check if global autorespond is enabled (master switch that controls all autoresponds)
    global_enabled = asyncio.run(_check_global_autorespond_enabled())
    if not global_enabled:
        logger.warning(f"🌐 GLOBAL AUTORESPOND DISABLED - Skipping all agent autoresponds for email {email_id}")
        return {"status": "autorespond_disabled", "message": "Global autorespond master switch is disabled"}

    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id in perform_autorespond_task: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}

    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found for auto-response.")
            return {"status": "error", "message": "Email not found"}

        # Debug subject tracking
        # logger.info(f"🔍 DEBUG AUTORESPOND: Retrieved email {email_id} from DB")
        # logger.info(f"🔍 DEBUG AUTORESPOND: email_obj.subject = '{email_obj.subject}' (type: {type(email_obj.subject)})")
        
        front_conversation_id = email_obj.front_conversation_id
        if not front_conversation_id:
            logger.error(f"Email {email_id} has no Front conversation ID for auto-response.")
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status="autorespond_failed_no_front_id", is_processed=True))
            return {"status": "error", "message": "Missing Front conversation ID for auto-response"}

        # Set up log context for capturing logs to database
        log_ctx = set_conversation_context(front_conversation_id, email_id)

        current_email_content = email_obj.content_text or email_obj.content_html or ""
        
        # # DEBUG: Log email content extraction details
        # logger.info(f"EMAIL CONTENT DEBUG - Email ID: {email_id}")
        # logger.info(f"EMAIL CONTENT DEBUG - content_text: {email_obj.content_text}")
        # logger.info(f"EMAIL CONTENT DEBUG - content_html: {email_obj.content_html}")
        # logger.info(f"EMAIL CONTENT DEBUG - final current_email_content: {current_email_content}")
        # logger.info(f"EMAIL CONTENT DEBUG - content length: {len(current_email_content)}")
        
        conversation_data = get_conversation_text(front_conversation_id)
        structured_history_messages = []
        if conversation_data and conversation_data.get('_structured_messages'):
            all_messages = conversation_data['_structured_messages']
            # Crude filter: if current email content appears at the end of structured history, remove it.
            # This helps avoid passing the current email (which the agent gets separately) as part of "history".
            if all_messages and current_email_content and all_messages[-1].get("body","").strip() == current_email_content.strip():
                logger.debug("Last message in structured_history matches current_email_content, removing from history for agent prompt.")
                structured_history_messages = all_messages[:-1]
            else:
                structured_history_messages = all_messages

        # --- Internal Domain Check ---
        # Check if the sender is from an internal domain - skip ALL autoresponds if filtering is enabled
        # UNLESS sandbox mode is enabled, in which case we still generate autoresponds for sandbox
        sender_email = email_obj.sender
        internal_domains = ["@precisemri.com", "@preciseimaging.com", "@radflow360.com", "@mediflow360.com", "@mediflow.com"]
        is_internal_sender = any(domain in sender_email.lower() for domain in internal_domains) if sender_email else False

        if is_internal_sender:
            # Check if internal domain filtering is enabled
            async def check_filtering_and_sandbox():
                async with AsyncSessionLocal() as async_db:
                    skip_internal = await system_settings_crud.get_setting_value(async_db, "skip_internal_domains", default=False)
                    lien_sandbox = await system_settings_crud.get_setting_value(async_db, "lien_test_mode", default=False)
                    bill_balance_sandbox = await system_settings_crud.get_setting_value(async_db, "bill_balance_test_mode", default=False)
                    apt_status_sandbox = await system_settings_crud.get_setting_value(async_db, "apt_status_test_mode", default=False)
                    return skip_internal, lien_sandbox, bill_balance_sandbox, apt_status_sandbox

            skip_internal_domains, lien_test_mode, bill_balance_test_mode, apt_status_test_mode = asyncio.run(check_filtering_and_sandbox())
            any_sandbox_enabled = lien_test_mode or bill_balance_test_mode or apt_status_test_mode

            if skip_internal_domains:
                if any_sandbox_enabled:
                    # Sandbox mode is enabled - continue processing so autorespond can be generated for sandbox
                    sandbox_types = []
                    if lien_test_mode:
                        sandbox_types.append("lien")
                    if bill_balance_test_mode:
                        sandbox_types.append("bill_balance")
                    if apt_status_test_mode:
                        sandbox_types.append("apt_status")
                    logger.info(f"🧪 SANDBOX MODE: Email {email_id} sender '{sender_email}' is internal but sandbox mode is enabled ({', '.join(sandbox_types)}). Processing for sandbox.")
                else:
                    # No sandbox mode - block autorespond as usual
                    logger.info(f"🚫 AUTORESPOND BLOCKED: Email {email_id} sender '{sender_email}' is from internal domain and filtering is ENABLED. Skipping all autoresponds.")
                    final_status = "processed_internal_sender_no_autorespond"
                    email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_status, is_processed=True))
                    return {
                        "status": "completed_autorespond_phase",
                        "email_id": email_id,
                        "final_db_status": final_status,
                        "auto_response_sent": False,
                        "auto_response_details": {"reason": f"Internal sender detected: {sender_email}, filtering enabled"},
                        "agent_handled_response": False
                    }
            else:
                logger.info(f"ℹ️ INTERNAL DOMAIN FILTERING DISABLED: Email {email_id} sender '{sender_email}' is from internal domain but filtering is OFF. Proceeding with autorespond (testing mode).")
        # --- End Internal Domain Check ---

        # --- No Action List Check ---
        # Check if the sender is on the no-action list - skip ALL autoresponds but still allow tagging
        async def _check_no_action_list(sender: str) -> bool:
            """Check if sender email/domain is on the no-action list."""
            from app.crud.tag_settings import tag_settings_crud
            async with AsyncSessionLocal() as async_db:
                workspace_settings = await tag_settings_crud.get_settings_dict(async_db, "WORKSPACE")
                no_action_list = workspace_settings.get("no_action_list", [])
                if not no_action_list or not sender:
                    return False
                sender_lower = sender.lower()
                for entry in no_action_list:
                    # Check for exact email match or domain match
                    if entry.startswith("@"):
                        # Domain pattern - check if sender ends with domain
                        if sender_lower.endswith(entry):
                            return True
                    else:
                        # Exact email match
                        if sender_lower == entry:
                            return True
                return False

        is_on_no_action_list = asyncio.run(_check_no_action_list(sender_email))
        if is_on_no_action_list:
            logger.info(f"🚫 NO-ACTION LIST: Email {email_id} sender '{sender_email}' is on the no-action list. Skipping all autoresponds (tagging still applied).")
            final_status = "processed_no_action_list"
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_status, is_processed=True))
            return {
                "status": "completed_autorespond_phase",
                "email_id": email_id,
                "final_db_status": final_status,
                "auto_response_sent": False,
                "auto_response_details": {"reason": f"Sender '{sender_email}' is on the no-action list"},
                "agent_handled_response": False
            }
        # --- End No Action List Check ---

        auto_response_processed_flag = False
        auto_response_details = None
        agent_handled_response = False
        agent_name_for_status = "none" # To track which agent ran for logging/status

        applied_tag_names = []
        if determined_tags is not None:
            applied_tag_names = determined_tags
        else:
            logger.warning("determined_tags not passed to autorespond task. Reading from DB, which may be stale.")
            applied_tag_names = [tag.name for tag in email_obj.tags if hasattr(tag, 'name')]

        # Log applied tags
        logger.info(f"Email {email_id} tags: {applied_tag_names}")

        # Extract document processing results for downstream agent use
        document_results = email_obj.ocr_results if hasattr(email_obj, 'ocr_results') and email_obj.ocr_results else None

        # --- Human Review Check for various tags ---
        triggered_human_review_tags = [tag for tag in applied_tag_names if tag in TAGS_REQUIRING_HUMAN_REVIEW]

        if triggered_human_review_tags:
            logger.info(f"Email {email_id} requires human review due to tags: {triggered_human_review_tags}. Applying '{HUMAN_REVIEW_TAG_NAME}' tag.")
            final_status = ""
            try:
                add_conversation_tags(front_conversation_id, [HUMAN_REVIEW_TAG_NAME])
                logger.info(f"Successfully applied '{HUMAN_REVIEW_TAG_NAME}' tag to conversation {front_conversation_id}.")
                final_status = "processed_human_review_needed"
            except Exception as e:
                logger.error(f"Failed to apply '{HUMAN_REVIEW_TAG_NAME}' tag for email {email_id}: {e}", exc_info=True)
                final_status = "processed_human_review_tag_failed"
            
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_status, is_processed=True))
            logger.info(f"Email {email_id} processing stopped after handling human review tag. Final status: {final_status}")
            return {
                "status": "completed_autorespond_phase",
                "email_id": email_id,
                "final_db_status": final_status,
                "auto_response_sent": False,
                "auto_response_details": {"reason": f"Tagged for human review due to: {', '.join(triggered_human_review_tags)}"},
                "agent_handled_response": False
            }
        # --- End Human Review Check ---

        if APT_STATUS_REQ_TAG_NAME in applied_tag_names:
            # Check if apt status test mode is enabled
            async def _check_apt_status_test_mode():
                async with AsyncSessionLocal() as async_db:
                    return await system_settings_crud.get_setting_value(async_db, "apt_status_test_mode", default=False)

            apt_status_test_mode_enabled = asyncio.run(_check_apt_status_test_mode())

            # Check if apt_status_req autorespond is enabled
            if not asyncio.run(_check_autorespond_enabled("autorespond_apt_status_req")):
                logger.info(f"📴 Apt Status Req autorespond DISABLED - Skipping agent for email {email_id}")
                auto_response_details = {"reason": "Apt Status Req autorespond is disabled"}
            else:
                agent_name_for_status = "apt_status_req"

                if apt_status_test_mode_enabled:
                    logger.info(f"🧪 APT STATUS TEST MODE: Email {email_id} tagged with '{APT_STATUS_REQ_TAG_NAME}'. Response will be saved to file (not sent)")
                else:
                    pass  # Normal production logging happens below

                # Use pre-extracted patient IDs from database (extracted before classification)
                def _get_all_patient_ids():
                    try:
                        if email_obj.extracted_patient_ids and len(email_obj.extracted_patient_ids) > 0:
                            logger.info(f"Found {len(email_obj.extracted_patient_ids)} pre-extracted patient ID(s) for {email_id}")
                            return email_obj.extracted_patient_ids
                        else:
                            return []
                    except Exception as e:
                        logger.error(f"Error accessing pre-extracted patient IDs for {email_id}: {e}", exc_info=True)
                        return []

                agent_result_dict = None
                async def _run_agent_sdk_orchestrator():
                    nonlocal agent_result_dict

                    # Get all pre-extracted patient IDs from database
                    extracted_patient_ids = _get_all_patient_ids()

                    # AI validation — filter patient IDs based on email context
                    if len(extracted_patient_ids) >= 1:
                        from app.agents.agent_helpers import validate_patient_ids_for_autorespond
                        validation_result = await validate_patient_ids_for_autorespond(
                            email_content=current_email_content,
                            email_subject=email_obj.subject or "",
                            structured_history_messages=structured_history_messages,
                            extracted_patient_ids=extracted_patient_ids,
                            conversation_id=front_conversation_id
                        )
                        filtered_ids = validation_result.get("filtered_patient_ids", extracted_patient_ids)
                        if filtered_ids:
                            extracted_patient_ids = filtered_ids
                            logger.info(f"🔍 AI VALIDATION: Filtered patient IDs: {extracted_patient_ids}")
                        else:
                            logger.warning(f"🔍 AI VALIDATION: All IDs filtered out, using original: {extracted_patient_ids}")
                        # Log validation details
                        details = validation_result.get("validation_details", {})
                        if details.get("patients_to_ignore"):
                            for ignored in details["patients_to_ignore"]:
                                logger.info(f"🔍 AI VALIDATION IGNORED: {ignored['patient_id']} - {ignored['reason']}")

                    # If no patient ID found, check if we've already asked for patient details
                    if not extracted_patient_ids:
                        # Check conversation history for previous "Please provide" requests
                        history_text = " ".join([msg.get("body", "") for msg in structured_history_messages])
                        if "Please provide the patient ID or first name, last name and date of birth" in history_text:
                            logger.info(f"Patient ID not found for {email_id}, but we've already asked for details. Continuing with agent.")
                        else:
                            logger.info(f"Patient ID not found for {email_id}, sending deterministic 'ask for patient details' response.")
                            # Send deterministic response asking for patient details
                            from app.agents.templates.shared_templates import TEMPLATE_REQUEST_PATIENT_ID

                            if apt_status_test_mode_enabled:
                                # In test mode, save the deterministic response to file
                                from app.agents.apt_status_req_agent import save_apt_status_test_response
                                save_apt_status_test_response(
                                    conversation_id=front_conversation_id,
                                    response_text=TEMPLATE_REQUEST_PATIENT_ID,
                                    patient_id=None,
                                    response_type="request_patient_id",
                                    details={"reason": "Deterministic response - requested patient details (saved to sandbox)"}
                                )
                                logger.info(f"🧪 APT STATUS TEST MODE: Saved deterministic 'ask for patient details' response to file")
                            else:
                                # Import the direct helper function (not the FunctionTool)
                                from app.agents.agent_helpers import send_reply_to_front_direct

                                await send_reply_to_front_direct(
                                    conversation_id=front_conversation_id,
                                    reply_text=TEMPLATE_REQUEST_PATIENT_ID,
                                    tags_to_add=None
                                )

                            agent_result_dict = {
                                "agent_handled": True,
                                "processed_flag": True,
                                "details": {"reason": "Deterministic response sent - requested patient details"}
                            }
                            return

                    # If we reach here, either patient IDs were found OR we've already asked for details
                    agent_result_dict = await handle_apt_status_request_agent_sdk(
                        front_conversation_id=front_conversation_id,
                        current_email_content=current_email_content,
                        structured_history_messages=structured_history_messages,
                        email_sender=sender_email,  # Pass sender email for authorization verification (may be spoofed for testing)
                        settings_obj=settings,  # Pass the main settings module
                        email_subject=email_obj.subject,  # Pass the email subject from DB
                        extracted_patient_ids=extracted_patient_ids,  # Pass ALL pre-extracted patient IDs
                        test_mode=apt_status_test_mode_enabled  # Pass test mode flag
                    )

                # Celery tasks are synchronous, so we run the async orchestrator using asyncio.run()
                # nest_asyncio.apply() should be at the top of the tasks file for this to work smoothly.
                try:
                    asyncio.run(_run_agent_sdk_orchestrator())
                except RuntimeError as e_async_run:
                    if "cannot be called from a running event loop" in str(e_async_run):
                        logger.warning(f"Asyncio run issue for agent orchestrator (loop already running?): {e_async_run}. Trying nest_asyncio if not already applied broadly.")
                        # This path might be complex if nest_asyncio isn't applied at the top or if it's a deeper issue.
                        # For now, log and the agent_result_dict will remain None or its initial state.
                        agent_result_dict = {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Asyncio runtime error: {e_async_run}"}}

                    else:
                        raise # Re-raise if it's a different RuntimeError

                if agent_result_dict:
                    agent_handled_response = agent_result_dict.get("agent_handled", False)
                    auto_response_processed_flag = agent_result_dict.get("processed_flag", False)
                    auto_response_details = agent_result_dict.get("details", {"reason": "Unknown agent processing outcome"})
                    if agent_handled_response:
                        logger.info(f"Agent SDK orchestrator handled response for {front_conversation_id}. Details: {auto_response_details}")
                    else:
                        logger.warning(f"Agent SDK orchestrator did NOT handle response for {front_conversation_id}. Details: {auto_response_details}")
                else:
                    logger.error(f"Agent SDK orchestrator call failed to return a result for {front_conversation_id}.")
                    auto_response_details = {"reason": "Agent orchestrator call failed or returned None."}

        elif any(tag in applied_tag_names for tag in MEDICAL_RECORDS_TAGS):
            # Check if medical_records autorespond is enabled
            if not asyncio.run(_check_autorespond_enabled("autorespond_medical_records")):
                logger.info(f"📴 Medical Records autorespond DISABLED - Skipping agent for email {email_id}")
                auto_response_details = {"reason": "Medical Records autorespond is disabled"}
            else:
                matched_medical_records_tags = [tag for tag in applied_tag_names if tag in MEDICAL_RECORDS_TAGS]
                agent_name_for_status = "medical_records"
                logger.info(f"Email {email_id} tagged with Medical Records & Images tag(s): {matched_medical_records_tags}. Attempting Medical Records agent.")

                # Log pre-extracted patient IDs for debugging
                if hasattr(email_obj, 'extracted_patient_ids') and email_obj.extracted_patient_ids:
                    logger.info(f"📋 Pre-extracted patient IDs available: {email_obj.extracted_patient_ids}")
                else:
                    logger.info("📋 No pre-extracted patient IDs found in database")

                email_sender = sender_email  # Use spoofed sender if testing is enabled
                if not email_sender:
                    logger.error(f"Cannot run Medical Records agent for {email_id}: sender email is missing.")
                    auto_response_details = {"reason": "Sender email missing for Medical Records agent."}
                else:
                    agent_result_dict = None
                    async def _run_medical_records_agent():
                        nonlocal agent_result_dict
                        agent_result_dict = await handle_release_of_records_request(
                            front_conversation_id=front_conversation_id,
                            current_email_content=current_email_content,
                            email_sender=email_sender,
                            structured_history_messages=structured_history_messages,
                            settings_obj=settings,
                            email_obj=email_obj
                        )

                    try:
                        asyncio.run(_run_medical_records_agent())
                    except Exception as e:
                        logger.error(f"Error running Medical Records agent for {email_id}: {e}", exc_info=True)
                        agent_result_dict = {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Agent execution error: {e}"}}

                    if agent_result_dict:
                        agent_handled_response = agent_result_dict.get("agent_handled", False)
                        auto_response_processed_flag = agent_result_dict.get("processed_flag", False)
                        auto_response_details = agent_result_dict.get("details", {"reason": "Unknown Medical Records agent processing outcome"})
                        if agent_handled_response:
                            logger.info(f"Medical Records agent handled response for {front_conversation_id}.")
                        else:
                            logger.warning(f"Medical Records agent did NOT handle response for {front_conversation_id}.")
                    else:
                        logger.error(f"Medical Records agent call failed to return a result for {front_conversation_id}.")
                        auto_response_details = {"reason": "Medical Records agent call failed or returned None."}

        elif BILL_OR_BALANCE_REQUEST_TAG_NAME in applied_tag_names:
            # Check if bill balance test mode is enabled
            async def _check_bill_balance_test_mode():
                async with AsyncSessionLocal() as async_db:
                    return await system_settings_crud.get_setting_value(async_db, "bill_balance_test_mode", default=False)

            bill_balance_test_mode_enabled = asyncio.run(_check_bill_balance_test_mode())

            # Check if bill_balance_request autorespond is enabled
            if not asyncio.run(_check_autorespond_enabled("autorespond_bill_balance_request")):
                logger.info(f"📴 Bill or Balance Request autorespond DISABLED - Skipping agent for email {email_id}")
                auto_response_details = {"reason": "Bill or Balance Request autorespond is disabled"}
            else:
                agent_name_for_status = "bill_balance_request"

                # Get pre-extracted patient IDs from database (like apt_status_req)
                def _get_bill_balance_patient_ids():
                    try:
                        if email_obj.extracted_patient_ids and len(email_obj.extracted_patient_ids) > 0:
                            logger.info(f"Found {len(email_obj.extracted_patient_ids)} pre-extracted patient ID(s) for bill balance {email_id}")
                            return email_obj.extracted_patient_ids
                        else:
                            return []
                    except Exception as e:
                        logger.error(f"Error accessing pre-extracted patient IDs for bill balance {email_id}: {e}", exc_info=True)
                        return []

                extracted_patient_ids = _get_bill_balance_patient_ids()

                if bill_balance_test_mode_enabled:
                    logger.info(f"🧪 BILL BALANCE TEST MODE: Email {email_id} tagged with '{BILL_OR_BALANCE_REQUEST_TAG_NAME}'. Response will be saved to file (not sent)")
                else:
                    logger.info(f"Email {email_id} tagged with '{BILL_OR_BALANCE_REQUEST_TAG_NAME}'. Attempting Bill/Balance agent.")

                agent_result_dict = None
                async def _run_bill_balance_agent():
                    nonlocal agent_result_dict
                    agent_result_dict = await handle_bill_balance_request(
                        front_conversation_id=front_conversation_id,
                        current_email_content=current_email_content,
                        structured_history_messages=structured_history_messages,
                        settings_obj=settings,
                        email_subject=email_obj.subject,
                        test_mode=bill_balance_test_mode_enabled,
                        extracted_patient_ids=extracted_patient_ids  # Pass ALL pre-extracted patient IDs
                    )

                try:
                    asyncio.run(_run_bill_balance_agent())
                except Exception as e:
                    logger.error(f"Error running Bill or balance Request agent for {email_id}: {e}", exc_info=True)
                    agent_result_dict = {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Agent execution error: {e}"}}

                if agent_result_dict:
                    agent_handled_response = agent_result_dict.get("agent_handled", False)
                    auto_response_processed_flag = agent_result_dict.get("processed_flag", False)
                    auto_response_details = agent_result_dict.get("details", {"reason": "Unknown Bill/Balance agent processing outcome"})
                    if agent_handled_response:
                        logger.info(f"Bill/Balance agent handled response for {front_conversation_id}.")
                    else:
                        logger.warning(f"Bill/Balance agent did NOT handle response for {front_conversation_id}.")
                else:
                    logger.error(f"Bill/Balance agent call failed to return a result for {front_conversation_id}.")
                    auto_response_details = {"reason": "Bill/Balance agent call failed or returned None."}

        elif MISSING_LIEN_REQUEST_TAG_NAME in applied_tag_names:
            # Check if missing_lien_request autorespond is enabled
            if not asyncio.run(_check_autorespond_enabled("autorespond_missing_lien_request")):
                logger.info(f"📴 Missing Lien Request autorespond DISABLED - Skipping agent for email {email_id}")
                auto_response_details = {"reason": "Missing Lien Request autorespond is disabled"}
            else:
                agent_name_for_status = "missing_lien_request"
                logger.info(f"Email {email_id} tagged with '{MISSING_LIEN_REQUEST_TAG_NAME}'. Attempting Missing Lien Request agent.")

                agent_result_dict = None
                async def _run_missing_lien_agent():
                    nonlocal agent_result_dict
                    agent_result_dict = await handle_missing_lien_request(
                        front_conversation_id=front_conversation_id,
                        current_email_content=current_email_content,
                        structured_history_messages=structured_history_messages,
                        settings_obj=settings,
                        email_subject=email_obj.subject
                    )

                try:
                    asyncio.run(_run_missing_lien_agent())
                except Exception as e:
                    logger.error(f"Error running Missing Lien Request agent for {email_id}: {e}", exc_info=True)
                    agent_result_dict = {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Agent execution error: {e}"}}

                if agent_result_dict:
                    agent_handled_response = agent_result_dict.get("agent_handled", False)
                    auto_response_processed_flag = agent_result_dict.get("processed_flag", False)
                    auto_response_details = agent_result_dict.get("details", {"reason": "Unknown Missing Lien Request agent processing outcome"})
                    if agent_handled_response:
                        logger.info(f"Missing Lien Request agent handled response for {front_conversation_id}.")
                    else:
                        logger.warning(f"Missing Lien Request agent did NOT handle response for {front_conversation_id}.")
                else:
                    logger.error(f"Missing Lien Request agent call failed to return a result for {front_conversation_id}.")
                    auto_response_details = {"reason": "Missing Lien Request agent call failed or returned None."}

        # --- BEGIN: Case Updates Agent Branch ---
        # Check for any Case Update tags (excluding those that require human review)
        matching_case_tags = [tag for tag in applied_tag_names if tag in CASE_UPDATE_TAGS]

        if not agent_handled_response and matching_case_tags:
            # Check if case_updates autorespond is enabled
            if not asyncio.run(_check_autorespond_enabled("autorespond_case_updates")):
                logger.info(f"📴 Case Updates autorespond DISABLED - Skipping agent for email {email_id}")
                auto_response_details = {"reason": "Case Updates autorespond is disabled"}
            else:
                agent_name_for_status = "case_updates"
                logger.info(
                    f"Email {email_id} tagged with Case Update tag(s) {matching_case_tags}. Attempting Case Updates agent."
                )

                agent_result_dict = None

                async def _run_case_updates_agent():
                    nonlocal agent_result_dict
                    agent_result_dict = await handle_case_update_request(
                        front_conversation_id=front_conversation_id,
                        current_email_content=current_email_content,
                        email_subject=email_obj.subject,
                        applied_case_tags=matching_case_tags,
                        structured_history_messages=structured_history_messages,
                        settings_obj=settings,
                    )

                try:
                    asyncio.run(_run_case_updates_agent())
                except Exception as e:
                    logger.error(
                        f"Error running Case Updates agent for {email_id}: {e}",
                        exc_info=True,
                    )
                    agent_result_dict = {
                        "agent_handled": False,
                        "processed_flag": False,
                        "details": {"reason": f"Agent execution error: {e}"},
                    }

                if agent_result_dict:
                    agent_handled_response = agent_result_dict.get("agent_handled", False)
                    auto_response_processed_flag = agent_result_dict.get("processed_flag", False)
                    auto_response_details = agent_result_dict.get(
                        "details", {"reason": "Unknown Case Updates agent outcome"}
                    )
                    if agent_handled_response:
                        logger.info(
                            f"Case Updates agent handled response for {front_conversation_id}."
                        )
                    else:
                        logger.warning(
                            f"Case Updates agent did NOT handle response for {front_conversation_id}."
                        )
                else:
                    logger.error(
                        f"Case Updates agent call failed to return a result for {front_conversation_id}."
                    )
                    auto_response_details = {
                        "reason": "Case Updates agent call failed or returned None."
                    }
        # --- END: Case Updates Agent Branch ---

        # --- BEGIN: PSL Lien Agent Branch ---
        elif not agent_handled_response and PSL_TAG_NAME in applied_tag_names and (RAD_LIEN_TAG_NAME in applied_tag_names or TECH_LIEN_TAG_NAME in applied_tag_names):
            has_rad_lien = RAD_LIEN_TAG_NAME in applied_tag_names
            has_tech_lien = TECH_LIEN_TAG_NAME in applied_tag_names
            logger.info(f"🔍 PSL LIEN CHECK: Matched PSL lien conditions")

            # Check if lien test mode is enabled
            async def _check_lien_test_mode():
                async with AsyncSessionLocal() as async_db:
                    return await system_settings_crud.get_setting_value(async_db, "lien_test_mode", default=False)

            lien_test_mode_enabled = asyncio.run(_check_lien_test_mode())

            # Check if liens autorespond is enabled (consolidated setting)
            if not asyncio.run(_check_autorespond_enabled("autorespond_liens")):
                logger.info(f"📴 Liens autorespond DISABLED - Skipping PSL agent for email {email_id}")
                auto_response_details = {"reason": "Liens autorespond is disabled"}
            else:
                agent_name_for_status = "psl_lien"
                lien_type = "PSL > Rad Lien" if has_rad_lien else "PSL > Tech Lien"

                if lien_test_mode_enabled:
                    logger.info(f"🧪 LIEN TEST MODE: Email {email_id} tagged with {lien_type}. Response will be saved to file (not sent)")
                else:
                    logger.info(f"Email {email_id} tagged with {lien_type}. Attempting PSL Lien agent.")

                agent_result_dict = None
                async def _run_psl_lien_agent():
                    nonlocal agent_result_dict
                    agent_result_dict = await handle_psl_lien_request(
                        front_conversation_id=front_conversation_id,
                        current_email_content=current_email_content,
                        applied_tags=applied_tag_names,
                        email_obj=email_obj,
                        document_analysis_results=document_results,
                        settings_obj=settings,
                        email_subject=email_obj.subject,
                        test_mode=lien_test_mode_enabled
                    )

                try:
                    asyncio.run(_run_psl_lien_agent())
                except Exception as e:
                    logger.error(f"Error running PSL Lien agent for {email_id}: {e}", exc_info=True)
                    agent_result_dict = {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Agent execution error: {e}"}}

                if agent_result_dict:
                    agent_handled_response = agent_result_dict.get("agent_handled", False)
                    auto_response_processed_flag = agent_result_dict.get("processed_flag", False)
                    auto_response_details = agent_result_dict.get("details", {"reason": "Unknown PSL Lien agent processing outcome"})
                    if agent_handled_response:
                        logger.info(f"PSL Lien agent handled response for {front_conversation_id}.")
                    else:
                        logger.warning(f"PSL Lien agent did NOT handle response for {front_conversation_id}.")
                else:
                    logger.error(f"PSL Lien agent call failed to return a result for {front_conversation_id}.")
                    auto_response_details = {"reason": "PSL Lien agent call failed or returned None."}
        # --- END: PSL Lien Agent Branch ---

        # --- BEGIN: ASL Lien Agent Branch ---
        elif not agent_handled_response and ASL_TAG_NAME in applied_tag_names and (RAD_LIEN_TAG_NAME in applied_tag_names or TECH_LIEN_TAG_NAME in applied_tag_names):
            has_rad_lien = RAD_LIEN_TAG_NAME in applied_tag_names
            has_tech_lien = TECH_LIEN_TAG_NAME in applied_tag_names
            logger.info(f"🔍 ASL LIEN CHECK: Matched ASL lien conditions")

            # Check if lien test mode is enabled
            async def _check_lien_test_mode():
                async with AsyncSessionLocal() as async_db:
                    return await system_settings_crud.get_setting_value(async_db, "lien_test_mode", default=False)

            lien_test_mode_enabled = asyncio.run(_check_lien_test_mode())

            # Check if liens autorespond is enabled (consolidated setting)
            if not asyncio.run(_check_autorespond_enabled("autorespond_liens")):
                logger.info(f"📴 Liens autorespond DISABLED - Skipping ASL agent for email {email_id}")
                auto_response_details = {"reason": "Liens autorespond is disabled"}
            else:
                agent_name_for_status = "asl_lien"
                lien_type = "ASL > Rad Lien" if has_rad_lien else "ASL > Tech Lien"

                if lien_test_mode_enabled:
                    logger.info(f"🧪 LIEN TEST MODE: Email {email_id} tagged with {lien_type}. Response will be saved to file (not sent)")
                else:
                    logger.info(f"Email {email_id} tagged with {lien_type}. Attempting ASL Lien agent.")

                agent_result_dict = None
                async def _run_asl_lien_agent():
                    nonlocal agent_result_dict
                    agent_result_dict = await handle_asl_lien_request(
                        front_conversation_id=front_conversation_id,
                        current_email_content=current_email_content,
                        applied_tags=applied_tag_names,
                        email_obj=email_obj,
                        document_analysis_results=document_results,
                        settings_obj=settings,
                        email_subject=email_obj.subject,
                        test_mode=lien_test_mode_enabled
                    )

                try:
                    asyncio.run(_run_asl_lien_agent())
                except Exception as e:
                    logger.error(f"Error running ASL Lien agent for {email_id}: {e}", exc_info=True)
                    agent_result_dict = {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Agent execution error: {e}"}}

                if agent_result_dict:
                    agent_handled_response = agent_result_dict.get("agent_handled", False)
                    auto_response_processed_flag = agent_result_dict.get("processed_flag", False)
                    auto_response_details = agent_result_dict.get("details", {"reason": "Unknown ASL Lien agent processing outcome"})
                    if agent_handled_response:
                        logger.info(f"ASL Lien agent handled response for {front_conversation_id}.")
                    else:
                        logger.warning(f"ASL Lien agent did NOT handle response for {front_conversation_id}.")
                else:
                    logger.error(f"ASL Lien agent call failed to return a result for {front_conversation_id}.")
                    auto_response_details = {"reason": "ASL Lien agent call failed or returned None."}
        # --- END: ASL Lien Agent Branch ---

        # --- BEGIN: Unknown Signature Lien Agent Branch (Rad Lien or Tech Lien without ASL/PSL) ---
        elif not agent_handled_response and (RAD_LIEN_TAG_NAME in applied_tag_names or TECH_LIEN_TAG_NAME in applied_tag_names) and ASL_TAG_NAME not in applied_tag_names and PSL_TAG_NAME not in applied_tag_names:
            has_rad_lien = RAD_LIEN_TAG_NAME in applied_tag_names
            has_tech_lien = TECH_LIEN_TAG_NAME in applied_tag_names
            logger.info(f"🔍 UNKNOWN SIGNATURE LIEN CHECK: Matched lien conditions without ASL/PSL signature type")

            # Check if lien test mode is enabled
            async def _check_lien_test_mode():
                async with AsyncSessionLocal() as async_db:
                    return await system_settings_crud.get_setting_value(async_db, "lien_test_mode", default=False)

            lien_test_mode_enabled = asyncio.run(_check_lien_test_mode())

            # Check if liens autorespond is enabled (consolidated setting)
            if not asyncio.run(_check_autorespond_enabled("autorespond_liens")):
                logger.info(f"📴 Liens autorespond DISABLED - Skipping lien agent for email {email_id}")
                auto_response_details = {"reason": "Liens autorespond is disabled"}
            else:
                agent_name_for_status = "unknown_sig_lien"
                lien_types = []
                if has_rad_lien:
                    lien_types.append("Rad Lien")
                if has_tech_lien:
                    lien_types.append("Tech Lien")
                lien_type_str = " + ".join(lien_types)

                if lien_test_mode_enabled:
                    logger.info(f"🧪 LIEN TEST MODE: Email {email_id} tagged with {lien_type_str} (unknown signature). Response will be saved to file (not sent)")
                else:
                    logger.info(f"Email {email_id} tagged with {lien_type_str} (unknown signature type). Attempting ASL Lien agent as default handler.")

                # Use ASL agent as the default handler for unknown signature liens
                agent_result_dict = None
                async def _run_unknown_sig_lien_agent():
                    nonlocal agent_result_dict
                    agent_result_dict = await handle_asl_lien_request(
                        front_conversation_id=front_conversation_id,
                        current_email_content=current_email_content,
                        applied_tags=applied_tag_names,
                        email_obj=email_obj,
                        document_analysis_results=document_results,
                        settings_obj=settings,
                        email_subject=email_obj.subject,
                        test_mode=lien_test_mode_enabled
                    )

                try:
                    asyncio.run(_run_unknown_sig_lien_agent())
                except Exception as e:
                    logger.error(f"Error running Unknown Signature Lien agent for {email_id}: {e}", exc_info=True)
                    agent_result_dict = {"agent_handled": False, "processed_flag": False, "details": {"reason": f"Agent execution error: {e}"}}

                if agent_result_dict:
                    agent_handled_response = agent_result_dict.get("agent_handled", False)
                    auto_response_processed_flag = agent_result_dict.get("processed_flag", False)
                    auto_response_details = agent_result_dict.get("details", {"reason": "Unknown signature Lien agent processing outcome"})
                    if agent_handled_response:
                        logger.info(f"Unknown Signature Lien agent handled response for {front_conversation_id}.")
                    else:
                        logger.warning(f"Unknown Signature Lien agent did NOT handle response for {front_conversation_id}.")
                else:
                    logger.error(f"Unknown Signature Lien agent call failed to return a result for {front_conversation_id}.")
                    auto_response_details = {"reason": "Unknown Signature Lien agent call failed or returned None."}
        # --- END: Unknown Signature Lien Agent Branch ---

        current_status_from_tagging = email_obj.status
        final_email_status = "processed_unknown_state" # Default

        if agent_handled_response: # This implies auto_response_processed_flag is also true from agent_result_dict
            final_email_status = f"processed_agent_{agent_name_for_status}"
            # auto_response_processed_flag is already set from agent_result_dict
        else:
            # No agent response (either not tagged for an agent, or agent chose not to handle, or agent error)
            auto_response_processed_flag = False # Explicitly ensure this is false if agent didn't handle
            
            reason_suffix = "no_agent_triggered"
            if agent_name_for_status != "none":
                reason_suffix = f"agent_{agent_name_for_status}_did_not_handle"

            if current_status_from_tagging == "tagging_completed_applied_tags":
                final_email_status = f"processed_tagged_no_autorespond_{reason_suffix}"
            elif current_status_from_tagging == "tagging_completed_no_tags":
                final_email_status = f"processed_notags_no_autorespond_{reason_suffix}"
            elif current_status_from_tagging == "tagging_completed_front_failed":
                 final_email_status = f"processed_tagged_frontfailed_no_autorespond_{reason_suffix}"
            else: # Other tagging statuses, or if tagging was skipped
                 final_email_status = f"processed_tag_status_({current_status_from_tagging})_no_autorespond_{reason_suffix}"
                 
        logger.info(f"Setting final status for email {email_id} to: {final_email_status}. Original tagging status: {current_status_from_tagging}. Agent handled: {agent_handled_response}")
        email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_email_status, is_processed=True))
        
        return {
            "status": "completed_autorespond_phase", 
            "email_id": email_id, 
            "final_db_status": final_email_status,
            "auto_response_sent": auto_response_processed_flag,
            "auto_response_details": auto_response_details,
            "agent_handled_response": agent_handled_response
        }

    except Exception as e:
        logger.exception(f"Critical error in perform_autorespond_task for {email_id}: {str(e)}")
        if db.is_active:
            db.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        # Flush captured logs to database
        ctx = clear_conversation_context()
        if ctx:
            flush_conversation_logs(ctx)
        if db.is_active:
            db.close()