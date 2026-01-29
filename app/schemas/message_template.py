"""Schemas for message templates."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID


class MessageTemplateBase(BaseModel):
    """Base schema for message templates."""
    template_key: str = Field(..., description="Unique key for the template")
    template_name: str = Field(..., description="Human-readable name for the template")
    template_body: str = Field(..., description="Template content with placeholders")
    description: Optional[str] = Field(None, description="Description of when this template is used")


class MessageTemplateCreate(MessageTemplateBase):
    """Schema for creating a message template."""
    updated_by: Optional[str] = Field(None, description="Identifier of who created the template")


class MessageTemplateUpdate(BaseModel):
    """Schema for updating a message template."""
    template_body: str = Field(..., description="New template content")
    template_name: Optional[str] = Field(None, description="Optional new name")
    description: Optional[str] = Field(None, description="Optional new description")
    updated_by: Optional[str] = Field(None, description="Identifier of who updated the template")
    expected_updated_at: Optional[datetime] = Field(None, description="Expected updated_at timestamp for optimistic concurrency control")


class MessageTemplateResponse(MessageTemplateBase):
    """Schema for message template response."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str]

    class Config:
        from_attributes = True


class MessageTemplateListResponse(BaseModel):
    """Schema for list of templates response."""
    templates: list[MessageTemplateResponse]
    count: int
