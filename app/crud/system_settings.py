"""CRUD operations for system settings."""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system_settings import SystemSetting
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class CRUDSystemSettings:
    """CRUD operations for system settings."""

    async def get_by_key(
        self,
        db: AsyncSession,
        setting_key: str
    ) -> Optional[SystemSetting]:
        """
        Get a setting by its key.

        Args:
            db: Database session
            setting_key: The key to look up

        Returns:
            SystemSetting object if found, None otherwise
        """
        result = await db.execute(
            select(SystemSetting).filter(SystemSetting.setting_key == setting_key)
        )
        return result.scalars().first()

    async def get_setting_value(
        self,
        db: AsyncSession,
        setting_key: str,
        default: bool = True
    ) -> bool:
        """
        Get setting value with default fallback.

        Args:
            db: Database session
            setting_key: The key to look up
            default: Default value if setting not found

        Returns:
            The setting value, or default if not found
        """
        setting = await self.get_by_key(db, setting_key)
        return setting.setting_value if setting else default

    async def is_email_processing_enabled(self, db: AsyncSession) -> bool:
        """
        Quick check if email processing is enabled.

        This is the primary method to check if incoming emails should be processed.
        Returns True by default if the setting doesn't exist yet.

        Args:
            db: Database session

        Returns:
            True if processing is enabled, False otherwise
        """
        enabled = await self.get_setting_value(
            db,
            "email_processing_enabled",
            default=True
        )
        logger.info(f"Email processing enabled status: {enabled}")
        return enabled

    async def update_setting(
        self,
        db: AsyncSession,
        setting_key: str,
        value: bool,
        updated_by: Optional[str] = None
    ) -> SystemSetting:
        """
        Update or create a setting.

        Args:
            db: Database session
            setting_key: The setting key to update
            value: The new boolean value
            updated_by: Optional identifier of who made the change

        Returns:
            The updated or created SystemSetting object
        """
        setting = await self.get_by_key(db, setting_key)

        if setting:
            # Update existing setting
            setting.setting_value = value
            setting.updated_at = datetime.utcnow()
            setting.updated_by = updated_by
            logger.info(
                f"Updated setting '{setting_key}' to {value} "
                f"(by: {updated_by or 'unknown'})"
            )
        else:
            # Create new setting
            description = None
            if setting_key == "email_processing_enabled":
                description = (
                    "Master switch to enable/disable all incoming email processing. "
                    "When disabled, emails are received and saved but not classified or tagged."
                )

            setting = SystemSetting(
                setting_key=setting_key,
                setting_value=value,
                description=description,
                updated_by=updated_by
            )
            db.add(setting)
            logger.info(
                f"Created new setting '{setting_key}' with value {value} "
                f"(by: {updated_by or 'unknown'})"
            )

        await db.commit()
        await db.refresh(setting)
        return setting

    async def toggle_email_processing(
        self,
        db: AsyncSession,
        enable: bool,
        updated_by: Optional[str] = None
    ) -> SystemSetting:
        """
        Toggle the email processing master switch.

        Args:
            db: Database session
            enable: True to enable processing, False to disable
            updated_by: Optional identifier of who made the change

        Returns:
            The updated SystemSetting object
        """
        return await self.update_setting(
            db,
            "email_processing_enabled",
            enable,
            updated_by
        )


# Create singleton instance
system_settings_crud = CRUDSystemSettings()
