"""Email processing tasks."""

import logging
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.sync import email as email_crud_sync
from app.crud.sync import tag as tag_crud_sync
from app.db.session import SessionLocal
from app.services.classification_service import classify_email_category, classify_email_subcategory
from app.services.frontapp_service import add_conversation_tags, get_conversation_text
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
        existing_tags: List[str] = []

        # Step 1: Top-level classification
        predicted_category, confidence = classify_email_category(
            front_conversation_id=front_conversation_id,
            existing_tags=existing_tags
        )

        if not predicted_category:
            logger.error(f"AI classification failed for email {email_id}. No category determined.")
            email_crud_sync.mark_as_processed(db, email_id=email_uuid)
            return {"status": "error", "message": "AI classification failed"}

        # Step 2: Sub-category classification
        predicted_subcategory, subcat_confidence = classify_email_subcategory(
            front_conversation_id=front_conversation_id,
            top_level_category=predicted_category,
            conversation_text=conversation_text,
            sender_info=sender_info,
            message_times=message_times
        )

        tags_to_apply = [predicted_category]
        if predicted_subcategory:
            tags_to_apply.append(predicted_subcategory)
            logger.info(f"Email {email_id} classified as '{predicted_category}/{predicted_subcategory}' with confidence {confidence:.2f}/{subcat_confidence:.2f}")
        else:
            logger.info(f"Email {email_id} classified as '{predicted_category}' (no subcategory) with confidence {confidence:.2f}")

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
                add_conversation_tags(
                    email_obj.front_conversation_id,
                    tags_to_apply
                )
                logger.info(f"Successfully applied tags {tags_to_apply} to Front conversation {email_obj.front_conversation_id}")
            except Exception as front_error:
                logger.error(f"Failed to update tags in Front for email {email_id}: {front_error}", exc_info=True)

        # Mark email as processed
        email_crud_sync.mark_as_processed(db, email_id=email_uuid)

        return {
            "status": "success",
            "email_id": email_id,
            "category": predicted_category,
            "subcategory": predicted_subcategory
        }

    except Exception as e:
        logger.exception(f"Error classifying/tagging email {email_id}: {str(e)}")
        db.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        db.close() 