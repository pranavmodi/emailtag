"""Outcome feedback model for firm intelligence attribution."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


FIRM_OUTCOME_EVENTS = (
    "contacted",
    "replied",
    "booked",
    "qualified",
    "won",
    "lost",
    "unsubscribed",
)

FIRM_OUTCOME_CHANNELS = ("email", "call")
POSITIVE_OUTCOME_EVENTS = ("booked", "qualified", "won")


class FirmOutcome(Base):
    """Client-reported GTM outcome linked to the outreach-time signal snapshot."""

    __tablename__ = "firm_outcome"
    __table_args__ = (
        CheckConstraint(
            "event IN ("
            "'contacted', 'replied', 'booked', 'qualified', 'won', "
            "'lost', 'unsubscribed')",
            name="ck_firm_outcome_event",
        ),
        CheckConstraint(
            "channel IN ('email', 'call')",
            name="ck_firm_outcome_channel",
        ),
        UniqueConstraint("idempotency_key", name="uq_firm_outcome_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pif_info.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    detail: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    firm_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("firm_event.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    attribution_snapshot: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    firm = relationship("PifInfo", back_populates="outcomes")
    firm_event = relationship("FirmEvent", back_populates="outcomes")
