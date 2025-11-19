"""Classification trace model for debugging email classification."""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, String, Integer, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClassificationTrace(Base):
    """Model for tracking classification workflow steps and LLM interactions."""

    __tablename__ = "classification_trace"

    # Primary identification
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    front_conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    email_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )

    # Classification step identification
    step_name: Mapped[str] = mapped_column(String(200), nullable=False)  # e.g., "ROOT", "ROOT_SCHEDULING"
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)  # Sequence in hierarchy
    classification_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # e.g., "Scheduling → RX"

    # LLM interaction details
    llm_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # e.g., "gpt-4o"
    prompt_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # The rule prompt used
    full_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Complete prompt sent to LLM
    llm_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Raw response from LLM
    chosen_option: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # The selected option

    # Email content format tracking
    email_format: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "structured_chain" or "raw_text"
    message_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Number of messages if structured

    # Timing and performance
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Token usage
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Document analysis context
    document_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Additional metadata (renamed to avoid SQLAlchemy reserved word)
    trace_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=datetime.utcnow
    )

    # Additional indexes
    __table_args__ = (
        Index('idx_classification_trace_conversation_order', 'front_conversation_id', 'step_order'),
        Index('idx_classification_trace_created_at', 'created_at'),
        Index('idx_classification_trace_email_id', 'email_id'),
    )
