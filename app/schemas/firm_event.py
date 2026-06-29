"""Pydantic schemas for firm trigger events and sensor ingest."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.firm_event import FIRM_EVENT_TYPES


FirmEventType = Literal[
    "new_referral",
    "records_surge",
    "became_warm",
    "went_quiet",
    "first_interaction",
    "new_decision_maker",
    "vendor_detected",
    "vendor_changed",
    "link_opened",
    "link_clicked",
    "job_posting",
    "pe_backed",
    "new_office",
    "news_mention",
]


class FirmEventRead(BaseModel):
    id: UUID
    firm_id: UUID
    event_type: FirmEventType
    occurred_at: datetime
    source: str
    detail: Dict[str, Any] = Field(default_factory=dict)
    score: float
    dedup_key: str
    delivered_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FirmEventListResponse(BaseModel):
    firm_id: UUID
    items: List[FirmEventRead]
    total: int


class ExternalFirmSignalIn(BaseModel):
    vendor: str = Field(..., min_length=1, max_length=80)
    signal_type: FirmEventType
    occurred_at: Optional[datetime] = None
    score: float = Field(50.0, ge=0.0, le=100.0)
    dedup_key: Optional[str] = Field(None, max_length=500)
    detail: Dict[str, Any] = Field(default_factory=dict)

    alias_type: Optional[str] = None
    alias_value: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    email: Optional[str] = None
    legacy_pif_id: Optional[str] = None

    @field_validator("vendor")
    @classmethod
    def normalize_vendor(cls, value: str) -> str:
        normalized = value.strip().lower().replace(" ", "_")
        if ":" in normalized:
            raise ValueError("vendor must not contain ':'")
        return normalized

    @field_validator("signal_type")
    @classmethod
    def ensure_external_or_engagement_signal(cls, value: str) -> str:
        allowed = {
            "job_posting",
            "pe_backed",
            "new_office",
            "news_mention",
            "link_opened",
            "link_clicked",
        }
        if value not in allowed:
            raise ValueError(
                "external ingest accepts job_posting, pe_backed, new_office, "
                "news_mention, link_opened, or link_clicked"
            )
        return value

    @field_validator("alias_type")
    @classmethod
    def ensure_supported_alias_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        allowed = {
            "legacy_pif_id",
            "domain",
            "alt_domain",
            "email_domain",
            "vanity_domain",
            "firm_name_fuzzy",
        }
        if value not in allowed:
            raise ValueError(f"alias_type must be one of {sorted(allowed)}")
        return value


class ExternalFirmSignalResponse(BaseModel):
    event: FirmEventRead
    created: bool
    matched_by: str
    matched_value: str


class FirmEventCatalogResponse(BaseModel):
    event_types: List[str] = Field(default_factory=lambda: list(FIRM_EVENT_TYPES))
    sources: List[str] = Field(default_factory=lambda: ["precise_stream", "engagement", "external:<vendor>"])
