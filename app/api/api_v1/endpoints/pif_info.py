"""PIF (Personal Injury Firm) information endpoints."""

import asyncio
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
    OutreachRequest,
    OutreachResponse,
    OutreachMessageResult,
    FirmLookupRequest,
    FirmLookupConversation,
    FirmLookupResponse,
    FirmLookupCreateRequest,
    FirmLookupCreateResponse,
    AnalyzeBehaviorResponse,
    BatchTaskResponse,
    ScoreResponse,
    AnalyticsSummaryResponse,
    PeopleSearchResponse,
    PersonSearchResult,
    LeadershipEmailHistoryResponse,
)
from app.schemas.autorespond_event import (
    AutorespondEventResponse,
    AutorespondEventListResponse,
    AutorespondEventSummary,
)
from app.crud import autorespond_event as autorespond_event_crud

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/firm-lookup", response_model=FirmLookupResponse)
async def firm_lookup(
    request: FirmLookupRequest,
    db: AsyncSession = Depends(get_db),
) -> FirmLookupResponse:
    """
    Search for a firm across local database and Front conversations.

    Step A: Search local pif_info table for matching firms.
    Step B: Search local email table for matching conversations.
    Step C: Search Front API for matching conversations.

    Args:
        request: Firm lookup parameters
        db: Database session

    Returns:
        Matching firms and conversations from all sources
    """
    from app.crud import email as email_crud
    from urllib.parse import urlparse

    logger.info(f"Firm lookup for: {request.firm_name}")

    # Step A: Search local pif_info table
    matching_firms_list, _ = await pif_info_crud.search(
        db, search=request.firm_name, skip=0, limit=10
    )

    # Step B: Search local email table
    # Extract domain from website if provided
    website_domain = None
    if request.website:
        try:
            parsed = urlparse(request.website if "://" in request.website else f"https://{request.website}")
            website_domain = parsed.hostname
            if website_domain and website_domain.startswith("www."):
                website_domain = website_domain[4:]
        except Exception:
            pass

    local_emails = await email_crud.search_by_firm_info(
        db,
        firm_name=request.firm_name,
        email_address=request.email,
        website_domain=website_domain,
        limit=50,
    )

    conversations: List[FirmLookupConversation] = []
    seen_conv_ids = set()

    for em in local_emails:
        if em.front_conversation_id and em.front_conversation_id not in seen_conv_ids:
            seen_conv_ids.add(em.front_conversation_id)
            snippet = (em.content_text or "")[:200] if em.content_text else None
            conversations.append(FirmLookupConversation(
                conversation_id=em.front_conversation_id,
                subject=em.subject,
                sender=em.sender,
                created_at=em.created_at.isoformat() if em.created_at else None,
                snippet=snippet,
                source="local",
            ))

    # Step C: Search Front API
    try:
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))
        from pifstats.src.front_client import search_front_conversations

        front_results = search_front_conversations(request.firm_name, limit=25)
        for conv in front_results:
            conv_id = conv.get("conversation_id", "")
            if conv_id and conv_id not in seen_conv_ids:
                seen_conv_ids.add(conv_id)
                recipients = conv.get("recipients", [])
                sender_str = recipients[0] if recipients else None
                created_at_val = conv.get("created_at")
                created_at_str = None
                if created_at_val:
                    if isinstance(created_at_val, (int, float)):
                        from datetime import datetime as dt
                        created_at_str = dt.fromtimestamp(created_at_val).isoformat()
                    else:
                        created_at_str = str(created_at_val)

                conversations.append(FirmLookupConversation(
                    conversation_id=conv_id,
                    subject=conv.get("subject"),
                    sender=sender_str,
                    created_at=created_at_str,
                    snippet=None,
                    source="front",
                ))
    except Exception as e:
        logger.error(f"Error searching Front API: {e}")

    logger.info(
        f"Firm lookup results: {len(matching_firms_list)} firms, "
        f"{len(conversations)} conversations"
    )

    return FirmLookupResponse(
        matching_firms=matching_firms_list,
        conversations=conversations,
        total_conversations=len(conversations),
    )


@router.post("/firm-lookup/create", response_model=FirmLookupCreateResponse)
async def firm_lookup_create(
    request: FirmLookupCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> FirmLookupCreateResponse:
    """
    Create a firm entry from lookup results and optionally start research.

    Creates a new PIF entry or updates an existing one if matched by name/website.
    Associates selected conversation IDs with the firm.

    Args:
        request: Firm creation parameters with optional conversation IDs
        db: Database session

    Returns:
        Created/updated firm and optional research task ID
    """
    logger.info(f"Creating firm from lookup: {request.firm_name}")

    # Check for existing firm by name or website
    existing = None
    if request.website:
        existing = await pif_info_crud.get_by_website(db, request.website)
    if not existing:
        existing = await pif_info_crud.get_by_firm_name(db, request.firm_name)

    is_new = False
    if existing:
        # Update existing: merge conversation IDs
        merged_conv_ids = list(
            set(existing.conversation_ids or []) | set(request.selected_conversation_ids or [])
        )
        update_data: Dict[str, Any] = {"conversation_ids": merged_conv_ids}

        # Update optional fields if provided and not already set
        if request.website and not existing.website:
            update_data["website"] = request.website
        if request.email and request.email not in (existing.emails or []):
            update_data["emails"] = list(set(existing.emails or []) | {request.email})
        if request.phone and request.phone not in (existing.phones or []):
            update_data["phones"] = list(set(existing.phones or []) | {request.phone})
        if request.contact_name:
            existing_names = {c.get("name", "").lower() for c in (existing.contacts or [])}
            if request.contact_name.lower() not in existing_names:
                new_contacts = list(existing.contacts or [])
                new_contacts.append({"name": request.contact_name, "title": "", "email": request.email or "", "phone": request.phone or "", "extension": ""})
                update_data["contacts"] = new_contacts

        pif = await pif_info_crud.update(db, db_obj=existing, obj_in=update_data)
    else:
        # Create new firm
        is_new = True
        contacts = []
        if request.contact_name:
            contacts.append({
                "name": request.contact_name,
                "title": "",
                "email": request.email or "",
                "phone": request.phone or "",
                "extension": "",
            })

        pif_create = PifInfoCreate(
            firm_name=request.firm_name,
            website=request.website,
            emails=[request.email] if request.email else [],
            phones=[request.phone] if request.phone else [],
            contacts=contacts,
            conversation_ids=request.selected_conversation_ids or [],
        )
        pif = await pif_info_crud.create(db, obj_in=pif_create)

    # Optionally start research
    task_id = None
    if request.start_research:
        try:
            await pif_info_crud.update(db, db_obj=pif, obj_in={"research_status": "queued"})
            from app.tasks.firm_research import research_firm_task
            task = research_firm_task.delay(str(pif.id))
            task_id = task.id
            logger.info(f"Research task queued for firm: {pif.firm_name}, task_id: {task_id}")
        except Exception as e:
            logger.error(f"Failed to start research for {pif.firm_name}: {e}")

    action = "Created" if is_new else "Updated"
    msg = f"{action} firm '{pif.firm_name}'"
    if task_id:
        msg += f" and started research (task_id: {task_id})"

    return FirmLookupCreateResponse(
        pif=pif,
        is_new=is_new,
        task_id=task_id,
        message=msg,
    )


@router.get("/", response_model=PifInfoListResponse)
async def list_pif_info(
    search: str = Query(None, description="Search term for firm name, email, or website"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query(
        None,
        description="Sort order: 'conversation_count' (most conversations first), 'firm_name' (alphabetical), or 'updated_at' (most recent first, default)"
    ),
    research_status: str = Query(
        None,
        description="Filter by research status: 'completed', 'pending', 'queued', 'in_progress', 'failed'"
    ),
    icp_tier: str = Query(
        None,
        description="Filter by ICP tier: 'A', 'B', 'C', 'D'"
    ),
    entity_type: str = Query(
        None,
        description="Filter by entity type: 'pi_law_firm', 'medical_referring', 'medical_facility', 'insurance', 'funding', 'collections', 'legal_other', 'administrative', 'patient_adjacent'"
    ),
    recently_researched: int = Query(
        None,
        description="Filter firms researched within the last N days (e.g. 7 for last week)"
    ),
    db: AsyncSession = Depends(get_db),
) -> PifInfoListResponse:
    """
    List all PIF info with optional search, filters, sorting, and pagination.

    Args:
        search: Optional search term
        page: Page number (1-indexed)
        page_size: Number of items per page
        sort_by: Sort order (conversation_count, firm_name, updated_at)
        research_status: Filter by research_status (e.g. 'completed')
        icp_tier: Filter by ICP tier ('A', 'B', 'C', 'D')
        recently_researched: Filter firms researched within the last N days
        db: Database session

    Returns:
        Paginated list of PIF info
    """
    skip = (page - 1) * page_size
    items, total = await pif_info_crud.search(
        db, search=search, skip=skip, limit=page_size, sort_by=sort_by,
        research_status=research_status, icp_tier=icp_tier,
        entity_type=entity_type,
        recently_researched_days=recently_researched,
    )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PifInfoListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/people", response_model=PeopleSearchResponse)
async def search_people(
    title: str = Query(None, description="Search term for person title (e.g. 'CMO', 'intake', 'paralegal')"),
    name: str = Query(None, description="Search term for person name"),
    role_category: str = Query(
        None,
        description="Filter staff by role category: intake_specialist, case_manager, paralegal, office_manager, billing_coordinator, medical_records, other"
    ),
    source: str = Query("all", description="Source filter: 'leadership', 'staff', or 'all'"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> PeopleSearchResponse:
    """
    Search across all firms' leadership and staff for people by title or name.

    Queries the leadership and staff JSONB arrays across all PIF records.
    Useful for finding all people with a specific role (e.g. all CMOs, all intake specialists).
    """
    skip = (page - 1) * page_size
    results, total = await pif_info_crud.search_people(
        db,
        title=title,
        name=name,
        role_category=role_category,
        source=source,
        skip=skip,
        limit=page_size,
    )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PeopleSearchResponse(
        results=[PersonSearchResult(**r) for r in results],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# ---------------------------------------------------------------------------
# Autorespond Event Tracking Endpoints
# (Must be before /{pif_id} catch-all routes)
# ---------------------------------------------------------------------------

@router.get("/autorespond-events", response_model=AutorespondEventListResponse)
async def list_autorespond_events(
    agent_type: str = Query(None, description="Filter by agent type"),
    search: str = Query(None, description="Search firm name, contact email, or subject"),
    date_from: str = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str = Query(None, description="End date (YYYY-MM-DD)"),
    test_mode: bool = Query(None, description="Filter by test mode"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> AutorespondEventListResponse:
    """List all autorespond events with optional filters and pagination."""
    skip = (page - 1) * page_size
    items, total = await autorespond_event_crud.list_events(
        db,
        agent_type=agent_type,
        search=search,
        date_from=date_from,
        date_to=date_to,
        test_mode=test_mode,
        skip=skip,
        limit=page_size,
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return AutorespondEventListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/autorespond-events/summary", response_model=AutorespondEventSummary)
async def get_autorespond_events_summary(
    db: AsyncSession = Depends(get_db),
) -> AutorespondEventSummary:
    """Get aggregate summary of autorespond activity."""
    data = await autorespond_event_crud.get_summary(db)
    return AutorespondEventSummary(**data)


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
            extracted_entity_type = getattr(firm_info, 'entity_type', 'pi_law_firm') or 'pi_law_firm'

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
                entity_type=extracted_entity_type,
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
    extracted_entity_type = getattr(firm_info, 'entity_type', 'pi_law_firm') or 'pi_law_firm'

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
        entity_type=extracted_entity_type,
    )

    return {
        "conversation_id": conversation_id,
        "extracted": True,
        "is_new_firm": is_new,
        "pif_id": str(pif.id),
        "firm_name": pif.firm_name,
        "entity_type": pif.entity_type,
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


@router.post("/{pif_id}/research-staff", response_model=ResearchStartResponse)
async def research_staff(
    pif_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ResearchStartResponse:
    """
    Start async staff research for a PIF using OpenAI web search.

    Searches for operational staff: intake specialists, case managers,
    paralegals, office managers, billing coordinators, etc.

    Args:
        pif_id: PIF info ID
        db: Database session

    Returns:
        Task ID and status for polling
    """
    pif = await pif_info_crud.get(db, id=pif_id)
    if not pif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PIF info not found",
        )

    await pif_info_crud.update(
        db,
        db_obj=pif,
        obj_in={"staff_research_status": "queued"}
    )

    from app.tasks.firm_research import research_staff_task

    task = research_staff_task.delay(str(pif_id))

    # Log queue routing for debugging
    route = research_staff_task.app.amqp.router.route(
        research_staff_task.app.amqp.queues, research_staff_task.name, {}, {}
    )
    logger.warning(f"Staff research task DISPATCHED for firm: {pif.firm_name}, task_id: {task.id}, routed_to_queue: {route.get('queue', 'UNKNOWN')}")

    return ResearchStartResponse(
        pif_id=pif_id,
        firm_name=pif.firm_name,
        task_id=task.id,
        status="queued",
        message="Staff research task queued. Poll /research-status/{task_id} for progress."
    )


@router.post("/{pif_id}/generate-outreach", response_model=OutreachResponse)
async def generate_outreach(
    pif_id: UUID,
    request: OutreachRequest,
    db: AsyncSession = Depends(get_db),
) -> OutreachResponse:
    """
    Generate personalized LinkedIn outreach messages for a firm's leadership.

    Takes a case study URL and client description, generates 4 message variants
    (short/long x Pranav/Neha) for each leadership member using OpenAI.

    Args:
        pif_id: PIF info ID
        request: OutreachRequest with case_study_url and client_description
        db: Database session

    Returns:
        OutreachResponse with generated messages for all leaders
    """
    pif = await pif_info_crud.get(db, id=pif_id)
    if not pif:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="PIF info not found",
        )

    if not pif.leadership or len(pif.leadership) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This firm has no leadership data. Please research the firm first.",
        )

    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))

    from pifstats.src.firm_researcher import generate_outreach_messages

    # Add firm name to each leader dict for context
    leaders = []
    for member in pif.leadership:
        leader_dict = dict(member) if isinstance(member, dict) else member
        if isinstance(leader_dict, dict):
            leader_dict["firm"] = pif.firm_name
        leaders.append(leader_dict)

    logger.info(f"Generating outreach messages for {len(leaders)} leaders at {pif.firm_name}")

    # Run synchronous blocking function in a thread to avoid blocking the event loop
    messages, errors = await asyncio.to_thread(
        generate_outreach_messages,
        leaders=leaders,
        case_study_url=request.case_study_url,
        client_description=request.client_description,
        behavioral_context=pif.behavioral_data,
        research_context=pif.research_data,
    )

    return OutreachResponse(
        pif_id=pif_id,
        firm_name=pif.firm_name,
        messages=[OutreachMessageResult(**msg) for msg in messages],
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Behavior Analysis & ICP Scoring Endpoints
# ---------------------------------------------------------------------------

@router.post("/{pif_id}/analyze-behavior", response_model=AnalyzeBehaviorResponse)
async def analyze_firm_behavior(
    pif_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AnalyzeBehaviorResponse:
    """
    Queue behavior analysis and ICP scoring for a firm.

    Dispatches an async Celery task that:
    - Fetches all emails for the firm's conversation IDs
    - Classifies them by topic using gpt-4o-mini
    - Computes ICP score deterministically
    - Updates the pif_info record

    Returns immediately with task_id for polling.
    """
    pif = await pif_info_crud.get(db, id=pif_id)
    if not pif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PIF info not found")

    from app.tasks.behavior_analysis import analyze_firm_behavior_task
    task = analyze_firm_behavior_task.delay(str(pif_id))

    logger.info(f"Behavior analysis task queued for {pif.firm_name}: {task.id}")

    return AnalyzeBehaviorResponse(
        pif_id=pif_id,
        firm_name=pif.firm_name,
        task_id=task.id,
        status="queued",
        message=f"Behavior analysis queued for '{pif.firm_name}'. Task ID: {task.id}",
    )


@router.post("/{pif_id}/analyze-leadership-emails", response_model=LeadershipEmailHistoryResponse)
async def analyze_leadership_emails(
    pif_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> LeadershipEmailHistoryResponse:
    """
    Queue leadership email history analysis for a firm.

    Dispatches a Celery task that:
    - Loads the firm's leadership array
    - For each leader, searches the email table by email or name match
    - Aggregates per leader: total emails, tag distribution, contact dates, subjects
    - Stores results in research_data['leadership_email_history']

    Returns immediately with task_id for polling.
    """
    pif = await pif_info_crud.get(db, id=pif_id)
    if not pif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PIF info not found")

    if not pif.leadership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No leadership data found. Run research first.",
        )

    from app.tasks.firm_research import analyze_leadership_emails_task
    task = analyze_leadership_emails_task.delay(str(pif_id))

    logger.info(f"Leadership email history task queued for {pif.firm_name}: {task.id}")

    return LeadershipEmailHistoryResponse(
        pif_id=pif_id,
        firm_name=pif.firm_name,
        task_id=task.id,
        status="queued",
        message=f"Leadership email history analysis queued for '{pif.firm_name}'. Task ID: {task.id}",
    )


@router.get("/{pif_id}/autorespond-events", response_model=AutorespondEventListResponse)
async def list_firm_autorespond_events(
    pif_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> AutorespondEventListResponse:
    """List autorespond events for a specific firm."""
    skip = (page - 1) * page_size
    items, total = await autorespond_event_crud.list_events(
        db, pif_id=pif_id, skip=skip, limit=page_size
    )
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0
    return AutorespondEventListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("/analyze-behavior/batch", response_model=BatchTaskResponse)
async def analyze_behavior_batch(
    db: AsyncSession = Depends(get_db),
) -> BatchTaskResponse:
    """
    Queue behavior analysis for ALL firms in the database.

    Dispatches analyze_all_firms_task which fans out individual tasks per firm.
    """
    from app.tasks.behavior_analysis import analyze_all_firms_task
    task = analyze_all_firms_task.delay()

    # Get total count for informational message
    all_ids = await pif_info_crud.get_all_ids(db)

    return BatchTaskResponse(
        task_id=task.id,
        message=f"Batch behavior analysis queued for {len(all_ids)} firms. Task ID: {task.id}",
        total=len(all_ids),
    )


@router.post("/{pif_id}/score", response_model=ScoreResponse)
async def score_firm_icp(
    pif_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ScoreResponse:
    """
    Run ICP scoring synchronously on a firm's existing behavioral_data.

    No LLM call - pure deterministic scoring.
    Updates and returns the score immediately.

    Requires behavioral_data to be present (run analyze-behavior first).
    """
    import sys
    import os
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    )
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from pifstats.src.icp_scorer import score_firm

    pif = await pif_info_crud.get(db, id=pif_id)
    if not pif:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PIF info not found")

    if not pif.behavioral_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No behavioral data found. Run analyze-behavior first.",
        )

    pif_dict = {
        "behavioral_data": pif.behavioral_data or {},
        "research_data": pif.research_data or {},
        "website": pif.website,
        "leadership": pif.leadership or [],
        "phones": pif.phones or [],
    }

    score_result = score_firm(pif_dict)

    from datetime import datetime as dt
    await pif_info_crud.update(
        db,
        db_obj=pif,
        obj_in={
            "icp_score": score_result["icp_score"],
            "icp_tier": score_result["icp_tier"],
            "score_breakdown": score_result["score_breakdown"],
            "icp_scored_at": dt.utcnow(),
        },
    )

    return ScoreResponse(
        pif_id=pif_id,
        firm_name=pif.firm_name,
        icp_score=score_result["icp_score"],
        icp_tier=score_result["icp_tier"],
        score_breakdown=score_result["score_breakdown"],
    )


@router.post("/score/batch", response_model=BatchTaskResponse)
async def score_batch(
    db: AsyncSession = Depends(get_db),
) -> BatchTaskResponse:
    """
    Re-score all firms that have behavioral_data (runs as a Celery task).
    """
    from app.tasks.behavior_analysis import score_all_firms_task
    task = score_all_firms_task.delay()

    return BatchTaskResponse(
        task_id=task.id,
        message=f"Batch ICP scoring queued. Task ID: {task.id}",
    )


@router.get("/analytics/summary", response_model=AnalyticsSummaryResponse)
async def get_analytics_summary(
    db: AsyncSession = Depends(get_db),
) -> AnalyticsSummaryResponse:
    """
    Aggregate analytics across all tracked PIF firms.

    Returns:
    - Total firms and breakdown by tier
    - Top pain points from behavioral data
    - Average monthly email volume by tier
    - Pipeline funnel counts by status
    - Firms contacted in last 30 days
    - High-priority firms needing recontact (tier A/B, last contact > 60 days)
    """
    from sqlalchemy import select, func, text
    from app.models.pif_info import PifInfo
    from app.crud.pif_pipeline import pif_pipeline as pipeline_crud
    from collections import Counter
    from datetime import datetime as dt

    # Total firms
    total_result = await db.execute(select(func.count(PifInfo.id)))
    total_firms = total_result.scalar() or 0

    # Firms by tier
    tier_result = await db.execute(
        select(PifInfo.icp_tier, func.count(PifInfo.id))
        .group_by(PifInfo.icp_tier)
    )
    firms_by_tier: Dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "unscored": 0}
    for tier, count in tier_result.fetchall():
        key = tier if tier in firms_by_tier else "unscored"
        firms_by_tier[key] = count

    # Firms by entity type
    entity_type_result = await db.execute(
        select(PifInfo.entity_type, func.count(PifInfo.id))
        .group_by(PifInfo.entity_type)
    )
    firms_by_entity_type: Dict[str, int] = {}
    for etype, count in entity_type_result.fetchall():
        firms_by_entity_type[etype or "pi_law_firm"] = count

    # Load all firms with behavioral data for aggregation
    all_pifs_result = await db.execute(
        select(PifInfo).where(PifInfo.behavioral_data.is_not(None))
    )
    all_pifs = all_pifs_result.scalars().all()

    # Top pain points
    pain_counter: Counter = Counter()
    for pif in all_pifs:
        bd = pif.behavioral_data or {}
        pp = bd.get("primary_pain_point")
        if pp:
            pain_counter[pp] += 1

    top_pain_points = [
        {"pain_point": k, "count": v}
        for k, v in pain_counter.most_common(5)
    ]

    # Average monthly volume by tier
    tier_volumes: Dict[str, List[float]] = {}
    for pif in all_pifs:
        if not pif.icp_tier:
            continue
        bd = pif.behavioral_data or {}
        monthly = bd.get("monthly_email_volume") or []
        if monthly:
            avg = sum(monthly) / len(monthly)
            tier_volumes.setdefault(pif.icp_tier, []).append(avg)

    avg_monthly_volume_by_tier = {
        tier: round(sum(vols) / len(vols), 1) if vols else 0.0
        for tier, vols in tier_volumes.items()
    }

    # Pipeline funnel
    pipeline_funnel = await pipeline_crud.get_status_counts(db)

    # Firms contacted last 30 days
    contacted_30 = sum(
        1 for pif in all_pifs
        if (pif.behavioral_data or {}).get("days_since_last_contact") is not None
        and (pif.behavioral_data or {}).get("days_since_last_contact") <= 30
    )

    # Firms needing recontact: tier A or B and last contact > 60 days
    needing_recontact = sum(
        1 for pif in all_pifs
        if pif.icp_tier in ("A", "B")
        and (pif.behavioral_data or {}).get("days_since_last_contact") is not None
        and (pif.behavioral_data or {}).get("days_since_last_contact") > 60
    )

    return AnalyticsSummaryResponse(
        total_firms_tracked=total_firms,
        firms_by_tier=firms_by_tier,
        firms_by_entity_type=firms_by_entity_type,
        top_pain_points=top_pain_points,
        avg_monthly_volume_by_tier=avg_monthly_volume_by_tier,
        pipeline_funnel=pipeline_funnel,
        firms_contacted_last_30_days=contacted_30,
        firms_needing_recontact=needing_recontact,
    )
