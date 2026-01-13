"""API endpoints for system settings management."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import os
import json
from app.db.session import get_db
from app.crud.system_settings import system_settings_crud
from app.schemas.system_settings import (
    EmailProcessingStatusResponse,
    SystemSettingUpdate,
    AllAutorespondSettingsResponse,
    AutorespondSettingDetail,
    AutorespondToggleRequest
)
from app.services.frontapp_service import get_conversation_tags_async
import logging

logger = logging.getLogger(__name__)

# Lien test uploads directory
LIEN_TEST_UPLOAD_DIR = "/tmp/lien_test_uploads"

# Bill balance test outputs directory
BILL_BALANCE_TEST_OUTPUT_DIR = "/tmp/bill_balance_test_outputs"

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


@router.get("/lien-test-mode-status")
async def get_lien_test_mode_status(db: AsyncSession = Depends(get_db)):
    """Get current lien test mode status."""
    try:
        setting = await system_settings_crud.get_by_key(db, "lien_test_mode")
        if setting:
            return {
                "lien_test_mode": setting.setting_value,
                "description": setting.description,
                "last_updated": setting.updated_at,
                "updated_by": setting.updated_by
            }
        else:
            return {
                "lien_test_mode": False,
                "description": "Lien upload test mode. When enabled, lien documents are saved to a local directory instead of uploading to RadFlow.",
                "last_updated": None,
                "updated_by": None
            }
    except Exception as e:
        logger.error(f"Error fetching lien test mode status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch lien test mode status: {str(e)}"
        )


@router.post("/lien-test-mode-toggle")
async def toggle_lien_test_mode(
    update: SystemSettingUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Toggle lien test mode on/off."""
    try:
        setting = await system_settings_crud.update_setting(
            db,
            "lien_test_mode",
            update.setting_value,
            updated_by=update.updated_by
        )

        return {
            "lien_test_mode": setting.setting_value,
            "description": setting.description or "Lien upload test mode",
            "last_updated": setting.updated_at,
            "updated_by": setting.updated_by
        }
    except Exception as e:
        logger.error(f"Error toggling lien test mode: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle lien test mode: {str(e)}"
        )


@router.get("/bill-balance-test-mode-status")
async def get_bill_balance_test_mode_status(db: AsyncSession = Depends(get_db)):
    """Get current bill balance test mode status."""
    try:
        setting = await system_settings_crud.get_by_key(db, "bill_balance_test_mode")
        if setting:
            return {
                "bill_balance_test_mode": setting.setting_value,
                "description": setting.description,
                "last_updated": setting.updated_at,
                "updated_by": setting.updated_by
            }
        else:
            return {
                "bill_balance_test_mode": False,
                "description": "Bill balance test mode. When enabled, responses are saved to a local directory instead of sending via Front API.",
                "last_updated": None,
                "updated_by": None
            }
    except Exception as e:
        logger.error(f"Error fetching bill balance test mode status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch bill balance test mode status: {str(e)}"
        )


@router.post("/bill-balance-test-mode-toggle")
async def toggle_bill_balance_test_mode(
    update: SystemSettingUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Toggle bill balance test mode on/off."""
    try:
        setting = await system_settings_crud.update_setting(
            db,
            "bill_balance_test_mode",
            update.setting_value,
            updated_by=update.updated_by
        )

        return {
            "bill_balance_test_mode": setting.setting_value,
            "description": setting.description or "Bill balance test mode",
            "last_updated": setting.updated_at,
            "updated_by": setting.updated_by
        }
    except Exception as e:
        logger.error(f"Error toggling bill balance test mode: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle bill balance test mode: {str(e)}"
        )


@router.get("/bill-balance-test-outputs")
async def list_bill_balance_test_outputs(db: AsyncSession = Depends(get_db)):
    """List all conversation IDs with bill balance test outputs, ordered by latest first."""
    try:
        from app.models.email import Email
        from sqlalchemy import select

        test_dir = Path(BILL_BALANCE_TEST_OUTPUT_DIR)

        if not test_dir.exists():
            return {"conversations": []}

        conversations = []
        for conv_dir in test_dir.iterdir():
            if conv_dir.is_dir():
                response_file = conv_dir / "response.json"

                # Get directory modification time
                latest_time = conv_dir.stat().st_mtime
                if response_file.exists():
                    latest_time = max(latest_time, response_file.stat().st_mtime)

                # Get conversation details from database
                conv_id = conv_dir.name
                conv_info = {
                    "conversation_id": conv_id,
                    "timestamp": latest_time,
                    "has_response": response_file.exists(),
                    "subject": None,
                    "sender": None,
                }

                # Try to get email info from database
                try:
                    stmt = select(Email).where(Email.front_conversation_id == conv_id).limit(1)
                    result = await db.execute(stmt)
                    email = result.scalar_one_or_none()
                    if email:
                        conv_info["subject"] = email.subject
                        conv_info["sender"] = email.sender
                except Exception as db_err:
                    logger.warning(f"Could not fetch email info for {conv_id}: {db_err}")

                # Try to get response data
                if response_file.exists():
                    try:
                        with open(response_file, "r") as f:
                            response_data = json.load(f)
                            conv_info["patient_id"] = response_data.get("patient_id")
                            conv_info["response_type"] = response_data.get("response_type")
                    except Exception as json_err:
                        logger.warning(f"Could not parse response.json for {conv_id}: {json_err}")

                conversations.append(conv_info)

        # Sort by timestamp descending (latest first)
        conversations.sort(key=lambda x: x["timestamp"], reverse=True)

        return {"conversations": conversations}
    except Exception as e:
        logger.error(f"Error listing bill balance test outputs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list bill balance test outputs: {str(e)}"
        )


@router.get("/bill-balance-test-outputs/{conversation_id}/response")
async def get_bill_balance_test_response(conversation_id: str):
    """Get the response.json for a specific bill balance test conversation."""
    try:
        response_file = Path(BILL_BALANCE_TEST_OUTPUT_DIR) / conversation_id / "response.json"

        if not response_file.exists():
            raise HTTPException(status_code=404, detail="Response file not found")

        # Security check - ensure path is within test directory
        if not str(response_file.resolve()).startswith(str(Path(BILL_BALANCE_TEST_OUTPUT_DIR).resolve())):
            raise HTTPException(status_code=403, detail="Access denied")

        with open(response_file, "r") as f:
            return json.load(f)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading bill balance test response: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read response file: {str(e)}"
        )


@router.delete("/bill-balance-test-outputs/{conversation_id}")
async def delete_bill_balance_test_output(conversation_id: str):
    """Delete a specific bill balance test output directory."""
    try:
        import shutil
        conv_dir = Path(BILL_BALANCE_TEST_OUTPUT_DIR) / conversation_id

        if not conv_dir.exists():
            raise HTTPException(status_code=404, detail="Conversation directory not found")

        # Security check
        if not str(conv_dir.resolve()).startswith(str(Path(BILL_BALANCE_TEST_OUTPUT_DIR).resolve())):
            raise HTTPException(status_code=403, detail="Access denied")

        shutil.rmtree(conv_dir)
        return {"message": f"Deleted test output for conversation {conversation_id}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting bill balance test output: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete test output: {str(e)}"
        )


@router.delete("/bill-balance-test-outputs")
async def clear_all_bill_balance_test_outputs():
    """Clear all bill balance test outputs."""
    try:
        import shutil
        test_dir = Path(BILL_BALANCE_TEST_OUTPUT_DIR)

        if test_dir.exists():
            shutil.rmtree(test_dir)
            test_dir.mkdir(parents=True, exist_ok=True)

        return {"message": "All bill balance test outputs cleared"}
    except Exception as e:
        logger.error(f"Error clearing bill balance test outputs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear test outputs: {str(e)}"
        )


@router.get("/lien-test-uploads")
async def list_lien_test_uploads(db: AsyncSession = Depends(get_db)):
    """List all conversation IDs with lien test uploads, ordered by latest first."""
    try:
        from app.models.email import Email
        from sqlalchemy import select, func

        test_dir = Path(LIEN_TEST_UPLOAD_DIR)

        if not test_dir.exists():
            return {"conversations": []}

        conversations = []
        for conv_dir in test_dir.iterdir():
            if conv_dir.is_dir():
                files = list(conv_dir.glob("*.pdf"))

                # Get directory modification time (latest file time)
                latest_file_time = max((f.stat().st_mtime for f in files), default=0) if files else conv_dir.stat().st_mtime

                # Get conversation details from database
                conv_id = conv_dir.name
                conv_info = {
                    "conversation_id": conv_id,
                    "file_count": len(files),
                    "files": [f.name for f in files],
                    "latest_upload_time": latest_file_time,
                    "subject": None,
                    "sender": None,
                    "email_count": 0
                }

                # Try to fetch email details from database
                try:
                    # Get the most recent email for this conversation
                    stmt = select(Email).where(
                        Email.front_conversation_id == conv_id
                    ).order_by(Email.created_at.desc()).limit(1)

                    result = await db.execute(stmt)
                    email = result.scalar_one_or_none()

                    if email:
                        conv_info["subject"] = email.subject
                        conv_info["sender"] = email.sender

                    # Get total email count for this conversation
                    count_stmt = select(func.count(Email.id)).where(
                        Email.front_conversation_id == conv_id
                    )
                    count_result = await db.execute(count_stmt)
                    conv_info["email_count"] = count_result.scalar() or 0

                except Exception as db_error:
                    logger.warning(f"Could not fetch details for conversation {conv_id}: {db_error}")

                conversations.append(conv_info)

        # Sort by latest upload time (most recent first)
        conversations.sort(key=lambda x: x.get("latest_upload_time", 0), reverse=True)

        return {"conversations": conversations}

    except Exception as e:
        logger.error(f"Error listing lien test uploads: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list lien test uploads: {str(e)}"
        )


@router.get("/lien-test-uploads/{conversation_id}")
async def get_lien_test_uploads_for_conversation(conversation_id: str):
    """Get all lien files for a specific conversation."""
    try:
        conv_dir = Path(LIEN_TEST_UPLOAD_DIR) / conversation_id

        if not conv_dir.exists():
            raise HTTPException(
                status_code=404,
                detail=f"No test uploads found for conversation {conversation_id}"
            )

        files = []
        for file_path in conv_dir.glob("*.pdf"):
            stat = file_path.stat()
            files.append({
                "filename": file_path.name,
                "size": stat.st_size,
                "created": stat.st_mtime
            })

        # Fetch current tags from Front (best-effort)
        tag_names: list[str] = []
        try:
            front_tags = await get_conversation_tags_async(conversation_id)
            if front_tags:
                tag_names = [t.get("name") for t in front_tags if t.get("name")]
        except Exception as tag_err:
            logger.warning(f"Could not fetch tags for lien test conversation {conversation_id}: {tag_err}")

        return {
            "conversation_id": conversation_id,
            "files": files,
            "tags": tag_names
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting lien test uploads for conversation {conversation_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get lien test uploads: {str(e)}"
        )


@router.get("/lien-test-uploads/{conversation_id}/response")
async def get_lien_test_response(conversation_id: str):
    """Get the generated autorespond message for a lien test conversation."""
    try:
        response_file = Path(LIEN_TEST_UPLOAD_DIR) / conversation_id / "response.json"

        if not response_file.exists():
            # No response generated yet
            return {
                "conversation_id": conversation_id,
                "hasResponse": False,
                "message": "No autorespond message generated yet"
            }

        # Security check: ensure file is within the test upload directory
        if not str(response_file.resolve()).startswith(str(Path(LIEN_TEST_UPLOAD_DIR).resolve())):
            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        # Read and return the response data
        with open(response_file, "r") as f:
            response_data = json.load(f)

        return {
            "conversation_id": conversation_id,
            "hasResponse": True,
            **response_data
        }

    except HTTPException:
        raise
    except FileNotFoundError:
        return {
            "conversation_id": conversation_id,
            "hasResponse": False,
            "message": "No autorespond message generated yet"
        }
    except Exception as e:
        logger.error(f"Error getting lien test response for conversation {conversation_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get response: {str(e)}"
        )


@router.get("/lien-test-uploads/{conversation_id}/{filename}")
async def download_lien_test_file(conversation_id: str, filename: str):
    """Download a specific lien test file."""
    try:
        file_path = Path(LIEN_TEST_UPLOAD_DIR) / conversation_id / filename

        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File not found: {filename}"
            )

        # Security check: ensure file is within the test upload directory
        if not str(file_path.resolve()).startswith(str(Path(LIEN_TEST_UPLOAD_DIR).resolve())):
            raise HTTPException(
                status_code=403,
                detail="Access denied"
            )

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type="application/pdf"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading lien test file {filename}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download file: {str(e)}"
        )


@router.delete("/lien-test-uploads")
async def clear_all_lien_test_uploads():
    """Delete all lien test uploads and clear the test directory."""
    try:
        import shutil

        test_dir = Path(LIEN_TEST_UPLOAD_DIR)

        if not test_dir.exists():
            return {
                "success": True,
                "message": "No test uploads to clear",
                "deleted_conversations": 0,
                "deleted_files": 0
            }

        # Count conversations and files before deletion
        deleted_conversations = 0
        deleted_files = 0

        for conv_dir in test_dir.iterdir():
            if conv_dir.is_dir():
                deleted_conversations += 1
                deleted_files += len(list(conv_dir.glob("*")))

        # Delete the entire directory and recreate it
        shutil.rmtree(test_dir)
        test_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Cleared lien test uploads: {deleted_conversations} conversations, {deleted_files} files")

        return {
            "success": True,
            "message": f"Cleared {deleted_conversations} conversations and {deleted_files} files",
            "deleted_conversations": deleted_conversations,
            "deleted_files": deleted_files
        }

    except Exception as e:
        logger.error(f"Error clearing lien test uploads: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear test uploads: {str(e)}"
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
