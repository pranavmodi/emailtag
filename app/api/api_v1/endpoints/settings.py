"""API endpoints for system settings management."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.crud.system_settings import system_settings_crud
from app.schemas.system_settings import (
    EmailProcessingStatusResponse,
    SystemSettingUpdate,
    AllAutorespondSettingsResponse,
    AutorespondSettingDetail,
    AutorespondToggleRequest
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


@router.get("/skip-internal-domains-status")
async def get_skip_internal_domains_status(
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current status of the internal domain filtering setting.

    When enabled, emails from @preciseimaging.com and @mediflow.com domains are skipped.
    When disabled (default for testing), all emails are processed regardless of sender domain.

    Returns:
        Dict with current status and metadata
    """
    try:
        setting = await system_settings_crud.get_by_key(db, "skip_internal_domains")

        if setting:
            return {
                "skip_internal_domains": setting.setting_value,
                "description": setting.description or "Filter emails from internal domains (preciseimaging.com, mediflow.com)",
                "last_updated": setting.updated_at,
                "updated_by": setting.updated_by
            }
        else:
            # Default state if setting doesn't exist yet - disabled for testing
            return {
                "skip_internal_domains": False,
                "description": "Filter emails from internal domains (preciseimaging.com, mediflow.com)",
                "last_updated": None,
                "updated_by": None
            }
    except Exception as e:
        logger.error(f"Error fetching skip internal domains status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch skip internal domains status: {str(e)}"
        )


@router.post("/skip-internal-domains-toggle")
async def toggle_skip_internal_domains(
    update: SystemSettingUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle the internal domain filtering setting.

    When enabled: Emails from @preciseimaging.com and @mediflow.com are skipped
    When disabled: All emails are processed (useful for testing)

    Args:
        update: SystemSettingUpdate with the new enabled/disabled state and optional user

    Returns:
        Dict with updated status
    """
    try:
        # Update the setting
        setting = await system_settings_crud.update_setting(
            db,
            "skip_internal_domains",
            update.setting_value,
            updated_by=update.updated_by
        )

        # Log the change prominently
        action = "ENABLED" if update.setting_value else "DISABLED"
        logger.warning(
            f"INTERNAL DOMAIN FILTERING {action} by {update.updated_by or 'unknown user'}"
        )

        return {
            "skip_internal_domains": setting.setting_value,
            "description": setting.description or "Filter emails from internal domains (preciseimaging.com, mediflow.com)",
            "last_updated": setting.updated_at,
            "updated_by": setting.updated_by
        }
    except Exception as e:
        logger.error(f"Error toggling skip internal domains: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle skip internal domains: {str(e)}"
        )


@router.get("/autorespond-settings", response_model=AllAutorespondSettingsResponse)
async def get_autorespond_settings(
    db: AsyncSession = Depends(get_db)
):
    """
    Get all autorespond settings with their current status.

    Returns the enabled/disabled status for each autorespond type:
    - Appointment Inquiry
    - Apt Status Req
    - Medical Records
    - Bill or Balance Request
    - Case Updates
    - Missing Lien Request
    - PSL Lien
    - ASL Lien

    Returns:
        AllAutorespondSettingsResponse with all autorespond settings
    """
    try:
        # Get global autorespond setting
        global_enabled = await system_settings_crud.get_setting_value(
            db, "global_autorespond_enabled", default=True
        )

        settings = await system_settings_crud.get_autorespond_settings(db)

        # Map of labels and descriptions
        autorespond_info = {
            "appointment_inquiry": {
                "label": "Appointment Inquiry",
                "description": "Automatic responses to appointment inquiry emails with patient appointment details"
            },
            "apt_status_req": {
                "label": "Apt Status Req",
                "description": "Automatic responses to appointment status request emails"
            },
            "medical_records": {
                "label": "Medical Records",
                "description": "Automatic responses to medical records requests (Release of Records, Image Request, CD Requests, Reports Request)"
            },
            "bill_balance_request": {
                "label": "Bill or Balance Request",
                "description": "Automatic responses to bill or balance request emails"
            },
            "case_updates": {
                "label": "Case Updates",
                "description": "Automatic responses to case update emails (Drop Pending, Promise to send payment, etc.)"
            },
            "missing_lien_request": {
                "label": "Missing Lien Request",
                "description": "Automatic responses to missing lien request emails"
            },
            "liens": {
                "label": "Liens (ASL & PSL)",
                "description": "Automatic responses to all lien submissions (Attorney Signed Liens and Patient Signed Liens)"
            }
        }

        # Consolidated liens setting
        liens_enabled = settings.get("autorespond_liens", True)

        response = AllAutorespondSettingsResponse(
            global_autorespond_enabled=global_enabled,
            appointment_inquiry=AutorespondSettingDetail(
                enabled=settings.get("autorespond_appointment_inquiry", True),
                label=autorespond_info["appointment_inquiry"]["label"],
                description=autorespond_info["appointment_inquiry"]["description"]
            ),
            apt_status_req=AutorespondSettingDetail(
                enabled=settings.get("autorespond_apt_status_req", True),
                label=autorespond_info["apt_status_req"]["label"],
                description=autorespond_info["apt_status_req"]["description"]
            ),
            medical_records=AutorespondSettingDetail(
                enabled=settings.get("autorespond_medical_records", True),
                label=autorespond_info["medical_records"]["label"],
                description=autorespond_info["medical_records"]["description"]
            ),
            bill_balance_request=AutorespondSettingDetail(
                enabled=settings.get("autorespond_bill_balance_request", True),
                label=autorespond_info["bill_balance_request"]["label"],
                description=autorespond_info["bill_balance_request"]["description"]
            ),
            case_updates=AutorespondSettingDetail(
                enabled=settings.get("autorespond_case_updates", True),
                label=autorespond_info["case_updates"]["label"],
                description=autorespond_info["case_updates"]["description"]
            ),
            missing_lien_request=AutorespondSettingDetail(
                enabled=settings.get("autorespond_missing_lien_request", True),
                label=autorespond_info["missing_lien_request"]["label"],
                description=autorespond_info["missing_lien_request"]["description"]
            ),
            liens=AutorespondSettingDetail(
                enabled=liens_enabled,
                label=autorespond_info["liens"]["label"],
                description=autorespond_info["liens"]["description"]
            )
        )

        return response
    except Exception as e:
        logger.error(f"Error fetching autorespond settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch autorespond settings: {str(e)}"
        )


@router.post("/autorespond-toggle")
async def toggle_autorespond_setting(
    request: AutorespondToggleRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle a specific autorespond type on or off.

    Args:
        request: AutorespondToggleRequest with autorespond type, new value, and optional user

    Returns:
        Success message with updated status
    """
    try:
        # Validate autorespond type
        valid_types = [
            "autorespond_appointment_inquiry",
            "autorespond_apt_status_req",
            "autorespond_medical_records",
            "autorespond_bill_balance_request",
            "autorespond_case_updates",
            "autorespond_missing_lien_request",
            "autorespond_liens"
        ]

        if request.autorespond_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid autorespond type. Must be one of: {', '.join(valid_types)}"
            )

        # Update the setting
        setting = await system_settings_crud.toggle_autorespond(
            db,
            autorespond_type=request.autorespond_type,
            enable=request.setting_value,
            updated_by=request.updated_by
        )

        # Log the change prominently
        action = "ENABLED" if request.setting_value else "DISABLED"
        logger.warning(
            f"AUTORESPOND '{request.autorespond_type}' {action} by {request.updated_by or 'unknown user'}"
        )

        return {
            "status": "success",
            "autorespond_type": request.autorespond_type,
            "enabled": setting.setting_value,
            "updated_by": setting.updated_by,
            "updated_at": setting.updated_at
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling autorespond setting: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle autorespond setting: {str(e)}"
        )


@router.post("/global-autorespond-toggle")
async def toggle_global_autorespond(
    request: SystemSettingUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle the global autorespond master switch.

    When disabled, ALL autoresponds are turned off regardless of individual settings.
    When enabled, individual autorespond settings are checked.

    Args:
        request: SystemSettingUpdate with new enabled/disabled state and optional user

    Returns:
        Success message with updated status
    """
    try:
        # Update the global setting
        setting = await system_settings_crud.update_setting(
            db,
            "global_autorespond_enabled",
            request.setting_value,
            request.updated_by
        )

        # Log the change prominently
        action = "ENABLED" if request.setting_value else "DISABLED"
        logger.warning(
            f"🌐 GLOBAL AUTORESPOND {action} by {request.updated_by or 'unknown user'}"
        )

        return {
            "status": "success",
            "global_autorespond_enabled": setting.setting_value,
            "updated_by": setting.updated_by,
            "updated_at": setting.updated_at
        }
    except Exception as e:
        logger.error(f"Error toggling global autorespond: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle global autorespond: {str(e)}"
        )


# --- BEGIN: Workspace Settings Endpoints ---

@router.get("/workspace-settings")
async def get_workspace_settings(
    db: AsyncSession = Depends(get_db)
):
    """
    Get workspace-level settings including sender verification toggle.

    Returns:
        Dictionary with workspace settings
    """
    try:
        from app.crud.tag_settings import tag_settings_crud

        # Get WORKSPACE settings
        workspace_settings = await tag_settings_crud.get_settings_dict(db, "WORKSPACE")

        return {
            "enable_sender_verification": workspace_settings.get("enable_sender_verification", True),
            "custom_placeholders": workspace_settings.get("custom_placeholders", {})
        }
    except Exception as e:
        logger.error(f"Error fetching workspace settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch workspace settings: {str(e)}"
        )


@router.post("/workspace-settings/sender-verification")
async def update_sender_verification(
    enabled: bool,
    updated_by: str = "Admin",
    db: AsyncSession = Depends(get_db)
):
    """
    Update sender verification enable/disable setting.

    Args:
        enabled: True to enable sender verification, False to disable
        updated_by: Username of person making the change

    Returns:
        Updated workspace settings with success message
    """
    try:
        from app.crud.tag_settings import tag_settings_crud

        # Get current WORKSPACE settings
        workspace_settings = await tag_settings_crud.get_settings_dict(db, "WORKSPACE")

        # Update the sender verification flag
        workspace_settings["enable_sender_verification"] = enabled

        # Save back to database (use 'update' method, not 'update_settings')
        await tag_settings_crud.update(db, "WORKSPACE", workspace_settings, updated_by)

        logger.info(f"Sender verification {'enabled' if enabled else 'disabled'} by {updated_by}")

        return {
            "success": True,
            "enable_sender_verification": enabled,
            "message": f"Sender verification {'enabled' if enabled else 'disabled'} successfully",
            "updated_by": updated_by
        }
    except Exception as e:
        logger.error(f"Error updating sender verification setting: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update sender verification setting: {str(e)}"
        )

# --- END: Workspace Settings Endpoints ---
