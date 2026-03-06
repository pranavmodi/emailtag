"""Personal Injury Firm information model."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import ARRAY, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PifInfo(Base):
    """Model for tracking personal injury law firm information extracted from conversations."""

    __tablename__ = "pif_info"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    website: Mapped[Optional[str]] = mapped_column(
        String(500), unique=True, nullable=True, index=True,
        comment="Firm website URL - unique identifier when available"
    )

    firm_name: Mapped[str] = mapped_column(
        String(500), nullable=False, index=True,
        comment="Name of the personal injury law firm"
    )

    emails: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list,
        comment="All email addresses associated with the firm"
    )

    phones: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list,
        comment="All phone numbers for the firm"
    )

    fax: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Fax number if available"
    )

    addresses: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list,
        comment="All physical addresses of the firm"
    )

    contacts: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list,
        comment="Array of contact person objects with name, title, email, phone, extension"
    )

    conversation_ids: Mapped[List[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, index=True,
        comment="Front conversation IDs involving this firm"
    )

    extraction_notes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True,
        comment="Notes from extraction process"
    )

    # Research fields
    leadership: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True,
        comment="Leadership team info: name, title, email, linkedin, phone, bio"
    )

    research_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
        comment="Additional research findings: practice areas, notable cases, etc."
    )

    research_status: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Research status: pending, in_progress, completed, failed"
    )

    last_researched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="Timestamp of last research"
    )

    # Behavioral intelligence fields
    behavioral_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
        comment="Email behavior analysis: volumes, topics, sender roles, etc."
    )

    icp_score: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True,
        comment="ICP score 0-100 from deterministic scoring"
    )

    icp_tier: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, index=True,
        comment="ICP tier: A (75-100), B (50-74), C (25-49), D (0-24)"
    )

    score_breakdown: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
        comment="Detailed score breakdown by category"
    )

    icp_scored_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="Timestamp of last ICP scoring"
    )

    # Outreach pipeline relationship
    outreach_pipeline: Mapped[List["PifOutreachPipeline"]] = relationship(  # type: ignore[name-defined]
        "PifOutreachPipeline", back_populates="pif", cascade="all, delete-orphan"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False,
        comment="Timestamp when firm was first seen"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
        comment="Timestamp of last update"
    )

    def __repr__(self) -> str:
        return f"<PifInfo(id={self.id}, firm_name='{self.firm_name}', website='{self.website}')>"
