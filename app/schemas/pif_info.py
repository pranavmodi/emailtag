"""Pydantic schemas for PIF (Personal Injury Firm) information."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, computed_field


class ContactPerson(BaseModel):
    """Contact person at the law firm."""
    name: str = Field(default="", description="Full name of the contact person")
    title: str = Field(default="", description="Job title or role")
    persona: Optional[str] = Field(None, description="Persona taxonomy key")
    email: str = Field(default="", description="Email address")
    phone: str = Field(default="", description="Phone number")
    extension: str = Field(default="", description="Phone extension if any")


class LeadershipMember(BaseModel):
    """Leadership team member from research."""
    name: str = Field(default="", description="Full name")
    title: str = Field(default="", description="Title/position at the firm")
    persona: Optional[str] = Field(None, description="Persona taxonomy key")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile URL")
    bio: Optional[str] = Field(None, description="Brief bio or description")
    image_url: Optional[str] = Field(None, description="Profile image URL")


class StaffMember(BaseModel):
    """Operational staff member from research."""
    name: str = Field(default="", description="Full name")
    title: str = Field(default="", description="Job title")
    role_category: str = Field(
        default="other",
        description="Role category: intake_specialist, case_manager, paralegal, office_manager, billing_coordinator, medical_records, other"
    )
    persona: Optional[str] = Field(None, description="Persona taxonomy key")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile URL")
    bio: Optional[str] = Field(None, description="Brief bio or description")


class PifInfoBase(BaseModel):
    """Base schema for PIF info."""
    firm_name: str = Field(..., description="Name of the personal injury law firm")
    entity_type: str = Field(default="pi_law_firm", description="Entity type classification")
    website: Optional[str] = Field(None, description="Firm website URL")
    canonical_website: Optional[str] = Field(None, description="Canonical registrable firm website")
    website_status: Optional[str] = Field(None, description="Website resolution status")
    website_source: Optional[str] = Field(None, description="Website resolution source")
    website_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
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
    entity_type: Optional[str] = None
    website: Optional[str] = None
    canonical_website: Optional[str] = None
    website_status: Optional[str] = None
    website_source: Optional[str] = None
    website_confidence: Optional[float] = None
    emails: Optional[List[str]] = None
    phones: Optional[List[str]] = None
    fax: Optional[str] = None
    addresses: Optional[List[str]] = None
    contacts: Optional[List[ContactPerson]] = None
    conversation_ids: Optional[List[str]] = None
    extraction_notes: Optional[str] = None


class BehavioralData(BaseModel):
    """Behavioral email analysis data for a firm."""
    total_email_count: int = 0
    monthly_email_volume: List[int] = Field(default_factory=list, description="Last 3 months oldest first")
    last_contact_date: Optional[str] = None
    days_since_last_contact: Optional[int] = None
    topic_distribution: Dict[str, int] = Field(default_factory=dict)
    primary_pain_point: Optional[str] = None
    sender_roles: Dict[str, int] = Field(default_factory=dict)
    contact_profiles: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    peak_contact_days: List[str] = Field(default_factory=list)
    after_hours_ratio: float = 0.0
    analyzed_at: Optional[str] = None


class ScoreBreakdown(BaseModel):
    """ICP score breakdown by category."""
    email_volume_score: int = 0
    email_volume_reason: str = ""
    recency_score: int = 0
    recency_reason: str = ""
    pain_signals_score: int = 0
    pain_signals_reason: str = ""
    firm_size_score: int = 0
    firm_size_reason: str = ""
    completeness_score: int = 0
    completeness_reason: str = ""
    total: int = 0
    scored_at: Optional[str] = None


class PifInfoResponse(PifInfoBase):
    """Schema for PIF info response."""
    id: UUID
    conversation_ids: List[str] = Field(default_factory=list)
    leadership: Optional[List[LeadershipMember]] = Field(None, description="Leadership team")
    research_data: Optional[Dict[str, Any]] = Field(None, description="Additional research findings")
    research_status: Optional[str] = Field(None, description="Research status")
    last_researched_at: Optional[datetime] = Field(None, description="Last research timestamp")
    staff: Optional[List[Dict[str, Any]]] = Field(None, description="Operational staff members")
    staff_research_status: Optional[str] = Field(None, description="Staff research status")
    # Behavioral intelligence
    behavioral_data: Optional[Dict[str, Any]] = Field(None, description="Email behavior analysis")
    icp_score: Optional[int] = Field(None, description="ICP score 0-100")
    icp_tier: Optional[str] = Field(None, description="ICP tier: A/B/C/D")
    score_breakdown: Optional[Dict[str, Any]] = Field(None, description="Score breakdown by category")
    icp_scored_at: Optional[datetime] = Field(None, description="When last scored")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @computed_field
    @property
    def contact_profiles(self) -> Optional[Dict[str, Any]]:
        """Expose behavioral_data.contact_profiles at top level for orchestrators."""
        if not self.behavioral_data:
            return None
        profiles = self.behavioral_data.get("contact_profiles")
        return profiles if isinstance(profiles, dict) else None


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


class FullEnrichmentStatusResponse(BaseModel):
    """Schema for full firm enrichment workflow polling."""
    task_id: str
    status: str
    message: str
    pif_id: Optional[UUID] = None
    firm_name: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class ResearchBatchRequest(BaseModel):
    """Batch research dispatch request for orchestrators."""
    limit: int = Field(10, ge=1, description="Maximum firms to queue; hard limit 25")
    kinds: List[str] = Field(
        default_factory=lambda: ["research"],
        description="Any of: research, research_staff, analyze_behavior",
    )
    order_by: str = Field("icp_score", description="Currently supports icp_score or updated_at")
    only_unresearched: bool = Field(True, description="Skip firms with completed research")


class ResearchBatchItem(BaseModel):
    """Batch dispatch result for one firm."""
    pif_id: UUID
    task_ids: Dict[str, str] = Field(default_factory=dict)


class ResearchTaskState(BaseModel):
    """Bulk research state for one queued/researched firm."""
    pif_id: UUID
    firm_name: str
    research_status: Optional[str] = None
    staff_research_status: Optional[str] = None
    behavior_status: Optional[str] = None
    icp_score: Optional[int] = None
    icp_tier: Optional[str] = None
    last_researched_at: Optional[datetime] = None
    updated_at: datetime


class ResearchStatusBulkResponse(BaseModel):
    """Bulk research polling response."""
    items: List[ResearchTaskState]
    total: int


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


class AnalyzeBehaviorResponse(BaseModel):
    """Schema for behavior analysis response."""
    pif_id: UUID
    firm_name: str
    task_id: str
    status: str = "queued"
    message: str


class AnalyzeBehaviorRequest(BaseModel):
    """Optional behavior-analysis request flags."""
    signatures: bool = Field(False, description="Run signature extraction after behavior analysis")


class BatchTaskResponse(BaseModel):
    """Schema for batch task dispatch response."""
    task_id: str
    message: str
    total: Optional[int] = None


class ScoreResponse(BaseModel):
    """Schema for synchronous ICP score response."""
    pif_id: UUID
    firm_name: str
    icp_score: int
    icp_tier: str
    score_breakdown: Dict[str, Any]


class PersonSearchResult(BaseModel):
    """A person found across leadership/staff data."""
    name: str
    title: str
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin: Optional[str] = None
    bio: Optional[str] = None
    role_category: Optional[str] = None
    persona: Optional[str] = None
    source: str  # 'leadership' or 'staff'
    firm_id: str
    firm_name: str
    firm_website: Optional[str] = None


class PeopleSearchResponse(BaseModel):
    """Response for people search endpoint."""
    results: List[PersonSearchResult]
    total: int
    page: int
    page_size: int
    total_pages: int


class AnalyticsSummaryResponse(BaseModel):
    """Schema for analytics summary across all firms."""
    total_firms_tracked: int
    firms_by_tier: Dict[str, int]
    firms_by_entity_type: Dict[str, int] = Field(default_factory=dict)
    top_pain_points: List[Dict[str, Any]]
    avg_monthly_volume_by_tier: Dict[str, float]
    pipeline_funnel: Dict[str, int]
    firms_contacted_last_30_days: int
    firms_needing_recontact: int


class LeadershipEmailHistoryResponse(BaseModel):
    """Schema for leadership email history analysis response."""
    pif_id: UUID
    firm_name: str
    task_id: str
    status: str = "queued"
    message: str
