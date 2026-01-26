"""Sync CRUD operations for PIF (Personal Injury Firm) information."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pif_info import PifInfo

logger = logging.getLogger(__name__)


class CRUDPifInfoSync:
    """Sync CRUD operations for PIF info (for Celery tasks)."""

    def get(self, db: Session, id: UUID) -> Optional[PifInfo]:
        """Get PIF info by ID."""
        result = db.execute(select(PifInfo).filter(PifInfo.id == id))
        return result.scalars().first()

    def update(
        self,
        db: Session,
        *,
        db_obj: PifInfo,
        obj_in: Dict[str, Any]
    ) -> PifInfo:
        """Update PIF info with dict data."""
        for field, value in obj_in.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        db_obj.updated_at = datetime.utcnow()
        db.add(db_obj)
        return db_obj


pif_info = CRUDPifInfoSync()
