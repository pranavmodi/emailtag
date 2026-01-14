"""CRUD operations for template attachments."""

import os
import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.template_attachment import TemplateAttachment


# Default storage directory for attachments (default to project data folder)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ATTACHMENTS_STORAGE_DIR = os.environ.get(
    "TEMPLATE_ATTACHMENTS_DIR",
    os.path.join(_PROJECT_ROOT, "data", "template_attachments")
)


class TemplateAttachmentCRUD:
    """CRUD operations for TemplateAttachment model."""

    def __init__(self, storage_dir: str = ATTACHMENTS_STORAGE_DIR):
        self.storage_dir = storage_dir

    def _ensure_storage_dir(self) -> None:
        """Ensure the storage directory exists."""
        os.makedirs(self.storage_dir, exist_ok=True)

    def _get_file_path(self, attachment_id: uuid.UUID, filename: str) -> str:
        """Generate the file path for an attachment."""
        # Use attachment ID as directory to avoid filename collisions
        ext = os.path.splitext(filename)[1]
        return os.path.join(self.storage_dir, f"{attachment_id}{ext}")

    async def get_by_id(
        self, db: AsyncSession, attachment_id: uuid.UUID
    ) -> Optional[TemplateAttachment]:
        """
        Get an attachment by its ID.

        Args:
            db: Database session
            attachment_id: The attachment UUID

        Returns:
            TemplateAttachment if found, None otherwise
        """
        result = await db.execute(
            select(TemplateAttachment).where(TemplateAttachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tag_name(
        self, db: AsyncSession, tag_name: str
    ) -> List[TemplateAttachment]:
        """
        Get all attachments for a specific tag.

        Args:
            db: Database session
            tag_name: The tag name to search for

        Returns:
            List of TemplateAttachment objects
        """
        result = await db.execute(
            select(TemplateAttachment)
            .where(TemplateAttachment.tag_name == tag_name)
            .order_by(TemplateAttachment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_tag_and_template(
        self, db: AsyncSession, tag_name: str, template_key: Optional[str] = None
    ) -> List[TemplateAttachment]:
        """
        Get attachments for a specific tag and optionally a specific template.

        Args:
            db: Database session
            tag_name: The tag name
            template_key: Optional template key to filter by

        Returns:
            List of TemplateAttachment objects
        """
        query = select(TemplateAttachment).where(
            TemplateAttachment.tag_name == tag_name
        )
        if template_key is not None:
            query = query.where(TemplateAttachment.template_key == template_key)

        query = query.order_by(TemplateAttachment.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_all(self, db: AsyncSession) -> List[TemplateAttachment]:
        """
        Get all attachments.

        Args:
            db: Database session

        Returns:
            List of all TemplateAttachment objects
        """
        result = await db.execute(
            select(TemplateAttachment).order_by(TemplateAttachment.created_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        db: AsyncSession,
        tag_name: str,
        filename: str,
        file_content: bytes,
        mime_type: str,
        template_key: Optional[str] = None,
        description: Optional[str] = None,
        uploaded_by: Optional[str] = None
    ) -> TemplateAttachment:
        """
        Create a new attachment and save the file.

        Args:
            db: Database session
            tag_name: The tag name this attachment belongs to
            filename: Original filename
            file_content: Binary content of the file
            mime_type: MIME type of the file
            template_key: Optional specific template key
            description: Optional description
            uploaded_by: User who uploaded

        Returns:
            Created TemplateAttachment object
        """
        self._ensure_storage_dir()

        # Generate ID and file path
        attachment_id = uuid.uuid4()
        file_path = self._get_file_path(attachment_id, filename)

        # Save file to disk
        with open(file_path, 'wb') as f:
            f.write(file_content)

        # Create database record
        attachment = TemplateAttachment(
            id=attachment_id,
            tag_name=tag_name,
            template_key=template_key,
            filename=filename,
            file_path=file_path,
            mime_type=mime_type,
            file_size=len(file_content),
            description=description,
            uploaded_by=uploaded_by
        )

        db.add(attachment)
        await db.commit()
        await db.refresh(attachment)
        return attachment

    async def delete(
        self, db: AsyncSession, attachment_id: uuid.UUID
    ) -> bool:
        """
        Delete an attachment and its file.

        Args:
            db: Database session
            attachment_id: The attachment UUID

        Returns:
            True if deleted, False if not found
        """
        attachment = await self.get_by_id(db, attachment_id)
        if not attachment:
            return False

        # Delete the file from disk
        if os.path.exists(attachment.file_path):
            os.remove(attachment.file_path)

        # Delete database record
        await db.delete(attachment)
        await db.commit()
        return True

    async def delete_by_tag_name(
        self, db: AsyncSession, tag_name: str
    ) -> int:
        """
        Delete all attachments for a tag.

        Args:
            db: Database session
            tag_name: The tag name

        Returns:
            Number of attachments deleted
        """
        attachments = await self.get_by_tag_name(db, tag_name)

        # Delete files from disk
        for attachment in attachments:
            if os.path.exists(attachment.file_path):
                os.remove(attachment.file_path)

        # Delete database records
        result = await db.execute(
            delete(TemplateAttachment).where(
                TemplateAttachment.tag_name == tag_name
            )
        )
        await db.commit()
        return result.rowcount

    def get_file_content(self, attachment: TemplateAttachment) -> Optional[bytes]:
        """
        Get the file content for an attachment.

        Args:
            attachment: The TemplateAttachment object

        Returns:
            File content as bytes, or None if file not found
        """
        if not os.path.exists(attachment.file_path):
            return None

        with open(attachment.file_path, 'rb') as f:
            return f.read()


# Global instance
template_attachment_crud = TemplateAttachmentCRUD()
