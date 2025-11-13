"""API endpoints for message template management."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.crud.message_template import message_template_crud
from app.schemas.message_template import (
    MessageTemplateResponse,
    MessageTemplateListResponse,
    MessageTemplateCreate,
    MessageTemplateUpdate
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
