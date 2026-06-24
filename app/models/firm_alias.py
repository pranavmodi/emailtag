"""Firm alias model for canonical PIF identity resolution."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


FIRM_ALIAS_TYPES = (
    "legacy_pif_id",
    "domain",
    "alt_domain",
    "email_domain",
    "vanity_domain",
    "firm_name_fuzzy",
)


class FirmAlias(Base):
    """Alias spine for stable firm identity and reversible dedup review."""

    __tablename__ = "firm_alias"
    __table_args__ = (
        CheckConstraint(
            "alias_type IN ('legacy_pif_id', 'domain', 'alt_domain', 'email_domain', "
            "'vanity_domain', 'firm_name_fuzzy')",
            name="ck_firm_alias_type",
        ),
        UniqueConstraint("alias_type", "alias_value", name="uq_firm_alias_type_value"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    alias_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    alias_value: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    firm_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pif_info.id", ondelete="CASCADE"), nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    firm = relationship("PifInfo", back_populates="aliases")
