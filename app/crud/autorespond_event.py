"""CRUD operations for autorespond event tracking."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import ARRAY, String, and_, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.autorespond_event import AutorespondEvent
from app.models.pif_info import PifInfo

logger = logging.getLogger(__name__)


def resolve_pif_for_sender(db: Session, sender_email: str) -> Optional[Dict[str, Any]]:
    """
    Resolve a sender email to a PIF firm (sync, for Celery tasks).

    Tries in order:
    1. Exact match in pif_info.emails array
    2. Domain match against pif_info.website
    3. Email match in contacts JSONB

    Returns dict with pif_id, firm_name, contact_name or None.
    """
    if not sender_email:
        return None

    sender_lower = sender_email.lower().strip()

    # 1. Exact email match in the emails array
    result = db.query(PifInfo).filter(
        PifInfo.emails.any(sender_lower)
    ).first()
    if result:
        # Try to find the contact name
        contact_name = _find_contact_name(result, sender_lower)
        return {
            "pif_id": result.id,
            "firm_name": result.firm_name,
            "contact_name": contact_name,
        }

    # 2. Domain match against website
    domain = sender_lower.split("@")[-1] if "@" in sender_lower else None
    if domain:
        result = db.query(PifInfo).filter(
            func.lower(PifInfo.website).contains(domain)
        ).first()
        if result:
            contact_name = _find_contact_name(result, sender_lower)
            return {
                "pif_id": result.id,
                "firm_name": result.firm_name,
                "contact_name": contact_name,
            }

    # 3. Search contacts JSONB for email match
    result = db.query(PifInfo).filter(
        text("EXISTS (SELECT 1 FROM jsonb_array_elements(pif_info.contacts) AS c WHERE lower(c->>'email') = :email)")
    ).params(email=sender_lower).first()
    if result:
        contact_name = _find_contact_name(result, sender_lower)
        return {
            "pif_id": result.id,
            "firm_name": result.firm_name,
            "contact_name": contact_name,
        }

    return None


def _find_contact_name(pif: PifInfo, sender_email: str) -> Optional[str]:
    """Find the contact name matching an email in a PIF record."""
    for contact in (pif.contacts or []):
        if isinstance(contact, dict) and contact.get("email", "").lower() == sender_email:
            return contact.get("name")
    for leader in (pif.leadership or []):
        if isinstance(leader, dict) and (leader.get("email") or "").lower() == sender_email:
            return leader.get("name")
    for staff in (pif.staff or []):
        if isinstance(staff, dict) and (staff.get("email") or "").lower() == sender_email:
            return staff.get("name")
    return None


def create_event_sync(
    db: Session,
    *,
    pif_id: Optional[UUID],
    firm_name: Optional[str],
    agent_type: str,
    contact_email: str,
    contact_name: Optional[str],
    conversation_id: str,
    email_subject: Optional[str],
    tags: List[str],
    response_sent: bool,
    test_mode: bool,
    details: Optional[Dict[str, Any]] = None,
) -> AutorespondEvent:
    """Create an autorespond event record (sync, for Celery tasks)."""
    event = AutorespondEvent(
        pif_id=pif_id,
        firm_name=firm_name,
        agent_type=agent_type,
        contact_email=contact_email,
        contact_name=contact_name,
        conversation_id=conversation_id,
        email_subject=email_subject,
        tags=tags or [],
        response_sent=response_sent,
        test_mode=test_mode,
        details=details,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


async def list_events(
    db: AsyncSession,
    *,
    pif_id: Optional[UUID] = None,
    agent_type: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    test_mode: Optional[bool] = None,
    skip: int = 0,
    limit: int = 20,
) -> tuple[List[AutorespondEvent], int]:
    """List autorespond events with filters and pagination."""
    query = select(AutorespondEvent)
    count_query = select(func.count(AutorespondEvent.id))

    filters = []
    if pif_id:
        filters.append(AutorespondEvent.pif_id == pif_id)
    if agent_type:
        filters.append(AutorespondEvent.agent_type == agent_type)
    if test_mode is not None:
        filters.append(AutorespondEvent.test_mode == test_mode)
    if search:
        search_term = f"%{search.lower()}%"
        filters.append(
            func.lower(AutorespondEvent.firm_name).like(search_term)
            | func.lower(AutorespondEvent.contact_email).like(search_term)
            | func.lower(AutorespondEvent.email_subject).like(search_term)
        )
    if date_from:
        try:
            dt_from = datetime.strptime(date_from, "%Y-%m-%d")
            filters.append(AutorespondEvent.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            filters.append(AutorespondEvent.created_at < dt_to)
        except ValueError:
            pass

    if filters:
        combined = and_(*filters)
        query = query.where(combined)
        count_query = count_query.where(combined)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(AutorespondEvent.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    return items, total


async def get_summary(db: AsyncSession) -> Dict[str, Any]:
    """Get aggregate summary of autorespond events."""
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    # Total
    total_result = await db.execute(select(func.count(AutorespondEvent.id)))
    total = total_result.scalar() or 0

    # Today
    today_result = await db.execute(
        select(func.count(AutorespondEvent.id)).where(
            AutorespondEvent.created_at >= today_start
        )
    )
    events_today = today_result.scalar() or 0

    # This week
    week_result = await db.execute(
        select(func.count(AutorespondEvent.id)).where(
            AutorespondEvent.created_at >= week_start
        )
    )
    events_this_week = week_result.scalar() or 0

    # By agent type
    type_result = await db.execute(
        select(AutorespondEvent.agent_type, func.count(AutorespondEvent.id))
        .group_by(AutorespondEvent.agent_type)
    )
    by_agent_type = {row[0]: row[1] for row in type_result.fetchall()}

    # By day (last 30 days)
    thirty_days_ago = now - timedelta(days=30)
    day_result = await db.execute(
        select(
            func.date_trunc("day", AutorespondEvent.created_at).label("day"),
            func.count(AutorespondEvent.id),
        )
        .where(AutorespondEvent.created_at >= thirty_days_ago)
        .group_by("day")
        .order_by("day")
    )
    by_day = [
        {"date": row[0].strftime("%Y-%m-%d"), "count": row[1]}
        for row in day_result.fetchall()
    ]

    # Top firms (top 10 by count)
    firm_result = await db.execute(
        select(
            AutorespondEvent.firm_name,
            AutorespondEvent.pif_id,
            func.count(AutorespondEvent.id).label("cnt"),
        )
        .where(AutorespondEvent.firm_name.is_not(None))
        .group_by(AutorespondEvent.firm_name, AutorespondEvent.pif_id)
        .order_by(func.count(AutorespondEvent.id).desc())
        .limit(10)
    )
    top_firms = [
        {
            "firm_name": row[0],
            "pif_id": str(row[1]) if row[1] else None,
            "count": row[2],
        }
        for row in firm_result.fetchall()
    ]

    return {
        "total_events": total,
        "events_today": events_today,
        "events_this_week": events_this_week,
        "by_agent_type": by_agent_type,
        "by_day": by_day,
        "top_firms": top_firms,
    }
