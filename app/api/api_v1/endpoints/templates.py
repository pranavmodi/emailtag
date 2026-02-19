"""API endpoints for message template and tag settings management."""
import logging
import re
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, List, Optional
from app.db.session import get_db
from app.core.exceptions import StaleUpdateError
from app.crud.message_template import message_template_crud
from app.crud.tag_settings import tag_settings_crud
from app.crud.template_attachment import template_attachment_crud
from app.schemas.message_template import (
    MessageTemplateResponse,
    MessageTemplateListResponse,
    MessageTemplateCreate,
    MessageTemplateUpdate
)
from app.schemas.tag_settings import (
    TagSettingsResponse,
    TagSettingsListResponse,
    TagSettingsCreate,
    TagSettingsUpdate
)
from app.schemas.template_attachment import (
    TemplateAttachmentResponse,
    TemplateAttachmentListResponse,
    TemplateAttachmentUploadResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/templates", response_model=MessageTemplateListResponse)
async def list_templates(db: AsyncSession = Depends(get_db)):
    """
    Get all message templates.

    Returns:
        List of all message templates with their details
    """
    try:
        templates = await message_template_crud.list_all(db)
        return MessageTemplateListResponse(
            templates=templates,
            count=len(templates)
        )
    except Exception as e:
        logger.error(f"Error fetching templates: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch templates: {str(e)}"
        )


@router.get("/templates/{template_key}", response_model=MessageTemplateResponse)
async def get_template(
    template_key: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific template by its key.

    Args:
        template_key: Unique key for the template

    Returns:
        MessageTemplateResponse with template details
    """
    try:
        template = await message_template_crud.get_by_key(db, template_key)
        if not template:
            raise HTTPException(
                status_code=404,
                detail=f"Template with key '{template_key}' not found"
            )
        return template
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching template '{template_key}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch template: {str(e)}"
        )


@router.post("/templates", response_model=MessageTemplateResponse)
async def create_template(
    template: MessageTemplateCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new message template.

    Args:
        template: Template data to create

    Returns:
        MessageTemplateResponse with created template details
    """
    try:
        # Check if template already exists
        existing = await message_template_crud.get_by_key(db, template.template_key)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Template with key '{template.template_key}' already exists"
            )

        new_template = await message_template_crud.create(
            db,
            template_key=template.template_key,
            template_name=template.template_name,
            template_body=template.template_body,
            description=template.description,
            updated_by=template.updated_by
        )

        logger.warning(f"📝 Template '{template.template_key}' CREATED by {template.updated_by or 'unknown user'}")
        return new_template
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create template: {str(e)}"
        )


@router.patch("/templates/{template_key}", response_model=MessageTemplateResponse)
async def update_template(
    template_key: str,
    template: MessageTemplateUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing message template.

    Args:
        template_key: Unique key for the template
        template: Template data to update

    Returns:
        MessageTemplateResponse with updated template details
    """
    try:
        updated_template = await message_template_crud.update(
            db,
            template_key=template_key,
            template_body=template.template_body,
            template_name=template.template_name,
            description=template.description,
            updated_by=template.updated_by,
            expected_updated_at=template.expected_updated_at
        )

        if not updated_template:
            raise HTTPException(
                status_code=404,
                detail=f"Template with key '{template_key}' not found"
            )

        logger.warning(f"📝 Template '{template_key}' UPDATED by {template.updated_by or 'unknown user'}")
        return updated_template
    except StaleUpdateError as e:
        raise HTTPException(
            status_code=409,
            detail=f"This template was modified by {e.updated_by or 'another user'} at {e.current_updated_at}. Please refresh and try again."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating template '{template_key}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update template: {str(e)}"
        )


# ============================================================================
# TAG SETTINGS ENDPOINTS
# ============================================================================


@router.get("/tag-settings", response_model=TagSettingsListResponse)
async def list_tag_settings(db: AsyncSession = Depends(get_db)):
    """
    Get all tag settings.

    Returns:
        List of all tag settings with their configurations
    """
    try:
        tag_settings = await tag_settings_crud.get_all(db)
        return TagSettingsListResponse(
            items=tag_settings,
            total=len(tag_settings)
        )
    except Exception as e:
        logger.error(f"Error fetching tag settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch tag settings: {str(e)}"
        )


@router.get("/tag-settings/{tag_name}", response_model=TagSettingsResponse)
async def get_tag_settings(
    tag_name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get settings for a specific tag.

    Args:
        tag_name: Name of the tag

    Returns:
        TagSettingsResponse with configuration details
    """
    try:
        tag_settings = await tag_settings_crud.get_by_tag_name(db, tag_name)
        if not tag_settings:
            raise HTTPException(
                status_code=404,
                detail=f"Settings for tag '{tag_name}' not found"
            )
        return tag_settings
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching settings for tag '{tag_name}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch tag settings: {str(e)}"
        )


@router.post("/tag-settings", response_model=TagSettingsResponse)
async def create_tag_settings(
    tag_settings: TagSettingsCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create new tag settings.

    Args:
        tag_settings: Tag settings data to create

    Returns:
        TagSettingsResponse with created settings
    """
    try:
        # Check if settings already exist for this tag
        existing = await tag_settings_crud.get_by_tag_name(db, tag_settings.tag_name)
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Settings for tag '{tag_settings.tag_name}' already exist. Use PATCH to update."
            )

        new_settings = await tag_settings_crud.create(
            db,
            tag_name=tag_settings.tag_name,
            settings=tag_settings.settings,
            updated_by=tag_settings.updated_by
        )

        logger.warning(f"⚙️ Tag settings for '{tag_settings.tag_name}' CREATED by {tag_settings.updated_by or 'unknown user'}")
        return new_settings
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating tag settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create tag settings: {str(e)}"
        )


@router.patch("/tag-settings/{tag_name}", response_model=TagSettingsResponse)
async def update_tag_settings(
    tag_name: str,
    tag_settings: TagSettingsUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update existing tag settings or create if doesn't exist.

    Args:
        tag_name: Name of the tag
        tag_settings: Tag settings data to update

    Returns:
        TagSettingsResponse with updated settings
    """
    try:
        updated_settings = await tag_settings_crud.update(
            db,
            tag_name=tag_name,
            settings=tag_settings.settings,
            updated_by=tag_settings.updated_by,
            expected_updated_at=tag_settings.expected_updated_at
        )

        logger.warning(f"⚙️ Tag settings for '{tag_name}' UPDATED by {tag_settings.updated_by or 'unknown user'}")
        return updated_settings
    except StaleUpdateError as e:
        raise HTTPException(
            status_code=409,
            detail=f"These settings were modified by {e.updated_by or 'another user'} at {e.current_updated_at}. Please refresh and try again."
        )
    except Exception as e:
        logger.error(f"Error updating tag settings for '{tag_name}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update tag settings: {str(e)}"
        )


@router.delete("/tag-settings/{tag_name}")
async def delete_tag_settings(
    tag_name: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete tag settings.

    Args:
        tag_name: Name of the tag

    Returns:
        Success message
    """
    try:
        deleted = await tag_settings_crud.delete(db, tag_name)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail=f"Settings for tag '{tag_name}' not found"
            )

        logger.warning(f"⚙️ Tag settings for '{tag_name}' DELETED")
        return {"message": f"Settings for tag '{tag_name}' deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tag settings for '{tag_name}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete tag settings: {str(e)}"
        )


# ============================================================================
# TABLE PREVIEW ENDPOINT
# ============================================================================

VALID_TABLE_TYPES = {
    "appointment_table",
    "billing_status_table",
    "lien_status_table",
    "call_log_table",
    "text_log_table",
}


def _get_day_suffix(day: int) -> str:
    """Returns the ordinal suffix for a day (st, nd, rd, th)."""
    if 10 <= day % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
    return suffix


def _transform_studies_for_table(raw_studies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Transform raw study data from MCP into the format expected by
    _generate_appointment_table_html. Extracted from fetch_appointment_details_by_patient_id.
    """
    transformed = []
    for study in raw_studies:
        appointment_datetime_str = "N/A"
        service_appt_time_str = study.get("study_date_time", "")
        study_image_count = study.get("image_count", 0)

        parsed_dt = None
        if service_appt_time_str:
            try:
                if "T" in service_appt_time_str:
                    parsed_dt = datetime.fromisoformat(service_appt_time_str.replace("Z", ""))
                else:
                    try:
                        parsed_dt = datetime.strptime(service_appt_time_str, "%m/%d/%Y %I:%M:%S %p")
                    except ValueError:
                        try:
                            parsed_time_obj = datetime.strptime(service_appt_time_str, "%I:%M %p").time()
                            appointment_datetime_str = f"Date N/A @ {parsed_time_obj.strftime('%I:%M %p')}"
                        except ValueError:
                            additional_formats = [
                                "%d %B %Y %I:%M %p", "%d %B %Y", "%Y-%m-%d %H:%M:%S",
                                "%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d",
                                "%m/%d/%y %I:%M %p", "%Y-%m-%d %I:%M %p",
                                "%B %d, %Y", "%d-%b-%Y", "%b %d, %Y", "%Y-%B-%d",
                            ]
                            for fmt in additional_formats:
                                try:
                                    parsed_dt = datetime.strptime(service_appt_time_str, fmt)
                                    break
                                except ValueError:
                                    continue
                            if not parsed_dt:
                                appointment_datetime_str = f"{service_appt_time_str} (Could not parse)"

                if parsed_dt:
                    if parsed_dt.time() == datetime.min.time():
                        day_name = parsed_dt.strftime('%A')
                        month_name = parsed_dt.strftime('%B')
                        day_num = parsed_dt.day
                        year = parsed_dt.year
                        day_suffix = _get_day_suffix(day_num)
                        appointment_datetime_str = f"{day_name}, {month_name} {day_num}{day_suffix}, {year}<br/><br/>N/A"
                    else:
                        day_name = parsed_dt.strftime('%A')
                        month_name = parsed_dt.strftime('%B')
                        day_num = parsed_dt.day
                        year = parsed_dt.year
                        day_suffix = _get_day_suffix(day_num)
                        time_str = parsed_dt.strftime('%I:%M %p').lstrip('0')
                        appointment_datetime_str = f"{day_name}, {month_name} {day_num}{day_suffix}, {year}<br/><br/>{time_str}"

            except ValueError:
                appointment_datetime_str = f"{service_appt_time_str} (Unparseable)"

        # Location display
        facility_info = study.get("facility", {})
        facility_address = facility_info.get('address', '').strip()
        if not facility_address or facility_address in ['N/A', 'Not Available', 'Not Available in Database']:
            location_display = "N/A"
        else:
            match = re.search(r'^(.*?)\s+([A-Za-z][A-Za-z\s]+?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$', facility_address)
            if match:
                street = match.group(1).strip()
                city = match.group(2).strip()
                state = match.group(3)
                zip_code = match.group(4)
                location_display = f"{street}<br/>{city}, {state} {zip_code}"
            else:
                location_display = facility_address

        images_available = "Yes" if study_image_count > 0 else "No"

        # MRI type from resources
        resources = study.get("resources", "")
        mri_type = "N/A"
        if resources:
            resources_upper = resources.upper()
            if "STAND" in resources_upper:
                mri_type = "Stand Up"
            elif "OPEN" in resources_upper:
                mri_type = "Open"
            elif "WIDE BORE" in resources_upper:
                mri_type = "Wide Bore"
            elif "CLOSED" in resources_upper:
                mri_type = "Closed"

        transformed.append({
            "study_id": study.get("authorization_number", "N/A"),
            "exam_description": study.get("study_description", "N/A"),
            "status": study.get("ordered_status", "N/A"),
            "appointment_datetime_str": appointment_datetime_str,
            "location_name": location_display,
            "mri_type": mri_type,
            "images_available": images_available,
            "report_available": "No",
            "_sort_datetime": parsed_dt,
        })

    # Sort chronologically: earliest first, N/A at bottom
    transformed.sort(
        key=lambda x: (x.get("_sort_datetime") is None, x.get("_sort_datetime") or datetime.max)
    )
    return transformed


@router.get("/preview-table")
async def preview_table(
    patient_id: str = Query(..., description="Patient ID to generate the table for"),
    table_type: str = Query(..., description="Type of table to generate"),
    signature_type: str = Query("ASL", description="Signature type for lien_status_table (ASL or PSL)"),
):
    """
    Generate a live preview of a data table using real patient data from RadFlow.

    Returns the same HTML tables that would be embedded in production autorespond emails.
    """
    if table_type not in VALID_TABLE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid table_type '{table_type}'. Must be one of: {', '.join(sorted(VALID_TABLE_TYPES))}"
        )

    if not patient_id.strip():
        raise HTTPException(status_code=400, detail="patient_id is required")

    patient_id = patient_id.strip()

    try:
        html = ""

        if table_type == "billing_status_table":
            from app.helpers.billing_status_table import generate_billing_status_table
            html = await generate_billing_status_table(patient_id)

        elif table_type == "call_log_table":
            from app.helpers.call_log_table import generate_call_log_table
            html = await generate_call_log_table(patient_id)

        elif table_type == "text_log_table":
            from app.helpers.text_log_table import generate_text_log_table
            html = await generate_text_log_table(patient_id)

        elif table_type == "lien_status_table":
            from app.agents.lien_agent import _generate_lien_status_table
            html = await _generate_lien_status_table(patient_id, [], signature_type)

        elif table_type == "appointment_table":
            from app.agents.agent_helpers import get_patient_and_study_info
            from app.agents.apt_status_req_agent import _generate_appointment_table_html

            info = await get_patient_and_study_info(patient_id)
            studies_result = info.get("study_result", {})

            if not isinstance(studies_result, dict) or not studies_result.get("success"):
                error_msg = studies_result.get("error", "Failed to fetch study details") if isinstance(studies_result, dict) else "Invalid response from study service"
                raise HTTPException(status_code=502, detail=str(error_msg))

            raw_studies = studies_result.get("studies", [])
            if not raw_studies:
                html = "<p>No appointments found for this patient.</p>"
            else:
                transformed = _transform_studies_for_table(raw_studies)
                html = _generate_appointment_table_html(transformed)

        return {
            "html": html,
            "table_type": table_type,
            "patient_id": patient_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"🔍 Error generating preview table (type={table_type}, patient={patient_id}): {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate {table_type} preview: {str(e)}"
        )


# ============================================================================
# TEMPLATE ATTACHMENTS ENDPOINTS
# ============================================================================

# Allowed MIME types for uploads
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.get("/tag-settings/{tag_name}/attachments", response_model=TemplateAttachmentListResponse)
async def list_tag_attachments(
    tag_name: str,
    template_key: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all attachments for a specific tag.

    Args:
        tag_name: Name of the tag
        template_key: Optional template key to filter by

    Returns:
        List of attachments for the tag
    """
    try:
        attachments = await template_attachment_crud.get_by_tag_and_template(
            db, tag_name, template_key
        )
        return TemplateAttachmentListResponse(
            items=attachments,
            total=len(attachments)
        )
    except Exception as e:
        logger.error(f"Error fetching attachments for tag '{tag_name}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch attachments: {str(e)}"
        )


@router.post("/tag-settings/{tag_name}/attachments", response_model=TemplateAttachmentUploadResponse)
async def upload_tag_attachment(
    tag_name: str,
    file: UploadFile = File(...),
    template_key: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    uploaded_by: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload an attachment for a tag.

    Args:
        tag_name: Name of the tag
        file: The file to upload
        template_key: Optional template key within the tag
        description: Optional description
        uploaded_by: User uploading

    Returns:
        Created attachment details
    """
    try:
        # Validate file type
        if file.content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"File type '{file.content_type}' not allowed. Allowed types: {', '.join(ALLOWED_MIME_TYPES)}"
            )

        # Read file content
        file_content = await file.read()

        # Validate file size
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB"
            )

        # Create attachment
        attachment = await template_attachment_crud.create(
            db,
            tag_name=tag_name,
            filename=file.filename or "unnamed",
            file_content=file_content,
            mime_type=file.content_type,
            template_key=template_key,
            description=description,
            uploaded_by=uploaded_by
        )

        logger.warning(f"📎 Attachment '{file.filename}' uploaded for tag '{tag_name}' by {uploaded_by or 'unknown user'}")

        return TemplateAttachmentUploadResponse(
            attachment=attachment,
            message=f"File '{file.filename}' uploaded successfully"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading attachment for tag '{tag_name}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload attachment: {str(e)}"
        )


@router.get("/tag-settings/{tag_name}/attachments/{attachment_id}")
async def get_attachment(
    tag_name: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get attachment metadata.

    Args:
        tag_name: Name of the tag
        attachment_id: UUID of the attachment

    Returns:
        Attachment metadata
    """
    try:
        attachment_uuid = uuid.UUID(attachment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid attachment ID format")

    try:
        attachment = await template_attachment_crud.get_by_id(db, attachment_uuid)
        if not attachment or attachment.tag_name != tag_name:
            raise HTTPException(
                status_code=404,
                detail=f"Attachment not found"
            )
        return attachment
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching attachment '{attachment_id}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch attachment: {str(e)}"
        )


@router.get("/tag-settings/{tag_name}/attachments/{attachment_id}/view")
async def view_attachment(
    tag_name: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    View an attachment file inline (opens in browser).

    Args:
        tag_name: Name of the tag
        attachment_id: UUID of the attachment

    Returns:
        File content served inline for browser viewing
    """
    try:
        attachment_uuid = uuid.UUID(attachment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid attachment ID format")

    try:
        attachment = await template_attachment_crud.get_by_id(db, attachment_uuid)
        if not attachment or attachment.tag_name != tag_name:
            raise HTTPException(
                status_code=404,
                detail=f"Attachment not found"
            )

        # Get file content
        file_content = template_attachment_crud.get_file_content(attachment)
        if file_content is None:
            raise HTTPException(
                status_code=404,
                detail="Attachment file not found on disk"
            )

        # Serve inline for viewing in browser
        return Response(
            content=file_content,
            media_type=attachment.mime_type,
            headers={
                "Content-Disposition": f'inline; filename="{attachment.filename}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error viewing attachment '{attachment_id}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to view attachment: {str(e)}"
        )


@router.get("/tag-settings/{tag_name}/attachments/{attachment_id}/download")
async def download_attachment(
    tag_name: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Download an attachment file.

    Args:
        tag_name: Name of the tag
        attachment_id: UUID of the attachment

    Returns:
        File content as binary response (forces download)
    """
    try:
        attachment_uuid = uuid.UUID(attachment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid attachment ID format")

    try:
        attachment = await template_attachment_crud.get_by_id(db, attachment_uuid)
        if not attachment or attachment.tag_name != tag_name:
            raise HTTPException(
                status_code=404,
                detail=f"Attachment not found"
            )

        # Get file content
        file_content = template_attachment_crud.get_file_content(attachment)
        if file_content is None:
            raise HTTPException(
                status_code=404,
                detail="Attachment file not found on disk"
            )

        return Response(
            content=file_content,
            media_type=attachment.mime_type,
            headers={
                "Content-Disposition": f'attachment; filename="{attachment.filename}"'
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading attachment '{attachment_id}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download attachment: {str(e)}"
        )


@router.delete("/tag-settings/{tag_name}/attachments/{attachment_id}")
async def delete_attachment(
    tag_name: str,
    attachment_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete an attachment.

    Args:
        tag_name: Name of the tag
        attachment_id: UUID of the attachment

    Returns:
        Success message
    """
    try:
        attachment_uuid = uuid.UUID(attachment_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid attachment ID format")

    try:
        # Verify attachment belongs to this tag
        attachment = await template_attachment_crud.get_by_id(db, attachment_uuid)
        if not attachment or attachment.tag_name != tag_name:
            raise HTTPException(
                status_code=404,
                detail=f"Attachment not found"
            )

        filename = attachment.filename
        deleted = await template_attachment_crud.delete(db, attachment_uuid)

        if deleted:
            logger.warning(f"📎 Attachment '{filename}' deleted from tag '{tag_name}'")
            return {"message": f"Attachment '{filename}' deleted successfully"}
        else:
            raise HTTPException(
                status_code=404,
                detail="Attachment not found"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting attachment '{attachment_id}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete attachment: {str(e)}"
        )
