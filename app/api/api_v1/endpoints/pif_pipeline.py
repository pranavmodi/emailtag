"""PIF outreach pipeline endpoints."""

import logging
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.pif_pipeline import pif_pipeline as pipeline_crud
from app.db.session import get_db
from app.schemas.pif_pipeline import (
    PipelineListResponse,
    PipelineRecordCreate,
    PipelineRecordResponse,
    PipelineRecordUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/", response_model=PipelineRecordResponse, status_code=status.HTTP_201_CREATED)
async def create_pipeline_record(
    record_in: PipelineRecordCreate,
    db: AsyncSession = Depends(get_db),
) -> PipelineRecordResponse:
    """
    Create a new outreach pipeline record for a firm.

    Args:
        record_in: Pipeline record data
        db: Database session

    Returns:
        Created pipeline record
    """
    # Verify the pif exists
    from app.crud.pif_info import pif_info as pif_info_crud
    pif = await pif_info_crud.get(db, id=record_in.pif_id)
    if not pif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PIF firm {record_in.pif_id} not found",
        )

    record = await pipeline_crud.create(db, obj_in=record_in)
    logger.info(f"Created pipeline record {record.id} for firm {pif.firm_name}")
    return record


@router.get("/by-firm/{pif_id}", response_model=PipelineListResponse)
async def list_pipeline_by_firm(
    pif_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PipelineListResponse:
    """
    List all pipeline records for a specific firm, sorted by created_at.

    Args:
        pif_id: PIF firm ID
        db: Database session

    Returns:
        List of pipeline records
    """
    records = await pipeline_crud.list_by_pif(db, pif_id=pif_id)
    return PipelineListResponse(items=records, total=len(records))


@router.get("/{record_id}", response_model=PipelineRecordResponse)
async def get_pipeline_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PipelineRecordResponse:
    """
    Get a single pipeline record by ID.

    Args:
        record_id: Pipeline record ID
        db: Database session

    Returns:
        Pipeline record
    """
    record = await pipeline_crud.get(db, record_id=record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline record not found",
        )
    return record


@router.put("/{record_id}", response_model=PipelineRecordResponse)
async def update_pipeline_record(
    record_id: UUID,
    record_in: PipelineRecordUpdate,
    db: AsyncSession = Depends(get_db),
) -> PipelineRecordResponse:
    """
    Update a pipeline record (status, notes, dates, etc.).

    Args:
        record_id: Pipeline record ID
        record_in: Updated data
        db: Database session

    Returns:
        Updated pipeline record
    """
    record = await pipeline_crud.get(db, record_id=record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline record not found",
        )

    updated = await pipeline_crud.update(db, db_obj=record, obj_in=record_in)
    return updated


@router.delete("/{record_id}", response_model=Dict[str, Any])
async def delete_pipeline_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Delete a pipeline record.

    Args:
        record_id: Pipeline record ID
        db: Database session

    Returns:
        Success message
    """
    deleted = await pipeline_crud.delete(db, record_id=record_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline record not found",
        )
    return {"status": "success", "message": f"Pipeline record {record_id} deleted"}
