"""Email processing tasks."""

import logging
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud.sync import email as email_crud_sync
from app.crud.sync import tag as tag_crud_sync
from app.db.session import SessionLocal
from app.services.classification_service import classify_email_category
from app.services.frontapp_service import add_conversation_tags
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
    Classify an email into a top-level category using AI analysis and apply it as a tag.

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
            # Mark as processed? Maybe needs manual review tag? For now, mark processed.
            email_crud_sync.mark_as_processed(db, email_id=email_uuid)
            return {"status": "error", "message": "Missing Front conversation ID"}

        # Assuming existing tags are not needed for classification context, pass empty list
        # Or fetch existing tags if needed: existing_tags = [t.name for t in email_obj.tags]
        existing_tags: List[str] = []

        # Classify content with AI - using the new service
        # Pass front_conversation_id instead of subject/content
        predicted_category, confidence = classify_email_category(
            front_conversation_id=front_conversation_id,
            existing_tags=existing_tags
        )

        if not predicted_category:
             logger.error(f"AI classification failed for email {email_id} (conversation {front_conversation_id}). No category determined.")
             # Mark as processed but without a category tag? Or leave unprocessed?
             # Let's mark as processed to avoid retries, but log the failure.
             email_crud_sync.mark_as_processed(db, email_id=email_uuid)
             return {"status": "error", "message": "AI classification failed"}

        logger.info(f"Email {email_id} classified as '{predicted_category}' with confidence {confidence:.2f}")

        # Create the category tag in database and associate with email
        # Use synchronous CRUD
        db_category_tag = tag_crud_sync.get_or_create(db, name=predicted_category)

        # Associate the single category tag with email
        email_obj.tags = [db_category_tag]
        db.commit()

        # Update tag in FrontApp
        if email_obj.front_conversation_id:
            try:
                # Pass the single category name in a list, as the function expects a list
                add_conversation_tags(
                    email_obj.front_conversation_id,
                    [predicted_category]
                )
                logger.info(f"Successfully applied category tag '{predicted_category}' to Front conversation {email_obj.front_conversation_id}")
            except Exception as front_error:
                logger.error(f"Failed to update category tag in Front for email {email_id} / conversation {email_obj.front_conversation_id}: {front_error}", exc_info=True)
                # Proceed even if FrontApp update fails, as the DB is updated.

        # Mark email as processed using synchronous CRUD
        email_crud_sync.mark_as_processed(db, email_id=email_uuid)

        return {
            "status": "success",
            "email_id": email_id,
            "category": predicted_category # Return the category instead of tags
        }

    except Exception as e:
        logger.exception(f"Error classifying/tagging email {email_id}: {str(e)}")
        # Attempt to rollback changes if an error occurred mid-process
        db.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        db.close() 