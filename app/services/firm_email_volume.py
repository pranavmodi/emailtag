"""Firm monthly email volume aggregation helpers."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Iterable

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.email import Email
from app.models.firm_email_volume import FirmEmailMonthlyVolume
from app.models.pif_info import PifInfo


def extract_front_message_datetime(email: Email) -> datetime:
    """Prefer Front's message timestamp; fall back to the local DB insert timestamp."""
    raw_data = email.raw_data or {}
    front_created_at: Any = None
    if isinstance(raw_data, dict):
        target = raw_data.get("target")
        if isinstance(target, dict):
            data = target.get("data")
            if isinstance(data, dict):
                front_created_at = data.get("created_at")

    if front_created_at is not None:
        try:
            return datetime.utcfromtimestamp(float(front_created_at))
        except (TypeError, ValueError, OSError, OverflowError):
            pass

    return email.created_at or datetime.utcnow()


def month_start(value: datetime) -> date:
    """Return the first day of the UTC calendar month for a timestamp."""
    return date(value.year, value.month, 1)


def trailing_month_starts(months: int = 12, *, now: datetime | None = None) -> list[date]:
    """Return calendar month starts oldest first, including the current month."""
    if months <= 0:
        return []

    anchor = now or datetime.utcnow()
    year = anchor.year
    month = anchor.month - (months - 1)
    while month <= 0:
        month += 12
        year -= 1

    starts: list[date] = []
    for _ in range(months):
        starts.append(date(year, month, 1))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return starts


def format_volume_points(
    rows: Iterable[FirmEmailMonthlyVolume],
    *,
    months: int = 12,
) -> list[dict[str, int | str]]:
    """Convert sparse summary rows into a dense oldest-first monthly series."""
    month_starts = trailing_month_starts(months)
    counts = {row.month: int(row.email_count or 0) for row in rows}
    return [
        {"month": value.strftime("%Y-%m"), "count": counts.get(value, 0)}
        for value in month_starts
    ]


async def get_monthly_email_volume_for_firms(
    db: AsyncSession,
    firm_ids: Iterable[uuid.UUID],
    *,
    months: int = 12,
) -> dict[str, list[dict[str, int | str]]]:
    """Return dense monthly volume series for a batch of firm ids."""
    ids = list(dict.fromkeys(firm_ids))
    if not ids:
        return {}

    month_starts = trailing_month_starts(months)
    if not month_starts:
        return {str(firm_id): [] for firm_id in ids}

    result = await db.execute(
        select(FirmEmailMonthlyVolume)
        .where(
            FirmEmailMonthlyVolume.firm_id.in_(ids),
            FirmEmailMonthlyVolume.month >= month_starts[0],
        )
        .order_by(FirmEmailMonthlyVolume.firm_id, FirmEmailMonthlyVolume.month)
    )
    rows_by_firm: dict[uuid.UUID, list[FirmEmailMonthlyVolume]] = {firm_id: [] for firm_id in ids}
    for row in result.scalars().all():
        rows_by_firm.setdefault(row.firm_id, []).append(row)

    return {
        str(firm_id): format_volume_points(rows, months=months)
        for firm_id, rows in rows_by_firm.items()
    }


async def increment_email_monthly_volume_for_email(db: AsyncSession, email: Email) -> None:
    """Increment cached monthly volume for firms already linked to an email conversation."""
    if not email.front_conversation_id:
        return

    result = await db.execute(
        select(PifInfo.id).where(PifInfo.conversation_ids.any(email.front_conversation_id))
    )
    firm_ids = [row[0] for row in result.all()]
    if not firm_ids:
        return

    target_month = month_start(extract_front_message_datetime(email))
    now = datetime.utcnow()
    values = [
        {
            "id": uuid.uuid4(),
            "firm_id": firm_id,
            "month": target_month,
            "email_count": 1,
            "created_at": now,
            "updated_at": now,
        }
        for firm_id in firm_ids
    ]
    stmt = insert(FirmEmailMonthlyVolume).values(values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_firm_email_monthly_volume_firm_month",
        set_={
            "email_count": FirmEmailMonthlyVolume.email_count + stmt.excluded.email_count,
            "updated_at": now,
        },
    )
    await db.execute(stmt)


async def refresh_firm_email_monthly_volume(
    db: AsyncSession,
    firm_id: uuid.UUID,
) -> None:
    """Rebuild cached monthly volume for one firm from stored email rows."""
    await db.execute(
        delete(FirmEmailMonthlyVolume).where(FirmEmailMonthlyVolume.firm_id == firm_id)
    )
    rows = (
        await db.execute(
            text(_REFRESH_SQL),
            {"firm_id": str(firm_id)},
        )
    ).mappings().all()
    if not rows:
        return

    now = datetime.utcnow()
    await db.execute(
        insert(FirmEmailMonthlyVolume).values(
            [
                {
                    "id": uuid.uuid4(),
                    "firm_id": firm_id,
                    "month": row["month"],
                    "email_count": row["email_count"],
                    "created_at": now,
                    "updated_at": now,
                }
                for row in rows
            ]
        )
    )


def refresh_firm_email_monthly_volume_sync(db: Session, firm_id: uuid.UUID) -> None:
    """Sync rebuild of cached monthly volume for one firm."""
    db.query(FirmEmailMonthlyVolume).filter(FirmEmailMonthlyVolume.firm_id == firm_id).delete()
    rows = db.execute(text(_REFRESH_SQL), {"firm_id": str(firm_id)}).mappings().all()
    if not rows:
        return

    now = datetime.utcnow()
    for row in rows:
        db.add(
            FirmEmailMonthlyVolume(
                firm_id=firm_id,
                month=row["month"],
                email_count=row["email_count"],
                created_at=now,
                updated_at=now,
            )
        )


_REFRESH_SQL = """
SELECT
    date_trunc(
        'month',
        COALESCE(
            CASE
                WHEN e.raw_data #>> '{target,data,created_at}' ~ '^[0-9]+(\\.[0-9]+)?$'
                THEN to_timestamp(
                    (e.raw_data #>> '{target,data,created_at}')::double precision
                ) AT TIME ZONE 'UTC'
                ELSE NULL
            END,
            e.created_at
        )
    )::date AS month,
    count(*) AS email_count
FROM pif_info p
JOIN LATERAL unnest(p.conversation_ids) AS cid(conversation_id) ON TRUE
JOIN email e ON e.front_conversation_id = cid.conversation_id
WHERE p.id = :firm_id
  AND p.conversation_ids IS NOT NULL
  AND cardinality(p.conversation_ids) > 0
GROUP BY month
"""
