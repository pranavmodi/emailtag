"""Usage tracking API endpoints."""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Cookie
from sqlalchemy import select, func, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.usage_event import UsageEvent
from app.models.user import User
from app.models.session import Session
from app.schemas.usage_event import (
    UsageEventCreate,
    UsageEventResponse,
    UsageStatsResponse,
)

router = APIRouter()


async def get_current_user(
    session_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Get current authenticated user from session token."""
    if not session_token:
        return None

    stmt = select(Session).where(Session.session_token == session_token)
    result = await db.execute(stmt)
    session = result.scalar_one_or_none()

    if not session or session.is_expired():
        return None

    stmt = select(User).where(User.id == session.user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


@router.post("/track", response_model=UsageEventResponse)
async def track_event(
    event_data: UsageEventCreate,
    request: Request,
    session_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db)
) -> UsageEventResponse:
    """
    Track a usage event for the current user.

    This endpoint logs user interactions with the settings pages.
    Only tracks events for authenticated users.
    """
    user = await get_current_user(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Get client info
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    # Create event
    event = UsageEvent(
        id=uuid.uuid4(),
        user_id=user.id,
        username=user.username,
        event_type=event_data.event_type,
        event_name=event_data.event_name,
        page_path=event_data.page_path,
        component=event_data.component,
        details=event_data.details,
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=event_data.session_id,
        duration_ms=event_data.duration_ms,
    )

    db.add(event)
    await db.commit()
    await db.refresh(event)

    return UsageEventResponse.model_validate(event)


@router.get("/stats", response_model=UsageStatsResponse)
async def get_usage_stats(
    username: str = "admin",
    days: int = 30,
    db: AsyncSession = Depends(get_db)
) -> UsageStatsResponse:
    """
    Get comprehensive usage statistics for a user.

    Args:
        username: Username to get stats for (default: admin)
        days: Number of days to include in stats (default: 30)
    """
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start - timedelta(days=30)

    # Base query for user events
    base_filter = and_(
        UsageEvent.username == username,
        UsageEvent.created_at >= start_date
    )

    # Total events
    stmt = select(func.count(UsageEvent.id)).where(base_filter)
    result = await db.execute(stmt)
    total_events = result.scalar() or 0

    # Total page views
    stmt = select(func.count(UsageEvent.id)).where(
        and_(base_filter, UsageEvent.event_type == "page_view")
    )
    result = await db.execute(stmt)
    total_page_views = result.scalar() or 0

    # Total actions
    stmt = select(func.count(UsageEvent.id)).where(
        and_(base_filter, UsageEvent.event_type.in_(["click", "action"]))
    )
    result = await db.execute(stmt)
    total_actions = result.scalar() or 0

    # Total sessions
    stmt = select(func.count(distinct(UsageEvent.session_id))).where(
        and_(base_filter, UsageEvent.session_id.isnot(None))
    )
    result = await db.execute(stmt)
    total_sessions = result.scalar() or 0

    # Unique pages
    stmt = select(func.count(distinct(UsageEvent.page_path))).where(
        and_(base_filter, UsageEvent.page_path.isnot(None))
    )
    result = await db.execute(stmt)
    unique_pages_visited = result.scalar() or 0

    # Events today
    stmt = select(func.count(UsageEvent.id)).where(
        and_(base_filter, UsageEvent.created_at >= today_start)
    )
    result = await db.execute(stmt)
    events_today = result.scalar() or 0

    # Events this week
    stmt = select(func.count(UsageEvent.id)).where(
        and_(base_filter, UsageEvent.created_at >= week_start)
    )
    result = await db.execute(stmt)
    events_this_week = result.scalar() or 0

    # Events this month
    stmt = select(func.count(UsageEvent.id)).where(
        and_(base_filter, UsageEvent.created_at >= month_start)
    )
    result = await db.execute(stmt)
    events_this_month = result.scalar() or 0

    # Page view counts
    stmt = select(
        UsageEvent.page_path,
        func.count(UsageEvent.id).label("count")
    ).where(
        and_(base_filter, UsageEvent.event_type == "page_view", UsageEvent.page_path.isnot(None))
    ).group_by(UsageEvent.page_path)
    result = await db.execute(stmt)
    page_view_counts = {row[0]: row[1] for row in result.fetchall()}

    # Most visited pages with last visit
    stmt = select(
        UsageEvent.page_path,
        func.count(UsageEvent.id).label("count"),
        func.max(UsageEvent.created_at).label("last_visit")
    ).where(
        and_(base_filter, UsageEvent.event_type == "page_view", UsageEvent.page_path.isnot(None))
    ).group_by(UsageEvent.page_path).order_by(func.count(UsageEvent.id).desc()).limit(10)
    result = await db.execute(stmt)
    most_visited_pages = [
        {"page": row[0], "count": row[1], "last_visit": row[2].isoformat() if row[2] else None}
        for row in result.fetchall()
    ]

    # Action counts
    stmt = select(
        UsageEvent.event_name,
        func.count(UsageEvent.id).label("count")
    ).where(
        and_(base_filter, UsageEvent.event_type.in_(["click", "action"]))
    ).group_by(UsageEvent.event_name)
    result = await db.execute(stmt)
    action_counts = {row[0]: row[1] for row in result.fetchall()}

    # Most common actions
    stmt = select(
        UsageEvent.event_name,
        func.count(UsageEvent.id).label("count"),
        func.max(UsageEvent.created_at).label("last_performed")
    ).where(
        and_(base_filter, UsageEvent.event_type.in_(["click", "action"]))
    ).group_by(UsageEvent.event_name).order_by(func.count(UsageEvent.id).desc()).limit(10)
    result = await db.execute(stmt)
    most_common_actions = [
        {"action": row[0], "count": row[1], "last_performed": row[2].isoformat() if row[2] else None}
        for row in result.fetchall()
    ]

    # Time spent stats
    stmt = select(func.sum(UsageEvent.duration_ms)).where(
        and_(base_filter, UsageEvent.duration_ms.isnot(None))
    )
    result = await db.execute(stmt)
    total_time_spent_ms = result.scalar() or 0

    # Average session duration
    avg_session_duration_ms = 0
    if total_sessions > 0:
        avg_session_duration_ms = total_time_spent_ms // total_sessions

    # Time spent per page
    stmt = select(
        UsageEvent.page_path,
        func.sum(UsageEvent.duration_ms).label("total_ms")
    ).where(
        and_(base_filter, UsageEvent.duration_ms.isnot(None), UsageEvent.page_path.isnot(None))
    ).group_by(UsageEvent.page_path)
    result = await db.execute(stmt)
    time_spent_per_page = {row[0]: row[1] or 0 for row in result.fetchall()}

    # Hourly activity
    stmt = select(
        func.extract('hour', UsageEvent.created_at).label("hour"),
        func.count(UsageEvent.id).label("count")
    ).where(base_filter).group_by(func.extract('hour', UsageEvent.created_at))
    result = await db.execute(stmt)
    hourly_activity = {str(int(row[0])): row[1] for row in result.fetchall()}

    # Daily activity
    stmt = select(
        func.date(UsageEvent.created_at).label("date"),
        func.count(UsageEvent.id).label("count")
    ).where(base_filter).group_by(func.date(UsageEvent.created_at)).order_by(func.date(UsageEvent.created_at))
    result = await db.execute(stmt)
    daily_activity = {str(row[0]): row[1] for row in result.fetchall()}

    # Session details
    stmt = select(
        UsageEvent.session_id,
        func.min(UsageEvent.created_at).label("start"),
        func.max(UsageEvent.created_at).label("end"),
        func.count(UsageEvent.id).label("events_count"),
        func.count(distinct(UsageEvent.page_path)).label("pages_visited")
    ).where(
        and_(base_filter, UsageEvent.session_id.isnot(None))
    ).group_by(UsageEvent.session_id).order_by(func.max(UsageEvent.created_at).desc()).limit(20)
    result = await db.execute(stmt)
    sessions = [
        {
            "session_id": row[0],
            "start": row[1].isoformat() if row[1] else None,
            "end": row[2].isoformat() if row[2] else None,
            "events_count": row[3],
            "pages_visited": row[4]
        }
        for row in result.fetchall()
    ]

    # Recent events
    stmt = select(UsageEvent).where(base_filter).order_by(UsageEvent.created_at.desc()).limit(50)
    result = await db.execute(stmt)
    recent_events = [UsageEventResponse.model_validate(e) for e in result.scalars().all()]

    return UsageStatsResponse(
        total_events=total_events,
        total_page_views=total_page_views,
        total_actions=total_actions,
        total_sessions=total_sessions,
        unique_pages_visited=unique_pages_visited,
        events_today=events_today,
        events_this_week=events_this_week,
        events_this_month=events_this_month,
        page_view_counts=page_view_counts,
        most_visited_pages=most_visited_pages,
        action_counts=action_counts,
        most_common_actions=most_common_actions,
        total_time_spent_ms=total_time_spent_ms,
        average_session_duration_ms=avg_session_duration_ms,
        time_spent_per_page=time_spent_per_page,
        hourly_activity=hourly_activity,
        daily_activity=daily_activity,
        sessions=sessions,
        recent_events=recent_events,
    )


@router.get("/events", response_model=List[UsageEventResponse])
async def get_events(
    username: str = "admin",
    event_type: Optional[str] = None,
    page_path: Optional[str] = None,
    days: int = 7,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
) -> List[UsageEventResponse]:
    """
    Get usage events with optional filters.

    Args:
        username: Filter by username
        event_type: Filter by event type (page_view, click, action, api_call)
        page_path: Filter by page path
        days: Number of days to include
        limit: Maximum number of events to return
        offset: Number of events to skip
    """
    start_date = datetime.utcnow() - timedelta(days=days)

    filters = [
        UsageEvent.username == username,
        UsageEvent.created_at >= start_date
    ]

    if event_type:
        filters.append(UsageEvent.event_type == event_type)
    if page_path:
        filters.append(UsageEvent.page_path == page_path)

    stmt = select(UsageEvent).where(
        and_(*filters)
    ).order_by(UsageEvent.created_at.desc()).offset(offset).limit(limit)

    result = await db.execute(stmt)
    events = result.scalars().all()

    return [UsageEventResponse.model_validate(e) for e in events]
