"""Autorespond event tracking model."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AutorespondEvent(Base):
    """Tracks every autorespond sent out, linking it to a PIF firm when possible."""

    __tablename__ = "autorespond_event"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    pif_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pif_info.id", ondelete="SET NULL"),
        nullable=True, index=True,
        comment="Matched PIF firm (nullable if no match found)"
    )

    firm_name: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="Firm name (denormalized for display even when pif_id is null)"
    )

    agent_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="Agent that handled: apt_status_req, bill_balance_request, medical_records, psl_lien, asl_lien, missing_lien_request, case_updates, unknown_sig_lien"
    )

    contact_email: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="Sender email that triggered the autorespond"
    )

    contact_name: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="Contact name resolved from PIF contacts or email"
    )

    conversation_id: Mapped[str] = mapped_column(
        String(200), nullable=False, index=True,
        comment="Front conversation ID"
    )

    email_subject: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Subject of the triggering email"
    )

    tags: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list,
        comment="Classification tags applied to the email"
    )

    response_sent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="Whether the reply was actually sent (vs agent chose not to)"
    )

    test_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="Whether this was a sandbox/test mode response"
    )

    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
        comment="Agent result details"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True,
        comment="When the autorespond was sent"
    )

    def __repr__(self) -> str:
        return f"<AutorespondEvent(id={self.id}, agent={self.agent_type}, firm={self.firm_name}, contact={self.contact_email})>"
