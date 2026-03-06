"""Pydantic schemas for PIF outreach pipeline."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PipelineRecordCreate(BaseModel):
    """Schema for creating a pipeline record."""
    pif_id: UUID = Field(..., description="PIF firm ID")
    contact_name: Optional[str] = Field(None, max_length=200)
    contact_linkedin: Optional[str] = Field(None, max_length=500)
    contact_email: Optional[str] = Field(None, max_length=200)
    outreach_type: str = Field(..., description="linkedin_connection / linkedin_inmail / email / referral")
    sender_persona: Optional[str] = Field(None, description="pranav or neha")
    status: str = Field(default="not_started")
    message_variant: Optional[str] = Field(None, max_length=50)
    sent_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    notes: Optional[str] = None


class PipelineRecordUpdate(BaseModel):
    """Schema for updating a pipeline record."""
    contact_name: Optional[str] = None
    contact_linkedin: Optional[str] = None
    contact_email: Optional[str] = None
    outreach_type: Optional[str] = None
    sender_persona: Optional[str] = None
    status: Optional[str] = None
    message_variant: Optional[str] = None
    sent_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    notes: Optional[str] = None


class PipelineRecordResponse(BaseModel):
    """Schema for pipeline record response."""
    id: UUID
    pif_id: UUID
    contact_name: Optional[str] = None
    contact_linkedin: Optional[str] = None
    contact_email: Optional[str] = None
    outreach_type: str
    sender_persona: Optional[str] = None
    status: str
    message_variant: Optional[str] = None
    sent_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PipelineListResponse(BaseModel):
    """Schema for list of pipeline records."""
    items: List[PipelineRecordResponse]
    total: int
