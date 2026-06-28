"""CRUD operations for PIF (Personal Injury Firm) information."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, or_, select, func, text, literal_column
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
        sort_by: Optional[str] = None,
        research_status: Optional[str] = None,
        icp_tier: Optional[str] = None,
        entity_type: Optional[str] = None,
        recently_researched_days: Optional[int] = None,
        website_presence: Optional[str] = None,
        research_presence: Optional[str] = None,
        staff_presence: Optional[str] = None,
        behavior_presence: Optional[str] = None,
        icp_presence: Optional[str] = None,
        active_only: bool = True,
    ) -> tuple[List[PifInfo], int]:
        """
        Search PIF info with optional text search, filters, and sorting.

        Args:
            db: Database session
            search: Optional search term
            skip: Number of records to skip (for pagination)
            limit: Maximum number of records to return
            sort_by: Sort order - 'conversation_count' (desc), 'firm_name' (asc),
                     or 'updated_at' (desc, default)
            research_status: Filter by research_status (e.g. 'completed', 'pending')
            icp_tier: Filter by ICP tier ('A', 'B', 'C', 'D')
            recently_researched_days: Filter firms researched within the last N days

        Returns a tuple of (items, total_count).
        """
        query = select(PifInfo)
        count_query = select(func.count(PifInfo.id))

        if active_only:
            query = query.filter(PifInfo.merged_into.is_(None))
            count_query = count_query.filter(PifInfo.merged_into.is_(None))

        if search:
            search_term = f"%{search.lower()}%"
            search_filter = or_(
                func.lower(PifInfo.firm_name).like(search_term),
                func.lower(PifInfo.website).like(search_term),
                func.lower(PifInfo.canonical_website).like(search_term),
                # Search in emails array - PostgreSQL specific
                PifInfo.emails.any(search.lower()),
            )
            query = query.filter(search_filter)
            count_query = count_query.filter(search_filter)

        if research_status:
            query = query.filter(PifInfo.research_status == research_status)
            count_query = count_query.filter(PifInfo.research_status == research_status)

        if icp_tier:
            query = query.filter(PifInfo.icp_tier == icp_tier)
            count_query = count_query.filter(PifInfo.icp_tier == icp_tier)

        if entity_type:
            query = query.filter(PifInfo.entity_type == entity_type)
            count_query = count_query.filter(PifInfo.entity_type == entity_type)

        if recently_researched_days is not None:
            from datetime import datetime, timedelta
            cutoff = datetime.utcnow() - timedelta(days=recently_researched_days)
            query = query.filter(PifInfo.last_researched_at >= cutoff)
            count_query = count_query.filter(PifInfo.last_researched_at >= cutoff)

        for field_name, value in (
            ("website_presence", website_presence),
            ("research_presence", research_presence),
            ("staff_presence", staff_presence),
            ("behavior_presence", behavior_presence),
            ("icp_presence", icp_presence),
        ):
            presence_filter = self._presence_filter(field_name, value)
            if presence_filter is not None:
                query = query.filter(presence_filter)
                count_query = count_query.filter(presence_filter)

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

    def _presence_filter(self, field_name: str, value: Optional[str]):
        """Translate dashboard presence filters into SQLAlchemy predicates."""
        if value in (None, "", "any"):
            return None

        if field_name == "website_presence":
            has_website = or_(
                PifInfo.canonical_website.is_not(None),
                PifInfo.website.is_not(None),
                PifInfo.website_status == "resolved",
            )
            missing_website = and_(
                PifInfo.canonical_website.is_(None),
                PifInfo.website.is_(None),
                or_(PifInfo.website_status.is_(None), PifInfo.website_status != "resolved"),
            )
            if value == "has":
                return has_website
            if value == "missing":
                return missing_website
            if value == "resolved":
                return PifInfo.website_status == "resolved"
            if value == "unresolved":
                return or_(PifInfo.website_status.is_(None), PifInfo.website_status != "resolved")

        if field_name == "research_presence":
            if value == "completed":
                return PifInfo.research_status == "completed"
            if value == "missing":
                return or_(
                    PifInfo.research_status.is_(None),
                    ~PifInfo.research_status.in_(["completed", "queued", "in_progress"]),
                )
            if value == "queued_or_running":
                return PifInfo.research_status.in_(["queued", "in_progress"])
            if value == "failed":
                return PifInfo.research_status == "failed"

        if field_name == "staff_presence":
            if value == "completed":
                return PifInfo.staff_research_status == "completed"
            if value == "missing":
                return or_(
                    PifInfo.staff_research_status.is_(None),
                    ~PifInfo.staff_research_status.in_(["completed", "queued", "in_progress"]),
                )
            if value == "queued_or_running":
                return PifInfo.staff_research_status.in_(["queued", "in_progress"])
            if value == "failed":
                return PifInfo.staff_research_status == "failed"

        if field_name == "behavior_presence":
            if value == "has":
                return PifInfo.behavioral_data.is_not(None)
            if value == "missing":
                return PifInfo.behavioral_data.is_(None)

        if field_name == "icp_presence":
            if value == "has":
                return PifInfo.icp_score.is_not(None)
            if value == "missing":
                return PifInfo.icp_score.is_(None)

        return None

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
        extraction_notes: Optional[str] = None,
        entity_type: str = "pi_law_firm",
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
                entity_type=entity_type,
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


    async def search_people(
        self,
        db: AsyncSession,
        *,
        title: Optional[str] = None,
        name: Optional[str] = None,
        role_category: Optional[str] = None,
        source: str = "all",
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Search across leadership and staff JSONB arrays for people by title/name.

        Uses jsonb_array_elements to unnest the arrays and filter.

        Args:
            title: Search term to match against person title (ILIKE)
            name: Search term to match against person name (ILIKE)
            role_category: Filter staff by role_category value (exact match)
            source: 'leadership', 'staff', or 'all'
            skip: Offset for pagination
            limit: Max results

        Returns:
            Tuple of (list of person dicts with firm context, total count)
        """
        queries = []

        if source in ("all", "leadership"):
            queries.append("""
                SELECT
                    person->>'name' AS name,
                    person->>'title' AS title,
                    person->>'email' AS email,
                    person->>'phone' AS phone,
                    person->>'linkedin' AS linkedin,
                    person->>'bio' AS bio,
                    NULL AS role_category,
                    'leadership' AS source,
                    pif.id AS firm_id,
                    pif.firm_name AS firm_name,
                    pif.website AS firm_website,
                    pif.entity_type AS entity_type
                FROM pif_info pif,
                     jsonb_array_elements(pif.leadership) AS person
                WHERE pif.leadership IS NOT NULL
            """)

        if source in ("all", "staff"):
            queries.append("""
                SELECT
                    person->>'name' AS name,
                    person->>'title' AS title,
                    person->>'email' AS email,
                    person->>'phone' AS phone,
                    person->>'linkedin' AS linkedin,
                    person->>'bio' AS bio,
                    person->>'role_category' AS role_category,
                    'staff' AS source,
                    pif.id AS firm_id,
                    pif.firm_name AS firm_name,
                    pif.website AS firm_website,
                    pif.entity_type AS entity_type
                FROM pif_info pif,
                     jsonb_array_elements(pif.staff) AS person
                WHERE pif.staff IS NOT NULL
            """)

        if not queries:
            return [], 0

        combined = " UNION ALL ".join(queries)

        # Build WHERE clauses for the outer query
        conditions = []
        params: Dict[str, Any] = {}

        if title:
            conditions.append("LOWER(title) LIKE :title_search")
            params["title_search"] = f"%{title.lower()}%"

        if name:
            conditions.append("LOWER(name) LIKE :name_search")
            params["name_search"] = f"%{name.lower()}%"

        if role_category:
            conditions.append("role_category = :role_cat")
            params["role_cat"] = role_category

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Count query
        count_sql = f"SELECT COUNT(*) FROM ({combined}) sub {where_clause}"
        count_result = await db.execute(text(count_sql), params)
        total = count_result.scalar() or 0

        # Data query with pagination
        data_sql = f"""
            SELECT * FROM ({combined}) sub
            {where_clause}
            ORDER BY firm_name ASC, source ASC, name ASC
            LIMIT :lim OFFSET :off
        """
        params["lim"] = limit
        params["off"] = skip

        result = await db.execute(text(data_sql), params)
        rows = result.mappings().all()

        people = [
            {
                "name": row["name"],
                "title": row["title"],
                "email": row["email"],
                "phone": row["phone"],
                "linkedin": row["linkedin"],
                "bio": row["bio"],
                "role_category": row["role_category"],
                "source": row["source"],
                "firm_id": str(row["firm_id"]),
                "firm_name": row["firm_name"],
                "firm_website": row["firm_website"],
            }
            for row in rows
        ]

        return people, total


pif_info = CRUDPifInfo(PifInfo)
