"""Bill Offer Phase 1 review API."""

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import bill_offer as crud
from app.crud.system_settings import system_settings_crud
from app.db.session import get_db
from app.models.bill_offer import BillOfferAgentStepStatus, BillOfferIntakeStatus
from app.schemas.bill_offer import (
    BillOfferAgentLogCreate,
    BillOfferAgentLogListResponse,
    BillOfferCorrectionAuditListResponse,
    BillOfferCorrectionRequest,
    BillOfferIntakeListResponse,
    BillOfferIntakeResponse,
    BillOfferManualReviewRequest,
    BillOfferReviewRequiredRequest,
    BillOfferRunAgentRequest,
    BillOfferRunAgentResponse,
    BillOfferSendReplyRequest,
    BillOfferSettingsResponse,
    BillOfferTaggedEmailListResponse,
    BillOfferTaggedEmailResponse,
)
from app.tasks.bill_offer import run_bill_offer_agent_task
from app.services.bill_offer_extraction_service import (
    build_reply_draft,
    compute_missing_fields,
    confidence_summary,
    merge_effective_facts,
)

router = APIRouter()


@router.get("/settings", response_model=BillOfferSettingsResponse)
async def get_bill_offer_settings(
    db: AsyncSession = Depends(get_db),
) -> BillOfferSettingsResponse:
    review_required = await system_settings_crud.get_setting_value(
        db, "autorespond_bill_offer_review_required", default=True
    )
    return BillOfferSettingsResponse(review_required=bool(review_required))


@router.post("/settings/review-required", response_model=BillOfferSettingsResponse)
async def set_bill_offer_review_required(
    payload: BillOfferReviewRequiredRequest,
    db: AsyncSession = Depends(get_db),
) -> BillOfferSettingsResponse:
    await system_settings_crud.toggle_autorespond(
        db,
        autorespond_type="autorespond_bill_offer_review_required",
        enable=payload.enabled,
        updated_by=payload.reviewed_by or "Settings2",
    )
    return BillOfferSettingsResponse(review_required=payload.enabled)


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


@router.get(
    "/conversations/{front_conversation_id}/corrections",
    response_model=BillOfferCorrectionAuditListResponse,
)
async def list_bill_offer_correction_audits(
    front_conversation_id: str,
    skip: int = 0,
    limit: int = Query(200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> BillOfferCorrectionAuditListResponse:
    items, total = await crud.list_correction_audits_for_conversation(
        db, front_conversation_id=front_conversation_id, skip=skip, limit=limit
    )
    return BillOfferCorrectionAuditListResponse(items=items, total=total)


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
    status_code=status.HTTP_202_ACCEPTED,
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

    run_id = str(uuid4())
    intake = await crud.upsert_intake_for_conversation(
        db,
        front_conversation_id=front_conversation_id,
        values={
            "email_id": email.id,
            "original_sender_email": email.sender,
            "last_run_id": run_id,
            "last_agent_run_status": "queued",
            "last_agent_action": "queued",
        },
    )
    await crud.create_log(
        db,
        obj_in=BillOfferAgentLogCreate(
            front_conversation_id=front_conversation_id,
            email_id=email.id,
            intake_id=intake.id,
            run_id=run_id,
            step_name="manual_run_queued",
            step_status=BillOfferAgentStepStatus.COMPLETED,
            input_snapshot={
                "send_reply": payload.send_reply,
                "triggered_by": payload.reviewed_by or "Settings2 manual trigger",
            },
            output_snapshot={"last_agent_run_status": "queued"},
            message="Queued Bill Offer agent run",
        ),
    )
    task = run_bill_offer_agent_task.apply_async(
        kwargs={
            "front_conversation_id": front_conversation_id,
            "email_id": str(email.id),
            "run_id": run_id,
            "send_reply": payload.send_reply,
            "triggered_by": payload.reviewed_by or "Settings2 manual trigger",
        },
        queue="processing",
    )

    intake = await crud.get_intake_by_conversation(db, front_conversation_id) or intake
    return BillOfferRunAgentResponse(
        status="queued",
        run_id=run_id,
        intake=intake,
        details={"task_id": task.id, "queued": True},
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
