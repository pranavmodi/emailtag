"""Pydantic schemas for processing trace models."""

import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field


class ProcessingTraceBase(BaseModel):
    """Base schema for processing traces."""
    front_conversation_id: str
    email_id: Optional[uuid.UUID] = None
    step_name: str = Field(..., max_length=100)
    step_type: str = Field(..., max_length=50)
    step_order: int
    task_id: Optional[str] = Field(None, max_length=100)
    parent_trace_id: Optional[uuid.UUID] = None
    status: str = Field(..., max_length=50)
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_data: Optional[Dict[str, Any]] = None
    trace_metadata: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    completed_at: Optional[datetime] = None


class ProcessingTraceCreate(ProcessingTraceBase):
    """Schema for creating a processing trace."""
    pass


class ProcessingTraceUpdate(BaseModel):
    """Schema for updating a processing trace."""
    status: Optional[str] = Field(None, max_length=50)
    output_data: Optional[Dict[str, Any]] = None
    error_data: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    completed_at: Optional[datetime] = None


class ProcessingTrace(ProcessingTraceBase):
    """Schema for reading processing traces."""
    id: uuid.UUID
    started_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class ProcessingTraceInDB(ProcessingTrace):
    """Schema for processing traces as stored in the database."""
    pass