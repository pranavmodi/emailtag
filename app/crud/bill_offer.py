"""CRUD helpers for Bill Offer intake."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill_offer import (
    BillOfferAgentLog,
    BillOfferCorrectionAudit,
    BillOfferIntake,
)
from app.models.email import Email, Tag
from app.schemas.bill_offer import (
    BillOfferAgentLogCreate,
    BillOfferIntakeCreate,
    BillOfferIntakeUpdate,
)


async def get_intake(db: AsyncSession, intake_id: UUID) -> Optional[BillOfferIntake]:
    result = await db.execute(select(BillOfferIntake).where(BillOfferIntake.id == intake_id))
    return result.scalar_one_or_none()


async def get_intake_by_conversation(
    db: AsyncSession, front_conversation_id: str
) -> Optional[BillOfferIntake]:
    result = await db.execute(
        select(BillOfferIntake).where(
            BillOfferIntake.front_conversation_id == front_conversation_id
        )
    )
    return result.scalar_one_or_none()


async def list_intakes(
    db: AsyncSession,
    *,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[List[BillOfferIntake], int]:
    filters = []
    if status:
        filters.append(BillOfferIntake.status == status)

    count_stmt = select(func.count(BillOfferIntake.id))
    stmt = select(BillOfferIntake)
    if filters:
        count_stmt = count_stmt.where(*filters)
        stmt = stmt.where(*filters)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    result = await db.execute(
        stmt.order_by(BillOfferIntake.updated_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all()), total


async def create_intake(
    db: AsyncSession, *, obj_in: BillOfferIntakeCreate
) -> BillOfferIntake:
    db_obj = BillOfferIntake(**obj_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def upsert_intake_for_conversation(
    db: AsyncSession,
    *,
    front_conversation_id: str,
    values: Dict[str, Any],
) -> BillOfferIntake:
    intake = await get_intake_by_conversation(db, front_conversation_id)
    if intake:
        for field, value in values.items():
            if hasattr(intake, field):
                setattr(intake, field, value)
        intake.updated_at = datetime.utcnow()
        db.add(intake)
    else:
        intake = BillOfferIntake(
            front_conversation_id=front_conversation_id,
            **{k: v for k, v in values.items() if hasattr(BillOfferIntake, k)},
        )
        db.add(intake)
    await db.commit()
    await db.refresh(intake)
    return intake


async def update_intake(
    db: AsyncSession,
    *,
    intake: BillOfferIntake,
    obj_in: BillOfferIntakeUpdate | Dict[str, Any],
) -> BillOfferIntake:
    update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(intake, field):
            setattr(intake, field, value)
    intake.updated_at = datetime.utcnow()
    db.add(intake)
    await db.commit()
    await db.refresh(intake)
    return intake


async def create_log(
    db: AsyncSession, *, obj_in: BillOfferAgentLogCreate
) -> BillOfferAgentLog:
    db_obj = BillOfferAgentLog(**obj_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def list_logs_for_conversation(
    db: AsyncSession,
    *,
    front_conversation_id: str,
    skip: int = 0,
    limit: int = 300,
) -> Tuple[List[BillOfferAgentLog], int]:
    total_result = await db.execute(
        select(func.count(BillOfferAgentLog.id)).where(
            BillOfferAgentLog.front_conversation_id == front_conversation_id
        )
    )
    total = total_result.scalar() or 0
    result = await db.execute(
        select(BillOfferAgentLog)
        .where(BillOfferAgentLog.front_conversation_id == front_conversation_id)
        .order_by(BillOfferAgentLog.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def create_correction_audit(
    db: AsyncSession,
    *,
    front_conversation_id: str,
    intake_id: UUID,
    field_name: str,
    previous_value: Any,
    new_value: Any,
    changed_by: Optional[str],
) -> BillOfferCorrectionAudit:
    db_obj = BillOfferCorrectionAudit(
        front_conversation_id=front_conversation_id,
        intake_id=intake_id,
        field_name=field_name,
        previous_value={"value": previous_value},
        new_value={"value": new_value},
        changed_by=changed_by,
    )
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


async def list_correction_audits_for_conversation(
    db: AsyncSession,
    *,
    front_conversation_id: str,
    skip: int = 0,
    limit: int = 200,
) -> Tuple[List[BillOfferCorrectionAudit], int]:
    total_result = await db.execute(
        select(func.count(BillOfferCorrectionAudit.id)).where(
            BillOfferCorrectionAudit.front_conversation_id == front_conversation_id
        )
    )
    total = total_result.scalar() or 0
    result = await db.execute(
        select(BillOfferCorrectionAudit)
        .where(BillOfferCorrectionAudit.front_conversation_id == front_conversation_id)
        .order_by(BillOfferCorrectionAudit.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all()), total


async def list_tagged_bill_offer_emails(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 100,
) -> Tuple[List[Dict[str, Any]], int]:
    """List latest email per Bill Offer conversation, most recent first."""

    result = await db.execute(
        select(Email)
        .join(Email.tags)
        .where(Tag.name == "Bill Offer")
        .order_by(Email.created_at.desc())
        .limit(max(limit + skip, limit))
    )
    emails = list(result.scalars().unique().all())

    deduped: List[Email] = []
    seen = set()
    for email in emails:
        if email.front_conversation_id in seen:
            continue
        seen.add(email.front_conversation_id)
        deduped.append(email)

    total_result = await db.execute(
        select(func.count(func.distinct(Email.front_conversation_id)))
        .select_from(Email)
        .join(Email.tags)
        .where(Tag.name == "Bill Offer")
    )
    total = total_result.scalar() or 0

    page = deduped[skip : skip + limit]
    conversation_ids = [email.front_conversation_id for email in page]
    intakes_by_conversation: Dict[str, BillOfferIntake] = {}
    if conversation_ids:
        intake_result = await db.execute(
            select(BillOfferIntake).where(
                BillOfferIntake.front_conversation_id.in_(conversation_ids)
            )
        )
        intakes_by_conversation = {
            intake.front_conversation_id: intake for intake in intake_result.scalars().all()
        }

    items = []
    for email in page:
        items.append(
            {
                "email": email,
                "intake": intakes_by_conversation.get(email.front_conversation_id),
            }
        )
    return items, total


async def get_latest_bill_offer_email_for_conversation(
    db: AsyncSession, *, front_conversation_id: str
) -> Optional[Email]:
    result = await db.execute(
        select(Email)
        .join(Email.tags)
        .where(Email.front_conversation_id == front_conversation_id)
        .where(Tag.name == "Bill Offer")
        .order_by(Email.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
