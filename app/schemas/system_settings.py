"""Schemas for system settings."""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class SystemSettingBase(BaseModel):
    """Base schema for system settings."""
    setting_key: str = Field(..., description="Unique key for the setting")
    setting_value: bool = Field(..., description="Boolean value of the setting")
    description: Optional[str] = Field(None, description="Description of what the setting does")


class SystemSettingUpdate(BaseModel):
    """Schema for updating a system setting."""
    setting_value: bool = Field(..., description="New boolean value for the setting")
    updated_by: Optional[str] = Field(None, description="Identifier of who made the change")


class SystemSettingResponse(BaseModel):
    """Schema for system setting response with metadata."""
    enabled: bool = Field(..., description="Whether the setting is enabled")
    description: Optional[str] = Field(None, description="Description of what the setting does")
    last_updated: Optional[datetime] = Field(None, description="When the setting was last updated")
    updated_by: Optional[str] = Field(None, description="Who last updated the setting")

    class Config:
        from_attributes = True


class EmailProcessingStatusResponse(BaseModel):
    """Schema for email processing status response."""
    processing_enabled: bool = Field(..., description="Whether email processing is currently enabled")
    description: str = Field(..., description="Explanation of what this setting controls")
    last_updated: Optional[datetime] = Field(None, description="When the setting was last changed")
    updated_by: Optional[str] = Field(None, description="Who last changed the setting")
