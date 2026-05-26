"""Inbox audit API endpoints — runs, misses, review, manual trigger."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import inbox_audit as crud
from app.db.session import get_db
from app.schemas.inbox_audit import (
    InboxAuditMissListResponse,
    InboxAuditMissResponse,
    InboxAuditRunListResponse,
    InboxAuditSummary,
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
    lookback_hours: int = Query(24, ge=1, le=168),
) -> TriggerRunResponse:
    """Manually trigger an audit fan-out across all Front inboxes."""
    from app.tasks.inbox_audit import audit_all_inboxes

    result = audit_all_inboxes.delay(lookback_hours=lookback_hours)
    return TriggerRunResponse(
        status="queued",
        task_id=result.id,
        message=f"Audit fan-out queued (lookback {lookback_hours}h).",
    )
