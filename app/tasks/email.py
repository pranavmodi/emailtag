"""Email processing tasks."""

import logging
from typing import Dict, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import settings
from app.crud import email as email_crud
from app.crud import tag as tag_crud
from app.db.session import SessionLocal
from app.services.ai import analyze_email_content
from app.services.frontapp import update_conversation_tags
from app.tasks.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.email.process_email")
def process_email(email_id: str) -> Dict:
    """
    Process an email by extracting content and sending it for tagging.
    
    Args:
        email_id: The UUID of the email to process
    
    Returns:
        Dict: Status of the processing
    """
    logger.info(f"Processing email {email_id}")
    
    # Convert string to UUID
    email_uuid = UUID(email_id)
    
    # Start tagging task
    tag_email.delay(email_id)
    
    return {"status": "processing", "email_id": email_id}


@celery_app.task(name="app.tasks.email.tag_email")
def tag_email(email_id: str) -> Dict:
    """
    Tag an email using AI analysis.
    
    Args:
        email_id: The UUID of the email to tag
    
    Returns:
        Dict: Status of the tagging process
    """
    logger.info(f"Tagging email {email_id}")
    
    # Convert string to UUID
    email_uuid = UUID(email_id)
    
    # Get database session
    db = SessionLocal()
    try:
        # Get email from database
        email_obj = email_crud.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found")
            return {"status": "error", "message": "Email not found"}
        
        # Get content for analysis
        content_text = email_obj.content_text or ""
        content_html = email_obj.content_html or ""
        
        # Analyze content with AI - using updated parameter names
        suggested_tags = analyze_email_content(content_text=content_text, content_html=content_html)
        
        # Create tags in database and associate with email
        db_tags = []
        for tag_name in suggested_tags:
            db_tag = tag_crud.get_or_create(db, name=tag_name)
            db_tags.append(db_tag)
        
        # Associate tags with email
        email_obj.tags = db_tags
        db.commit()
        
        # Update tags in FrontApp
        if email_obj.front_conversation_id:
            update_conversation_tags(
                email_obj.front_conversation_id, 
                [tag.front_tag_id for tag in db_tags if tag.front_tag_id]
            )
        
        # Mark email as processed
        email_crud.mark_as_processed(db, email_id=email_uuid)
        
        return {
            "status": "success", 
            "email_id": email_id, 
            "tags": [tag.name for tag in db_tags]
        }
    
    except Exception as e:
        logger.exception(f"Error tagging email {email_id}: {str(e)}")
        return {"status": "error", "message": str(e)}
    
    finally:
        db.close() 