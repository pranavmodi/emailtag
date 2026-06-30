"""Personal Injury Firm information model."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import ARRAY, CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PifInfo(Base):
    """Model for tracking personal injury law firm information extracted from conversations."""

    __tablename__ = "pif_info"
    __table_args__ = (
        CheckConstraint(
            "website_status IS NULL OR website_status IN ('resolved', 'pending', 'none')",
            name="ck_pif_info_website_status",
        ),
        CheckConstraint(
            "website_source IS NULL OR website_source IN ('email_verified', 'web_search', 'human', 'human_confirmed')",
            name="ck_pif_info_website_source",
        ),
        CheckConstraint(
            "merge_status IS NULL OR merge_status IN ('active', 'merged')",
            name="ck_pif_info_merge_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pi_law_firm", index=True,
        comment="Entity type: pi_law_firm, medical_referring, medical_facility, insurance, funding, collections, legal_other, administrative, patient_adjacent"
    )

    website: Mapped[Optional[str]] = mapped_column(
        String(500), unique=True, nullable=True, index=True,
        comment="Firm website URL - unique identifier when available"
    )

    canonical_website: Mapped[Optional[str]] = mapped_column(
        String(500), unique=True, nullable=True, index=True,
        comment="Canonical registrable website domain from firm identity resolution"
    )

    website_status: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, index=True,
        comment="Website resolution status: resolved, pending, none"
    )

    website_source: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Website resolution source: email_verified, web_search, human"
    )

    website_confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True,
        comment="Website resolution confidence from 0.0 to 1.0"
    )

    website_candidate: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="Unverified website candidate from web search, pending human review"
    )

    merged_into: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pif_info.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Surviving pif_info.id when this row has been soft-merged",
    )

    merge_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        index=True,
        comment="Soft-merge status: active or merged",
    )

    merged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="Timestamp when this row was soft-merged into another firm",
    )

    merged_from: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Provenance for records merged into this survivor",
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
        ARRAY(String), nullable=False, default=list,
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

    # Staff research fields
    staff: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True,
        comment="Operational staff: intake specialists, case managers, paralegals, etc."
    )

    staff_research_status: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="Staff research status: queued, in_progress, completed, failed"
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

    vendor_stack: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSONB, nullable=True,
        comment="Detected practice management vendors: [{vendor, source, confidence}]"
    )

    # Outreach pipeline relationship
    outreach_pipeline: Mapped[List["PifOutreachPipeline"]] = relationship(  # type: ignore[name-defined]
        "PifOutreachPipeline", back_populates="pif", cascade="all, delete-orphan"
    )

    aliases: Mapped[List["FirmAlias"]] = relationship(  # type: ignore[name-defined]
        "FirmAlias", back_populates="firm", cascade="all, delete-orphan"
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
