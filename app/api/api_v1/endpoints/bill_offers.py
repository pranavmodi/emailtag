"""Bill Offer Phase 1 review API."""

import copy
import re
from datetime import datetime
from typing import Any, Dict, Optional
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
    normalize_medpay_status,
)

router = APIRouter()


def _build_document_source_map(extracted_facts: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not isinstance(extracted_facts, dict):
        return {}
    document_facts = extracted_facts.get("_document_facts")
    if not isinstance(document_facts, list):
        return {}

    source_map: Dict[str, str] = {}
    for index, document in enumerate(document_facts):
        if not isinstance(document, dict):
            continue
        filename = str(document.get("filename") or document.get("document_id") or f"Document {index + 1}")
        document_id = document.get("document_id")
        if document_id:
            source_map[str(document_id)] = filename
        source_map.setdefault(f"ocr_{index + 1}", filename)
    return source_map


def _replace_source_references(value: Any, source_map: Dict[str, str]) -> Any:
    if not isinstance(value, str) or not source_map:
        return value
    resolved = value
    for source_id, filename in source_map.items():
        resolved = re.sub(rf"\b{re.escape(source_id)}\b", filename, resolved)
    return resolved


def _decorate_extracted_facts_for_response(
    extracted_facts: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Use document filenames in API display fields while preserving stored raw facts."""
    if not isinstance(extracted_facts, dict):
        return extracted_facts

    source_map = _build_document_source_map(extracted_facts)
    if not source_map:
        return extracted_facts

    facts = copy.deepcopy(extracted_facts)
    for field_value in facts.values():
        if not isinstance(field_value, dict):
            continue
        source_id = field_value.get("source_id")
        if source_id and str(source_id) in source_map:
            field_value["source_id"] = source_map[str(source_id)]
        for text_key in ("evidence", "ambiguity_notes"):
            if text_key in field_value:
                field_value[text_key] = _replace_source_references(field_value[text_key], source_map)

    conflicts = facts.get("_conflicts")
    if isinstance(conflicts, list):
        for conflict in conflicts:
            if not isinstance(conflict, dict):
                continue
            if "description" in conflict:
                conflict["description"] = _replace_source_references(conflict["description"], source_map)
            if isinstance(conflict.get("sources"), list):
                conflict["sources"] = [
                    source_map.get(str(source), str(source)) for source in conflict["sources"]
                ]

    meta = facts.get("_meta")
    if isinstance(meta, dict) and "summary" in meta:
        meta["summary"] = _replace_source_references(meta["summary"], source_map)

    document_facts = facts.get("_document_facts")
    if isinstance(document_facts, list):
        for document in document_facts:
            if not isinstance(document, dict):
                continue
            if "notes" in document:
                document["notes"] = _replace_source_references(document["notes"], source_map)
            for extracted_field in document.get("extracted_fields") or []:
                if isinstance(extracted_field, dict):
                    for text_key in ("evidence", "ambiguity_notes"):
                        if text_key in extracted_field:
                            extracted_field[text_key] = _replace_source_references(
                                extracted_field[text_key], source_map
                            )

    return facts


def _intake_response(intake: Any) -> Optional[BillOfferIntakeResponse]:
    if intake is None:
        return None
    response = BillOfferIntakeResponse.model_validate(intake)
    response.extracted_facts = _decorate_extracted_facts_for_response(response.extracted_facts)
    for facts in (response.extracted_facts, response.corrected_facts):
        if not isinstance(facts, dict):
            continue
        medpay_fact = facts.get("medpay_status")
        if isinstance(medpay_fact, dict):
            medpay_fact["value"] = normalize_medpay_status(medpay_fact.get("value")) or ""

    if response.status != BillOfferIntakeStatus.MANUAL_REVIEW:
        effective = merge_effective_facts(response.extracted_facts, response.corrected_facts)
        missing_fields = compute_missing_fields(effective) if response.patient_id else []
        response.missing_fields = missing_fields
        response.status = (
            BillOfferIntakeStatus.PENDING_PATIENT
            if not response.patient_id
            else BillOfferIntakeStatus.PENDING_DETAILS
            if missing_fields
            else BillOfferIntakeStatus.READY_FOR_PHASE_2
        )
    return response


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
    return BillOfferIntakeListResponse(items=[_intake_response(item) for item in items], total=total)


@router.get("/tagged-emails", response_model=BillOfferTaggedEmailListResponse)
async def list_bill_offer_tagged_emails(
    skip: int = 0,
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None, max_length=200),
    status_filter: Optional[str] = Query(None, alias="status", max_length=50),
    db: AsyncSession = Depends(get_db),
) -> BillOfferTaggedEmailListResponse:
    rows, total = await crud.list_tagged_bill_offer_emails(
        db,
        skip=skip,
        limit=limit,
        search=search,
        status=status_filter,
    )
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
                search_text=row.get("search_text"),
                tags=["Bill Offer"],
                has_intake=bool(intake),
                intake=_intake_response(intake) if intake else None,
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
    return _intake_response(intake)


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
    return _intake_response(intake)


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
    return _intake_response(intake)


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
        intake=_intake_response(intake),
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
    return _intake_response(intake)


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
    return _intake_response(intake)
