"""CRUD operations for system settings."""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system_settings import SystemSetting
from app.core.exceptions import StaleUpdateError
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

    async def _get_by_key_for_update(
        self,
        db: AsyncSession,
        setting_key: str
    ) -> Optional[SystemSetting]:
        """Get a setting by its key with a row-level lock (SELECT FOR UPDATE)."""
        result = await db.execute(
            select(SystemSetting)
            .filter(SystemSetting.setting_key == setting_key)
            .with_for_update()
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
        updated_by: Optional[str] = None,
        expected_updated_at: Optional[datetime] = None
    ) -> SystemSetting:
        """
        Update or create a setting with optimistic concurrency control.

        Args:
            db: Database session
            setting_key: The setting key to update
            value: The new boolean value
            updated_by: Optional identifier of who made the change
            expected_updated_at: If provided, the update will only proceed if the
                current updated_at matches this value. Raises StaleUpdateError on mismatch.

        Returns:
            The updated or created SystemSetting object

        Raises:
            StaleUpdateError: If expected_updated_at doesn't match the current value
        """
        # Use FOR UPDATE lock to prevent concurrent modifications
        setting = await self._get_by_key_for_update(db, setting_key)

        if setting:
            # Check optimistic concurrency if client provided expected timestamp
            if expected_updated_at is not None and setting.updated_at is not None:
                if setting.updated_at != expected_updated_at:
                    raise StaleUpdateError(
                        setting_key=setting_key,
                        current_updated_at=setting.updated_at,
                        expected_updated_at=expected_updated_at,
                        updated_by=setting.updated_by,
                    )

            # Update existing setting
            setting.setting_value = value
            setting.updated_at = datetime.utcnow()
            setting.updated_by = updated_by
            logger.info(
                f"Updated setting '{setting_key}' to {value} "
                f"(by: {updated_by or 'unknown'})"
            )
        else:
            # Create new setting — no conflict possible
            description = None
            if setting_key == "email_processing_enabled":
                description = (
                    "Master switch to enable/disable all incoming email processing. "
                    "When disabled, emails are received and saved but not classified or tagged."
                )
            elif setting_key == "skip_internal_domains":
                description = (
                    "Filter emails from internal domains (@precisemri.com, @mediflow.com). "
                    "When enabled, emails from these domains are skipped. "
                    "When disabled (default for testing), all emails are processed."
                )
            elif setting_key == "lien_test_mode":
                description = (
                    "Lien upload test mode. When enabled, lien documents are saved to a local directory "
                    "(/tmp/lien_test_uploads/{conversation_id}/) instead of uploading to RadFlow via MCP. "
                    "Use this for testing lien processing without affecting production data."
                )
            elif setting_key == "bill_balance_test_mode":
                description = (
                    "Bill balance test mode. When enabled, bill balance responses are saved to a local directory "
                    "(/tmp/bill_balance_test_outputs/{conversation_id}/) instead of sending via Front API. "
                    "Use this for testing bill balance processing without affecting production data."
                )
            elif setting_key == "apt_status_test_mode":
                description = (
                    "Apt status test mode. When enabled, apt status responses are saved to a local directory "
                    "(/tmp/apt_status_test_outputs/{conversation_id}/) instead of sending via Front API. "
                    "Use this for testing apt status processing without affecting production data."
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
        updated_by: Optional[str] = None,
        expected_updated_at: Optional[datetime] = None
    ) -> SystemSetting:
        """
        Toggle the email processing master switch.

        Args:
            db: Database session
            enable: True to enable processing, False to disable
            updated_by: Optional identifier of who made the change
            expected_updated_at: Optional timestamp for optimistic concurrency control

        Returns:
            The updated SystemSetting object
        """
        return await self.update_setting(
            db,
            "email_processing_enabled",
            enable,
            updated_by,
            expected_updated_at=expected_updated_at
        )

    async def get_autorespond_settings(self, db: AsyncSession) -> dict:
        """
        Get all autorespond settings with their current values.

        Returns a dictionary with autorespond type as key and enabled status as value.
        Defaults to True for any setting that doesn't exist.

        Args:
            db: Database session

        Returns:
            Dictionary mapping autorespond types to their enabled status
        """
        autorespond_types = [
            "autorespond_appointment_inquiry",
            "autorespond_apt_status_req",
            "autorespond_medical_records",
            "autorespond_bill_balance_request",
            "autorespond_case_updates",
            "autorespond_missing_lien_request",
            "autorespond_liens"  # Consolidated liens setting (replaces PSL/ASL)
        ]

        settings = {}
        for setting_key in autorespond_types:
            settings[setting_key] = await self.get_setting_value(db, setting_key, default=True)

        return settings

    async def is_autorespond_enabled(
        self,
        db: AsyncSession,
        autorespond_type: str
    ) -> bool:
        """
        Check if a specific autorespond type is enabled.

        Args:
            db: Database session
            autorespond_type: The autorespond type key (e.g., "autorespond_apt_status_req")

        Returns:
            True if enabled, False otherwise (defaults to True if not set)
        """
        enabled = await self.get_setting_value(
            db,
            autorespond_type,
            default=True
        )
        return enabled

    async def toggle_autorespond(
        self,
        db: AsyncSession,
        autorespond_type: str,
        enable: bool,
        updated_by: Optional[str] = None,
        expected_updated_at: Optional[datetime] = None
    ) -> SystemSetting:
        """
        Toggle a specific autorespond type.

        Args:
            db: Database session
            autorespond_type: The autorespond type key
            enable: True to enable, False to disable
            updated_by: Optional identifier of who made the change
            expected_updated_at: Optional timestamp for optimistic concurrency control

        Returns:
            The updated SystemSetting object
        """
        # Map of autorespond types to human-readable descriptions
        descriptions = {
            "autorespond_appointment_inquiry": "Enable/disable automatic responses to appointment inquiry emails",
            "autorespond_apt_status_req": "Enable/disable automatic responses to appointment status request emails (Apt status req tag)",
            "autorespond_medical_records": "Enable/disable automatic responses to medical records requests (Release of Records, Image Request, CD Requests, Reports Request)",
            "autorespond_bill_balance_request": "Enable/disable automatic responses to bill or balance request emails",
            "autorespond_case_updates": "Enable/disable automatic responses to case update emails (Drop Pending, Promise to send payment, etc.)",
            "autorespond_missing_lien_request": "Enable/disable automatic responses to missing lien request emails",
            "autorespond_psl_lien": "Enable/disable automatic responses to Patient Signed Lien (PSL) emails",
            "autorespond_asl_lien": "Enable/disable automatic responses to Attorney Signed Lien (ASL) emails"
        }

        description = descriptions.get(autorespond_type, f"Enable/disable {autorespond_type}")

        # Use FOR UPDATE lock
        setting = await self._get_by_key_for_update(db, autorespond_type)

        if setting:
            # Check optimistic concurrency
            if expected_updated_at is not None and setting.updated_at is not None:
                if setting.updated_at != expected_updated_at:
                    raise StaleUpdateError(
                        setting_key=autorespond_type,
                        current_updated_at=setting.updated_at,
                        expected_updated_at=expected_updated_at,
                        updated_by=setting.updated_by,
                    )

            # Update existing setting
            setting.setting_value = enable
            setting.updated_at = datetime.utcnow()
            setting.updated_by = updated_by
            logger.info(
                f"Updated setting '{autorespond_type}' to {enable} "
                f"(by: {updated_by or 'unknown'})"
            )
        else:
            # Create new setting
            setting = SystemSetting(
                setting_key=autorespond_type,
                setting_value=enable,
                description=description,
                updated_by=updated_by
            )
            db.add(setting)
            logger.info(
                f"Created new setting '{autorespond_type}' with value {enable} "
                f"(by: {updated_by or 'unknown'})"
            )

        await db.commit()
        await db.refresh(setting)
        return setting


# Create singleton instance
system_settings_crud = CRUDSystemSettings()
