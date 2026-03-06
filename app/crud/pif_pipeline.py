"""CRUD operations for PIF outreach pipeline."""

import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pif_pipeline import PifOutreachPipeline
from app.schemas.pif_pipeline import PipelineRecordCreate, PipelineRecordUpdate

logger = logging.getLogger(__name__)


class CRUDPifPipeline:
    """CRUD operations for PIF outreach pipeline records."""

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: PipelineRecordCreate,
    ) -> PifOutreachPipeline:
        """Create a new pipeline record."""
        now = datetime.utcnow()
        record = PifOutreachPipeline(
            id=uuid4(),
            pif_id=obj_in.pif_id,
            contact_name=obj_in.contact_name,
            contact_linkedin=obj_in.contact_linkedin,
            contact_email=obj_in.contact_email,
            outreach_type=obj_in.outreach_type,
            sender_persona=obj_in.sender_persona,
            status=obj_in.status,
            message_variant=obj_in.message_variant,
            sent_at=obj_in.sent_at,
            replied_at=obj_in.replied_at,
            notes=obj_in.notes,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        logger.info(f"Created pipeline record {record.id} for firm {record.pif_id}")
        return record

    async def get(self, db: AsyncSession, record_id: UUID) -> Optional[PifOutreachPipeline]:
        """Get a single pipeline record by ID."""
        result = await db.execute(
            select(PifOutreachPipeline).where(PifOutreachPipeline.id == record_id)
        )
        return result.scalars().first()

    async def list_by_pif(
        self,
        db: AsyncSession,
        pif_id: UUID,
    ) -> List[PifOutreachPipeline]:
        """Get all pipeline records for a firm, sorted by created_at."""
        result = await db.execute(
            select(PifOutreachPipeline)
            .where(PifOutreachPipeline.pif_id == pif_id)
            .order_by(PifOutreachPipeline.created_at.asc())
        )
        return result.scalars().all()

    async def update(
        self,
        db: AsyncSession,
        *,
        db_obj: PifOutreachPipeline,
        obj_in: PipelineRecordUpdate,
    ) -> PifOutreachPipeline:
        """Update a pipeline record."""
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db_obj.updated_at = datetime.utcnow()
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, record_id: UUID) -> bool:
        """Delete a pipeline record. Returns True if deleted."""
        record = await self.get(db, record_id)
        if not record:
            return False
        await db.delete(record)
        await db.commit()
        return True

    async def get_status_counts(self, db: AsyncSession) -> dict:
        """Get count of records by status for the pipeline funnel."""
        from sqlalchemy import func
        result = await db.execute(
            select(PifOutreachPipeline.status, func.count(PifOutreachPipeline.id))
            .group_by(PifOutreachPipeline.status)
        )
        return {row[0]: row[1] for row in result.fetchall()}


pif_pipeline = CRUDPifPipeline()
