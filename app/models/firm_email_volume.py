"""Cached monthly email volume per firm."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FirmEmailMonthlyVolume(Base):
    """Monthly count of stored email messages linked to a firm."""

    __tablename__ = "firm_email_monthly_volume"
    __table_args__ = (
        UniqueConstraint("firm_id", "month", name="uq_firm_email_monthly_volume_firm_month"),
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
    month: Mapped[date] = mapped_column(
        Date, nullable=False, index=True, comment="First day of the UTC calendar month"
    )
    email_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    firm = relationship("PifInfo", back_populates="email_monthly_volume")
