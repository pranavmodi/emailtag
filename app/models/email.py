"""Email model for database interactions."""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, String, Table, Integer, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.patient_conversation_data import PatientConversationData # Forward reference

# Many-to-many relationship between emails and tags
email_tag_association = Table(
    "email_tag_association",
    Base.metadata,
    Column("email_id", UUID(as_uuid=True), ForeignKey("email.id"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tag.id"), primary_key=True)
)


class Email(Base):
    """Email model for database storage."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    front_conversation_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=True)
    sender: Mapped[str] = mapped_column(String, nullable=False)
    recipients: Mapped[List[str]] = mapped_column(JSON, nullable=False)
    content_text: Mapped[str] = mapped_column(String, nullable=True)
    content_html: Mapped[str] = mapped_column(String, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Add status field
    status: Mapped[str] = mapped_column(String, default="pending_initial", index=True) # e.g., pending_initial, pending_ocr, ocr_completed, processing, processed, error
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Add OCR tracking fields
    ocr_attachments_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ocr_attachments_completed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Store structured OCR results for potentially multiple attachments
    # Each item in the list should be a dict representing one attachment's results
    # e.g., [{"attachment_id": "att_123", "patient_id": "P1", "accession_nums": ["A1"], ...}, ...]
    ocr_results: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    
    # Store extracted patient IDs (from text extraction, before classification)
    # Array of patient IDs found in the email content
    extracted_patient_ids: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True, index=True)

    # Lien modification detection tracking
    lien_modification_checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lien_modifications_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lien_modification_results: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    
    # Relationships
    tags: Mapped[List["Tag"]] = relationship(
        "Tag", secondary=email_tag_association, back_populates="emails"
    )
    
    # Relationship to PatientConversationData
    # An email might be the source for multiple patient data entries if it contains multiple patient IDs
    related_patient_data: Mapped[List["PatientConversationData"]] = relationship(
        "PatientConversationData", back_populates="source_email"
    )
    
    # Relationship to processing traces
    processing_traces: Mapped[List["EmailProcessingTrace"]] = relationship(
        "EmailProcessingTrace", back_populates="email"
    )


class Tag(Base):
    """Tag model for categorizing emails."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    front_tag_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    emails: Mapped[List[Email]] = relationship(
        "Email", secondary=email_tag_association, back_populates="tags"
    ) 