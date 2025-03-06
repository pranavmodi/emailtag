"""CRUD operations for email data."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.email import Email
from app.schemas.email import EmailCreate, EmailUpdate


class CRUDEmail(CRUDBase[Email, EmailCreate, EmailUpdate]):
    """CRUD operations for emails."""

    async def get_by_front_conversation_id(
        self, db: AsyncSession, *, front_conversation_id: str
    ) -> Optional[Email]:
        """Get email by FrontApp conversation ID."""
        result = await db.execute(
            select(self.model).filter(self.model.front_conversation_id == front_conversation_id)
        )
        return result.scalars().first()

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


# Create an instance of the CRUD
email = CRUDEmail(Email) 