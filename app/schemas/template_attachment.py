"""Pydantic schemas for template attachments."""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field


class TemplateAttachmentBase(BaseModel):
    """Base schema for template attachment."""
    tag_name: str = Field(..., description="Tag name this attachment belongs to")
    template_key: Optional[str] = Field(None, description="Specific template key within the tag")
    filename: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type of the file")
    file_size: int = Field(..., description="File size in bytes")
    description: Optional[str] = Field(None, description="Optional description")


class TemplateAttachmentCreate(BaseModel):
    """Schema for creating template attachment (file is uploaded separately)."""
    tag_name: str = Field(..., description="Tag name this attachment belongs to")
    template_key: Optional[str] = Field(None, description="Specific template key within the tag")
    description: Optional[str] = Field(None, description="Optional description")
    uploaded_by: Optional[str] = Field(None, description="User uploading the attachment")


class TemplateAttachmentResponse(TemplateAttachmentBase):
    """Schema for template attachment response."""
    id: UUID
    created_at: datetime
    uploaded_by: Optional[str] = None

    class Config:
        from_attributes = True


class TemplateAttachmentListResponse(BaseModel):
    """Schema for list of template attachments."""
    items: List[TemplateAttachmentResponse]
    total: int


class TemplateAttachmentUploadResponse(BaseModel):
    """Schema for upload response."""
    attachment: TemplateAttachmentResponse
    message: str = "File uploaded successfully"
