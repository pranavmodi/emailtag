"""Pydantic schemas for inbox audit."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class InboxAuditRunResponse(BaseModel):
    id: UUID
    inbox_id: str
    inbox_name: Optional[str] = None
    inbox_address: Optional[str] = None
    run_at: datetime
    lookback_start: datetime
    lookback_end: datetime
    total_received: int
    total_processed: int
    total_missed: int
    status: str
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class InboxAuditMissResponse(BaseModel):
    id: UUID
    audit_run_id: UUID
    conversation_id: str
    front_url: Optional[str] = None
    inbox_id: str
    inbox_name: Optional[str] = None
    state: str
    reason: Optional[str] = None
    subject: Optional[str] = None
    detected_at: datetime
    reviewed: bool
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class InboxAuditRunListResponse(BaseModel):
    items: List[InboxAuditRunResponse]
    total: int


class InboxAuditMissListResponse(BaseModel):
    items: List[InboxAuditMissResponse]
    total: int


class InboxAuditSummary(BaseModel):
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    open_misses: int = 0
    misses_by_day: List[dict] = Field(default_factory=list)
    misses_by_inbox: List[dict] = Field(default_factory=list)


class ReviewMissRequest(BaseModel):
    reviewed_by: Optional[str] = None
    notes: Optional[str] = None


class TriggerRunResponse(BaseModel):
    status: str
    task_id: Optional[str] = None
    message: str
