"""Helpers for deriving firm contact dates from linked email conversations."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.email import Email
from app.models.pif_info import PifInfo


INTERNAL_SENDER_PATTERNS = (
    "%@precisemri.com%",
    "%@mediflow360.com%",
    "%@radflow360.com%",
)


def refresh_first_contacted_precise_at_sync(db: Session, firm: PifInfo) -> Optional[datetime]:
    """Set a firm's first external email timestamp from its linked conversations."""
    first_contacted_at = first_external_email_at_sync(db, firm.conversation_ids or [])
    firm.first_contacted_precise_at = first_contacted_at
    return first_contacted_at


async def refresh_first_contacted_precise_at(
    db: AsyncSession,
    firm: PifInfo,
) -> Optional[datetime]:
    """Async variant of refresh_first_contacted_precise_at_sync."""
    first_contacted_at = await first_external_email_at(db, firm.conversation_ids or [])
    firm.first_contacted_precise_at = first_contacted_at
    db.add(firm)
    await db.commit()
    await db.refresh(firm)
    return first_contacted_at


def first_external_email_at_sync(
    db: Session,
    conversation_ids: Iterable[str],
) -> Optional[datetime]:
    """Return the earliest email timestamp from a non-internal sender."""
    ids = _clean_conversation_ids(conversation_ids)
    if not ids:
        return None

    return db.execute(_first_external_email_stmt(ids)).scalar_one_or_none()


async def first_external_email_at(
    db: AsyncSession,
    conversation_ids: Iterable[str],
) -> Optional[datetime]:
    """Async variant of first_external_email_at_sync."""
    ids = _clean_conversation_ids(conversation_ids)
    if not ids:
        return None

    result = await db.execute(_first_external_email_stmt(ids))
    return result.scalar_one_or_none()


def _first_external_email_stmt(conversation_ids: list[str]):
    sender = func.lower(Email.sender)
    stmt = (
        select(func.min(Email.created_at))
        .where(Email.front_conversation_id.in_(conversation_ids))
        .where(Email.sender.is_not(None))
    )
    for pattern in INTERNAL_SENDER_PATTERNS:
        stmt = stmt.where(sender.not_like(pattern))
    return stmt


def _clean_conversation_ids(conversation_ids: Iterable[str]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for value in conversation_ids or []:
        if not value:
            continue
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            ids.append(normalized)
            seen.add(normalized)
    return ids
