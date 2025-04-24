"""Email processing tasks."""

import logging
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.sync import email as email_crud_sync
from app.crud.sync import tag as tag_crud_sync
from app.db.session import SessionLocal
from app.services.classification_service import classify_email_tags_hierarchical, remove_conflicting_tags
from app.services.frontapp_service import add_conversation_tags, get_conversation_text, get_conversation_tags, remove_conversation_tags
from app.tasks.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.email.process_email")
def process_email(email_id: str) -> Dict:
    """
    Process an email by validating its ID and starting the classification task.

    Args:
        email_id: The UUID of the email to process

    Returns:
        Dict: Status of the processing initiation
    """
    logger.info(f"Processing email {email_id}")

    # Convert string to UUID
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}

    # Start classification/tagging task
    # Rename tag_email task to classify_email_category_task for clarity? Let's keep tag_email for now.
    tag_email.delay(email_id)

    return {"status": "processing", "email_id": email_id}


@celery_app.task(name="app.tasks.email.tag_email")
def tag_email(email_id: str) -> Dict:
    """
    Classify an email into a category and subcategory using AI analysis and apply tags.

    Args:
        email_id: The UUID of the email to classify and tag

    Returns:
        Dict: Status of the classification and tagging process
    """
    logger.info(f"Classifying email {email_id}")

    # Convert string to UUID
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id in tag_email task: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}

    # Get database session
    db = SessionLocal()
    try:
        # Get email from database using synchronous CRUD
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found for classification")
            return {"status": "error", "message": "Email not found"}

        # Get front conversation ID for analysis
        front_conversation_id = email_obj.front_conversation_id
        if not front_conversation_id:
            logger.error(f"Email {email_id} does not have a Front conversation ID. Cannot classify.")
            email_crud_sync.mark_as_processed(db, email_id=email_uuid)
            return {"status": "error", "message": "Missing Front conversation ID"}

        # Get conversation data
        conversation_data = get_conversation_text(front_conversation_id)
        if not conversation_data or not isinstance(conversation_data, dict):
            logger.error(f"Failed to get conversation data for {front_conversation_id}")
            return {"status": "error", "message": "Failed to get conversation data"}

        conversation_text = conversation_data.get('text', '')
        sender_info = ", ".join(map(str, conversation_data.get('senders', ['Unknown Sender'])))
        message_times = ", ".join(map(str, conversation_data.get('timestamps', ['Unknown Timestamps'])))

        # Get existing tags
        existing_tags_data = get_conversation_tags(front_conversation_id)
        if existing_tags_data:
            existing_tags = [tag.get('name') for tag in existing_tags_data if tag.get('name')]
            logger.info(f"Found existing tags for {front_conversation_id}: {existing_tags}")
        else:
            existing_tags = []
            logger.warning(f"Could not retrieve existing tags for {front_conversation_id} or none exist.")

        # *** NEW: Hierarchical Classification ***
        tags_to_apply = classify_email_tags_hierarchical(
            front_conversation_id=front_conversation_id,
            conversation_text=conversation_text,
            sender_info=sender_info,
            message_times=message_times
        )
        # *** END NEW ***

        # Ensure tags are unique before proceeding
        if tags_to_apply:
             unique_tags_to_apply = list(dict.fromkeys(tags_to_apply)) # Preserve order while deduplicating
             if len(unique_tags_to_apply) != len(tags_to_apply):
                 logger.info(f"Removed duplicate tags. Original: {tags_to_apply}, Unique: {unique_tags_to_apply}")
                 tags_to_apply = unique_tags_to_apply

        if not tags_to_apply:
             logger.error(f"Hierarchical classification failed for email {email_id}. No tags determined.")
             # Optionally mark as processed even if tagging failed, or leave for retry?
             # email_crud_sync.mark_as_processed(db, email_id=email_uuid) 
             return {"status": "error", "message": "Hierarchical classification failed to determine tags"}

        logger.info(f"Email {email_id} classified with tags: {tags_to_apply}")

        # --- Explicitly remove 'Human review required' tag if applying other tags --- 
        human_review_tag = "AI: Human review required"
        if tags_to_apply != [human_review_tag] and human_review_tag in existing_tags:
             logger.info(f"Attempting to remove '{human_review_tag}' tag before applying new tags: {tags_to_apply}")
             try:
                 remove_conversation_tags(front_conversation_id, [human_review_tag])
                 logger.info(f"Successfully removed '{human_review_tag}' tag for conversation {front_conversation_id}.")
             except Exception as remove_hr_error:
                 logger.error(f"Failed to remove '{human_review_tag}' tag for {front_conversation_id}: {remove_hr_error}. Proceeding anyway.")
        # ------------------------------------------------------------------------

        # *** NEW: Remove conflicting tags before adding new ones ***
        logger.info(f"Attempting to remove other conflicting tags for {front_conversation_id} based on hierarchy.")
        removal_success = remove_conflicting_tags(
            conversation_id=front_conversation_id,
            existing_tags=existing_tags, # Pass the original list fetched earlier
            new_tags=tags_to_apply, # Pass the unique list determined by classification
            hierarchy=settings.EMAIL_CATEGORIES # Pass the hierarchy from settings
        )
        if not removal_success:
            logger.warning(f"Failed to remove conflicting tags for conversation {front_conversation_id}. Proceeding to add new tags anyway.")
            # Decide if you want to stop processing here or continue.
            # Continuing might leave conflicting tags, but ensures new tags are applied.
        else:
            logger.info(f"Successfully processed conflicting tag removal for {front_conversation_id}.")
        # *** END NEW ***

        # Create and associate tags in database
        db_tags = []
        for tag_name in tags_to_apply:
            db_tag = tag_crud_sync.get_or_create(db, name=tag_name)
            db_tags.append(db_tag)

        # Associate tags with email
        email_obj.tags = db_tags
        db.commit()

        # Update tags in FrontApp
        if email_obj.front_conversation_id:
            try:
                # Use the tags determined by the new function
                add_conversation_tags(
                    email_obj.front_conversation_id,
                    tags_to_apply
                )
                logger.info(f"Successfully applied tags {tags_to_apply} to Front conversation {email_obj.front_conversation_id}")
            except Exception as front_error:
                logger.error(f"Failed to update tags in Front for email {email_id}: {front_error}", exc_info=True)

        # Mark email as processed
        email_crud_sync.mark_as_processed(db, email_id=email_uuid)

        # Update return value - maybe just return the tags?
        return {
            "status": "success",
            "email_id": email_id,
            "applied_tags": tags_to_apply 
            # "category": predicted_category, # Removed old category/subcategory
            # "subcategory": predicted_subcategory
        }

    except Exception as e:
        logger.exception(f"Error classifying/tagging email {email_id}: {str(e)}")
        db.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        db.close() 