"""Pydantic schemas for firm aliases."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FirmAliasBase(BaseModel):
    alias_type: str = Field(..., description="Alias type from the identity contract")
    alias_value: str = Field(..., description="Normalized alias value")
    firm_id: UUID
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    source: str = Field(..., description="Alias provenance")


class FirmAliasCreate(FirmAliasBase):
    pass


class FirmAliasUpdate(BaseModel):
    firm_id: UUID | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    source: str | None = None


class FirmAliasResponse(FirmAliasBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
