"""CRUD operations for message templates."""
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.message_template import MessageTemplate
from app.core.exceptions import StaleUpdateError
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class CRUDMessageTemplate:
    """CRUD operations for message templates."""

    async def get_by_key(
        self,
        db: AsyncSession,
        template_key: str
    ) -> Optional[MessageTemplate]:
        """
        Get a template by its key.

        Args:
            db: Database session
            template_key: The unique template key

        Returns:
            MessageTemplate if found, None otherwise
        """
        result = await db.execute(
            select(MessageTemplate).filter(MessageTemplate.template_key == template_key)
        )
        return result.scalars().first()

    async def _get_by_key_for_update(
        self,
        db: AsyncSession,
        template_key: str
    ) -> Optional[MessageTemplate]:
        """Get a template by its key with a row-level lock (SELECT FOR UPDATE)."""
        result = await db.execute(
            select(MessageTemplate)
            .filter(MessageTemplate.template_key == template_key)
            .with_for_update()
        )
        return result.scalars().first()

    async def get_template_body(
        self,
        db: AsyncSession,
        template_key: str,
        default: Optional[str] = None
    ) -> Optional[str]:
        """
        Get just the template body content for a given key.

        Args:
            db: Database session
            template_key: The unique template key
            default: Default value if template not found

        Returns:
            Template body string or default
        """
        template = await self.get_by_key(db, template_key)
        if template:
            return template.template_body
        return default

    async def list_all(self, db: AsyncSession) -> List[MessageTemplate]:
        """
        Get all templates.

        Args:
            db: Database session

        Returns:
            List of all MessageTemplate objects
        """
        result = await db.execute(select(MessageTemplate))
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        template_key: str,
        template_name: str,
        template_body: str,
        description: Optional[str] = None,
        updated_by: Optional[str] = None
    ) -> MessageTemplate:
        """
        Create a new template.

        Args:
            db: Database session
            template_key: Unique key for the template
            template_name: Human-readable name
            template_body: Template content with placeholders
            description: Optional description
            updated_by: Who created the template

        Returns:
            The created MessageTemplate object
        """
        template = MessageTemplate(
            template_key=template_key,
            template_name=template_name,
            template_body=template_body,
            description=description,
            updated_by=updated_by
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)
        logger.info(f"Created template '{template_key}' by {updated_by or 'unknown'}")
        return template

    async def update(
        self,
        db: AsyncSession,
        template_key: str,
        template_body: str,
        template_name: Optional[str] = None,
        description: Optional[str] = None,
        updated_by: Optional[str] = None,
        expected_updated_at: Optional[datetime] = None
    ) -> Optional[MessageTemplate]:
        """
        Update an existing template with optimistic concurrency control.

        Args:
            db: Database session
            template_key: Unique key for the template
            template_body: New template content
            template_name: Optional new name
            description: Optional new description
            updated_by: Who updated the template
            expected_updated_at: If provided, rejects the update if the record
                has been modified since this timestamp.

        Returns:
            Updated MessageTemplate object or None if not found

        Raises:
            StaleUpdateError: If expected_updated_at doesn't match
        """
        # Use FOR UPDATE lock
        template = await self._get_by_key_for_update(db, template_key)
        if not template:
            logger.warning(f"Template '{template_key}' not found for update")
            return None

        # Check optimistic concurrency
        if expected_updated_at is not None and template.updated_at is not None:
            if template.updated_at != expected_updated_at:
                raise StaleUpdateError(
                    setting_key=template_key,
                    current_updated_at=template.updated_at,
                    expected_updated_at=expected_updated_at,
                    updated_by=template.updated_by,
                )

        template.template_body = template_body
        if template_name:
            template.template_name = template_name
        if description is not None:
            template.description = description
        template.updated_by = updated_by
        template.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(template)
        logger.info(f"Updated template '{template_key}' by {updated_by or 'unknown'}")
        return template

    async def create_or_update(
        self,
        db: AsyncSession,
        template_key: str,
        template_name: str,
        template_body: str,
        description: Optional[str] = None,
        updated_by: Optional[str] = None
    ) -> MessageTemplate:
        """
        Create a new template or update if it already exists.

        Args:
            db: Database session
            template_key: Unique key for the template
            template_name: Human-readable name
            template_body: Template content
            description: Optional description
            updated_by: Who created/updated the template

        Returns:
            The created or updated MessageTemplate object
        """
        existing = await self.get_by_key(db, template_key)
        if existing:
            return await self.update(
                db, template_key, template_body, template_name, description, updated_by
            )
        else:
            return await self.create(
                db, template_key, template_name, template_body, description, updated_by
            )


# Create singleton instance
message_template_crud = CRUDMessageTemplate()
