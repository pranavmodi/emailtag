"""Core firm trigger event creation, deduplication, and delivery hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.firm_event import FirmEvent


@dataclass(frozen=True)
class FirmEventCandidate:
    firm_id: UUID
    event_type: str
    occurred_at: datetime
    source: str
    detail: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    dedup_key: str = ""


def build_dedup_key(
    *,
    source: str,
    event_type: str,
    firm_id: UUID,
    material: str,
) -> str:
    return f"{source}:{event_type}:{firm_id}:{material}".lower()


async def create_firm_event(
    db: AsyncSession,
    candidate: FirmEventCandidate,
) -> tuple[FirmEvent, bool]:
    existing = await get_event_by_dedup_key(db, candidate.dedup_key)
    if existing:
        return existing, False

    event = FirmEvent(
        firm_id=candidate.firm_id,
        event_type=candidate.event_type,
        occurred_at=candidate.occurred_at,
        source=candidate.source,
        detail=candidate.detail,
        score=candidate.score,
        dedup_key=candidate.dedup_key,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event, True


def create_firm_event_sync(
    db: Session,
    candidate: FirmEventCandidate,
) -> tuple[FirmEvent, bool]:
    existing = get_event_by_dedup_key_sync(db, candidate.dedup_key)
    if existing:
        return existing, False

    event = FirmEvent(
        firm_id=candidate.firm_id,
        event_type=candidate.event_type,
        occurred_at=candidate.occurred_at,
        source=candidate.source,
        detail=candidate.detail,
        score=candidate.score,
        dedup_key=candidate.dedup_key,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event, True


async def create_firm_events(
    db: AsyncSession,
    candidates: Iterable[FirmEventCandidate],
) -> list[tuple[FirmEvent, bool]]:
    results = []
    for candidate in candidates:
        results.append(await create_firm_event(db, candidate))
    return results


async def get_event_by_dedup_key(db: AsyncSession, dedup_key: str) -> Optional[FirmEvent]:
    result = await db.execute(select(FirmEvent).where(FirmEvent.dedup_key == dedup_key))
    return result.scalars().first()


def get_event_by_dedup_key_sync(db: Session, dedup_key: str) -> Optional[FirmEvent]:
    return db.execute(select(FirmEvent).where(FirmEvent.dedup_key == dedup_key)).scalars().first()


async def list_recent_events_for_firm(
    db: AsyncSession,
    firm_id: UUID,
    *,
    limit: int = 50,
    mark_delivered: bool = True,
) -> list[FirmEvent]:
    result = await db.execute(
        select(FirmEvent)
        .where(FirmEvent.firm_id == firm_id)
        .order_by(FirmEvent.occurred_at.desc(), FirmEvent.created_at.desc())
        .limit(limit)
    )
    events = list(result.scalars().all())
    if mark_delivered:
        now = datetime.utcnow()
        changed = False
        for event in events:
            if event.delivered_at is None:
                event.delivered_at = now
                changed = True
        if changed:
            await db.commit()
            for event in events:
                await db.refresh(event)
    return events


def queue_push_delivery_hook(event: FirmEvent) -> None:
    """Phase-2 placeholder for webhook delivery to possibleos."""
    return None
