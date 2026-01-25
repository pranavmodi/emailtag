"""Pydantic schemas for usage events."""

from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


class UsageEventCreate(BaseModel):
    """Schema for creating a usage event."""
    event_type: str = Field(..., description="Type of event: page_view, click, action, api_call")
    event_name: str = Field(..., description="Specific event identifier")
    page_path: Optional[str] = Field(None, description="URL path of the page")
    component: Optional[str] = Field(None, description="UI component involved")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    session_id: Optional[str] = Field(None, description="Browser session ID")
    duration_ms: Optional[int] = Field(None, description="Duration in milliseconds")


class UsageEventResponse(BaseModel):
    """Schema for usage event response."""
    id: UUID
    user_id: UUID
    username: str
    event_type: str
    event_name: str
    page_path: Optional[str]
    component: Optional[str]
    details: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    user_agent: Optional[str]
    session_id: Optional[str]
    duration_ms: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class UsageStatsResponse(BaseModel):
    """Comprehensive usage statistics response."""
    # Overall stats
    total_events: int
    total_page_views: int
    total_actions: int
    total_sessions: int
    unique_pages_visited: int

    # Time-based stats
    events_today: int
    events_this_week: int
    events_this_month: int

    # Page stats
    page_view_counts: Dict[str, int]  # page_path -> count
    most_visited_pages: List[Dict[str, Any]]  # [{page, count, last_visit}]

    # Action stats
    action_counts: Dict[str, int]  # event_name -> count
    most_common_actions: List[Dict[str, Any]]  # [{action, count, last_performed}]

    # Time spent stats
    total_time_spent_ms: int
    average_session_duration_ms: int
    time_spent_per_page: Dict[str, int]  # page_path -> total_ms

    # Activity timeline
    hourly_activity: Dict[str, int]  # hour (0-23) -> count
    daily_activity: Dict[str, int]  # date string -> count

    # Session stats
    sessions: List[Dict[str, Any]]  # [{session_id, start, end, events_count, pages_visited}]

    # Recent activity
    recent_events: List[UsageEventResponse]


class DailyActivityResponse(BaseModel):
    """Daily activity breakdown."""
    date: str
    total_events: int
    page_views: int
    actions: int
    unique_pages: int
    total_duration_ms: int
    events: List[UsageEventResponse]
