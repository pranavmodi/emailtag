"""PIF (Personal Injury Firm) extraction task."""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from celery.utils.log import get_task_logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.tasks.worker import celery_app
from app.db.session import SessionLocal
from app.models.pif_info import PifInfo

logger = get_task_logger(__name__)


def get_by_website_sync(db: Session, website: str) -> Optional[PifInfo]:
    """Get PIF info by website URL (sync)."""
    return db.query(PifInfo).filter(PifInfo.website == website).first()


def get_by_firm_name_sync(db: Session, firm_name: str) -> Optional[PifInfo]:
    """Get PIF info by firm name (sync, case-insensitive)."""
    return db.query(PifInfo).filter(
        func.lower(PifInfo.firm_name) == func.lower(firm_name)
    ).first()


def merge_contacts(
    existing_contacts: List[Dict[str, Any]],
    new_contacts: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Merge contact lists, deduplicating by email or name."""
    contacts_by_key = {}

    for contact in (existing_contacts or []):
        key = contact.get("email") or contact.get("name") or str(contact)
        if key:
            contacts_by_key[key.lower()] = contact

    for contact in (new_contacts or []):
        key = contact.get("email") or contact.get("name") or str(contact)
        if key:
            key_lower = key.lower()
            if key_lower not in contacts_by_key:
                contacts_by_key[key_lower] = contact
            else:
                # Merge contact info
                existing = contacts_by_key[key_lower]
                for field in ["name", "title", "email", "phone", "extension"]:
                    if contact.get(field) and not existing.get(field):
                        existing[field] = contact[field]

    return list(contacts_by_key.values())


def upsert_pif_sync(
    db: Session,
    firm_name: str,
    website: Optional[str],
    emails: List[str],
    phones: List[str],
    fax: Optional[str],
    addresses: List[str],
    contacts: List[Dict[str, Any]],
    conversation_id: str,
    extraction_notes: Optional[str] = None
) -> tuple[PifInfo, bool]:
    """
    Upsert PIF info from extraction results (sync version).

    Returns tuple of (pif_info, is_new_record).
    """
    existing = None

    # Try to find by website first (if provided)
    if website:
        existing = get_by_website_sync(db, website)

    # If not found by website, try by firm name
    if not existing and firm_name:
        existing = get_by_firm_name_sync(db, firm_name)

    if existing:
        # Merge data into existing record
        merged_emails = list(set(existing.emails or []) | set(emails or []))
        merged_phones = list(set(existing.phones or []) | set(phones or []))
        merged_addresses = list(set(existing.addresses or []) | set(addresses or []))
        merged_conv_ids = list(set(existing.conversation_ids or []) | {conversation_id})
        merged_contacts = merge_contacts(existing.contacts or [], contacts)

        existing.emails = merged_emails
        existing.phones = merged_phones
        existing.addresses = merged_addresses
        existing.conversation_ids = merged_conv_ids
        existing.contacts = merged_contacts

        if website and not existing.website:
            existing.website = website
        if fax and not existing.fax:
            existing.fax = fax

        existing.updated_at = datetime.utcnow()

        db.add(existing)
        db.commit()
        db.refresh(existing)

        logger.info(f"Updated existing PIF info for '{firm_name}' (ID: {existing.id})")
        return existing, False
    else:
        # Create new record
        new_pif = PifInfo(
            firm_name=firm_name,
            website=website,
            emails=emails or [],
            phones=phones or [],
            fax=fax,
            addresses=addresses or [],
            contacts=contacts or [],
            conversation_ids=[conversation_id],
            extraction_notes=extraction_notes,
        )

        db.add(new_pif)
        db.commit()
        db.refresh(new_pif)

        logger.info(f"Created new PIF info for '{firm_name}' (ID: {new_pif.id})")
        return new_pif, True


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
    logger.info(f"Starting PIF extraction for conversation {conversation_id}")

    db = SessionLocal()
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

        # Store in database using sync session
        contacts_dicts = [c.model_dump() for c in firm_info.contacts]

        pif, is_new = upsert_pif_sync(
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
        if db.is_active:
            db.rollback()
        return {
            "conversation_id": conversation_id,
            "status": "error",
            "error": str(e)
        }
    finally:
        if db.is_active:
            db.close()
