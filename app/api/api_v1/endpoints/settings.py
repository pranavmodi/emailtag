"""API endpoints for system settings management."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
import os
import json
from app.db.session import get_db
from app.crud.system_settings import system_settings_crud
from app.core.exceptions import StaleUpdateError
from app.schemas.system_settings import (
    EmailProcessingStatusResponse,
    SystemSettingUpdate,
    AllAutorespondSettingsResponse,
    AutorespondSettingDetail,
    AutorespondToggleRequest
)
from app.services.frontapp_service import get_conversation_tags_async
from app.services import test_email_service
from pydantic import BaseModel
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class SendTestEmailRequest(BaseModel):
    """Request model for sending test emails."""
    scenario_keys: List[str]
    recipient_email: Optional[str] = None

# Lien test uploads directory
LIEN_TEST_UPLOAD_DIR = "/tmp/lien_test_uploads"

# Bill balance test outputs directory
BILL_BALANCE_TEST_OUTPUT_DIR = "/tmp/bill_balance_test_outputs"

# Apt status test outputs directory
APT_STATUS_TEST_OUTPUT_DIR = "/tmp/apt_status_test_outputs"

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
            updated_by=update.updated_by,
            expected_updated_at=update.expected_updated_at
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
    except StaleUpdateError as e:
        raise HTTPException(
            status_code=409,
            detail=f"This setting was modified by {e.updated_by or 'another user'} at {e.current_updated_at}. Please refresh and try again."
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

    When enabled, emails from @precisemri.com and @mediflow.com domains are skipped.
    When disabled (default for testing), all emails are processed regardless of sender domain.

    Returns:
        Dict with current status and metadata
    """
    try:
        setting = await system_settings_crud.get_by_key(db, "skip_internal_domains")

        if setting:
            return {
                "skip_internal_domains": setting.setting_value,
                "description": setting.description or "Filter emails from internal domains (precisemri.com, mediflow.com)",
                "last_updated": setting.updated_at,
                "updated_by": setting.updated_by
            }
        else:
            # Default state if setting doesn't exist yet - disabled for testing
            return {
                "skip_internal_domains": False,
                "description": "Filter emails from internal domains (precisemri.com, mediflow.com)",
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

    When enabled: Emails from @precisemri.com and @mediflow.com are skipped
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
            updated_by=update.updated_by,
            expected_updated_at=update.expected_updated_at
        )

        # Log the change prominently
        action = "ENABLED" if update.setting_value else "DISABLED"
        logger.warning(
            f"INTERNAL DOMAIN FILTERING {action} by {update.updated_by or 'unknown user'}"
        )

        return {
            "skip_internal_domains": setting.setting_value,
            "description": setting.description or "Filter emails from internal domains (precisemri.com, mediflow.com)",
            "last_updated": setting.updated_at,
            "updated_by": setting.updated_by
        }
    except StaleUpdateError as e:
        raise HTTPException(
            status_code=409,
            detail=f"This setting was modified by {e.updated_by or 'another user'} at {e.current_updated_at}. Please refresh and try again."
        )
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
            updated_by=update.updated_by,
            expected_updated_at=update.expected_updated_at
        )

        return {
            "lien_test_mode": setting.setting_value,
            "description": setting.description or "Lien upload test mode",
            "last_updated": setting.updated_at,
            "updated_by": setting.updated_by
        }
    except StaleUpdateError as e:
        raise HTTPException(
            status_code=409,
            detail=f"This setting was modified by {e.updated_by or 'another user'} at {e.current_updated_at}. Please refresh and try again."
        )
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
            updated_by=update.updated_by,
            expected_updated_at=update.expected_updated_at
        )

        return {
            "bill_balance_test_mode": setting.setting_value,
            "description": setting.description or "Bill balance test mode",
            "last_updated": setting.updated_at,
            "updated_by": setting.updated_by
        }
    except StaleUpdateError as e:
        raise HTTPException(
            status_code=409,
            detail=f"This setting was modified by {e.updated_by or 'another user'} at {e.current_updated_at}. Please refresh and try again."
        )
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
                # Find all response files (response_*.json pattern for multi-patient support)
                response_files = list(conv_dir.glob("response_*.json"))
                # Also check for legacy response.json
                legacy_response = conv_dir / "response.json"
                if legacy_response.exists():
                    response_files.append(legacy_response)

                # Get directory modification time
                latest_time = conv_dir.stat().st_mtime
                for rf in response_files:
                    latest_time = max(latest_time, rf.stat().st_mtime)

                # Get conversation details from database
                conv_id = conv_dir.name
                conv_info = {
                    "conversation_id": conv_id,
                    "timestamp": latest_time,
                    "has_response": len(response_files) > 0,
                    "response_count": len(response_files),  # Number of responses (patients)
                    "subject": None,
                    "sender": None,
                    "patient_ids": [],  # List of all patient IDs
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

                # Try to get response data from all response files
                for rf in response_files:
                    try:
                        with open(rf, "r") as f:
                            response_data = json.load(f)
                            patient_id = response_data.get("patient_id")
                            if patient_id:
                                conv_info["patient_ids"].append(patient_id)
                            # Use first response's type for display
                            if not conv_info.get("response_type"):
                                conv_info["response_type"] = response_data.get("response_type")
                    except Exception as json_err:
                        logger.warning(f"Could not parse {rf.name} for {conv_id}: {json_err}")

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
    """Get all response files for a specific bill balance test conversation.

    Returns an object with 'responses' array containing all patient responses.
    For backward compatibility, also includes top-level fields from first response.
    """
    try:
        conv_dir = Path(BILL_BALANCE_TEST_OUTPUT_DIR) / conversation_id

        if not conv_dir.exists():
            raise HTTPException(status_code=404, detail="Conversation directory not found")

        # Security check - ensure path is within test directory
        if not str(conv_dir.resolve()).startswith(str(Path(BILL_BALANCE_TEST_OUTPUT_DIR).resolve())):
            raise HTTPException(status_code=403, detail="Access denied")

        # Find all response files
        response_files = list(conv_dir.glob("response_*.json"))
        # Also check for legacy response.json
        legacy_response = conv_dir / "response.json"
        if legacy_response.exists():
            response_files.append(legacy_response)

        if not response_files:
            raise HTTPException(status_code=404, detail="No response files found")

        # Load all responses
        responses = []
        for rf in sorted(response_files, key=lambda x: x.stat().st_mtime):
            try:
                with open(rf, "r") as f:
                    response_data = json.load(f)
                    response_data["_filename"] = rf.name
                    responses.append(response_data)
            except Exception as json_err:
                logger.warning(f"Could not parse {rf.name}: {json_err}")

        if not responses:
            raise HTTPException(status_code=404, detail="No valid response files found")

        # Return all responses, with first response's fields at top level for backward compatibility
        first_response = responses[0]
        return {
            # Top-level fields from first response (backward compatibility)
            "conversation_id": first_response.get("conversation_id"),
            "timestamp": first_response.get("timestamp"),
            "response_text": first_response.get("response_text"),
            "patient_id": first_response.get("patient_id"),
            "response_type": first_response.get("response_type"),
            "details": first_response.get("details"),
            "status": first_response.get("status"),
            # New field: all responses for multi-patient support
            "responses": responses,
            "response_count": len(responses)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading bill balance test response: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read response file: {str(e)}"
        )


@router.get("/bill-balance-test-outputs/{conversation_id}/attachment/{filename}")
async def get_bill_balance_test_attachment(conversation_id: str, filename: str):
    """Serve a bill PDF attachment from a bill balance test output directory."""
    try:
        file_path = Path(BILL_BALANCE_TEST_OUTPUT_DIR) / conversation_id / filename

        # Security check - ensure path stays within test output directory
        if not str(file_path.resolve()).startswith(str(Path(BILL_BALANCE_TEST_OUTPUT_DIR).resolve())):
            raise HTTPException(status_code=403, detail="Access denied")

        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"Attachment not found: {filename}")

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type="application/pdf"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving bill balance attachment {filename}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to serve attachment: {str(e)}"
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


@router.get("/apt-status-test-mode-status")
async def get_apt_status_test_mode_status(db: AsyncSession = Depends(get_db)):
    """Get current apt status test mode status."""
    try:
        setting = await system_settings_crud.get_by_key(db, "apt_status_test_mode")
        if setting:
            return {
                "apt_status_test_mode": setting.setting_value,
                "description": setting.description,
                "last_updated": setting.updated_at,
                "updated_by": setting.updated_by
            }
        else:
            return {
                "apt_status_test_mode": False,
                "description": "Apt status test mode. When enabled, responses are saved to a local directory instead of sending via Front API.",
                "last_updated": None,
                "updated_by": None
            }
    except Exception as e:
        logger.error(f"Error fetching apt status test mode status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch apt status test mode status: {str(e)}"
        )


@router.post("/apt-status-test-mode-toggle")
async def toggle_apt_status_test_mode(
    update: SystemSettingUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Toggle apt status test mode on/off."""
    try:
        setting = await system_settings_crud.update_setting(
            db,
            "apt_status_test_mode",
            update.setting_value,
            updated_by=update.updated_by,
            expected_updated_at=update.expected_updated_at
        )

        return {
            "apt_status_test_mode": setting.setting_value,
            "description": setting.description or "Apt status test mode",
            "last_updated": setting.updated_at,
            "updated_by": setting.updated_by
        }
    except StaleUpdateError as e:
        raise HTTPException(
            status_code=409,
            detail=f"This setting was modified by {e.updated_by or 'another user'} at {e.current_updated_at}. Please refresh and try again."
        )
    except Exception as e:
        logger.error(f"Error toggling apt status test mode: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle apt status test mode: {str(e)}"
        )


@router.get("/apt-status-test-outputs")
async def list_apt_status_test_outputs(db: AsyncSession = Depends(get_db)):
    """List all conversation IDs with apt status test outputs, ordered by latest first."""
    try:
        from app.models.email import Email
        from sqlalchemy import select

        test_dir = Path(APT_STATUS_TEST_OUTPUT_DIR)

        if not test_dir.exists():
            return {"conversations": []}

        conversations = []
        for conv_dir in test_dir.iterdir():
            if conv_dir.is_dir():
                # Find all response files
                response_files = list(conv_dir.glob("response*.json"))

                # Get directory modification time
                latest_time = conv_dir.stat().st_mtime
                for rf in response_files:
                    latest_time = max(latest_time, rf.stat().st_mtime)

                conv_id = conv_dir.name
                conv_info = {
                    "conversation_id": conv_id,
                    "timestamp": latest_time,
                    "has_response": len(response_files) > 0,
                    "response_count": len(response_files),
                    "subject": None,
                    "sender": None,
                    "patient_ids": [],
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

                # Try to get patient IDs from response files
                for rf in response_files:
                    try:
                        with open(rf, "r") as f:
                            response_data = json.load(f)
                            patient_id = response_data.get("patient_id")
                            if patient_id:
                                conv_info["patient_ids"].append(patient_id)
                    except Exception as json_err:
                        logger.warning(f"Could not parse {rf.name} for {conv_id}: {json_err}")

                conversations.append(conv_info)

        # Sort by timestamp descending (latest first)
        conversations.sort(key=lambda x: x["timestamp"], reverse=True)

        return {"conversations": conversations}
    except Exception as e:
        logger.error(f"Error listing apt status test outputs: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list apt status test outputs: {str(e)}"
        )


@router.get("/apt-status-test-outputs/{conversation_id}/response")
async def get_apt_status_test_response(conversation_id: str):
    """Get all response files for a specific apt status test conversation."""
    try:
        conv_dir = Path(APT_STATUS_TEST_OUTPUT_DIR) / conversation_id

        if not conv_dir.exists():
            raise HTTPException(status_code=404, detail="Conversation directory not found")

        # Security check
        if not str(conv_dir.resolve()).startswith(str(Path(APT_STATUS_TEST_OUTPUT_DIR).resolve())):
            raise HTTPException(status_code=403, detail="Access denied")

        # Find all response files
        response_files = list(conv_dir.glob("response*.json"))

        if not response_files:
            raise HTTPException(status_code=404, detail="No response files found")

        # Load all responses
        responses = []
        for rf in sorted(response_files, key=lambda x: x.stat().st_mtime):
            try:
                with open(rf, "r") as f:
                    response_data = json.load(f)
                    response_data["_filename"] = rf.name
                    responses.append(response_data)
            except Exception as json_err:
                logger.warning(f"Could not parse {rf.name}: {json_err}")

        if not responses:
            raise HTTPException(status_code=404, detail="No valid response files found")

        first_response = responses[0]
        return {
            "conversation_id": first_response.get("conversation_id"),
            "timestamp": first_response.get("timestamp"),
            "response_text": first_response.get("response_text"),
            "patient_id": first_response.get("patient_id"),
            "response_type": first_response.get("response_type", "apt_status"),
            "details": first_response.get("details"),
            "status": first_response.get("status"),
            "responses": responses,
            "response_count": len(responses)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reading apt status test response: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read response file: {str(e)}"
        )


@router.delete("/apt-status-test-outputs/{conversation_id}")
async def delete_apt_status_test_output(conversation_id: str):
    """Delete a specific apt status test output directory."""
    try:
        import shutil
        conv_dir = Path(APT_STATUS_TEST_OUTPUT_DIR) / conversation_id

        if not conv_dir.exists():
            raise HTTPException(status_code=404, detail="Conversation directory not found")

        # Security check
        if not str(conv_dir.resolve()).startswith(str(Path(APT_STATUS_TEST_OUTPUT_DIR).resolve())):
            raise HTTPException(status_code=403, detail="Access denied")

        shutil.rmtree(conv_dir)
        return {"message": f"Deleted test output for conversation {conversation_id}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting apt status test output: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete test output: {str(e)}"
        )


@router.delete("/apt-status-test-outputs")
async def clear_all_apt_status_test_outputs():
    """Clear all apt status test outputs."""
    try:
        import shutil
        test_dir = Path(APT_STATUS_TEST_OUTPUT_DIR)

        if test_dir.exists():
            shutil.rmtree(test_dir)
            test_dir.mkdir(parents=True, exist_ok=True)

        return {"message": "All apt status test outputs cleared"}
    except Exception as e:
        logger.error(f"Error clearing apt status test outputs: {e}")
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
                    "email_count": 0,
                    "tags": [],
                }

                # Read tags from response.json if it exists
                response_file = conv_dir / "response.json"
                if response_file.exists():
                    try:
                        import json
                        with open(response_file, "r") as f:
                            response_data = json.load(f)
                        conv_info["tags"] = response_data.get("tags_to_add", [])
                    except Exception:
                        pass

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
            updated_by=request.updated_by,
            expected_updated_at=request.expected_updated_at
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
    except StaleUpdateError as e:
        raise HTTPException(
            status_code=409,
            detail=f"This setting was modified by {e.updated_by or 'another user'} at {e.current_updated_at}. Please refresh and try again."
        )
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
            request.updated_by,
            expected_updated_at=request.expected_updated_at
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
    except StaleUpdateError as e:
        raise HTTPException(
            status_code=409,
            detail=f"This setting was modified by {e.updated_by or 'another user'} at {e.current_updated_at}. Please refresh and try again."
        )
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

        # Get current WORKSPACE settings with row lock
        workspace_row = await tag_settings_crud._get_by_tag_name_for_update(db, "WORKSPACE")
        workspace_settings = workspace_row.settings if workspace_row else {}

        # Update the sender verification flag
        workspace_settings["enable_sender_verification"] = enabled

        # Save back to database (row is already locked)
        if workspace_row:
            workspace_row.settings = workspace_settings
            workspace_row.updated_by = updated_by
            # JSONB columns need flag_modified to ensure SQLAlchemy detects in-place dict changes
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(workspace_row, "settings")
            await db.commit()
            await db.refresh(workspace_row)
        else:
            await tag_settings_crud.create(db, "WORKSPACE", workspace_settings, updated_by)

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

# --- No Action List Endpoints ---

@router.get("/workspace-settings/no-action-list")
async def get_no_action_list(
    db: AsyncSession = Depends(get_db)
):
    """
    Get the list of email addresses and domains that should not trigger
    automated actions (replies or uploads). These senders will still be
    tagged by AI but no automated actions will be performed.

    Returns:
        Dictionary with no_action_list array and metadata
    """
    try:
        from app.crud.tag_settings import tag_settings_crud

        workspace_settings = await tag_settings_crud.get_settings_dict(db, "WORKSPACE")
        no_action_list = workspace_settings.get("no_action_list", [])

        return {
            "no_action_list": no_action_list,
            "count": len(no_action_list),
            "description": "Email addresses and domains that will be tagged but not receive automated replies or uploads"
        }
    except Exception as e:
        logger.error(f"Error fetching no-action list: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch no-action list: {str(e)}"
        )


@router.post("/workspace-settings/no-action-list")
async def add_no_action_item(
    item: str,
    updated_by: str = "Admin",
    db: AsyncSession = Depends(get_db)
):
    """
    Add an email address or domain to the no-action list.

    Items can be:
    - Full email addresses: user@example.com
    - Domain patterns: @example.com (will match any email from that domain)

    Args:
        item: Email address or domain pattern to add
        updated_by: Username of person making the change

    Returns:
        Updated no-action list
    """
    try:
        from app.crud.tag_settings import tag_settings_crud

        # Normalize the item (lowercase, strip whitespace)
        normalized_item = item.strip().lower()

        if not normalized_item:
            raise HTTPException(status_code=400, detail="Item cannot be empty")

        # Basic validation
        if "@" not in normalized_item:
            raise HTTPException(
                status_code=400,
                detail="Item must be an email address (user@domain.com) or domain pattern (@domain.com)"
            )

        # Get current workspace settings with row lock to prevent concurrent modifications
        workspace_row = await tag_settings_crud._get_by_tag_name_for_update(db, "WORKSPACE")
        workspace_settings = workspace_row.settings if workspace_row else {}
        no_action_list = workspace_settings.get("no_action_list", [])

        # Check for duplicates
        if normalized_item in no_action_list:
            raise HTTPException(
                status_code=400,
                detail=f"'{normalized_item}' is already in the no-action list"
            )

        # Add the item
        no_action_list.append(normalized_item)
        workspace_settings["no_action_list"] = no_action_list

        # Save back to database (row is already locked)
        if workspace_row:
            workspace_row.settings = workspace_settings
            workspace_row.updated_by = updated_by
            # JSONB columns need flag_modified to ensure SQLAlchemy detects in-place dict changes
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(workspace_row, "settings")
            await db.commit()
            await db.refresh(workspace_row)
        else:
            await tag_settings_crud.create(db, "WORKSPACE", workspace_settings, updated_by)

        logger.info(f"Added '{normalized_item}' to no-action list by {updated_by}")

        return {
            "success": True,
            "message": f"Added '{normalized_item}' to no-action list",
            "no_action_list": no_action_list,
            "count": len(no_action_list),
            "updated_by": updated_by
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding to no-action list: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add to no-action list: {str(e)}"
        )


@router.delete("/workspace-settings/no-action-list/{item:path}")
async def remove_no_action_item(
    item: str,
    updated_by: str = "Admin",
    db: AsyncSession = Depends(get_db)
):
    """
    Remove an email address or domain from the no-action list.

    Args:
        item: Email address or domain pattern to remove
        updated_by: Username of person making the change

    Returns:
        Updated no-action list
    """
    try:
        from app.crud.tag_settings import tag_settings_crud
        from urllib.parse import unquote

        # URL decode and normalize the item
        decoded_item = unquote(item)
        normalized_item = decoded_item.strip().lower()

        # Get current workspace settings with row lock to prevent concurrent modifications
        workspace_row = await tag_settings_crud._get_by_tag_name_for_update(db, "WORKSPACE")
        workspace_settings = workspace_row.settings if workspace_row else {}
        no_action_list = workspace_settings.get("no_action_list", [])

        # Check if item exists
        if normalized_item not in no_action_list:
            raise HTTPException(
                status_code=404,
                detail=f"'{normalized_item}' not found in no-action list"
            )

        # Remove the item
        no_action_list.remove(normalized_item)
        workspace_settings["no_action_list"] = no_action_list

        # Save back to database (row is already locked)
        if workspace_row:
            workspace_row.settings = workspace_settings
            workspace_row.updated_by = updated_by
            # JSONB columns need flag_modified to ensure SQLAlchemy detects in-place dict changes
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(workspace_row, "settings")
            await db.commit()
            await db.refresh(workspace_row)
        else:
            await tag_settings_crud.create(db, "WORKSPACE", workspace_settings, updated_by)

        logger.info(f"Removed '{normalized_item}' from no-action list by {updated_by}")

        return {
            "success": True,
            "message": f"Removed '{normalized_item}' from no-action list",
            "no_action_list": no_action_list,
            "count": len(no_action_list),
            "updated_by": updated_by
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing from no-action list: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to remove from no-action list: {str(e)}"
        )

# --- END: Workspace Settings Endpoints ---


# --- BEGIN: Test Email Endpoints ---

@router.get("/test-email-scenarios")
async def get_test_email_scenarios():
    """
    Get all available test email scenarios grouped by type.

    Returns:
        Dict with scenarios grouped by type, type labels, and SMTP config status
    """
    try:
        scenarios_data = test_email_service.get_scenarios_by_type()
        smtp_config = test_email_service.check_smtp_config()

        return {
            "scenarios": scenarios_data["scenarios"],
            "types": scenarios_data["types"],
            "smtp_configured": smtp_config["smtp_configured"],
            "recipient_email": smtp_config["recipient_email"],
        }
    except Exception as e:
        logger.error(f"Error fetching test email scenarios: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch test email scenarios: {str(e)}"
        )


@router.get("/test-email-config")
async def get_test_email_config():
    """
    Get SMTP configuration status (not credentials).

    Returns:
        Dict with SMTP configuration status
    """
    try:
        config = test_email_service.check_smtp_config()
        return config
    except Exception as e:
        logger.error(f"Error checking SMTP config: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check SMTP config: {str(e)}"
        )


@router.post("/test-email-scenarios/send")
async def send_test_emails(request: SendTestEmailRequest):
    """
    Send one or more test email scenarios.

    Args:
        request: SendTestEmailRequest with scenario_keys and optional recipient_email

    Returns:
        Dict with results for each scenario
    """
    try:
        results = []
        for scenario_key in request.scenario_keys:
            result = test_email_service.send_test_email(
                scenario_key=scenario_key,
                recipient_email=request.recipient_email
            )
            results.append(result)

        # Log summary
        success_count = sum(1 for r in results if r["status"] == "success")
        logger.info(f"Sent {success_count}/{len(results)} test emails successfully")

        return {"results": results}
    except Exception as e:
        logger.error(f"Error sending test emails: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send test emails: {str(e)}"
        )

# --- END: Test Email Endpoints ---


# --- START: Credential Screening Endpoints ---

@router.get("/credential-screening-status")
async def get_credential_screening_status(
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current status of the RX credential screening setting.

    When enabled (default), RX documents are screened for provider credentials
    against allowed/disallowed lists. When disabled, credential screening is skipped.

    Returns:
        Dict with current status and metadata
    """
    try:
        setting = await system_settings_crud.get_by_key(db, "credential_screening_enabled")

        if setting:
            return {
                "credential_screening_enabled": setting.setting_value,
                "description": setting.description or "Screen RX provider credentials against allowed/disallowed lists",
                "last_updated": setting.updated_at,
                "updated_by": setting.updated_by
            }
        else:
            return {
                "credential_screening_enabled": True,
                "description": "Screen RX provider credentials against allowed/disallowed lists",
                "last_updated": None,
                "updated_by": None
            }
    except Exception as e:
        logger.error(f"Error fetching credential screening status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch credential screening status: {str(e)}"
        )


@router.post("/credential-screening-toggle")
async def toggle_credential_screening(
    update: SystemSettingUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Toggle the RX credential screening setting.

    When enabled: RX documents are screened and 'credential review' tag is applied for disallowed providers
    When disabled: Credential screening is skipped entirely

    Args:
        update: SystemSettingUpdate with the new enabled/disabled state and optional user

    Returns:
        Dict with updated status
    """
    try:
        setting = await system_settings_crud.update_setting(
            db,
            "credential_screening_enabled",
            update.setting_value,
            updated_by=update.updated_by,
            expected_updated_at=update.expected_updated_at
        )

        action = "ENABLED" if update.setting_value else "DISABLED"
        logger.warning(
            f"RX CREDENTIAL SCREENING {action} by {update.updated_by or 'unknown user'}"
        )

        return {
            "credential_screening_enabled": setting.setting_value,
            "description": setting.description or "Screen RX provider credentials against allowed/disallowed lists",
            "last_updated": setting.updated_at,
            "updated_by": setting.updated_by
        }
    except StaleUpdateError as e:
        raise HTTPException(
            status_code=409,
            detail=f"This setting was modified by {e.updated_by or 'another user'} at {e.current_updated_at}. Please refresh and try again."
        )
    except Exception as e:
        logger.error(f"Error toggling credential screening: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle credential screening: {str(e)}"
        )

# --- END: Credential Screening Endpoints ---
