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

# Agent imports
from app.agents.apt_status_req_agent import handle_apt_status_request_agent_sdk
from app.agents.release_records_autorespond import handle_release_of_records_request
from app.agents.bill_balance_request_agent import handle_bill_balance_request
from app.agents.case_updates_agent import handle_case_update_request
from app.agents.missing_lien_request_agent import handle_missing_lien_request
from app.agents.psl_lien_agent import handle_psl_lien_request
from app.agents.asl_lien_agent import handle_asl_lien_request
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
        # Check if the sender is from an internal domain - skip ALL autoresponds if so
        sender_email = email_obj.sender
        internal_domains = ["@precisemri.com", "@radflow360.com", "@mediflow360.com"]
        is_internal_sender = any(domain in sender_email.lower() for domain in internal_domains) if sender_email else False

        if is_internal_sender:
            logger.info(f"🚫 AUTORESPOND BLOCKED: Email {email_id} sender '{sender_email}' is from internal domain. Skipping all autoresponds.")
            final_status = "processed_internal_sender_no_autorespond"
            email_crud_sync.update(db, db_obj=email_obj, obj_in=EmailUpdate(status=final_status, is_processed=True))
            return {
                "status": "completed_autorespond_phase",
                "email_id": email_id,
                "final_db_status": final_status,
                "auto_response_sent": False,
                "auto_response_details": {"reason": f"Internal sender detected: {sender_email}"},
                "agent_handled_response": False
            }
        # --- End Internal Domain Check ---

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
            # Check if apt_status_req autorespond is enabled
            if not asyncio.run(_check_autorespond_enabled("autorespond_apt_status_req")):
                logger.info(f"📴 Apt Status Req autorespond DISABLED - Skipping agent for email {email_id}")
                auto_response_details = {"reason": "Apt Status Req autorespond is disabled"}
            else:
                agent_name_for_status = "apt_status_req"
                logger.info(f"Email {email_id} (conv: {front_conversation_id}) tagged with '{APT_STATUS_REQ_TAG_NAME}'. Attempting agent SDK via orchestrator.")

                # Use pre-extracted patient IDs from database (extracted before classification)
                def _get_first_patient_id():
                    try:
                        if email_obj.extracted_patient_ids and len(email_obj.extracted_patient_ids) > 0:
                            extracted_patient_id = email_obj.extracted_patient_ids[0]  # Use first patient ID for backward compatibility
                            logger.info(f"🔍 AUTORESPOND: Using pre-extracted patient ID for {email_id}: {extracted_patient_id}")
                            logger.info(f"🔍 AUTORESPOND: Full list of extracted patient IDs: {email_obj.extracted_patient_ids}")
                            return extracted_patient_id
                        else:
                            logger.info(f"🔍 AUTORESPOND: No pre-extracted patient IDs found for {email_id}")
                            return None
                    except Exception as e:
                        logger.error(f"Error accessing pre-extracted patient IDs for {email_id}: {e}", exc_info=True)
                        return None

                agent_result_dict = None
                async def _run_agent_sdk_orchestrator():
                    nonlocal agent_result_dict

                    # Get pre-extracted patient ID from database
                    extracted_patient_id = _get_first_patient_id()

                    # If no patient ID found, check if we've already asked for patient details
                    if not extracted_patient_id:
                        # Check conversation history for previous "Please provide" requests
                        history_text = " ".join([msg.get("body", "") for msg in structured_history_messages])
                        if "Please provide the patient ID or first name, last name and date of birth" in history_text:
                            logger.info(f"Patient ID not found for {email_id}, but we've already asked for details. Continuing with agent.")
                        else:
                            logger.info(f"Patient ID not found for {email_id}, sending deterministic 'ask for patient details' response.")
                            # Send deterministic response asking for patient details
                            from app.agents.templates.shared_templates import TEMPLATE_REQUEST_PATIENT_ID

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

                    # If we reach here, either patient ID was found OR we've already asked for details
                    agent_result_dict = await handle_apt_status_request_agent_sdk(
                        front_conversation_id=front_conversation_id,
                        current_email_content=current_email_content,
                        structured_history_messages=structured_history_messages,
                        settings_obj=settings,  # Pass the main settings module
                        email_subject=email_obj.subject,  # Pass the email subject from DB
                        extracted_patient_id=extracted_patient_id  # Pass the pre-extracted patient ID
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

                email_sender = email_obj.sender
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
            # Check if bill_balance_request autorespond is enabled
            if not asyncio.run(_check_autorespond_enabled("autorespond_bill_balance_request")):
                logger.info(f"📴 Bill or Balance Request autorespond DISABLED - Skipping agent for email {email_id}")
                auto_response_details = {"reason": "Bill or Balance Request autorespond is disabled"}
            else:
                agent_name_for_status = "bill_balance_request"
                logger.info(f"Email {email_id} tagged with '{BILL_OR_BALANCE_REQUEST_TAG_NAME}'. Attempting Bill/Balance agent.")

                agent_result_dict = None
                async def _run_bill_balance_agent():
                    nonlocal agent_result_dict
                    agent_result_dict = await handle_bill_balance_request(
                        front_conversation_id=front_conversation_id,
                        current_email_content=current_email_content,
                        structured_history_messages=structured_history_messages,
                        settings_obj=settings,
                        email_subject=email_obj.subject
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
        elif not agent_handled_response:
            # Check for any Case Update tags (excluding those that require human review)
            matching_case_tags = [tag for tag in applied_tag_names if tag in CASE_UPDATE_TAGS]

            if matching_case_tags:
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
        elif not agent_handled_response:
            # Check for PSL Lien tags (both PSL and either Rad Lien or Tech Lien required)
            has_psl = PSL_TAG_NAME in applied_tag_names
            has_rad_lien = RAD_LIEN_TAG_NAME in applied_tag_names
            has_tech_lien = TECH_LIEN_TAG_NAME in applied_tag_names

            if has_psl and (has_rad_lien or has_tech_lien):
                # Check if psl_lien autorespond is enabled
                if not asyncio.run(_check_autorespond_enabled("autorespond_psl_lien")):
                    logger.info(f"📴 PSL Lien autorespond DISABLED - Skipping agent for email {email_id}")
                    auto_response_details = {"reason": "PSL Lien autorespond is disabled"}
                else:
                    agent_name_for_status = "psl_lien"
                    lien_type = "PSL > Rad Lien" if has_rad_lien else "PSL > Tech Lien"
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
                            email_subject=email_obj.subject
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
        elif not agent_handled_response:
            # Check for ASL Lien tags (both ASL and either Rad Lien or Tech Lien required)
            has_asl = ASL_TAG_NAME in applied_tag_names
            has_rad_lien = RAD_LIEN_TAG_NAME in applied_tag_names
            has_tech_lien = TECH_LIEN_TAG_NAME in applied_tag_names

            if has_asl and (has_rad_lien or has_tech_lien):
                # Check if asl_lien autorespond is enabled
                if not asyncio.run(_check_autorespond_enabled("autorespond_asl_lien")):
                    logger.info(f"📴 ASL Lien autorespond DISABLED - Skipping agent for email {email_id}")
                    auto_response_details = {"reason": "ASL Lien autorespond is disabled"}
                else:
                    agent_name_for_status = "asl_lien"
                    lien_type = "ASL > Rad Lien" if has_rad_lien else "ASL > Tech Lien"
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
                            email_subject=email_obj.subject
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
        if db.is_active:
            db.close() 