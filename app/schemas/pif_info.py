"""Pydantic schemas for PIF (Personal Injury Firm) information."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ContactPerson(BaseModel):
    """Contact person at the law firm."""
    name: str = Field(default="", description="Full name of the contact person")
    title: str = Field(default="", description="Job title or role")
    email: str = Field(default="", description="Email address")
    phone: str = Field(default="", description="Phone number")
    extension: str = Field(default="", description="Phone extension if any")


class PifInfoBase(BaseModel):
    """Base schema for PIF info."""
    firm_name: str = Field(..., description="Name of the personal injury law firm")
    website: Optional[str] = Field(None, description="Firm website URL")
    emails: List[str] = Field(default_factory=list, description="Email addresses")
    phones: List[str] = Field(default_factory=list, description="Phone numbers")
    fax: Optional[str] = Field(None, description="Fax number")
    addresses: List[str] = Field(default_factory=list, description="Physical addresses")
    contacts: List[ContactPerson] = Field(default_factory=list, description="Contact persons")
    extraction_notes: Optional[str] = Field(None, description="Notes from extraction")


class PifInfoCreate(PifInfoBase):
    """Schema for creating PIF info."""
    conversation_ids: List[str] = Field(default_factory=list, description="Front conversation IDs")


class PifInfoUpdate(BaseModel):
    """Schema for updating PIF info."""
    firm_name: Optional[str] = None
    website: Optional[str] = None
    emails: Optional[List[str]] = None
    phones: Optional[List[str]] = None
    fax: Optional[str] = None
    addresses: Optional[List[str]] = None
    contacts: Optional[List[ContactPerson]] = None
    conversation_ids: Optional[List[str]] = None
    extraction_notes: Optional[str] = None


class PifInfoResponse(PifInfoBase):
    """Schema for PIF info response."""
    id: UUID
    conversation_ids: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PifInfoListResponse(BaseModel):
    """Schema for list of PIF info."""
    items: List[PifInfoResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PifInfoSearchParams(BaseModel):
    """Schema for PIF info search parameters."""
    search: Optional[str] = Field(None, description="Search term for firm name, email, or website")
    page: int = Field(1, ge=1, description="Page number")
    page_size: int = Field(20, ge=1, le=100, description="Items per page")


class ProcessDayRequest(BaseModel):
    """Schema for processing a day's conversations."""
    target_date: str = Field(..., description="Date to process (YYYY-MM-DD format)")


class ProcessDayResponse(BaseModel):
    """Schema for process day response."""
    date: str
    total_conversations: int
    processed: int
    firms_found: int
    firms_updated: int
    firms_created: int
    errors: List[str] = Field(default_factory=list)
