"""Patient Conversation Data model for database interactions."""

import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class PatientConversationData(Base):
    """
    Stores patient-specific data extracted or relevant to a Front conversation.
    Each record is unique for a given patient_id within a specific front_conversation_id.
    """

    __tablename__ = "patient_conversation_data"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    front_conversation_id: Mapped[str] = mapped_column(
        String, 
        index=True, 
        nullable=False,
        comment="The Front conversation ID this patient data is associated with."
    )
    
    patient_id: Mapped[str] = mapped_column(
        String, 
        index=True, 
        nullable=False,
        comment="The unique identifier for the patient (e.g., PREXXXXX)."
    )
    
    # Foreign key to the specific email message that was the source of this data entry/update
    # This helps in tracing why/when this data was captured or updated.
    source_email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("email.id"), 
        nullable=False,
        index=True,
        comment="The ID of the email message from which this patient data was extracted or updated."
    )

    patient_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, 
        nullable=True,
        comment="Structured JSON data for the patient (demographics, contact, etc.)."
    )
    
    appointment_info: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB, 
        nullable=True,
        comment="Structured JSON data for appointments related to the patient in this conversation."
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, comment="Timestamp of when the record was created."
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="Timestamp of when the record was last updated."
    )

    # Relationship to the Email model (optional, for easier access if needed)
    source_email: Mapped["Email"] = relationship(back_populates="related_patient_data")

    __table_args__ = (
        UniqueConstraint('front_conversation_id', 'patient_id', name='uq_front_conversation_patient'),
    )

    def __repr__(self) -> str:
        return f"<PatientConversationData(id={self.id}, patient_id='{self.patient_id}', conversation_id='{self.front_conversation_id}')>"

# Add a back-population relationship to the Email model.
# This requires modifying the Email model in app/models/email.py
# Email.related_patient_data = relationship("PatientConversationData", back_populates="source_email") 