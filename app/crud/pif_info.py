"""CRUD operations for PIF (Personal Injury Firm) information."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import or_, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.pif_info import PifInfo
from app.schemas.pif_info import PifInfoCreate, PifInfoUpdate

logger = logging.getLogger(__name__)


class CRUDPifInfo(CRUDBase[PifInfo, PifInfoCreate, PifInfoUpdate]):
    """CRUD operations for PIF info."""

    async def get_by_website(self, db: AsyncSession, website: str) -> Optional[PifInfo]:
        """Get PIF info by website URL."""
        result = await db.execute(
            select(PifInfo).filter(PifInfo.website == website)
        )
        return result.scalars().first()

    async def get_by_firm_name(self, db: AsyncSession, firm_name: str) -> Optional[PifInfo]:
        """Get PIF info by firm name (case-insensitive)."""
        result = await db.execute(
            select(PifInfo).filter(func.lower(PifInfo.firm_name) == func.lower(firm_name))
        )
        return result.scalars().first()

    async def search(
        self,
        db: AsyncSession,
        *,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
        sort_by: Optional[str] = None
    ) -> tuple[List[PifInfo], int]:
        """
        Search PIF info with optional text search and sorting.

        Args:
            db: Database session
            search: Optional search term
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            sort_by: Sort order - 'conversation_count' (desc), 'firm_name' (asc),
                     or 'updated_at' (desc, default)

        Returns a tuple of (items, total_count).
        """
        query = select(PifInfo)
        count_query = select(func.count(PifInfo.id))

        if search:
            search_term = f"%{search.lower()}%"
            search_filter = or_(
                func.lower(PifInfo.firm_name).like(search_term),
                func.lower(PifInfo.website).like(search_term),
                # Search in emails array - PostgreSQL specific
                PifInfo.emails.any(search.lower()),
            )
            query = query.filter(search_filter)
            count_query = count_query.filter(search_filter)

        # Get total count
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        if sort_by == "conversation_count":
            # Sort by array length (number of conversations) - descending
            query = query.order_by(
                func.cardinality(PifInfo.conversation_ids).desc(),
                PifInfo.firm_name.asc()  # Secondary sort by name
            )
        elif sort_by == "firm_name":
            query = query.order_by(PifInfo.firm_name.asc())
        else:
            # Default: sort by updated_at descending
            query = query.order_by(PifInfo.updated_at.desc())

        # Get paginated results
        query = query.offset(skip).limit(limit)
        result = await db.execute(query)
        items = result.scalars().all()

        return items, total

    async def get_all(
        self,
        db: AsyncSession,
        *,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[List[PifInfo], int]:
        """Get all PIF info with pagination."""
        return await self.search(db, skip=skip, limit=limit)

    async def upsert_from_extraction(
        self,
        db: AsyncSession,
        *,
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
        Upsert PIF info from extraction results.

        Matches by website first, then by firm name.
        Merges data if existing record found.

        Returns tuple of (pif_info, is_new_record).
        """
        existing = None

        # Try to find by website first (if provided)
        if website:
            existing = await self.get_by_website(db, website)

        # If not found by website, try by firm name
        if not existing and firm_name:
            existing = await self.get_by_firm_name(db, firm_name)

        if existing:
            # Merge data into existing record
            merged_emails = list(set(existing.emails or []) | set(emails or []))
            merged_phones = list(set(existing.phones or []) | set(phones or []))
            merged_addresses = list(set(existing.addresses or []) | set(addresses or []))

            # Add conversation ID if not already present
            merged_conv_ids = list(set(existing.conversation_ids or []) | {conversation_id})

            # Merge contacts (deduplicate by email if present, else by name)
            existing_contacts = existing.contacts or []
            merged_contacts = self._merge_contacts(existing_contacts, contacts)

            # Update record
            existing.emails = merged_emails
            existing.phones = merged_phones
            existing.addresses = merged_addresses
            existing.conversation_ids = merged_conv_ids
            existing.contacts = merged_contacts

            # Update website if not set but now provided
            if website and not existing.website:
                existing.website = website

            # Update fax if not set but now provided
            if fax and not existing.fax:
                existing.fax = fax

            existing.updated_at = datetime.utcnow()

            db.add(existing)
            await db.commit()
            await db.refresh(existing)

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
            await db.commit()
            await db.refresh(new_pif)

            logger.info(f"Created new PIF info for '{firm_name}' (ID: {new_pif.id})")
            return new_pif, True

    def _merge_contacts(
        self,
        existing_contacts: List[Dict[str, Any]],
        new_contacts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge contact lists, deduplicating by email or name."""
        contacts_by_key = {}

        for contact in existing_contacts:
            key = contact.get("email") or contact.get("name") or str(contact)
            if key:
                contacts_by_key[key.lower()] = contact

        for contact in new_contacts:
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

    async def get_all_ids(self, db: AsyncSession) -> List[UUID]:
        """Get all PIF IDs for batch processing."""
        result = await db.execute(select(PifInfo.id))
        return [row[0] for row in result.fetchall()]

    async def get_scored_sorted(
        self,
        db: AsyncSession,
        *,
        tier_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[List[PifInfo], int]:
        """Get firms sorted by ICP score descending, optionally filtered by tier."""
        query = select(PifInfo).where(PifInfo.icp_score.is_not(None))
        count_query = select(func.count(PifInfo.id)).where(PifInfo.icp_score.is_not(None))

        if tier_filter:
            query = query.where(PifInfo.icp_tier == tier_filter)
            count_query = count_query.where(PifInfo.icp_tier == tier_filter)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(PifInfo.icp_score.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all(), total

    async def add_conversation(
        self,
        db: AsyncSession,
        *,
        pif_id: UUID,
        conversation_id: str
    ) -> Optional[PifInfo]:
        """Add a conversation ID to an existing PIF record."""
        pif = await self.get(db, id=pif_id)
        if not pif:
            return None

        if conversation_id not in (pif.conversation_ids or []):
            pif.conversation_ids = list(set(pif.conversation_ids or []) | {conversation_id})
            pif.updated_at = datetime.utcnow()
            db.add(pif)
            await db.commit()
            await db.refresh(pif)

        return pif


pif_info = CRUDPifInfo(PifInfo)
