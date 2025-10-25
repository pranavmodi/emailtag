"""API endpoints for system settings management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.crud.system_settings import system_settings_crud
from app.schemas.system_settings import (
    EmailProcessingStatusResponse,
    SystemSettingUpdate
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/email-processing-status", response_model=EmailProcessingStatusResponse)
async def get_email_processing_status(
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current status of the email processing master switch.

    This endpoint returns whether email processing is currently enabled or disabled,
    along with metadata about when and by whom it was last changed.

    Returns:
        EmailProcessingStatusResponse with current status and metadata
    """
    try:
        setting = await system_settings_crud.get_by_key(db, "email_processing_enabled")

        if setting:
            return EmailProcessingStatusResponse(
                processing_enabled=setting.setting_value,
                description=setting.description or "Master switch for email processing",
                last_updated=setting.updated_at,
                updated_by=setting.updated_by
            )
        else:
            # Default state if setting doesn't exist yet
            return EmailProcessingStatusResponse(
                processing_enabled=True,
                description=(
                    "Master switch to enable/disable all incoming email processing. "
                    "When disabled, emails are received and saved but not classified or tagged."
                ),
                last_updated=None,
                updated_by=None
            )
    except Exception as e:
        logger.error(f"Error fetching email processing status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch email processing status: {str(e)}"
        )


@router.post("/email-processing-toggle", response_model=EmailProcessingStatusResponse)
async def toggle_email_processing(
    update: SystemSettingUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle the email processing master switch.

    This endpoint enables or disables all incoming email processing. When disabled,
    emails will still be received via the webhook and saved to the database, but
    they will NOT be queued for classification, tagging, or any other processing.

    Args:
        update: SystemSettingUpdate with the new enabled/disabled state and optional user

    Returns:
        EmailProcessingStatusResponse with updated status
    """
    try:
        # Update the setting
        setting = await system_settings_crud.toggle_email_processing(
            db,
            enable=update.setting_value,
            updated_by=update.updated_by
        )

        # Log the change prominently
        action = "ENABLED" if update.setting_value else "DISABLED"
        logger.warning(
            f"EMAIL PROCESSING {action} by {update.updated_by or 'unknown user'}"
        )

        return EmailProcessingStatusResponse(
            processing_enabled=setting.setting_value,
            description=setting.description or "Master switch for email processing",
            last_updated=setting.updated_at,
            updated_by=setting.updated_by
        )
    except Exception as e:
        logger.error(f"Error toggling email processing: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle email processing: {str(e)}"
        )
