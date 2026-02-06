"""Conversation log model for storing worker logs per conversation."""

import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import Column, String, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationLog(Base):
    """Model for storing log entries captured during email processing.

    Log entries are accumulated during task execution and stored as a JSONB array
    for efficient retrieval and querying. This allows viewing the same logs that
    appear in Celery worker console output through the classification-traces UI.
    """

    __tablename__ = "conversation_logs"

    # Primary identification
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Conversation/Email linkage
    front_conversation_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    email_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email.id"), nullable=True, index=True
    )

    # Log entries stored as JSONB array
    # Each entry has: {timestamp, level, module, func_name, line_no, message, extra}
    log_entries: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )

    # Summary statistics for quick filtering
    total_entries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Time range of logs
    first_log_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_log_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True, index=True
    )

    # Standard timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Additional indexes for efficient queries
    __table_args__ = (
        Index('idx_conversation_logs_last_log_at', 'last_log_at'),
        Index('idx_conversation_logs_error_count', 'error_count'),
    )

    def __repr__(self) -> str:
        return (
            f"<ConversationLog(id={self.id}, "
            f"conversation_id={self.front_conversation_id}, "
            f"entries={self.total_entries}, "
            f"errors={self.error_count})>"
        )
