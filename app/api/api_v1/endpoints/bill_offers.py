"""Bill Offer Phase 1 review API."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.bill_offer_agent import handle_bill_offer_request
from app.crud import bill_offer as crud
from app.db.session import get_db
from app.models.bill_offer import BillOfferIntakeStatus
from app.schemas.bill_offer import (
    BillOfferAgentLogListResponse,
    BillOfferCorrectionRequest,
    BillOfferIntakeListResponse,
    BillOfferIntakeResponse,
    BillOfferManualReviewRequest,
    BillOfferRunAgentRequest,
    BillOfferRunAgentResponse,
    BillOfferSendReplyRequest,
    BillOfferTaggedEmailListResponse,
    BillOfferTaggedEmailResponse,
)
from app.services.bill_offer_extraction_service import (
    build_reply_draft,
    compute_missing_fields,
    confidence_summary,
    merge_effective_facts,
)
from app.services.frontapp_service import get_conversation_text

router = APIRouter()


@router.get("", response_model=BillOfferIntakeListResponse)
async def list_bill_offer_intakes(
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = 0,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> BillOfferIntakeListResponse:
    items, total = await crud.list_intakes(
        db, status=status_filter, skip=skip, limit=limit
    )
    return BillOfferIntakeListResponse(items=items, total=total)


@router.get("/tagged-emails", response_model=BillOfferTaggedEmailListResponse)
async def list_bill_offer_tagged_emails(
    skip: int = 0,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> BillOfferTaggedEmailListResponse:
    rows, total = await crud.list_tagged_bill_offer_emails(db, skip=skip, limit=limit)
    items = []
    for row in rows:
        email = row["email"]
        intake = row.get("intake")
        items.append(
            BillOfferTaggedEmailResponse(
                front_conversation_id=email.front_conversation_id,
                email_id=email.id,
                subject=email.subject,
                sender=email.sender,
                received_at=email.created_at,
                tags=["Bill Offer"],
                has_intake=bool(intake),
                intake=intake,
            )
        )
    return BillOfferTaggedEmailListResponse(items=items, total=total)


@router.get("/{intake_id}", response_model=BillOfferIntakeResponse)
async def get_bill_offer_intake(
    intake_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> BillOfferIntakeResponse:
    intake = await crud.get_intake(db, intake_id)
    if not intake:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intake not found")
    return intake


@router.get(
    "/conversations/{front_conversation_id}/logs",
    response_model=BillOfferAgentLogListResponse,
)
async def list_bill_offer_logs(
    front_conversation_id: str,
    skip: int = 0,
    limit: int = Query(300, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> BillOfferAgentLogListResponse:
    items, total = await crud.list_logs_for_conversation(
        db, front_conversation_id=front_conversation_id, skip=skip, limit=limit
    )
    return BillOfferAgentLogListResponse(items=items, total=total)


@router.patch("/{intake_id}", response_model=BillOfferIntakeResponse)
async def update_bill_offer_corrections(
    intake_id: UUID,
    payload: BillOfferCorrectionRequest,
    db: AsyncSession = Depends(get_db),
) -> BillOfferIntakeResponse:
    intake = await crud.get_intake(db, intake_id)
    if not intake:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intake not found")

    current_corrected = dict(intake.corrected_facts or {})
    for field, value in payload.corrected_facts.items():
        previous = current_corrected.get(field)
        if previous != value:
            await crud.create_correction_audit(
                db,
                front_conversation_id=intake.front_conversation_id,
                intake_id=intake.id,
                field_name=field,
                previous_value=previous,
                new_value=value,
                changed_by=payload.reviewed_by,
            )
        current_corrected[field] = value

    update_values = {
        "corrected_facts": current_corrected,
        "reviewed_by": payload.reviewed_by,
    }
    if payload.patient_id is not None:
        update_values["patient_id"] = payload.patient_id
    if payload.patient_match is not None:
        update_values["patient_match"] = payload.patient_match

    intake = await crud.update_intake(db, intake=intake, obj_in=update_values)
    return intake


@router.post("/{intake_id}/rerun-check", response_model=BillOfferIntakeResponse)
async def rerun_bill_offer_check(
    intake_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> BillOfferIntakeResponse:
    intake = await crud.get_intake(db, intake_id)
    if not intake:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intake not found")

    effective = merge_effective_facts(intake.extracted_facts, intake.corrected_facts)
    missing_fields = compute_missing_fields(effective) if intake.patient_id else []
    new_status = (
        BillOfferIntakeStatus.PENDING_PATIENT
        if not intake.patient_id
        else BillOfferIntakeStatus.PENDING_DETAILS
        if missing_fields
        else BillOfferIntakeStatus.READY_FOR_PHASE_2
    )
    reply_draft = build_reply_draft(
        patient_found=bool(intake.patient_id),
        patient_data=intake.patient_data,
        missing_fields=missing_fields,
        effective_facts=effective,
    )
    intake = await crud.update_intake(
        db,
        intake=intake,
        obj_in={
            "status": new_status,
            "missing_fields": missing_fields,
            "confidence": confidence_summary(effective),
            "reply_draft": reply_draft,
            "last_agent_action": "rerun_check",
        },
    )
    return intake


@router.post(
    "/conversations/{front_conversation_id}/run-agent",
    response_model=BillOfferRunAgentResponse,
)
async def run_bill_offer_agent_for_conversation(
    front_conversation_id: str,
    payload: BillOfferRunAgentRequest,
    db: AsyncSession = Depends(get_db),
) -> BillOfferRunAgentResponse:
    email = await crud.get_latest_bill_offer_email_for_conversation(
        db, front_conversation_id=front_conversation_id
    )
    if not email:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Bill Offer tagged email found for this conversation",
        )

    conversation_data = get_conversation_text(front_conversation_id)
    structured_history_messages = []
    if conversation_data and conversation_data.get("_structured_messages"):
        structured_history_messages = conversation_data["_structured_messages"]

    result = await handle_bill_offer_request(
        front_conversation_id=front_conversation_id,
        current_email_content=email.content_text or email.content_html or "",
        structured_history_messages=structured_history_messages,
        email_sender=email.sender,
        email_subject=email.subject,
        extracted_patient_ids=email.extracted_patient_ids or [],
        ocr_results=email.ocr_results,
        raw_data=email.raw_data,
        email_id=email.id,
        send_reply=payload.send_reply,
        triggered_by=payload.reviewed_by or "Settings2 manual trigger",
    )

    intake = await crud.get_intake_by_conversation(db, front_conversation_id)
    if not intake:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Agent completed without creating an intake",
        )
    return BillOfferRunAgentResponse(
        status=result.get("details", {}).get("status", "completed"),
        run_id=result.get("run_id", ""),
        intake=intake,
        details=result.get("details", {}),
    )


@router.post("/{intake_id}/send-reply", response_model=BillOfferIntakeResponse)
async def send_bill_offer_reply(
    intake_id: UUID,
    payload: BillOfferSendReplyRequest,
    db: AsyncSession = Depends(get_db),
) -> BillOfferIntakeResponse:
    from app.agents.agent_helpers import send_reply_to_front_direct
    from app.agents.bill_offer_agent import WAITING_PENDING_OFFER_DETAILS_TAG

    intake = await crud.get_intake(db, intake_id)
    if not intake:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intake not found")
    if not intake.reply_draft:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No reply draft exists")

    tags_to_add = []
    if intake.status in {
        BillOfferIntakeStatus.PENDING_PATIENT,
        BillOfferIntakeStatus.PENDING_DETAILS,
    }:
        tags_to_add.append(WAITING_PENDING_OFFER_DETAILS_TAG)

    result = await send_reply_to_front_direct(
        conversation_id=intake.front_conversation_id,
        reply_text=intake.reply_draft,
        tags_to_add=tags_to_add,
    )
    if result.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=result.get("message", "Failed to send reply"),
        )

    intake = await crud.update_intake(
        db,
        intake=intake,
        obj_in={
            "reply_sent_at": datetime.utcnow(),
            "reviewed_by": payload.reviewed_by,
            "reviewed_at": datetime.utcnow(),
            "last_agent_action": "approved_reply_sent",
        },
    )
    return intake


@router.post("/{intake_id}/manual-review", response_model=BillOfferIntakeResponse)
async def mark_bill_offer_manual_review(
    intake_id: UUID,
    payload: BillOfferManualReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> BillOfferIntakeResponse:
    intake = await crud.get_intake(db, intake_id)
    if not intake:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intake not found")
    intake = await crud.update_intake(
        db,
        intake=intake,
        obj_in={
            "status": BillOfferIntakeStatus.MANUAL_REVIEW,
            "reviewed_by": payload.reviewed_by,
            "reviewed_at": datetime.utcnow(),
            "last_agent_action": f"manual_review: {payload.reason or 'No reason provided'}",
        },
    )
    return intake
