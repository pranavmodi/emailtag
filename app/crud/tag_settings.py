"""CRUD operations for tag settings."""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.tag_settings import TagSettings


class TagSettingsCRUD:
    """CRUD operations for TagSettings model."""

    async def get_by_tag_name(
        self, db: AsyncSession, tag_name: str
    ) -> Optional[TagSettings]:
        """
        Get settings for a specific tag.

        Args:
            db: Database session
            tag_name: The tag name to search for

        Returns:
            TagSettings object if found, None otherwise
        """
        result = await db.execute(
            select(TagSettings).where(TagSettings.tag_name == tag_name)
        )
        return result.scalar_one_or_none()

    async def get_settings_dict(
        self, db: AsyncSession, tag_name: str, default: Optional[dict] = None
    ) -> dict:
        """
        Get settings dictionary for a specific tag.

        Args:
            db: Database session
            tag_name: The tag name to search for
            default: Default dictionary to return if not found

        Returns:
            Settings dictionary or default
        """
        tag_settings = await self.get_by_tag_name(db, tag_name)
        if tag_settings:
            return tag_settings.settings
        return default or {}

    async def get_all(self, db: AsyncSession) -> List[TagSettings]:
        """
        Get all tag settings.

        Args:
            db: Database session

        Returns:
            List of all TagSettings objects
        """
        result = await db.execute(select(TagSettings))
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        tag_name: str,
        settings: dict,
        updated_by: Optional[str] = None
    ) -> TagSettings:
        """
        Create new tag settings.

        Args:
            db: Database session
            tag_name: The tag name
            settings: Settings dictionary
            updated_by: Optional user identifier

        Returns:
            Created TagSettings object
        """
        tag_settings = TagSettings(
            tag_name=tag_name,
            settings=settings,
            updated_by=updated_by
        )
        db.add(tag_settings)
        await db.commit()
        await db.refresh(tag_settings)
        return tag_settings

    async def update(
        self,
        db: AsyncSession,
        tag_name: str,
        settings: dict,
        updated_by: Optional[str] = None
    ) -> Optional[TagSettings]:
        """
        Update existing tag settings or create if doesn't exist.

        Args:
            db: Database session
            tag_name: The tag name
            settings: Settings dictionary
            updated_by: Optional user identifier

        Returns:
            Updated TagSettings object
        """
        tag_settings = await self.get_by_tag_name(db, tag_name)

        if tag_settings:
            # Update existing
            tag_settings.settings = settings
            tag_settings.updated_by = updated_by
            await db.commit()
            await db.refresh(tag_settings)
            return tag_settings
        else:
            # Create new
            return await self.create(db, tag_name, settings, updated_by)

    async def delete(
        self, db: AsyncSession, tag_name: str
    ) -> bool:
        """
        Delete tag settings.

        Args:
            db: Database session
            tag_name: The tag name

        Returns:
            True if deleted, False if not found
        """
        tag_settings = await self.get_by_tag_name(db, tag_name)
        if tag_settings:
            await db.delete(tag_settings)
            await db.commit()
            return True
        return False

    async def get_setting_value(
        self,
        db: AsyncSession,
        tag_name: str,
        setting_key: str,
        default: any = None
    ) -> any:
        """
        Get a specific setting value for a tag.

        Args:
            db: Database session
            tag_name: The tag name
            setting_key: The setting key to retrieve
            default: Default value if not found

        Returns:
            Setting value or default
        """
        settings = await self.get_settings_dict(db, tag_name)
        return settings.get(setting_key, default)


# Global instance
tag_settings_crud = TagSettingsCRUD()
