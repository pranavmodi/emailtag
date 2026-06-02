"""Schemas for Bill Offer intake and review."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


JsonDict = Dict[str, Any]


class BillOfferIntakeBase(BaseModel):
    front_conversation_id: str
    email_id: Optional[UUID] = None
    status: str = "pending_patient"
    patient_id: Optional[str] = None
    patient_match: Optional[JsonDict] = None
    patient_data: Optional[JsonDict] = None
    extracted_facts: Optional[JsonDict] = None
    corrected_facts: Optional[JsonDict] = None
    missing_fields: Optional[List[str]] = None
    confidence: Optional[JsonDict] = None
    original_sender_email: Optional[str] = None
    last_agent_action: Optional[str] = None
    last_run_id: Optional[str] = None
    last_agent_run_status: Optional[str] = None
    reply_draft: Optional[str] = None
    reply_sent_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class BillOfferIntakeCreate(BillOfferIntakeBase):
    pass


class BillOfferIntakeUpdate(BaseModel):
    email_id: Optional[UUID] = None
    status: Optional[str] = None
    patient_id: Optional[str] = None
    patient_match: Optional[JsonDict] = None
    patient_data: Optional[JsonDict] = None
    extracted_facts: Optional[JsonDict] = None
    corrected_facts: Optional[JsonDict] = None
    missing_fields: Optional[List[str]] = None
    confidence: Optional[JsonDict] = None
    original_sender_email: Optional[str] = None
    last_agent_action: Optional[str] = None
    last_run_id: Optional[str] = None
    last_agent_run_status: Optional[str] = None
    reply_draft: Optional[str] = None
    reply_sent_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class BillOfferIntakeResponse(BillOfferIntakeBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BillOfferCorrectionRequest(BaseModel):
    corrected_facts: JsonDict = Field(default_factory=dict)
    patient_id: Optional[str] = None
    patient_match: Optional[JsonDict] = None
    reviewed_by: Optional[str] = None


class BillOfferManualReviewRequest(BaseModel):
    reviewed_by: Optional[str] = None
    reason: Optional[str] = None


class BillOfferSendReplyRequest(BaseModel):
    reviewed_by: Optional[str] = None


class BillOfferRunAgentRequest(BaseModel):
    reviewed_by: Optional[str] = None
    send_reply: bool = False


class BillOfferReviewRequiredRequest(BaseModel):
    enabled: bool
    reviewed_by: Optional[str] = None


class BillOfferSettingsResponse(BaseModel):
    review_required: bool


class BillOfferAgentLogCreate(BaseModel):
    front_conversation_id: str
    email_id: Optional[UUID] = None
    intake_id: Optional[UUID] = None
    run_id: str
    step_name: str
    step_status: str
    input_snapshot: Optional[JsonDict] = None
    output_snapshot: Optional[JsonDict] = None
    message: Optional[str] = None
    error: Optional[str] = None


class BillOfferAgentLogResponse(BillOfferAgentLogCreate):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class BillOfferCorrectionAuditResponse(BaseModel):
    id: UUID
    front_conversation_id: str
    intake_id: UUID
    field_name: str
    previous_value: Optional[JsonDict] = None
    new_value: Optional[JsonDict] = None
    changed_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BillOfferTaggedEmailResponse(BaseModel):
    front_conversation_id: str
    email_id: UUID
    subject: Optional[str] = None
    sender: str
    received_at: datetime
    tags: List[str] = Field(default_factory=list)
    has_intake: bool = False
    intake: Optional[BillOfferIntakeResponse] = None


class BillOfferTaggedEmailListResponse(BaseModel):
    items: List[BillOfferTaggedEmailResponse]
    total: int


class BillOfferIntakeListResponse(BaseModel):
    items: List[BillOfferIntakeResponse]
    total: int


class BillOfferAgentLogListResponse(BaseModel):
    items: List[BillOfferAgentLogResponse]
    total: int


class BillOfferCorrectionAuditListResponse(BaseModel):
    items: List[BillOfferCorrectionAuditResponse]
    total: int


class BillOfferRunAgentResponse(BaseModel):
    status: str
    run_id: str
    intake: BillOfferIntakeResponse
    details: JsonDict = Field(default_factory=dict)
