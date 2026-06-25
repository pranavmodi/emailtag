"""Audit records for reversible firm merges."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FirmMergeAudit(Base):
    """Durable undo record for a non-destructive firm merge."""

    __tablename__ = "firm_merge_audit"
    __table_args__ = (
        CheckConstraint(
            "status IN ('applied', 'undone')",
            name="ck_firm_merge_audit_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canonical_domain: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    survivor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pif_info.id"), nullable=False, index=True
    )
    loser_ids: Mapped[List[str]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Soft-merged pif_info ids as strings",
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="applied", index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False, default="merge")
    plan: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    before_state: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Complete pre-merge snapshot for survivor, losers, and alias rows",
    )
    after_state: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    undone_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
