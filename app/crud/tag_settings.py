"""CRUD operations for tag settings."""

from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.tag_settings import TagSettings
from app.core.exceptions import StaleUpdateError
from datetime import datetime


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

    async def _get_by_tag_name_for_update(
        self, db: AsyncSession, tag_name: str
    ) -> Optional[TagSettings]:
        """Get settings with a row-level lock (SELECT FOR UPDATE)."""
        result = await db.execute(
            select(TagSettings)
            .where(TagSettings.tag_name == tag_name)
            .with_for_update()
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
        updated_by: Optional[str] = None,
        expected_updated_at: Optional[datetime] = None
    ) -> Optional[TagSettings]:
        """
        Update existing tag settings or create if doesn't exist.
        Uses optimistic concurrency control when expected_updated_at is provided.

        Args:
            db: Database session
            tag_name: The tag name
            settings: Settings dictionary
            updated_by: Optional user identifier
            expected_updated_at: If provided, rejects the update if the record
                has been modified since this timestamp.

        Returns:
            Updated TagSettings object

        Raises:
            StaleUpdateError: If expected_updated_at doesn't match
        """
        # Use FOR UPDATE lock
        tag_settings = await self._get_by_tag_name_for_update(db, tag_name)

        if tag_settings:
            # Check optimistic concurrency
            if expected_updated_at is not None and tag_settings.updated_at is not None:
                if tag_settings.updated_at != expected_updated_at:
                    raise StaleUpdateError(
                        setting_key=tag_name,
                        current_updated_at=tag_settings.updated_at,
                        expected_updated_at=expected_updated_at,
                        updated_by=tag_settings.updated_by,
                    )

            # Update existing
            tag_settings.settings = settings
            tag_settings.updated_by = updated_by
            # Ensure SQLAlchemy detects JSONB dict changes even if same object reference
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(tag_settings, "settings")
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
