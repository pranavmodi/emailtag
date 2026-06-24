"""CRUD operations for firm aliases."""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.firm_alias import FirmAlias
from app.schemas.firm_alias import FirmAliasCreate, FirmAliasUpdate


class CRUDFirmAlias(CRUDBase[FirmAlias, FirmAliasCreate, FirmAliasUpdate]):
    """Minimal CRUD for the firm_alias identity table."""

    async def get_by_alias(
        self, db: AsyncSession, *, alias_type: str, alias_value: str
    ) -> Optional[FirmAlias]:
        result = await db.execute(
            select(FirmAlias).where(
                FirmAlias.alias_type == alias_type,
                FirmAlias.alias_value == alias_value.lower(),
            )
        )
        return result.scalars().first()

    async def list_by_firm(self, db: AsyncSession, *, firm_id: UUID) -> list[FirmAlias]:
        result = await db.execute(select(FirmAlias).where(FirmAlias.firm_id == firm_id))
        return result.scalars().all()

    async def upsert_alias(
        self,
        db: AsyncSession,
        *,
        alias_type: str,
        alias_value: str,
        firm_id: UUID,
        confidence: float,
        source: str,
    ) -> FirmAlias:
        normalized = alias_value.lower()
        existing = await self.get_by_alias(db, alias_type=alias_type, alias_value=normalized)
        if existing:
            existing.firm_id = firm_id
            existing.confidence = confidence
            existing.source = source
            db.add(existing)
            await db.commit()
            await db.refresh(existing)
            return existing

        alias = FirmAlias(
            alias_type=alias_type,
            alias_value=normalized,
            firm_id=firm_id,
            confidence=confidence,
            source=source,
        )
        db.add(alias)
        await db.commit()
        await db.refresh(alias)
        return alias


firm_alias = CRUDFirmAlias(FirmAlias)
