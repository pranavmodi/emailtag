"""Outreach pipeline model for PIF (Personal Injury Firm) management."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PifOutreachPipeline(Base):
    """Model for tracking outreach pipeline records for PI law firms."""

    __tablename__ = "pif_outreach_pipeline"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    pif_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pif_info.id", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="FK to pif_info"
    )

    contact_name: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="Name of the contact person being reached out to"
    )

    contact_linkedin: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="LinkedIn URL of the contact"
    )

    contact_email: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True,
        comment="Email of the contact"
    )

    outreach_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Type: linkedin_connection, linkedin_inmail, email, referral"
    )

    sender_persona: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True,
        comment="Sender persona: pranav or neha"
    )

    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="not_started",
        comment="Status: not_started, sent, replied, meeting_booked, closed_won, closed_lost"
    )

    message_variant: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Message variant used: shortPranav, longNeha, etc."
    )

    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="When the message was sent"
    )

    replied_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="When they replied"
    )

    notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Freeform notes about this outreach"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False,
        comment="When the record was created"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
        comment="When the record was last updated"
    )

    pif: Mapped["PifInfo"] = relationship(  # type: ignore[name-defined]
        "PifInfo", back_populates="outreach_pipeline"
    )

    def __repr__(self) -> str:
        return f"<PifOutreachPipeline(id={self.id}, pif_id={self.pif_id}, status='{self.status}')>"
