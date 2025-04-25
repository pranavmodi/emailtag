"""Email schemas for the API."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class EmailBase(BaseModel):
    """Base schema for email data."""
    
    front_conversation_id: str
    subject: Optional[str] = None
    sender: str
    recipients: List[str]
    content_text: Optional[str] = None
    content_html: Optional[str] = None


class EmailCreate(EmailBase):
    """Schema for creating a new email."""
    
    raw_data: Dict[str, Any]
    status: Optional[str] = "pending_initial"
    ocr_attachments_total: Optional[int] = None
    ocr_attachments_completed: Optional[int] = 0


class EmailUpdate(BaseModel):
    """Schema for updating an email."""
    
    status: Optional[str] = None
    ocr_patient_id: Optional[str] = None
    ocr_date_of_birth: Optional[str] = None
    ocr_date_of_incident: Optional[str] = None
    ocr_metadata: Optional[str] = None
    ocr_attachments_completed: Optional[int] = None


class EmailInDBBase(EmailBase):
    """Base schema for email in database."""
    
    id: UUID
    status: str
    ocr_attachments_total: Optional[int] = None
    ocr_attachments_completed: Optional[int] = None
    ocr_patient_id: Optional[str] = None
    ocr_date_of_birth: Optional[str] = None
    ocr_date_of_incident: Optional[str] = None
    ocr_metadata: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        """Pydantic config."""
        
        from_attributes = True


class Email(EmailInDBBase):
    """Schema for email data returned to the client."""
    
    pass


class EmailInDB(EmailInDBBase):
    """Schema for email data in the database."""
    
    raw_data: Dict[str, Any]


class TagBase(BaseModel):
    """Base schema for tag data."""
    
    name: str
    description: Optional[str] = None
    front_tag_id: Optional[str] = None


class TagCreate(TagBase):
    """Schema for creating a new tag."""
    
    pass


class TagUpdate(BaseModel):
    """Schema for updating a tag."""
    
    name: Optional[str] = None
    description: Optional[str] = None
    front_tag_id: Optional[str] = None


class TagInDBBase(TagBase):
    """Base schema for tag in database."""
    
    id: UUID
    created_at: datetime
    
    class Config:
        """Pydantic config."""
        
        from_attributes = True


class Tag(TagInDBBase):
    """Schema for tag data returned to the client."""
    
    pass


class FrontAppWebhook(BaseModel):
    """Schema for FrontApp webhook payload."""
    
    _links: Dict[str, Any]
    id: str
    type: str
    conversation: Dict[str, Any] = Field(default_factory=dict)
    target: Dict[str, Any] = Field(default_factory=dict)
    source: Dict[str, Any] = Field(default_factory=dict)
    emitted_at: float


class PreprocessingWebhook(BaseModel):
    """Schema for preprocessing service webhook payload."""
    
    email_id: UUID
    ocr_text: Optional[str] = None
    cleaned_text: Optional[str] = None
    cleaned_html: Optional[str] = None
    extracted_entities: Optional[List[Any]] = None
    confidence_score: Optional[float] = None
    processing_status: Optional[str] = None
    error_message: Optional[str] = None
    # Add other fields expected from the preprocessing service if known
    # e.g., cleaned_text: str, entities: List[str], etc. 