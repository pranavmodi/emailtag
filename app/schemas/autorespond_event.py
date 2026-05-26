"""Pydantic schemas for autorespond event tracking."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AutorespondEventResponse(BaseModel):
    """Schema for a single autorespond event."""
    id: UUID
    pif_id: Optional[UUID] = None
    firm_name: Optional[str] = None
    agent_type: str
    contact_email: str
    contact_name: Optional[str] = None
    conversation_id: str
    email_subject: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    response_sent: bool = True
    test_mode: bool = False
    details: Optional[Dict[str, Any]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AutorespondEventListResponse(BaseModel):
    """Paginated list of autorespond events."""
    items: List[AutorespondEventResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AutorespondEventSummary(BaseModel):
    """Aggregate summary of autorespond activity."""
    total_events: int = 0
    events_today: int = 0
    events_this_week: int = 0
    by_agent_type: Dict[str, int] = Field(default_factory=dict)
    by_day: List[Dict[str, Any]] = Field(default_factory=list)
    top_firms: List[Dict[str, Any]] = Field(default_factory=list)
