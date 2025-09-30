"""Processing trace model for email workflow debugging."""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy import Column, String, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EmailProcessingTrace(Base):
    """Model for tracking email processing workflow steps."""
    
    __tablename__ = "email_processing_trace"

    # Primary identification
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    front_conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    email_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email.id"), nullable=True, index=True
    )
    
    # Trace step identification
    step_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    step_type: Mapped[str] = mapped_column(String(50), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Processing context
    task_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    parent_trace_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("email_processing_trace.id"), nullable=True
    )
    
    # Status and timing
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Input and output data
    input_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    output_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    
    # Additional metadata (renamed to avoid SQLAlchemy reserved word)
    trace_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), default=datetime.utcnow
    )
    
    # Relationships
    email: Mapped[Optional["Email"]] = relationship("Email", back_populates="processing_traces")
    parent_trace: Mapped[Optional["EmailProcessingTrace"]] = relationship(
        "EmailProcessingTrace", remote_side=[id], back_populates="child_traces"
    )
    child_traces: Mapped[list["EmailProcessingTrace"]] = relationship(
        "EmailProcessingTrace", back_populates="parent_trace"
    )

    # Additional indexes defined at class level
    __table_args__ = (
        Index('idx_trace_conversation_step_order', 'front_conversation_id', 'step_order'),
        Index('idx_trace_created_at', 'created_at'),
    )


# Step type constants
class StepTypes:
    ENTRY_POINT = "entry_point"
    VALIDATION = "validation"
    EXTRACTION = "extraction"
    AI_PROCESSING = "ai_processing"
    API_CALL = "api_call"
    DATABASE = "database"
    TASK_QUEUE = "task_queue"
    BUSINESS_LOGIC = "business_logic"
    ERROR_HANDLING = "error_handling"


# Step name constants
class TraceSteps:
    # Entry points
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_PARSED = "webhook_parsed"
    WEBHOOK_VALIDATED = "webhook_validated"
    
    # Email processing
    EMAIL_CREATED = "email_created"
    CONTENT_EXTRACTED = "content_extracted"
    AUTORESPONSE_CHECK = "autoresponse_check"
    PATIENT_ID_EXTRACTION = "patient_id_extraction"
    OPENAI_PATIENT_EXTRACTION = "openai_patient_extraction"
    MCP_PATIENT_LOOKUP = "mcp_patient_lookup"
    
    # Task orchestration
    TASK_QUEUED = "task_queued"
    OCR_REQUIREMENTS_CHECK = "ocr_requirements_check"
    ATTACHMENT_PROCESSING = "attachment_processing"
    
    # AI processing
    TOPIC_SPLIT_ANALYSIS = "topic_split_analysis"
    ARCHIVE_CHECK = "archive_check"
    AI_CLASSIFICATION = "ai_classification"
    LIEN_PROCESSING = "lien_processing"
    LIEN_MODIFICATION_CHECK = "lien_modification_check"
    
    # FrontApp integration
    FRONT_TAGS_RETRIEVED = "front_tags_retrieved"
    FRONT_TAGS_APPLIED = "front_tags_applied"
    FRONT_TAGS_REMOVED = "front_tags_removed"
    CONVERSATION_SPLIT = "conversation_split"
    
    # Autoresponse
    AGENT_SELECTED = "agent_selected"
    RESPONSE_GENERATED = "response_generated"
    RESPONSE_SENT = "response_sent"
    
    # Status updates
    STATUS_UPDATED = "status_updated"
    PROCESSING_COMPLETED = "processing_completed"


# Status constants
class TraceStatus:
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"