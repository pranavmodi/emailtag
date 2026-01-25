"""PIF (Personal Injury Firm) extraction task."""

import logging
from typing import Dict, Any

from celery.utils.log import get_task_logger

from app.tasks.worker import celery_app
from app.db.session import AsyncSessionLocal
from app.crud.pif_info import pif_info as pif_info_crud

logger = get_task_logger(__name__)


@celery_app.task(name="app.tasks.pif_extraction.extract_pif_from_conversation")
def extract_pif_from_conversation(conversation_id: str) -> Dict[str, Any]:
    """
    Extract personal injury firm information from a Front conversation.

    This task runs asynchronously after each email is received via webhook.
    It extracts firm contact information and stores it in the pif_info table.

    Args:
        conversation_id: The Front conversation ID to process

    Returns:
        Dict with extraction results
    """
    import asyncio

    logger.info(f"Starting PIF extraction for conversation {conversation_id}")

    try:
        # Import pifstats modules
        import sys
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from pifstats.src.front_client import get_conversation_with_messages
        from pifstats.src.entity_extractor import extract_firm_info

        # Get conversation data
        conv_data = get_conversation_with_messages(conversation_id)
        if not conv_data.get("full_text"):
            logger.info(f"No content found for conversation {conversation_id}, skipping PIF extraction")
            return {
                "conversation_id": conversation_id,
                "status": "skipped",
                "reason": "no_content"
            }

        # Extract firm info using OpenAI
        firm_info = extract_firm_info(conv_data["full_text"])

        if not firm_info or not firm_info.firm_name:
            logger.info(f"No firm information found in conversation {conversation_id}")
            return {
                "conversation_id": conversation_id,
                "status": "no_firm_found",
                "reason": "extraction_returned_empty"
            }

        logger.info(f"Extracted firm info for '{firm_info.firm_name}' from conversation {conversation_id}")

        # Store in database using async session
        async def store_firm_info():
            async with AsyncSessionLocal() as db:
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

                return pif, is_new

        # Run the async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            pif, is_new = loop.run_until_complete(store_firm_info())
        finally:
            loop.close()

        action = "created" if is_new else "updated"
        logger.info(f"PIF extraction complete: {action} firm '{firm_info.firm_name}' (ID: {pif.id})")

        return {
            "conversation_id": conversation_id,
            "status": "success",
            "action": action,
            "pif_id": str(pif.id),
            "firm_name": firm_info.firm_name,
            "emails_count": len(firm_info.firm_emails),
            "phones_count": len(firm_info.firm_phones),
            "contacts_count": len(firm_info.contacts),
        }

    except Exception as e:
        logger.error(f"Error extracting PIF from conversation {conversation_id}: {str(e)}", exc_info=True)
        return {
            "conversation_id": conversation_id,
            "status": "error",
            "error": str(e)
        }
