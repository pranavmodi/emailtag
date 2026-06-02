"""Bill Offer intake models."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BillOfferIntakeStatus:
    """Supported Phase 1 intake statuses."""

    PENDING_PATIENT = "pending_patient"
    PENDING_DETAILS = "pending_details"
    READY_FOR_PHASE_2 = "ready_for_phase_2"
    MANUAL_REVIEW = "manual_review"


class BillOfferAgentStepStatus:
    """Supported agent log step statuses."""

    STARTED = "started"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


class BillOfferIntake(Base):
    """Current state of one Bill Offer conversation."""

    __tablename__ = "bill_offer_intake"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    front_conversation_id: Mapped[str] = mapped_column(
        String(200), nullable=False, unique=True, index=True
    )
    email_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=BillOfferIntakeStatus.PENDING_PATIENT, index=True
    )

    patient_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    patient_match: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    patient_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    extracted_facts: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    corrected_facts: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    missing_fields: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    original_sender_email: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_agent_action: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    last_run_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    last_agent_run_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reply_draft: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reply_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    reviewed_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    logs: Mapped[List["BillOfferAgentLog"]] = relationship(
        "BillOfferAgentLog", back_populates="intake", cascade="all, delete-orphan"
    )
    correction_audits: Mapped[List["BillOfferCorrectionAudit"]] = relationship(
        "BillOfferCorrectionAudit", back_populates="intake", cascade="all, delete-orphan"
    )


class BillOfferAgentLog(Base):
    """Detailed step log for a Bill Offer agent run."""

    __tablename__ = "bill_offer_agent_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    front_conversation_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    email_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email.id", ondelete="SET NULL"), nullable=True, index=True
    )
    intake_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bill_offer_intake.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    step_status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    input_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    output_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    intake: Mapped[Optional["BillOfferIntake"]] = relationship(
        "BillOfferIntake", back_populates="logs"
    )


class BillOfferCorrectionAudit(Base):
    """User correction audit trail for extracted Bill Offer fields."""

    __tablename__ = "bill_offer_correction_audit"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    front_conversation_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    intake_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bill_offer_intake.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    previous_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    changed_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    intake: Mapped["BillOfferIntake"] = relationship(
        "BillOfferIntake", back_populates="correction_audits"
    )

    __table_args__ = (
        UniqueConstraint("intake_id", "field_name", "created_at", name="uq_bill_offer_audit_event"),
    )
