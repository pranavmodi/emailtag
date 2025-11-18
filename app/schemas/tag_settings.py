"""Pydantic schemas for tag settings."""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class TagSettingsBase(BaseModel):
    """Base schema for tag settings."""
    tag_name: str = Field(..., description="Tag name these settings apply to")
    settings: dict = Field(default_factory=dict, description="Settings dictionary")


class TagSettingsCreate(TagSettingsBase):
    """Schema for creating tag settings."""
    updated_by: Optional[str] = Field(None, description="User who created the settings")


class TagSettingsUpdate(BaseModel):
    """Schema for updating tag settings."""
    settings: dict = Field(..., description="Settings dictionary")
    updated_by: Optional[str] = Field(None, description="User who updated the settings")


class TagSettingsResponse(TagSettingsBase):
    """Schema for tag settings response."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str] = None

    class Config:
        from_attributes = True


class TagSettingsListResponse(BaseModel):
    """Schema for list of tag settings."""
    items: list[TagSettingsResponse]
    total: int
