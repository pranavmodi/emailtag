"""Tag management endpoints."""

import logging
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import tag as tag_crud
from app.db.session import get_db
from app.schemas.email import Tag, TagCreate, TagUpdate
from app.services.frontapp import create_tag as create_frontapp_tag

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[Tag])
async def read_tags(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> List[Tag]:
    """
    Retrieve tags.
    
    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        db: Database session
        
    Returns:
        List[Tag]: List of tags
    """
    return await tag_crud.get_multi(db, skip=skip, limit=limit)


@router.post("/", response_model=Tag, status_code=status.HTTP_201_CREATED)
async def create_tag(
    tag_in: TagCreate,
    db: AsyncSession = Depends(get_db),
) -> Tag:
    """
    Create new tag.
    
    Args:
        tag_in: Tag data
        db: Database session
        
    Returns:
        Tag: Created tag
    """
    # Check if tag already exists
    existing_tag = await tag_crud.get_by_name(db, name=tag_in.name)
    if existing_tag:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tag with name '{tag_in.name}' already exists",
        )
    
    # Create tag in FrontApp if not already linked
    if not tag_in.front_tag_id:
        frontapp_tag = create_frontapp_tag(tag_in.name, tag_in.description)
        if frontapp_tag:
            tag_in.front_tag_id = frontapp_tag["id"]
    
    # Create tag in database
    return await tag_crud.create(db, obj_in=tag_in)


@router.get("/{tag_id}", response_model=Tag)
async def read_tag(
    tag_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Tag:
    """
    Get tag by ID.
    
    Args:
        tag_id: Tag ID
        db: Database session
        
    Returns:
        Tag: Tag data
    """
    tag = await tag_crud.get(db, id=tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found",
        )
    return tag


@router.put("/{tag_id}", response_model=Tag)
async def update_tag(
    tag_id: UUID,
    tag_in: TagUpdate,
    db: AsyncSession = Depends(get_db),
) -> Tag:
    """
    Update a tag.
    
    Args:
        tag_id: Tag ID
        tag_in: Updated tag data
        db: Database session
        
    Returns:
        Tag: Updated tag
    """
    tag = await tag_crud.get(db, id=tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found",
        )
    
    # If name is being updated, check for duplicates
    if tag_in.name and tag_in.name != tag.name:
        existing_tag = await tag_crud.get_by_name(db, name=tag_in.name)
        if existing_tag:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tag with name '{tag_in.name}' already exists",
            )
    
    return await tag_crud.update(db, db_obj=tag, obj_in=tag_in)


@router.delete("/{tag_id}", response_model=Dict[str, Any])
async def delete_tag(
    tag_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Delete a tag.
    
    Args:
        tag_id: Tag ID
        db: Database session
        
    Returns:
        Dict[str, Any]: Status message
    """
    tag = await tag_crud.get(db, id=tag_id)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tag not found",
        )
    
    await tag_crud.remove(db, id=tag_id)
    return {"status": "success", "message": f"Tag '{tag.name}' deleted"} 