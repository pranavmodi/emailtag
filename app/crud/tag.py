"""CRUD operations for tag data."""

from typing import List, Optional
from datetime import date, datetime

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.email import Tag, Email, email_tag_association
from app.schemas.email import TagCreate, TagUpdate


class CRUDTag(CRUDBase[Tag, TagCreate, TagUpdate]):
    """CRUD operations for tags."""

    async def get_by_name(
        self, db: AsyncSession, *, name: str
    ) -> Optional[Tag]:
        """Get tag by name."""
        result = await db.execute(
            select(self.model).filter(self.model.name == name)
        )
        return result.scalars().first()

    async def get_or_create(
        self, db: AsyncSession, *, name: str, description: Optional[str] = None, front_tag_id: Optional[str] = None
    ) -> Tag:
        """Get a tag by name or create it if it doesn't exist."""
        tag = await self.get_by_name(db, name=name)
        if not tag:
            tag_in = TagCreate(
                name=name,
                description=description,
                front_tag_id=front_tag_id,
            )
            tag = await self.create(db, obj_in=tag_in)
        return tag

    async def get_conversation_ids_by_tag_and_date(
        self,
        db: AsyncSession,
        *,
        tag_name: str,
        target_date: date
    ) -> List[str]:
        """
        Get all conversation IDs tagged with a specific tag on a specific date.

        Note: Since the email_tag_association table doesn't track when tags are applied,
        this uses the email's created_at date as the filter.

        Args:
            db: Database session
            tag_name: Name of the tag to filter by
            target_date: Date to filter emails by (using created_at)

        Returns:
            List[str]: List of unique front_conversation_id values
        """
        # Get the tag first
        tag = await self.get_by_name(db, name=tag_name)
        if not tag:
            return []

        # Query emails with this tag on the specified date
        # We filter by the date portion of created_at
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        result = await db.execute(
            select(Email.front_conversation_id)
            .distinct()
            .join(email_tag_association, Email.id == email_tag_association.c.email_id)
            .join(Tag, Tag.id == email_tag_association.c.tag_id)
            .where(
                and_(
                    Tag.name == tag_name,
                    Email.created_at >= start_of_day,
                    Email.created_at <= end_of_day
                )
            )
            .order_by(Email.front_conversation_id)
        )

        return list(result.scalars().all())


# Create an instance of the CRUD
tag = CRUDTag(Tag) 