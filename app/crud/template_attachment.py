"""CRUD operations for template attachments."""

import uuid
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.template_attachment import TemplateAttachment


class TemplateAttachmentCRUD:
    """CRUD operations for TemplateAttachment model."""

    async def get_by_id(
        self, db: AsyncSession, attachment_id: uuid.UUID
    ) -> Optional[TemplateAttachment]:
        result = await db.execute(
            select(TemplateAttachment).where(TemplateAttachment.id == attachment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tag_name(
        self, db: AsyncSession, tag_name: str
    ) -> List[TemplateAttachment]:
        result = await db.execute(
            select(TemplateAttachment)
            .where(TemplateAttachment.tag_name == tag_name)
            .order_by(TemplateAttachment.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_tag_and_template(
        self, db: AsyncSession, tag_name: str, template_key: Optional[str] = None
    ) -> List[TemplateAttachment]:
        query = select(TemplateAttachment).where(
            TemplateAttachment.tag_name == tag_name
        )
        if template_key is not None:
            query = query.where(TemplateAttachment.template_key == template_key)

        query = query.order_by(TemplateAttachment.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_all(self, db: AsyncSession) -> List[TemplateAttachment]:
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
        attachment_id = uuid.uuid4()

        attachment = TemplateAttachment(
            id=attachment_id,
            tag_name=tag_name,
            template_key=template_key,
            filename=filename,
            file_content=file_content,
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
        attachment = await self.get_by_id(db, attachment_id)
        if not attachment:
            return False

        await db.delete(attachment)
        await db.commit()
        return True

    async def delete_by_tag_name(
        self, db: AsyncSession, tag_name: str
    ) -> int:
        result = await db.execute(
            delete(TemplateAttachment).where(
                TemplateAttachment.tag_name == tag_name
            )
        )
        await db.commit()
        return result.rowcount


# Global instance
template_attachment_crud = TemplateAttachmentCRUD()
