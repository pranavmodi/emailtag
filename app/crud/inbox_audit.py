"""CRUD operations for inbox audit (sync for Celery, async for API)."""

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.email import Email, Tag
from app.models.inbox_audit import InboxAuditMiss, InboxAuditRun, RunStatus
from app.models.processing_trace import EmailProcessingTrace, TraceStatus


# Sync helpers (used by Celery task)


def get_processed_conversation_ids_sync(
    db: Session, conversation_ids: List[str]
) -> Tuple[set, set, set]:
    """Return audit state sets for a batch of conversation IDs.

    A conversation was stored if it has a row in `email`.
    A conversation was seen if any webhook/processing trace exists.
    A conversation was processed if it reached a downstream terminal workflow step.
    """
    if not conversation_ids:
        return set(), set(), set()

    received_rows = db.execute(
        select(Email.front_conversation_id).where(
            Email.front_conversation_id.in_(conversation_ids)
        )
    ).all()
    received = {row[0] for row in received_rows}

    trace_rows = db.execute(
        select(EmailProcessingTrace.front_conversation_id)
        .where(EmailProcessingTrace.front_conversation_id.in_(conversation_ids))
        .distinct()
    ).all()
    seen = {row[0] for row in trace_rows}

    terminal_steps = {
        "orchestration_queued_tagging",
        "autorespond_completed",
        "archive_executed",
        "front_tags_applied",
    }
    processed_rows = db.execute(
        select(EmailProcessingTrace.front_conversation_id)
        .where(EmailProcessingTrace.front_conversation_id.in_(conversation_ids))
        .where(EmailProcessingTrace.status == TraceStatus.COMPLETED)
        .where(EmailProcessingTrace.step_name.in_(terminal_steps))
        .distinct()
    ).all()
    processed = {row[0] for row in processed_rows}

    return received, seen, processed


def create_run_sync(
    db: Session,
    *,
    inbox_id: str,
    inbox_name: Optional[str],
    inbox_address: Optional[str],
    lookback_start: datetime,
    lookback_end: datetime,
    total_received: int,
    total_processed: int,
    total_missed: int,
    status: str = RunStatus.SUCCESS,
    error_message: Optional[str] = None,
) -> InboxAuditRun:
    run = InboxAuditRun(
        inbox_id=inbox_id,
        inbox_name=inbox_name,
        inbox_address=inbox_address,
        run_at=datetime.utcnow(),
        lookback_start=lookback_start,
        lookback_end=lookback_end,
        total_received=total_received,
        total_processed=total_processed,
        total_missed=total_missed,
        status=status,
        error_message=error_message,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def create_misses_sync(
    db: Session, *, audit_run_id: UUID, misses: List[Dict[str, Any]]
) -> int:
    """Bulk insert miss rows. Returns count created."""
    if not misses:
        return 0
    objs = [
        InboxAuditMiss(
            audit_run_id=audit_run_id,
            conversation_id=m["conversation_id"],
            front_url=m.get("front_url"),
            inbox_id=m["inbox_id"],
            inbox_name=m.get("inbox_name"),
            state=m["state"],
            reason=m.get("reason"),
            subject=m.get("subject"),
            detected_at=m.get("detected_at") or datetime.utcnow(),
        )
        for m in misses
    ]
    db.bulk_save_objects(objs)
    db.commit()
    return len(objs)


# Async helpers (used by API)


async def list_runs(
    db: AsyncSession,
    *,
    days: int = 30,
    inbox_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
) -> Tuple[List[InboxAuditRun], int]:
    since = datetime.utcnow() - timedelta(days=days)
    filters = [InboxAuditRun.run_at >= since]
    if inbox_id:
        filters.append(InboxAuditRun.inbox_id == inbox_id)
    combined = and_(*filters)

    total_result = await db.execute(
        select(func.count(InboxAuditRun.id)).where(combined)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(InboxAuditRun)
        .where(combined)
        .order_by(InboxAuditRun.run_at.desc(), InboxAuditRun.inbox_name)
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def list_misses(
    db: AsyncSession,
    *,
    reviewed: Optional[bool] = None,
    state: Optional[str] = None,
    inbox_id: Optional[str] = None,
    days: int = 30,
    skip: int = 0,
    limit: int = 200,
) -> Tuple[List[InboxAuditMiss], int]:
    since = datetime.utcnow() - timedelta(days=days)
    filters = [InboxAuditMiss.detected_at >= since]
    if reviewed is not None:
        filters.append(InboxAuditMiss.reviewed == reviewed)
    if state:
        filters.append(InboxAuditMiss.state == state)
    if inbox_id:
        filters.append(InboxAuditMiss.inbox_id == inbox_id)
    combined = and_(*filters)

    total_result = await db.execute(
        select(func.count(InboxAuditMiss.id)).where(combined)
    )
    total = total_result.scalar() or 0

    result = await db.execute(
        select(InboxAuditMiss)
        .where(combined)
        .order_by(InboxAuditMiss.detected_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def mark_reviewed(
    db: AsyncSession,
    *,
    miss_id: UUID,
    reviewed_by: Optional[str],
    notes: Optional[str],
) -> Optional[InboxAuditMiss]:
    result = await db.execute(select(InboxAuditMiss).where(InboxAuditMiss.id == miss_id))
    miss = result.scalar_one_or_none()
    if not miss:
        return None
    miss.reviewed = True
    miss.reviewed_by = reviewed_by
    miss.reviewed_at = datetime.utcnow()
    if notes:
        miss.notes = notes
    await db.commit()
    await db.refresh(miss)
    return miss


def build_miss_tag_counts(
    conversation_ids: Iterable[str],
    tag_rows: Iterable[Tuple[str, Optional[str]]],
) -> List[Dict[str, Any]]:
    """Count distinct missed conversations by local tag name."""
    conversations = set(conversation_ids)
    counts: Dict[str, int] = {}
    tagged_conversations = set()
    seen_pairs = set()

    for conversation_id, tag_name in tag_rows:
        if conversation_id not in conversations:
            continue
        label = tag_name or "Unknown tag"
        pair = (conversation_id, label)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        counts[label] = counts.get(label, 0) + 1
        tagged_conversations.add(conversation_id)

    no_local_tags = len(conversations - tagged_conversations)
    if no_local_tags:
        counts["No local tags"] = no_local_tags

    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


async def get_miss(db: AsyncSession, *, miss_id: UUID) -> Optional[InboxAuditMiss]:
    result = await db.execute(select(InboxAuditMiss).where(InboxAuditMiss.id == miss_id))
    return result.scalar_one_or_none()


async def list_open_miss_conversation_ids(
    db: AsyncSession, *, limit: int = 500
) -> List[str]:
    result = await db.execute(
        select(InboxAuditMiss.conversation_id)
        .where(InboxAuditMiss.reviewed.is_(False))
        .distinct()
        .order_by(InboxAuditMiss.conversation_id)
        .limit(limit)
    )
    return [row[0] for row in result.fetchall()]


async def get_summary(db: AsyncSession, *, days: int = 7) -> Dict[str, Any]:
    """Top-of-page summary: latest run, open misses, trend, and breakdowns."""
    since = datetime.utcnow() - timedelta(days=days)

    last_run_result = await db.execute(
        select(InboxAuditRun).order_by(InboxAuditRun.run_at.desc()).limit(1)
    )
    last_run = last_run_result.scalar_one_or_none()

    open_misses_result = await db.execute(
        select(func.count(InboxAuditMiss.id)).where(InboxAuditMiss.reviewed.is_(False))
    )
    open_misses = open_misses_result.scalar() or 0

    by_day_result = await db.execute(
        select(
            func.date_trunc("day", InboxAuditMiss.detected_at).label("day"),
            func.count(InboxAuditMiss.id),
        )
        .where(InboxAuditMiss.detected_at >= since)
        .group_by("day")
        .order_by("day")
    )
    misses_by_day = [
        {"date": row[0].strftime("%Y-%m-%d"), "count": row[1]}
        for row in by_day_result.fetchall()
    ]

    by_inbox_result = await db.execute(
        select(
            InboxAuditMiss.inbox_id,
            InboxAuditMiss.inbox_name,
            func.count(InboxAuditMiss.id).label("cnt"),
        )
        .where(InboxAuditMiss.detected_at >= since)
        .group_by(InboxAuditMiss.inbox_id, InboxAuditMiss.inbox_name)
        .order_by(func.count(InboxAuditMiss.id).desc())
    )
    misses_by_inbox = [
        {"inbox_id": row[0], "inbox_name": row[1], "count": row[2]}
        for row in by_inbox_result.fetchall()
    ]

    by_state_result = await db.execute(
        select(
            InboxAuditMiss.state,
            func.count(func.distinct(InboxAuditMiss.conversation_id)).label("cnt"),
        )
        .where(InboxAuditMiss.reviewed.is_(False))
        .group_by(InboxAuditMiss.state)
        .order_by(func.count(func.distinct(InboxAuditMiss.conversation_id)).desc())
    )
    misses_by_state = [
        {"state": row[0], "count": row[1]} for row in by_state_result.fetchall()
    ]

    return {
        "last_run_at": last_run.run_at if last_run else None,
        "last_run_status": last_run.status if last_run else None,
        "open_misses": open_misses,
        "misses_by_day": misses_by_day,
        "misses_by_inbox": misses_by_inbox,
        "misses_by_state": misses_by_state,
    }
