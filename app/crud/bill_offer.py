"""CRUD helpers for Bill Offer intake."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
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

MESSAGE_SEARCH_SNIPPET_CHARS = 4000
CONVERSATION_SEARCH_TEXT_CHARS = 30000


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


async def _build_tagged_email_rows(
    db: AsyncSession,
    page: List[Email],
) -> List[Dict[str, Any]]:
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

    search_text_by_conversation = await _build_conversation_search_text(
        db,
        conversation_ids,
    )

    return [
        {
            "email": email,
            "intake": intakes_by_conversation.get(email.front_conversation_id),
            "search_text": search_text_by_conversation.get(email.front_conversation_id, ""),
        }
        for email in page
    ]


async def _build_conversation_search_text(
    db: AsyncSession,
    conversation_ids: List[str],
) -> Dict[str, str]:
    if not conversation_ids:
        return {}

    result = await db.execute(
        select(
            Email.front_conversation_id,
            Email.subject,
            Email.sender,
            func.substr(Email.content_text, 1, MESSAGE_SEARCH_SNIPPET_CHARS).label(
                "content_text"
            ),
        ).where(Email.front_conversation_id.in_(conversation_ids))
    )

    search_text_by_conversation: Dict[str, str] = {}
    for row in result.all():
        current = search_text_by_conversation.get(row.front_conversation_id, "")
        if len(current) >= CONVERSATION_SEARCH_TEXT_CHARS:
            continue

        snippet = "\n".join(
            str(value or "")
            for value in (
                row.front_conversation_id,
                row.subject,
                row.sender,
                row.content_text,
            )
        )
        next_value = f"{current}\n{snippet}" if current else snippet
        search_text_by_conversation[row.front_conversation_id] = next_value[
            :CONVERSATION_SEARCH_TEXT_CHARS
        ]

    return search_text_by_conversation


async def list_tagged_bill_offer_emails(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """List latest email per Bill Offer conversation, most recent first."""

    search_term = (search or "").strip()
    base_conditions = [Tag.name == "Bill Offer"]
    if search_term:
        pattern = f"%{search_term}%"
        if search_term.lower().startswith("cnv_"):
            base_conditions.append(Email.front_conversation_id.ilike(pattern))
        else:
            base_conditions.append(
                or_(
                    Email.front_conversation_id.ilike(pattern),
                    Email.subject.ilike(pattern),
                    Email.sender.ilike(pattern),
                    Email.content_text.ilike(pattern),
                )
            )

    status_term = (status or "").strip()
    if status_term == "processed":
        base_conditions.append(BillOfferIntake.id.isnot(None))
    elif status_term == "unprocessed":
        base_conditions.append(BillOfferIntake.id.is_(None))
    elif status_term:
        base_conditions.append(BillOfferIntake.status == status_term)

    result = await db.execute(
        select(Email)
        .join(Email.tags)
        .outerjoin(
            BillOfferIntake,
            BillOfferIntake.front_conversation_id == Email.front_conversation_id,
        )
        .where(*base_conditions)
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
        .outerjoin(
            BillOfferIntake,
            BillOfferIntake.front_conversation_id == Email.front_conversation_id,
        )
        .where(*base_conditions)
    )
    total = total_result.scalar() or 0

    page = deduped[skip : skip + limit]
    return await _build_tagged_email_rows(db, page), total


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
