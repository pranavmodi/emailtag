"""Persisted results from manually triggered model evaluations."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelEvaluationRun(Base):
    """One provider/model result for one evaluation case."""

    __tablename__ = "model_evaluation_runs"
    __table_args__ = (
        UniqueConstraint(
            "case_type",
            "case_id",
            "model_key",
            name="uq_model_eval_run_case_model",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    result_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    objective: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    model_key: Mapped[str] = mapped_column(String(320), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    output: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    raw_usage: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    request_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(14, 8), nullable=False, default=Decimal("0")
    )
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    human_rating: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    human_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ModelEvaluationCaseReview(Base):
    """Human-approved reference output for one evaluation case."""

    __tablename__ = "model_evaluation_case_reviews"
    __table_args__ = (
        UniqueConstraint("case_type", "case_id", name="uq_model_eval_case_review"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    reference_output: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    reference_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown", server_default="unknown"
    )
    seed_model_key: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    seed_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ModelEvaluationModelSetting(Base):
    """Evaluation-only switch controlling whether a catalog model may be run."""

    __tablename__ = "model_evaluation_model_settings"

    model_key: Mapped[str] = mapped_column(String(320), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
