"""Inbox audit models — daily reconciliation of Front inboxes vs our DB."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MissState:
    NEVER_RECEIVED = "never_received"
    RECEIVED_BUT_FAILED = "received_but_failed"


class RunStatus:
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class InboxAuditRun(Base):
    """One row per inbox per daily audit run."""

    __tablename__ = "inbox_audit_run"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    inbox_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    inbox_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    inbox_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    run_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    lookback_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lookback_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    total_received: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_missed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(String(50), nullable=False, default=RunStatus.SUCCESS)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    misses: Mapped[list["InboxAuditMiss"]] = relationship(
        "InboxAuditMiss", back_populates="run", cascade="all, delete-orphan"
    )


class InboxAuditMiss(Base):
    """One row per missed conversation detected in an audit run."""

    __tablename__ = "inbox_audit_miss"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    audit_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inbox_audit_run.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    conversation_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    front_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    inbox_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    inbox_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    state: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    subject: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    run: Mapped["InboxAuditRun"] = relationship("InboxAuditRun", back_populates="misses")
