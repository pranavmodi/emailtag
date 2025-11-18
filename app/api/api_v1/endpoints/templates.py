"""API endpoints for message template and tag settings management."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.crud.message_template import message_template_crud
from app.crud.tag_settings import tag_settings_crud
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
            updated_by=template.updated_by
        )

        if not updated_template:
            raise HTTPException(
                status_code=404,
                detail=f"Template with key '{template_key}' not found"
            )

        logger.warning(f"📝 Template '{template_key}' UPDATED by {template.updated_by or 'unknown user'}")
        return updated_template
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
            updated_by=tag_settings.updated_by
        )

        logger.warning(f"⚙️ Tag settings for '{tag_name}' UPDATED by {tag_settings.updated_by or 'unknown user'}")
        return updated_settings
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
