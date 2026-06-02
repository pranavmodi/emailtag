"""Celery tasks for Bill Offer review workflows."""

import asyncio
import logging
from typing import Any, Dict
from uuid import UUID

from app.agents.bill_offer_agent import handle_bill_offer_request
from app.crud import bill_offer as bill_offer_crud
from app.crud.sync import email as email_crud_sync
from app.db.session import AsyncSessionLocal, SessionLocal
from app.models.bill_offer import BillOfferIntakeStatus
from app.services.frontapp_service import get_conversation_text
from app.tasks.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.bill_offer.run_bill_offer_agent_task")
def run_bill_offer_agent_task(
    *,
    front_conversation_id: str,
    email_id: str,
    run_id: str,
    send_reply: bool = False,
    triggered_by: str = "Settings2 manual trigger",
) -> Dict[str, Any]:
    """Run the Bill Offer agent outside the FastAPI request lifecycle."""
    logger.info(
        "Starting queued Bill Offer agent run: conversation=%s email_id=%s run_id=%s",
        front_conversation_id,
        email_id,
        run_id,
    )
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error("Invalid email_id for queued Bill Offer run: %s", email_id)
        return {
            "status": "error",
            "front_conversation_id": front_conversation_id,
            "run_id": run_id,
            "message": "Invalid email ID",
        }

    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error("Email %s not found for queued Bill Offer run", email_id)
            asyncio.run(
                _mark_bill_offer_run_failed(
                    front_conversation_id=front_conversation_id,
                    run_id=run_id,
                    reason="Email not found",
                )
            )
            return {
                "status": "error",
                "front_conversation_id": front_conversation_id,
                "run_id": run_id,
                "message": "Email not found",
            }

        try:
            conversation_data = get_conversation_text(front_conversation_id)
        except Exception as exc:
            logger.warning(
                "Front conversation retrieval failed for queued Bill Offer run; "
                "falling back to stored email body: conversation=%s run_id=%s error=%s",
                front_conversation_id,
                run_id,
                exc,
            )
            conversation_data = None
        structured_history_messages = []
        if conversation_data and conversation_data.get("_structured_messages"):
            structured_history_messages = conversation_data["_structured_messages"]

        async def _run() -> Dict[str, Any]:
            return await handle_bill_offer_request(
                front_conversation_id=front_conversation_id,
                current_email_content=email_obj.content_text or email_obj.content_html or "",
                structured_history_messages=structured_history_messages,
                email_sender=email_obj.sender,
                email_subject=email_obj.subject,
                extracted_patient_ids=email_obj.extracted_patient_ids or [],
                ocr_results=email_obj.ocr_results,
                raw_data=email_obj.raw_data,
                email_id=email_obj.id,
                send_reply=send_reply,
                triggered_by=triggered_by,
                run_id=run_id,
            )

        result = asyncio.run(_run())
        logger.info(
            "Completed queued Bill Offer agent run: conversation=%s run_id=%s handled=%s",
            front_conversation_id,
            run_id,
            result.get("agent_handled"),
        )
        return result
    except Exception as exc:
        logger.error(
            "Queued Bill Offer agent run failed: conversation=%s run_id=%s error=%s",
            front_conversation_id,
            run_id,
            exc,
            exc_info=True,
        )
        asyncio.run(
            _mark_bill_offer_run_failed(
                front_conversation_id=front_conversation_id,
                run_id=run_id,
                reason=str(exc),
            )
        )
        return {
            "status": "error",
            "front_conversation_id": front_conversation_id,
            "run_id": run_id,
            "message": str(exc),
        }
    finally:
        db.close()


async def _mark_bill_offer_run_failed(
    *,
    front_conversation_id: str,
    run_id: str,
    reason: str,
) -> None:
    async with AsyncSessionLocal() as db:
        intake = await bill_offer_crud.get_intake_by_conversation(db, front_conversation_id)
        if not intake:
            return
        await bill_offer_crud.update_intake(
            db,
            intake=intake,
            obj_in={
                "status": BillOfferIntakeStatus.MANUAL_REVIEW,
                "last_agent_action": "failed",
                "last_run_id": run_id,
                "last_agent_run_status": "failed",
                "patient_match": {
                    **(intake.patient_match or {}),
                    "queued_run_failure": reason,
                },
            },
        )
