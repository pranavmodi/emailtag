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


class LeadershipMember(BaseModel):
    """Leadership team member from research."""
    name: str = Field(default="", description="Full name")
    title: str = Field(default="", description="Title/position at the firm")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile URL")
    bio: Optional[str] = Field(None, description="Brief bio or description")
    image_url: Optional[str] = Field(None, description="Profile image URL")


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
    leadership: Optional[List[LeadershipMember]] = Field(None, description="Leadership team")
    research_data: Optional[Dict[str, Any]] = Field(None, description="Additional research findings")
    research_status: Optional[str] = Field(None, description="Research status")
    last_researched_at: Optional[datetime] = Field(None, description="Last research timestamp")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ResearchResponse(BaseModel):
    """Schema for research response."""
    pif_id: UUID
    firm_name: str
    status: str
    leadership: List[LeadershipMember] = Field(default_factory=list)
    research_data: Optional[Dict[str, Any]] = None
    message: str


class ResearchStartResponse(BaseModel):
    """Schema for async research start response."""
    pif_id: UUID
    firm_name: str
    task_id: str
    status: str = "queued"
    message: str


class ResearchStatusResponse(BaseModel):
    """Schema for research status polling response."""
    pif_id: UUID
    firm_name: str
    task_id: str
    status: str  # queued, in_progress, completed, failed
    leadership: Optional[List[LeadershipMember]] = None
    research_data: Optional[Dict[str, Any]] = None
    message: str


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


class OutreachRequest(BaseModel):
    """Schema for outreach message generation request."""
    case_study_url: str
    client_description: str


class OutreachMessageResult(BaseModel):
    """Schema for outreach messages generated for a single leader."""
    name: str
    title: str
    subjectShortPranav: str
    subjectShortNeha: str
    subjectLongPranav: str
    subjectLongNeha: str
    shortPranav: str
    shortNeha: str
    longPranav: str
    longNeha: str


class OutreachResponse(BaseModel):
    """Schema for outreach generation response."""
    pif_id: UUID
    firm_name: str
    messages: List[OutreachMessageResult]
    errors: List[str] = Field(default_factory=list)


class FirmLookupRequest(BaseModel):
    """Schema for firm lookup request."""
    firm_name: str = Field(..., description="Name of the firm to search for")
    website: Optional[str] = Field(None, description="Firm website URL")
    email: Optional[str] = Field(None, description="Email address associated with the firm")
    phone: Optional[str] = Field(None, description="Phone number")
    contact_name: Optional[str] = Field(None, description="Name of a contact person")


class FirmLookupConversation(BaseModel):
    """Schema for a conversation found during firm lookup."""
    conversation_id: str
    subject: Optional[str] = None
    sender: Optional[str] = None
    created_at: Optional[str] = None
    snippet: Optional[str] = None
    source: str = Field(..., description="Source of the conversation: 'local' or 'front'")


class FirmLookupResponse(BaseModel):
    """Schema for firm lookup response."""
    matching_firms: List[PifInfoResponse] = Field(default_factory=list)
    conversations: List[FirmLookupConversation] = Field(default_factory=list)
    total_conversations: int = 0


class FirmLookupCreateRequest(BaseModel):
    """Schema for creating a firm from lookup results."""
    firm_name: str = Field(..., description="Name of the firm")
    website: Optional[str] = Field(None, description="Firm website URL")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    contact_name: Optional[str] = Field(None, description="Contact person name")
    selected_conversation_ids: List[str] = Field(default_factory=list, description="Conversation IDs to associate")
    start_research: bool = Field(False, description="Whether to start research immediately")


class FirmLookupCreateResponse(BaseModel):
    """Schema for firm lookup create response."""
    pif: PifInfoResponse
    is_new: bool
    task_id: Optional[str] = Field(None, description="Research task ID if research was started")
    message: str
