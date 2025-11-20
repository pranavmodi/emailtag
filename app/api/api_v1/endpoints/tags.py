"""Tag management endpoints."""

import asyncio
import logging
from typing import Any, Dict, List
from uuid import UUID
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import tag as tag_crud
from app.db.session import get_db
from app.schemas.email import (
    Tag, TagCreate, TagUpdate, ConversationsByTagResponse,
    TagStatisticsResponse, ConversationTagStatus,
    AllTagsStatisticsResponse, TagStatisticsSummary
)
from app.services.frontapp import create_tag as create_frontapp_tag
from app.services.frontapp_service import get_conversation_tags_async

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


@router.get("/conversations-by-date", response_model=ConversationsByTagResponse)
async def get_conversations_by_tag_and_date(
    tag_name: str = Query(..., description="Tag name to filter by"),
    target_date: date = Query(..., description="Date to filter emails by (format: YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> ConversationsByTagResponse:
    """
    Get all conversation IDs that were tagged with a specific tag on a specific date.

    Note: This uses the email's created_at date to filter, since the email_tag_association
    table doesn't track when tags are applied.

    Args:
        tag_name: Name of the tag to filter by (e.g., "Apt Status Req")
        target_date: Date to filter by (e.g., 2025-11-13)
        db: Database session

    Returns:
        ConversationsByTagResponse: Tag name, date, list of conversation IDs, and count

    Example:
        GET /api/v1/tags/conversations-by-date?tag_name=Apt%20Status%20Req&target_date=2025-11-13
    """
    logger.info(f"Fetching conversations for tag '{tag_name}' on date {target_date}")

    # Verify tag exists
    tag = await tag_crud.get_by_name(db, name=tag_name)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tag '{tag_name}' not found"
        )

    # Get conversation IDs
    conversation_ids = await tag_crud.get_conversation_ids_by_tag_and_date(
        db,
        tag_name=tag_name,
        target_date=target_date
    )

    logger.info(f"Found {len(conversation_ids)} conversations for tag '{tag_name}' on {target_date}")

    return ConversationsByTagResponse(
        tag_name=tag_name,
        date=target_date.isoformat(),
        conversation_ids=conversation_ids,
        count=len(conversation_ids)
    )


@router.get("/tag-statistics", response_model=TagStatisticsResponse)
async def get_tag_statistics(
    tag_name: str = Query(..., description="Tag name to analyze"),
    target_date: date = Query(..., description="Date to analyze (format: YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> TagStatisticsResponse:
    """
    Get statistics about conversations tagged on a specific date, including their current tag status in Front.

    This endpoint:
    1. Finds all conversations that were tagged with the specified tag on the given date (in our DB)
    2. Fetches current tags from Front API for each conversation
    3. Calculates how many still have the tag vs. have been re-tagged

    Args:
        tag_name: Name of the tag to analyze (e.g., "Apt Status Req")
        target_date: Date to analyze (e.g., 2025-11-13)
        db: Database session

    Returns:
        TagStatisticsResponse: Statistics including counts, percentages, and per-conversation details

    Example:
        GET /api/v1/tags/tag-statistics?tag_name=Apt%20Status%20Req&target_date=2025-11-13
    """
    logger.info(f"Fetching tag statistics for tag '{tag_name}' on date {target_date}")

    # Verify tag exists
    tag = await tag_crud.get_by_name(db, name=tag_name)
    if not tag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tag '{tag_name}' not found"
        )

    # Get conversation IDs from our database
    conversation_ids = await tag_crud.get_conversation_ids_by_tag_and_date(
        db,
        tag_name=tag_name,
        target_date=target_date
    )

    if not conversation_ids:
        logger.info(f"No conversations found for tag '{tag_name}' on {target_date}")
        return TagStatisticsResponse(
            tag_name=tag_name,
            date=target_date.isoformat(),
            total_conversations=0,
            still_tagged=0,
            re_tagged=0,
            still_tagged_percentage=0.0,
            re_tagged_percentage=0.0,
            conversations=[]
        )

    # Fetch current tags from Front for each conversation (sequentially to avoid rate limits)
    results = []
    for idx, conv_id in enumerate(conversation_ids, 1):
        try:
            logger.debug(f"Fetching tags for conversation {idx}/{len(conversation_ids)}: {conv_id}")
            front_tags = await get_conversation_tags_async(conv_id)

            if front_tags is None:
                logger.warning(f"Could not fetch tags from Front for conversation {conv_id}")
                results.append((conv_id, None, []))
            else:
                tag_names = [t.get('name', '') for t in front_tags if t.get('name')]
                results.append((conv_id, front_tags, tag_names))

            # Small delay between requests to avoid rate limits
            await asyncio.sleep(0.1)  # 100ms delay between requests

        except Exception as e:
            logger.error(f"Error processing conversation {conv_id}: {e}")
            results.append((conv_id, None, ["ERROR_FETCHING_TAGS"]))

    # Process results
    conversations_status = []
    still_tagged_count = 0
    re_tagged_count = 0
    fetch_failed_count = 0

    for conv_id, front_tags, current_tag_names in results:
        # Track fetch failures
        if front_tags is None:
            fetch_failed_count += 1
            still_has_tag = False
        else:
            still_has_tag = tag_name in current_tag_names

        if still_has_tag:
            still_tagged_count += 1
        else:
            re_tagged_count += 1

        conversations_status.append(ConversationTagStatus(
            conversation_id=conv_id,
            still_has_tag=still_has_tag,
            current_tags=current_tag_names
        ))

    total = len(conversation_ids)
    still_tagged_pct = (still_tagged_count / total * 100) if total > 0 else 0.0
    re_tagged_pct = (re_tagged_count / total * 100) if total > 0 else 0.0

    logger.info(f"Tag statistics for '{tag_name}' on {target_date}: "
                f"{still_tagged_count}/{total} still tagged ({still_tagged_pct:.1f}%), "
                f"{re_tagged_count}/{total} re-tagged ({re_tagged_pct:.1f}%), "
                f"{fetch_failed_count} fetch failed")

    return TagStatisticsResponse(
        tag_name=tag_name,
        date=target_date.isoformat(),
        total_conversations=total,
        still_tagged=still_tagged_count,
        re_tagged=re_tagged_count,
        fetch_failed=fetch_failed_count,
        still_tagged_percentage=round(still_tagged_pct, 2),
        re_tagged_percentage=round(re_tagged_pct, 2),
        conversations=conversations_status
    )


@router.get("/all-tags-statistics", response_model=AllTagsStatisticsResponse)
async def get_all_tags_statistics(
    target_date: date = Query(..., description="Date to analyze (format: YYYY-MM-DD)"),
    hour: int = Query(None, ge=0, le=23, description="Optional hour (0-23) to filter by"),
    db: AsyncSession = Depends(get_db),
) -> AllTagsStatisticsResponse:
    """
    Get statistics for all tags applied on a specific date, optionally filtered by hour.

    This endpoint:
    1. Finds all tags that were applied to conversations on the given date/hour (in our DB)
    2. For each tag, fetches current tags from Front API for ALL conversations
    3. Calculates retention statistics for each tag

    Note: Due to Front API limitations (no batch endpoint), this makes one API call per unique conversation.
    Results are deduplicated - each conversation is fetched only once even if it has multiple tags.

    Args:
        target_date: Date to analyze (e.g., 2025-11-13)
        hour: Optional hour (0-23) to filter by. If not provided, analyzes entire day.
        db: Database session

    Returns:
        AllTagsStatisticsResponse: Statistics for all tags including retention percentages

    Example:
        GET /api/v1/tags/all-tags-statistics?target_date=2025-11-13&hour=14
    """
    if hour is not None:
        logger.info(f"Fetching statistics for all tags on date {target_date} hour {hour}")
    else:
        logger.info(f"Fetching statistics for all tags on date {target_date}")

    # Get all tags and their conversations for this date/hour
    tags_dict = await tag_crud.get_all_tags_by_date(db, target_date=target_date, hour=hour)

    if not tags_dict:
        logger.info(f"No tags found for date {target_date}")
        return AllTagsStatisticsResponse(
            date=target_date.isoformat(),
            total_conversations=0,
            total_tags=0,
            tag_statistics=[]
        )

    # Step 1: Collect ALL unique conversation IDs across all tags
    # This prevents fetching the same conversation multiple times
    tag_to_conversations = {}
    all_unique_conv_ids = set()

    for tag_name, conversation_ids in tags_dict.items():
        tag_to_conversations[tag_name] = {
            'conversations_to_check': conversation_ids,  # Check ALL conversations
            'total_count': len(conversation_ids)
        }
        all_unique_conv_ids.update(conversation_ids)

    logger.info(f"Fetching tags for {len(all_unique_conv_ids)} unique conversations (deduplicated across {len(tags_dict)} tags)")

    # Step 2: Fetch current tags from Front for each UNIQUE conversation (sequentially to avoid rate limits)
    conversation_current_tags = {}
    failed_fetches = set()  # Track which conversations failed to fetch

    for idx, conv_id in enumerate(all_unique_conv_ids, 1):
        try:
            logger.debug(f"Fetching tags for conversation {idx}/{len(all_unique_conv_ids)}: {conv_id}")
            front_tags = await get_conversation_tags_async(conv_id)

            if front_tags is None:
                logger.warning(f"Could not fetch tags from Front for conversation {conv_id}")
                conversation_current_tags[conv_id] = []
                failed_fetches.add(conv_id)  # Mark as failed
            else:
                tag_names = [t.get('name', '') for t in front_tags if t.get('name')]
                conversation_current_tags[conv_id] = tag_names

            # Small delay between requests to avoid rate limits
            await asyncio.sleep(0.1)  # 100ms delay between requests

        except Exception as e:
            logger.error(f"Error fetching tags for conversation {conv_id}: {e}")
            conversation_current_tags[conv_id] = []
            failed_fetches.add(conv_id)  # Mark as failed

    # Step 3: Calculate statistics for each tag based on fetched data
    tag_statistics = []

    for tag_name, tag_data in tag_to_conversations.items():
        still_tagged_count = 0
        re_tagged_count = 0
        fetch_failed_count = 0

        conversations_to_check = tag_data['conversations_to_check']
        total_for_tag = tag_data['total_count']

        for conv_id in conversations_to_check:
            # Check if fetch failed for this conversation
            if conv_id in failed_fetches:
                fetch_failed_count += 1
                re_tagged_count += 1  # Count as re-tagged
                continue

            current_tags = conversation_current_tags.get(conv_id, [])

            if tag_name in current_tags:
                still_tagged_count += 1
            else:
                re_tagged_count += 1

        # Calculate percentages based on checked conversations
        checked_count = len(conversations_to_check)
        still_tagged_pct = (still_tagged_count / checked_count * 100) if checked_count > 0 else 0.0
        re_tagged_pct = (re_tagged_count / checked_count * 100) if checked_count > 0 else 0.0

        tag_statistics.append(TagStatisticsSummary(
            tag_name=tag_name,
            total_conversations=total_for_tag,  # Show actual total, not just checked
            still_tagged=still_tagged_count,
            re_tagged=re_tagged_count,
            fetch_failed=fetch_failed_count,
            still_tagged_percentage=round(still_tagged_pct, 2),
            re_tagged_percentage=round(re_tagged_pct, 2)
        ))

    # Sort by total conversations descending
    tag_statistics.sort(key=lambda x: x.total_conversations, reverse=True)

    logger.info(f"Found {len(tags_dict)} tags with {len(all_unique_conv_ids)} unique conversations checked on {target_date}")

    return AllTagsStatisticsResponse(
        date=target_date.isoformat(),
        total_conversations=len(all_unique_conv_ids),
        total_tags=len(tags_dict),
        tag_statistics=tag_statistics
    )


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


@router.post("/eval-classification", response_model=Dict[str, Any])
async def eval_classification(
    conversation_id: str = Query(None, description="Front conversation ID to evaluate"),
    target_date: date = Query(None, description="Date to evaluate all conversations (format: YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Run classification in eval mode - predict tags without applying them to Front.
    Compare predicted tags with actual tags that were applied.

    For bulk evaluations (by date), tasks are queued via Celery to avoid blocking.
    For single conversation eval, runs synchronously.

    Args:
        conversation_id: Optional - Single conversation ID to evaluate
        target_date: Optional - Date to evaluate all conversations
        db: Database session

    Returns:
        Dict with comparison results: {
            "conversation_id" or "date": ...,
            "mode": "sync" or "async",
            "results": [...] (sync only),
            "queued_tasks": int (async only),
            "summary": {...}
        }
    """
    from app.crud import email as email_crud
    from app.tasks.email import eval_single_conversation_task

    if not conversation_id and not target_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either conversation_id or target_date"
        )

    if conversation_id:
        # Single conversation - queue Celery task for non-blocking execution
        logger.info(f"🧪 EVAL MODE (ASYNC): Queuing classification task for conversation {conversation_id}")

        task = eval_single_conversation_task.apply_async(
            args=[conversation_id],
            queue='processing'
        )

        return {
            "mode": "async",
            "conversation_id": conversation_id,
            "task_id": task.id,
            "message": f"Eval task queued for {conversation_id}. Use task_id to check status.",
            "status_url": f"/api/v1/tags/eval-status/{task.id}"
        }

    else:
        # Bulk evaluation - queue Celery tasks for non-blocking execution
        logger.info(f"🧪 EVAL MODE (ASYNC): Queuing classification tasks for all conversations on {target_date}")

        # Get all emails created on target date
        emails = await email_crud.get_emails_by_date(db, target_date)

        # Queue Celery tasks
        queued_count = 0
        conversation_ids = []
        for email in emails:
            if email.front_conversation_id:
                # Queue the task in Celery
                eval_single_conversation_task.apply_async(
                    args=[email.front_conversation_id],
                    queue='processing'
                )
                queued_count += 1
                conversation_ids.append(email.front_conversation_id)

        logger.info(f"🧪 EVAL: Queued {queued_count} evaluation tasks for {target_date}")

        return {
            "mode": "async",
            "date": str(target_date),
            "queued_tasks": queued_count,
            "conversation_ids": conversation_ids,
            "message": f"Queued {queued_count} evaluation tasks. Results will be logged. Check Celery logs for individual results.",
            "note": "Future version will support result collection via task IDs or database storage."
        }


@router.get("/eval-status/{task_id}", response_model=Dict[str, Any])
async def get_eval_status(task_id: str) -> Dict[str, Any]:
    """
    Get the status and result of an eval classification task.

    Args:
        task_id: Celery task ID

    Returns:
        Dict with task status and result (if completed)
    """
    from celery.result import AsyncResult
    from app.tasks.worker import celery_app

    task_result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": task_result.state,  # PENDING, STARTED, SUCCESS, FAILURE, RETRY
    }

    if task_result.ready():
        # Task completed
        if task_result.successful():
            response["result"] = task_result.result
            response["message"] = "Eval completed successfully"
        else:
            response["error"] = str(task_result.result)
            response["message"] = "Eval failed"
    else:
        # Task still running
        response["message"] = f"Eval task is {task_result.state.lower()}"

    return response


async def _eval_single_conversation(conversation_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Evaluate classification for a single conversation.

    Returns dict with predicted vs actual tags comparison.
    """
    from app.crud import email as email_crud
    from app.services.classification_service import classify_email_tags_hierarchical
    from app.services.frontapp_service import get_conversation_text

    try:
        # Get conversation data
        conversation_data = get_conversation_text(conversation_id)
        if not conversation_data or "error" in conversation_data:
            return {
                "conversation_id": conversation_id,
                "error": "Failed to retrieve conversation",
                "predicted_tags": [],
                "actual_tags": [],
                "exact_match": False,
                "partial_match": False,
                "accuracy": 0.0
            }

        conversation_text = conversation_data.get("text", "")
        sender_info = conversation_data.get("sender_info", {})
        message_times = conversation_data.get("message_times", {})
        recipients_to_info = conversation_data.get("recipients_to_info", {})
        recipients_cc_info = conversation_data.get("recipients_cc_info", {})
        structured_messages = conversation_data.get("_structured_messages", [])

        # Get email object to retrieve document analysis results and actual tags
        # Use load_tags=True to eagerly load tags and avoid lazy-loading issues
        email = await email_crud.get_by_front_conversation_id(
            db, front_conversation_id=conversation_id, load_tags=True
        )
        document_results = None
        if email and hasattr(email, 'ocr_results') and email.ocr_results:
            document_results = email.ocr_results
            logger.info(f"🧪 EVAL: Using {len(document_results)} OCR results for classification")

        # Run classification WITH document analysis (production-like, but without applying tags)
        predicted_tags = classify_email_tags_hierarchical(
            front_conversation_id=conversation_id,
            conversation_text=conversation_text,
            sender_info=sender_info,
            message_times=message_times,
            document_analysis_results=document_results,  # ✅ Include document analysis
            recipients_to_info=recipients_to_info,
            recipients_cc_info=recipients_cc_info,
            structured_messages=structured_messages
        )

        # Get actual tags from database (already eagerly loaded)
        actual_tags = []
        if email and email.tags:
            actual_tags = [tag.name for tag in email.tags]

        # Calculate match metrics
        predicted_set = set(predicted_tags)
        actual_set = set(actual_tags)

        exact_match = predicted_set == actual_set
        partial_match = len(predicted_set & actual_set) > 0

        # Calculate accuracy (Jaccard similarity)
        if predicted_set or actual_set:
            intersection = len(predicted_set & actual_set)
            union = len(predicted_set | actual_set)
            accuracy = (intersection / union * 100) if union > 0 else 0
        else:
            accuracy = 100.0 if not predicted_set and not actual_set else 0.0

        return {
            "conversation_id": conversation_id,
            "predicted_tags": predicted_tags,
            "actual_tags": actual_tags,
            "exact_match": exact_match,
            "partial_match": partial_match,
            "accuracy": round(accuracy, 2),
            "matching_tags": list(predicted_set & actual_set),
            "missing_tags": list(actual_set - predicted_set),
            "extra_tags": list(predicted_set - actual_set)
        }

    except Exception as e:
        logger.error(f"Error evaluating conversation {conversation_id}: {e}", exc_info=True)
        return {
            "conversation_id": conversation_id,
            "error": str(e),
            "predicted_tags": [],
            "actual_tags": [],
            "exact_match": False,
            "partial_match": False,
            "accuracy": 0.0
        }
