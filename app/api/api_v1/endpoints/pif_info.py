"""PIF (Personal Injury Firm) information endpoints."""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.pif_info import pif_info as pif_info_crud
from app.db.session import get_db
from app.schemas.pif_info import (
    PifInfoCreate,
    PifInfoUpdate,
    PifInfoResponse,
    PifInfoListResponse,
    ProcessDayRequest,
    ProcessDayResponse,
    ResearchResponse,
    ResearchStartResponse,
    ResearchStatusResponse,
    LeadershipMember,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=PifInfoListResponse)
async def list_pif_info(
    search: str = Query(None, description="Search term for firm name, email, or website"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> PifInfoListResponse:
    """
    List all PIF info with optional search and pagination.

    Args:
        search: Optional search term
        page: Page number (1-indexed)
        page_size: Number of items per page
        db: Database session

    Returns:
        Paginated list of PIF info
    """
    skip = (page - 1) * page_size
    items, total = await pif_info_crud.search(db, search=search, skip=skip, limit=page_size)

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PifInfoListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{pif_id}", response_model=PifInfoResponse)
async def get_pif_info(
    pif_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PifInfoResponse:
    """
    Get PIF info by ID.

    Args:
        pif_id: PIF info ID
        db: Database session

    Returns:
        PIF info details
    """
    pif = await pif_info_crud.get(db, id=pif_id)
    if not pif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PIF info not found",
        )
    return pif


@router.post("/", response_model=PifInfoResponse, status_code=status.HTTP_201_CREATED)
async def create_pif_info(
    pif_in: PifInfoCreate,
    db: AsyncSession = Depends(get_db),
) -> PifInfoResponse:
    """
    Create new PIF info.

    Args:
        pif_in: PIF info data
        db: Database session

    Returns:
        Created PIF info
    """
    # Check if website already exists
    if pif_in.website:
        existing = await pif_info_crud.get_by_website(db, pif_in.website)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PIF info with website '{pif_in.website}' already exists",
            )

    return await pif_info_crud.create(db, obj_in=pif_in)


@router.put("/{pif_id}", response_model=PifInfoResponse)
async def update_pif_info(
    pif_id: UUID,
    pif_in: PifInfoUpdate,
    db: AsyncSession = Depends(get_db),
) -> PifInfoResponse:
    """
    Update PIF info.

    Args:
        pif_id: PIF info ID
        pif_in: Updated PIF info data
        db: Database session

    Returns:
        Updated PIF info
    """
    pif = await pif_info_crud.get(db, id=pif_id)
    if not pif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PIF info not found",
        )

    return await pif_info_crud.update(db, db_obj=pif, obj_in=pif_in)


@router.delete("/{pif_id}", response_model=Dict[str, Any])
async def delete_pif_info(
    pif_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Delete PIF info.

    Args:
        pif_id: PIF info ID
        db: Database session

    Returns:
        Success message
    """
    pif = await pif_info_crud.get(db, id=pif_id)
    if not pif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PIF info not found",
        )

    await pif_info_crud.remove(db, id=pif_id)
    return {"status": "success", "message": f"PIF info '{pif.firm_name}' deleted"}


@router.post("/process-day", response_model=ProcessDayResponse)
async def process_day_conversations(
    request: ProcessDayRequest,
    db: AsyncSession = Depends(get_db),
) -> ProcessDayResponse:
    """
    Process all conversations from a specific day to extract PIF info.

    This endpoint:
    1. Fetches all conversations from the specified date
    2. Extracts firm information from each conversation
    3. Upserts the extracted data into the pif_info table

    Args:
        request: Request containing target_date
        db: Database session

    Returns:
        Processing summary
    """
    from app.crud import email as email_crud

    try:
        target_date = datetime.strptime(request.target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD",
        )

    logger.info(f"Processing conversations for date: {target_date}")

    # Get all emails from the target date
    emails = await email_crud.get_emails_by_date(db, target_date)
    conversation_ids = [e.front_conversation_id for e in emails if e.front_conversation_id]

    logger.info(f"Found {len(conversation_ids)} conversations for {target_date}")

    # Import pifstats extraction
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))

    from pifstats.src.front_client import get_conversation_with_messages
    from pifstats.src.entity_extractor import extract_firm_info

    processed = 0
    firms_found = 0
    firms_created = 0
    firms_updated = 0
    errors = []

    for conv_id in conversation_ids:
        try:
            # Get conversation data
            conv_data = get_conversation_with_messages(conv_id)
            if not conv_data.get("full_text"):
                continue

            processed += 1

            # Extract firm info
            firm_info = extract_firm_info(conv_data["full_text"])
            if not firm_info or not firm_info.firm_name:
                continue

            firms_found += 1

            # Upsert to database
            contacts_dicts = [c.model_dump() for c in firm_info.contacts]

            pif, is_new = await pif_info_crud.upsert_from_extraction(
                db,
                firm_name=firm_info.firm_name,
                website=firm_info.firm_website or None,
                emails=firm_info.firm_emails,
                phones=firm_info.firm_phones,
                fax=firm_info.firm_fax or None,
                addresses=[firm_info.firm_address] if firm_info.firm_address else [],
                contacts=contacts_dicts,
                conversation_id=conv_id,
                extraction_notes=firm_info.extraction_notes or None,
            )

            if is_new:
                firms_created += 1
            else:
                firms_updated += 1

        except Exception as e:
            logger.error(f"Error processing conversation {conv_id}: {e}")
            errors.append(f"{conv_id}: {str(e)}")

    logger.info(
        f"Processed {processed} conversations, found {firms_found} firms, "
        f"created {firms_created}, updated {firms_updated}"
    )

    return ProcessDayResponse(
        date=request.target_date,
        total_conversations=len(conversation_ids),
        processed=processed,
        firms_found=firms_found,
        firms_created=firms_created,
        firms_updated=firms_updated,
        errors=errors[:10],  # Limit errors to first 10
    )


@router.post("/extract-conversation/{conversation_id}", response_model=Dict[str, Any])
async def extract_from_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Extract PIF info from a single conversation.

    Args:
        conversation_id: Front conversation ID
        db: Database session

    Returns:
        Extracted firm info and database operation result
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))

    from pifstats.src.front_client import get_conversation_with_messages
    from pifstats.src.entity_extractor import extract_firm_info

    # Get conversation data
    conv_data = get_conversation_with_messages(conversation_id)
    if not conv_data.get("full_text"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No content found for conversation {conversation_id}",
        )

    # Extract firm info
    firm_info = extract_firm_info(conv_data["full_text"])
    if not firm_info or not firm_info.firm_name:
        return {
            "conversation_id": conversation_id,
            "extracted": False,
            "message": "No firm information found in conversation",
        }

    # Upsert to database
    contacts_dicts = [c.model_dump() for c in firm_info.contacts]

    pif, is_new = await pif_info_crud.upsert_from_extraction(
        db,
        firm_name=firm_info.firm_name,
        website=firm_info.firm_website or None,
        emails=firm_info.firm_emails,
        phones=firm_info.firm_phones,
        fax=firm_info.firm_fax or None,
        addresses=[firm_info.firm_address] if firm_info.firm_address else [],
        contacts=contacts_dicts,
        conversation_id=conversation_id,
        extraction_notes=firm_info.extraction_notes or None,
    )

    return {
        "conversation_id": conversation_id,
        "extracted": True,
        "is_new_firm": is_new,
        "pif_id": str(pif.id),
        "firm_name": pif.firm_name,
        "firm_info": {
            "website": pif.website,
            "emails": pif.emails,
            "phones": pif.phones,
            "fax": pif.fax,
            "addresses": pif.addresses,
            "contacts": pif.contacts,
            "conversation_count": len(pif.conversation_ids),
        },
    }


@router.get("/conversations/{date_str}", response_model=List[str])
async def get_conversations_for_date(
    date_str: str,
    db: AsyncSession = Depends(get_db),
) -> List[str]:
    """
    Get all conversation IDs for a specific date.

    Args:
        date_str: Date in YYYY-MM-DD format
        db: Database session

    Returns:
        List of conversation IDs
    """
    from app.crud import email as email_crud

    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD",
        )

    emails = await email_crud.get_emails_by_date(db, target_date)
    return [e.front_conversation_id for e in emails if e.front_conversation_id]


@router.post("/{pif_id}/research", response_model=ResearchStartResponse)
async def research_firm(
    pif_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ResearchStartResponse:
    """
    Start async deep research for a PIF using OpenAI web search.

    This endpoint:
    1. Looks up the firm by ID
    2. Queues a Celery task for research
    3. Returns immediately with a task_id for polling

    The research includes:
    - Initial firm research (leadership, practice areas, etc.)
    - Deep LinkedIn research on each leadership member

    Args:
        pif_id: PIF info ID
        db: Database session

    Returns:
        Task ID and status for polling
    """
    # Get the PIF record
    pif = await pif_info_crud.get(db, id=pif_id)
    if not pif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PIF info not found",
        )

    # Update status to queued
    await pif_info_crud.update(
        db,
        db_obj=pif,
        obj_in={"research_status": "queued"}
    )

    # Start the Celery task
    from app.tasks.firm_research import research_firm_task

    task = research_firm_task.delay(str(pif_id))

    logger.info(f"Research task queued for firm: {pif.firm_name}, task_id: {task.id}")

    return ResearchStartResponse(
        pif_id=pif_id,
        firm_name=pif.firm_name,
        task_id=task.id,
        status="queued",
        message="Research task queued. Poll /research-status/{task_id} for progress."
    )


@router.get("/research-status/{task_id}", response_model=ResearchStatusResponse)
async def get_research_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> ResearchStatusResponse:
    """
    Poll for research task status.

    Args:
        task_id: Celery task ID
        db: Database session

    Returns:
        Current status of the research task
    """
    from celery.result import AsyncResult
    from app.tasks.worker import celery_app

    result = AsyncResult(task_id, app=celery_app)

    # Get task state
    if result.state == "PENDING":
        return ResearchStatusResponse(
            pif_id=UUID("00000000-0000-0000-0000-000000000000"),
            firm_name="",
            task_id=task_id,
            status="queued",
            message="Research task is queued"
        )
    elif result.state == "STARTED" or result.state == "RETRY":
        return ResearchStatusResponse(
            pif_id=UUID("00000000-0000-0000-0000-000000000000"),
            firm_name="",
            task_id=task_id,
            status="in_progress",
            message="Research is in progress"
        )
    elif result.state == "SUCCESS":
        task_result = result.result or {}
        pif_id_str = task_result.get("pif_id", "00000000-0000-0000-0000-000000000000")

        # Get the updated PIF record
        pif = await pif_info_crud.get(db, id=UUID(pif_id_str))

        if pif and pif.research_status == "completed":
            leadership = [
                LeadershipMember(**member)
                for member in (pif.leadership or [])
            ]
            return ResearchStatusResponse(
                pif_id=pif.id,
                firm_name=pif.firm_name,
                task_id=task_id,
                status="completed",
                leadership=leadership,
                research_data=pif.research_data,
                message=task_result.get("message", "Research completed")
            )

        return ResearchStatusResponse(
            pif_id=UUID(pif_id_str),
            firm_name=task_result.get("firm_name", ""),
            task_id=task_id,
            status=task_result.get("status", "completed"),
            message=task_result.get("message", "Research completed")
        )
    elif result.state == "FAILURE":
        return ResearchStatusResponse(
            pif_id=UUID("00000000-0000-0000-0000-000000000000"),
            firm_name="",
            task_id=task_id,
            status="failed",
            message=f"Research failed: {str(result.result)}"
        )
    else:
        return ResearchStatusResponse(
            pif_id=UUID("00000000-0000-0000-0000-000000000000"),
            firm_name="",
            task_id=task_id,
            status=result.state.lower(),
            message=f"Research status: {result.state}"
        )
