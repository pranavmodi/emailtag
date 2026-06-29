"""Firm trigger event model for the firm intelligence contract."""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


FIRM_EVENT_TYPES = (
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
)


class FirmEvent(Base):
    """Idempotent signal/moment emitted for a firm."""

    __tablename__ = "firm_event"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'new_referral', 'records_surge', 'became_warm', 'went_quiet', "
            "'first_interaction', 'new_decision_maker', 'vendor_detected', "
            "'vendor_changed', 'link_opened', 'link_clicked', 'job_posting', "
            "'pe_backed', 'new_office', 'news_mention')",
            name="ck_firm_event_type",
        ),
        CheckConstraint(
            "source IN ('precise_stream', 'engagement') OR source LIKE 'external:%'",
            name="ck_firm_event_source",
        ),
        UniqueConstraint("dedup_key", name="uq_firm_event_dedup_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pif_info.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    detail: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, index=True)
    dedup_key: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    firm = relationship("PifInfo", back_populates="events")
