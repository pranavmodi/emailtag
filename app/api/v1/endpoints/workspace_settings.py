"""
Workspace Settings API Endpoints

Endpoints for managing workspace-level settings including security features
like sender verification toggle.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Any, Dict

from app.db.session import get_async_db
from app.crud.tag_settings import tag_settings_crud
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


class WorkspaceSettingsResponse(BaseModel):
    """Response model for workspace settings."""
    enable_sender_verification: bool
    custom_placeholders: Dict[str, Any] = {}


class UpdateSenderVerificationRequest(BaseModel):
    """Request model for updating sender verification setting."""
    enabled: bool
    updated_by: str = "Admin"


@router.get("/workspace-settings", response_model=WorkspaceSettingsResponse)
async def get_workspace_settings(
    db: AsyncSession = Depends(get_async_db),
    current_user: str = Depends(get_current_user)
):
    """
    Get workspace-level settings.

    Returns:
        WorkspaceSettingsResponse with current workspace settings
    """
    try:
        # Get WORKSPACE settings
        workspace_settings = await tag_settings_crud.get_settings_dict(db, "WORKSPACE")

        return WorkspaceSettingsResponse(
            enable_sender_verification=workspace_settings.get("enable_sender_verification", True),
            custom_placeholders=workspace_settings.get("custom_placeholders", {})
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch workspace settings: {str(e)}")


@router.post("/workspace-settings/sender-verification")
async def update_sender_verification(
    request: UpdateSenderVerificationRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: str = Depends(get_current_user)
):
    """
    Update sender verification enable/disable setting.

    Args:
        request: UpdateSenderVerificationRequest with enabled flag

    Returns:
        Updated workspace settings
    """
    try:
        # Get current WORKSPACE settings
        workspace_settings = await tag_settings_crud.get_settings_dict(db, "WORKSPACE")

        # Update the sender verification flag
        workspace_settings["enable_sender_verification"] = request.enabled

        # Save back to database
        await tag_settings_crud.update_settings(db, "WORKSPACE", workspace_settings)

        return {
            "success": True,
            "enable_sender_verification": request.enabled,
            "message": f"Sender verification {'enabled' if request.enabled else 'disabled'} successfully",
            "updated_by": request.updated_by
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update sender verification setting: {str(e)}"
        )
