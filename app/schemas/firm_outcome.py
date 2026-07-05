"""Pydantic schemas for firm outcome feedback and attribution."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


FirmOutcomeEvent = Literal[
    "contacted",
    "replied",
    "booked",
    "qualified",
    "won",
    "lost",
    "unsubscribed",
]
FirmOutcomeChannel = Literal["email", "call"]


class FirmOutcomeIn(BaseModel):
    idempotency_key: str = Field(..., min_length=1, max_length=200)
    event: FirmOutcomeEvent
    occurred_at: Optional[datetime] = None
    channel: FirmOutcomeChannel
    detail: Dict[str, Any] = Field(default_factory=dict)
    firm_event_id: Optional[UUID] = None
    attribution_snapshot: Dict[str, Any] = Field(default_factory=dict)

    alias_type: Optional[str] = None
    alias_value: Optional[str] = None
    website: Optional[str] = None
    domain: Optional[str] = None
    email: Optional[str] = None
    legacy_pif_id: Optional[str] = None

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


class FirmOutcomeRead(BaseModel):
    id: UUID
    firm_id: UUID
    event: FirmOutcomeEvent
    occurred_at: datetime
    channel: FirmOutcomeChannel
    detail: Dict[str, Any] = Field(default_factory=dict)
    firm_event_id: Optional[UUID] = None
    attribution_snapshot: Dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FirmOutcomeResponse(BaseModel):
    outcome: FirmOutcomeRead
    created: bool
    matched_by: str
    matched_value: str


class AttributionMetric(BaseModel):
    total_count: int
    booked_or_qualified_count: int
    booked_or_qualified_rate: float


class TriggerAttributionBucket(AttributionMetric):
    trigger_type: str


class FieldPresenceAttribution(BaseModel):
    field: str
    present: AttributionMetric
    absent: AttributionMetric


class FirmAttributionResponse(BaseModel):
    by_trigger_type: List[TriggerAttributionBucket] = Field(default_factory=list)
    by_core_field_presence: List[FieldPresenceAttribution] = Field(default_factory=list)
