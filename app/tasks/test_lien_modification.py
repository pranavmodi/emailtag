"""
Test task for lien modification detection.

This module provides tasks for testing and debugging the lien modification detection service.
"""

import logging
from typing import Dict, List, Any
from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy.orm import Session

from app.tasks.worker import celery_app
from app.db.session import SessionLocal
from app.crud.sync import email as email_crud_sync
from app.services.lien_modification_service import LienModificationDetectionService, check_lien_modifications

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.test_lien_modification.test_lien_modification_detection")
def test_lien_modification_detection(email_id: str) -> Dict:
    """
    Test lien modification detection for a specific email.
    
    This task is useful for debugging and testing the lien modification detection
    functionality on existing emails.
    
    Args:
        email_id: The UUID of the email to test
        
    Returns:
        Dict containing test results
    """
    logger.info(f"Testing lien modification detection for email {email_id}")
    
    try:
        email_uuid = UUID(email_id)
    except ValueError:
        logger.error(f"Invalid UUID format for email_id: {email_id}")
        return {"status": "error", "message": "Invalid email ID format"}
    
    db = SessionLocal()
    try:
        email_obj = email_crud_sync.get(db, id=email_uuid)
        if not email_obj:
            logger.error(f"Email {email_id} not found")
            return {"status": "error", "message": "Email not found"}
        
        # Check if email has attachments
        if not email_obj.has_attachments:
            logger.info(f"Email {email_id} has no attachments")
            return {
                "status": "success",
                "message": "Email has no attachments",
                "email_id": email_id,
                "modifications_detected": False
            }
        
        # Get current tags
        current_tags = [tag.name for tag in email_obj.tags if hasattr(tag, 'name')]
        logger.info(f"Current tags for email {email_id}: {current_tags}")
        
        # Extract attachments data
        attachments_data = []
        if email_obj.raw_data and isinstance(email_obj.raw_data, dict):
            target_data = email_obj.raw_data.get('target', {}).get('data', {})
            attachments_data = target_data.get('attachments', [])
        
        if not attachments_data:
            logger.warning(f"Email {email_id} marked as having attachments but no attachment data found")
            return {
                "status": "warning",
                "message": "Email marked as having attachments but no attachment data found",
                "email_id": email_id,
                "modifications_detected": False
            }
        
        logger.info(f"Found {len(attachments_data)} attachments for email {email_id}")
        
        # Test the lien modification detection service
        service = LienModificationDetectionService()
        
        # Check if this is a lien-related email
        is_lien_related = service.is_lien_related_email(current_tags)
        logger.info(f"Email {email_id} is lien-related: {is_lien_related}")
        
        if not is_lien_related:
            return {
                "status": "success",
                "message": "Email is not lien-related",
                "email_id": email_id,
                "is_lien_related": False,
                "current_tags": current_tags,
                "modifications_detected": False
            }
        
        # Run lien modification detection
        import asyncio
        
        async def _run_detection():
            return await check_lien_modifications(
                email_tags=current_tags,
                attachments_data=attachments_data
            )
        
        modifications_detected, modification_results = asyncio.run(_run_detection())
        
        logger.info(f"Lien modification detection complete for email {email_id}: {modifications_detected}")
        
        return {
            "status": "success",
            "email_id": email_id,
            "is_lien_related": is_lien_related,
            "current_tags": current_tags,
            "attachments_count": len(attachments_data),
            "modifications_detected": modifications_detected,
            "modification_results": modification_results,
            "recommended_action": "Override to 'Lien Modified'" if modifications_detected else "Keep current tags"
        }
        
    except Exception as e:
        logger.exception(f"Error testing lien modification detection for email {email_id}: {e}")
        return {
            "status": "error",
            "message": str(e),
            "email_id": email_id
        }
    finally:
        if db.is_active:
            db.close()


@celery_app.task(name="app.tasks.test_lien_modification.test_strikethrough_detection")
def test_strikethrough_detection(attachment_url: str, provider: str = None) -> Dict:
    """
    Test strikethrough detection for a specific attachment URL.
    
    Args:
        attachment_url: URL of the attachment to test
        provider: Strikethrough detection provider to use (google, roboflow, openai)
        
    Returns:
        Dict containing test results
    """
    logger.info(f"Testing strikethrough detection for attachment {attachment_url} with provider {provider}")
    
    try:
        service = LienModificationDetectionService(provider)
        
        import asyncio
        
        async def _run_detection():
            return await service.detect_modifications_in_attachment(attachment_url)
        
        result = asyncio.run(_run_detection())
        
        logger.info(f"Strikethrough detection complete for {attachment_url}: {result.get('modifications_detected', False)}")
        
        return {
            "status": "success",
            "attachment_url": attachment_url,
            "provider": provider or "default",
            "result": result
        }
        
    except Exception as e:
        logger.exception(f"Error testing strikethrough detection for {attachment_url}: {e}")
        return {
            "status": "error",
            "message": str(e),
            "attachment_url": attachment_url
        }


@celery_app.task(name="app.tasks.test_lien_modification.test_provider_status")
def test_provider_status() -> Dict:
    """
    Test the status of all strikethrough detection providers.
    
    Returns:
        Dict containing provider status information
    """
    logger.info("Testing strikethrough detection provider status")
    
    try:
        from app.services.pdf_strikethrough_service import get_provider_status, is_strikethrough_feature_supported
        
        status = get_provider_status()
        
        # Test each provider's support
        providers = ['google', 'roboflow', 'openai']
        provider_support = {}
        
        for provider in providers:
            provider_support[provider] = is_strikethrough_feature_supported(provider)
        
        return {
            "status": "success",
            "provider_status": status,
            "provider_support": provider_support,
            "recommended_provider": "roboflow" if provider_support.get("roboflow") else "openai"
        }
        
    except Exception as e:
        logger.exception(f"Error testing provider status: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


# Utility function to manually trigger lien modification detection
def manually_check_email_for_lien_modifications(email_id: str) -> Dict:
    """
    Manually check an email for lien modifications (synchronous version for testing).
    
    Args:
        email_id: The UUID of the email to check
        
    Returns:
        Dict containing the results
    """
    task_result = test_lien_modification_detection.delay(email_id)
    return task_result.get(timeout=300)  # 5 minute timeout 