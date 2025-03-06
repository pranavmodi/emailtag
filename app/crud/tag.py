"""CRUD operations for tag data."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.email import Tag
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


# Create an instance of the CRUD
tag = CRUDTag(Tag) 