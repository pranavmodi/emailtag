"""Pydantic schemas for the v2 firm intelligence contract."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FirmAliases(BaseModel):
    legacy_pif_ids: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    vanity_domains: List[str] = Field(default_factory=list)


class FirmIdentity(BaseModel):
    metro: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    size_hint: Optional[str] = None
    icp_tier: Optional[str] = None
    case_mix: Dict[str, Any] = Field(default_factory=dict)
    value_tier: Optional[str] = None
    volume_proxy: Optional[int] = None


class FirmPersonFreshness(BaseModel):
    last_seen_at: Optional[datetime] = None
    source: Optional[str] = None


class FirmPerson(BaseModel):
    person_id: UUID
    name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    persona: Optional[str] = None
    is_decision_maker: bool = False
    freshness: FirmPersonFreshness = Field(default_factory=FirmPersonFreshness)
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class FirmRelationship(BaseModel):
    warm_score_neutral: Optional[float] = None
    trajectory: Optional[str] = None
    last_referral_at: Optional[datetime] = None
    last_records_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    monthly_email_volume: List[int] = Field(default_factory=list)
    total_email_count: int = 0
    inbox_breakdown: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    autorespond_seen: bool = False


class FirmBehavior(BaseModel):
    primary_pain_point: Optional[str] = None
    topic_distribution: Dict[str, int] = Field(default_factory=dict)
    sender_roles: Dict[str, int] = Field(default_factory=dict)
    after_hours_ratio: float = 0.0
    peak_contact_days: List[str] = Field(default_factory=list)


class VendorEvidence(BaseModel):
    signal: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class VendorStack(BaseModel):
    case_mgmt: Optional[str] = None
    other: Dict[str, Any] = Field(default_factory=dict)
    evidence: List[VendorEvidence] = Field(default_factory=list)


class FirmIcp(BaseModel):
    score: Optional[int] = None
    tier: Optional[str] = None
    score_breakdown: Dict[str, Any] = Field(default_factory=dict)


class FirmResearch(BaseModel):
    summary: Optional[str] = None
    practice_areas: List[str] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    research_status: Optional[str] = None
    last_researched_at: Optional[datetime] = None


class FirmProvenance(BaseModel):
    profile_version: int = 1
    refined_at: Optional[datetime] = None
    raw_observed_through: Optional[datetime] = None
    freshness_age_hours: Optional[float] = None
    source: str = "emailtag"


class FirmProfile(BaseModel):
    firm_id: UUID
    canonical_website: Optional[str] = None
    website_status: Optional[str] = None
    firm_name: str
    aliases: FirmAliases = Field(default_factory=FirmAliases)
    identity: FirmIdentity = Field(default_factory=FirmIdentity)
    people: List[FirmPerson] = Field(default_factory=list)
    relationship: FirmRelationship = Field(default_factory=FirmRelationship)
    behavior: FirmBehavior = Field(default_factory=FirmBehavior)
    vendor_stack: VendorStack = Field(default_factory=VendorStack)
    icp: FirmIcp = Field(default_factory=FirmIcp)
    research: FirmResearch = Field(default_factory=FirmResearch)
    provenance: FirmProvenance = Field(default_factory=FirmProvenance)


class FirmDeltaResponse(BaseModel):
    items: List[FirmProfile]
    next_cursor: Optional[str] = None
    total: int


class FirmResolveResponse(BaseModel):
    firm_id: UUID
    matched_by: str
    matched_value: str


class FirmPeopleResponse(BaseModel):
    firm_id: UUID
    people: List[FirmPerson]


class FirmIntelHealthResponse(BaseModel):
    status: str
    total_firms: int
    coverage: Dict[str, Any] = Field(default_factory=dict)
    freshness: Dict[str, Any] = Field(default_factory=dict)
    source: str = "emailtag"
