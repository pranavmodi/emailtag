"""Pydantic schemas for PatientConversationData."""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


class PatientConversationDataBase(BaseModel):
    """Base schema for patient conversation data."""
    front_conversation_id: str = Field(..., description="The Front conversation ID.")
    patient_id: str = Field(..., description="The patient identifier (e.g., PREXXXXX).")
    source_email_id: UUID = Field(..., description="The ID of the email message sourcing this data.")
    patient_info: Optional[Dict[str, Any]] = Field(None, description="Structured JSON patient data.")
    appointment_info: Optional[Dict[str, Any]] = Field(None, description="Structured JSON appointment data.")


class PatientConversationDataCreate(PatientConversationDataBase):
    """Schema for creating a new patient conversation data record."""
    pass


class PatientConversationDataUpdate(BaseModel):
    """Schema for updating an existing patient conversation data record."""
    patient_info: Optional[Dict[str, Any]] = Field(None, description="Updated structured JSON patient data.")
    appointment_info: Optional[Dict[str, Any]] = Field(None, description="Updated structured JSON appointment data.")
    source_email_id: Optional[UUID] = Field(None, description="Update the source email ID if necessary.")


class PatientConversationDataInDBBase(PatientConversationDataBase):
    """Base schema for patient conversation data in database."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PatientConversationData(PatientConversationDataInDBBase):
    """Schema for patient conversation data returned to the client."""
    pass


class PatientConversationDataInDB(PatientConversationDataInDBBase):
    """Schema for patient conversation data as represented in the database."""
    pass 