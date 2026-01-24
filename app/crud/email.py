"""CRUD operations for email data."""

from datetime import date, datetime, timedelta
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.email import Email
from app.schemas.email import EmailCreate, EmailUpdate


class CRUDEmail(CRUDBase[Email, EmailCreate, EmailUpdate]):
    """CRUD operations for emails."""

    async def get_by_front_conversation_id(
        self, db: AsyncSession, *, front_conversation_id: str, load_tags: bool = False
    ) -> Optional[Email]:
        """
        Get email by FrontApp conversation ID.

        Args:
            db: Database session
            front_conversation_id: Front conversation ID
            load_tags: If True, eagerly load the tags relationship
        """
        query = select(self.model).filter(self.model.front_conversation_id == front_conversation_id)

        if load_tags:
            # Eagerly load tags to avoid lazy-loading issues in async context
            query = query.options(selectinload(self.model.tags))

        result = await db.execute(query)
        return result.scalars().first()

    async def get_conversation_content(
        self, db: AsyncSession, *, front_conversation_id: str
    ) -> str:
        """
        Retrieve all email content for a given conversation ID,
        formatted as a single string, in chronological order.
        """
        result = await db.execute(
            select(self.model)
            .filter(self.model.front_conversation_id == front_conversation_id)
            .order_by(self.model.created_at.asc())
        )
        emails = result.scalars().all()
        
        conversation_thread = []
        for email_obj in emails:
            # We can customize this part further, e.g., add sender, timestamp
            header = f"--- Email from: {email_obj.sender} at {email_obj.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')} ---"
            content = email_obj.content_text or "" # Default to empty string if content_text is None
            conversation_thread.append(f"{header}\n{content}")
            
        return "\n\n".join(conversation_thread)

    async def get_unprocessed(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> List[Email]:
        """Get all unprocessed emails."""
        result = await db.execute(
            select(self.model)
            .filter(self.model.processed == False)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_as_processed(self, db: AsyncSession, *, email_id: UUID) -> Optional[Email]:
        """Mark an email as processed."""
        email = await self.get(db, id=email_id)
        if not email:
            return None
        update_data = {"processed": True}
        return await self.update(db, db_obj=email, obj_in=update_data)

    async def get_archived_by_date(
        self, db: AsyncSession, *, target_date: date, hour: Optional[int] = None
    ) -> List[Email]:
        """
        Get all archived emails for a specific date, optionally filtered by hour.
        Returns only the most recent email per conversation to avoid duplicates.

        Args:
            db: Database session
            target_date: Date to filter by (uses created_at field)
            hour: Optional hour (0-23) to filter by

        Returns:
            List of Email objects with status='archived_in_orchestration', deduplicated by conversation_id
        """
        from sqlalchemy import distinct

        # Build base query with DISTINCT ON to get one email per conversation
        # PostgreSQL DISTINCT ON returns the first row for each distinct value
        query = (
            select(self.model)
            .filter(self.model.status == "archived_in_orchestration")
            .distinct(self.model.front_conversation_id)
        )

        # Filter by date
        if hour is not None:
            # Filter by specific hour
            start_datetime = datetime.combine(target_date, datetime.min.time()) + timedelta(hours=hour)
            end_datetime = start_datetime + timedelta(hours=1)
            query = query.filter(
                self.model.created_at >= start_datetime,
                self.model.created_at < end_datetime
            )
        else:
            # Filter by entire day
            start_datetime = datetime.combine(target_date, datetime.min.time())
            end_datetime = start_datetime + timedelta(days=1)
            query = query.filter(
                self.model.created_at >= start_datetime,
                self.model.created_at < end_datetime
            )

        # IMPORTANT: When using DISTINCT ON, must order by the DISTINCT column first
        # Then by updated_at to get the most recently updated email for each conversation
        query = query.order_by(
            self.model.front_conversation_id,
            self.model.updated_at.desc()
        )

        # Eagerly load tags for archived emails
        query = query.options(selectinload(self.model.tags))

        result = await db.execute(query)
        return result.scalars().all()

    async def get_emails_by_date(
        self, db: AsyncSession, target_date: date
    ) -> List[Email]:
        """
        Get all emails for a specific date, deduplicated by conversation ID.

        Args:
            db: Database session
            target_date: Date to filter by (uses created_at field)

        Returns:
            List of Email objects, one per unique conversation
        """
        # Build query with DISTINCT ON to get one email per conversation
        query = (
            select(self.model)
            .distinct(self.model.front_conversation_id)
        )

        # Filter by entire day
        start_datetime = datetime.combine(target_date, datetime.min.time())
        end_datetime = start_datetime + timedelta(days=1)
        query = query.filter(
            self.model.created_at >= start_datetime,
            self.model.created_at < end_datetime
        )

        # Order by conversation ID first (required for DISTINCT ON), then by created_at
        query = query.order_by(
            self.model.front_conversation_id,
            self.model.created_at.desc()
        )

        result = await db.execute(query)
        return result.scalars().all()


# Create an instance of the CRUD
email = CRUDEmail(Email) 