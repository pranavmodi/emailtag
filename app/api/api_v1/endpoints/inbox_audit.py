"""Inbox audit API endpoints — runs, misses, review, manual trigger."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.crud import inbox_audit as crud
from app.db.session import get_db
from app.schemas.inbox_audit import (
    InboxAuditMissListResponse,
    InboxAuditMissResponse,
    InboxAuditRunListResponse,
    InboxAuditSummary,
    QueueProcessingResponse,
    QueueProcessingStatusRequest,
    QueueProcessingStatusResponse,
    QueueProcessingStatusItem,
    ReviewMissRequest,
    TriggerRunResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/summary", response_model=InboxAuditSummary)
async def get_audit_summary(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> InboxAuditSummary:
    data = await crud.get_summary(db, days=days)
    return InboxAuditSummary(**data)


@router.get("/runs", response_model=InboxAuditRunListResponse)
async def list_audit_runs(
    days: int = Query(30, ge=1, le=90),
    inbox_id: Optional[str] = None,
    skip: int = 0,
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> InboxAuditRunListResponse:
    items, total = await crud.list_runs(
        db, days=days, inbox_id=inbox_id, skip=skip, limit=limit
    )
    return InboxAuditRunListResponse(items=items, total=total)


@router.get("/misses", response_model=InboxAuditMissListResponse)
async def list_audit_misses(
    reviewed: Optional[bool] = None,
    state: Optional[str] = None,
    inbox_id: Optional[str] = None,
    days: int = Query(30, ge=1, le=90),
    skip: int = 0,
    limit: int = Query(200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> InboxAuditMissListResponse:
    items, total = await crud.list_misses(
        db,
        reviewed=reviewed,
        state=state,
        inbox_id=inbox_id,
        days=days,
        skip=skip,
        limit=limit,
    )
    return InboxAuditMissListResponse(items=items, total=total)


@router.post("/misses/{miss_id}/review", response_model=InboxAuditMissResponse)
async def review_audit_miss(
    miss_id: UUID,
    payload: ReviewMissRequest,
    db: AsyncSession = Depends(get_db),
) -> InboxAuditMissResponse:
    miss = await crud.mark_reviewed(
        db,
        miss_id=miss_id,
        reviewed_by=payload.reviewed_by,
        notes=payload.notes,
    )
    if not miss:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Miss not found")
    return miss


@router.post("/run", response_model=TriggerRunResponse)
async def trigger_audit_run(
    lookback_hours: Optional[int] = Query(None, ge=1, le=168),
) -> TriggerRunResponse:
    """Manually trigger an audit fan-out across all Front inboxes."""
    from app.tasks.inbox_audit import audit_all_inboxes

    effective_lookback_hours = lookback_hours or settings.INBOX_AUDIT_LOOKBACK_HOURS
    result = audit_all_inboxes.delay(lookback_hours=effective_lookback_hours)
    return TriggerRunResponse(
        status="queued",
        task_id=result.id,
        message=f"Audit fan-out queued (lookback {effective_lookback_hours}h).",
    )


@router.post("/misses/{miss_id}/queue-processing", response_model=QueueProcessingResponse)
async def queue_miss_processing(
    miss_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> QueueProcessingResponse:
    """Queue recovery processing for one audit miss conversation."""
    miss = await crud.get_miss(db, miss_id=miss_id)
    if not miss:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Miss not found")

    from app.tasks.inbox_audit import queue_conversation_for_processing

    result = queue_conversation_for_processing.apply_async(
        args=[miss.conversation_id],
        queue="processing",
    )
    return QueueProcessingResponse(
        status="queued",
        queued_count=1,
        task_ids=[result.id],
        conversation_ids=[miss.conversation_id],
        message=f"Queued processing for {miss.conversation_id}.",
    )


@router.post("/misses/queue-processing/status", response_model=QueueProcessingStatusResponse)
async def get_queue_processing_status(
    payload: QueueProcessingStatusRequest,
) -> QueueProcessingStatusResponse:
    """Return live status for a batch of queued inbox audit recovery tasks."""
    from celery.result import AsyncResult

    from app.tasks.worker import celery_app

    items = []
    processed = 0
    failed = 0
    failed_conversation_ids = []

    for task in payload.tasks:
        result = AsyncResult(task.task_id, app=celery_app)
        state = result.state
        task_status = "pending"
        error_message = None

        if state == "SUCCESS":
            value = result.result if isinstance(result.result, dict) else {}
            if value.get("status") == "error":
                task_status = "failed"
                error_message = value.get("message") or "Recovery task failed"
                failed += 1
                failed_conversation_ids.append(task.conversation_id)
            else:
                process_task_id = value.get("process_task_id")
                if process_task_id:
                    process_result = AsyncResult(process_task_id, app=celery_app)
                    state = f"RECOVERY_SUCCESS/{process_result.state}"
                    if process_result.state == "SUCCESS":
                        task_status = "processed"
                        processed += 1
                    elif process_result.state in {"FAILURE", "REVOKED"}:
                        task_status = "failed"
                        error_message = (
                            str(process_result.result)
                            if process_result.result
                            else process_result.state
                        )
                        failed += 1
                        failed_conversation_ids.append(task.conversation_id)
                else:
                    task_status = "processed"
                    processed += 1
        elif state in {"FAILURE", "REVOKED"}:
            task_status = "failed"
            error_message = str(result.result) if result.result else state
            failed += 1
            failed_conversation_ids.append(task.conversation_id)

        items.append(
            QueueProcessingStatusItem(
                task_id=task.task_id,
                conversation_id=task.conversation_id,
                state=state,
                status=task_status,
                error_message=error_message,
            )
        )

    total_queued = len(payload.tasks)
    pending = max(0, total_queued - processed - failed)
    return QueueProcessingStatusResponse(
        total_queued=total_queued,
        processed=processed,
        failed=failed,
        pending=pending,
        failed_conversation_ids=failed_conversation_ids,
        items=items,
    )


@router.post("/misses/queue-processing", response_model=QueueProcessingResponse)
async def queue_all_open_misses_processing(
    limit: int = Query(5000, ge=1, le=10000),
    dispatch_interval_seconds: float = Query(5.0, ge=0.5, le=300),
    db: AsyncSession = Depends(get_db),
) -> QueueProcessingResponse:
    """Queue recovery processing for distinct open audit miss conversations.

    Bulk recovery is deliberately paced because each recovery task calls Front.
    """
    conversation_ids = await crud.list_open_miss_conversation_ids(db, limit=limit)
    if not conversation_ids:
        return QueueProcessingResponse(
            status="empty",
            queued_count=0,
            task_ids=[],
            conversation_ids=[],
            message="No open miss conversations to queue.",
        )

    from app.tasks.inbox_audit import queue_conversation_for_processing

    task_ids = []
    for index, conversation_id in enumerate(conversation_ids):
        result = queue_conversation_for_processing.apply_async(
            args=[conversation_id],
            queue="processing",
            countdown=index * dispatch_interval_seconds,
        )
        task_ids.append(result.id)

    total_delay_seconds = max(0.0, (len(conversation_ids) - 1) * dispatch_interval_seconds)
    return QueueProcessingResponse(
        status="queued",
        queued_count=len(conversation_ids),
        task_ids=task_ids,
        conversation_ids=conversation_ids,
        message=(
            f"Queued processing for {len(conversation_ids)} open miss conversation(s), "
            f"spaced {dispatch_interval_seconds:g}s apart over about "
            f"{total_delay_seconds / 60:.1f} minute(s)."
        ),
    )
