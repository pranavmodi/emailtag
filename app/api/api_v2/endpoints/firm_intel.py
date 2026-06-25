"""Read-only v2 firm intelligence contract endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.autorespond_event import AutorespondEvent
from app.models.email import Email
from app.models.firm_alias import FirmAlias
from app.models.pif_info import PifInfo
from app.schemas.firm_intel import (
    FirmDeltaResponse,
    FirmIntelHealthResponse,
    FirmPeopleResponse,
    FirmProfile,
    FirmResolveResponse,
)
from app.services.firm_identity import canonical_domain
from app.services.firm_intel import build_firm_profile


async def require_pifstats_token(
    authorization: Optional[str] = Header(None),
    x_pifstats_auth_token: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
) -> None:
    configured = settings.PIFSTATS_AUTH_TOKEN
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PIFStats auth token is not configured",
        )

    presented = x_pifstats_auth_token or x_api_key
    if not presented and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value:
            presented = value
        else:
            presented = authorization

    if presented != configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIFStats auth token",
        )


router = APIRouter(dependencies=[Depends(require_pifstats_token)])


@router.get("/firms", response_model=FirmDeltaResponse)
async def list_firms(
    updated_since: Optional[datetime] = Query(None),
    cursor: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> FirmDeltaResponse:
    offset = _decode_cursor(cursor)
    query = select(PifInfo)
    count_query = select(func.count(PifInfo.id))
    if updated_since:
        query = query.where(PifInfo.updated_at >= updated_since)
        count_query = count_query.where(PifInfo.updated_at >= updated_since)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(
        query.order_by(PifInfo.updated_at.asc(), PifInfo.id.asc())
        .offset(offset)
        .limit(limit + 1)
    )
    firms = result.scalars().all()
    next_cursor = str(offset + limit) if len(firms) > limit else None
    firms = firms[:limit]

    profiles = [await build_profile_for_firm(db, firm) for firm in firms]
    return FirmDeltaResponse(items=profiles, next_cursor=next_cursor, total=total)


@router.get("/firms/resolve", response_model=FirmResolveResponse)
async def resolve_firm(
    website: Optional[str] = Query(None),
    domain: Optional[str] = Query(None),
    email: Optional[str] = Query(None),
    legacy_pif_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> FirmResolveResponse:
    if not any([website, domain, email, legacy_pif_id]):
        raise HTTPException(status_code=400, detail="Provide website, domain, email, or legacy_pif_id")

    resolved = await resolve_firm_id(
        db,
        website=website,
        domain=domain,
        email=email,
        legacy_pif_id=legacy_pif_id,
    )
    if not resolved:
        raise HTTPException(status_code=404, detail="Firm not found")
    firm_id, matched_by, matched_value = resolved
    return FirmResolveResponse(
        firm_id=firm_id,
        matched_by=matched_by,
        matched_value=matched_value,
    )


@router.get("/firms/{firm_id}", response_model=FirmProfile)
async def get_firm(
    firm_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FirmProfile:
    firm = await get_firm_by_id(db, firm_id)
    if not firm:
        raise HTTPException(status_code=404, detail="Firm not found")
    return await build_profile_for_firm(db, firm)


@router.get("/firms/{firm_id}/people", response_model=FirmPeopleResponse)
async def get_firm_people(
    firm_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FirmPeopleResponse:
    firm = await get_firm_by_id(db, firm_id)
    if not firm:
        raise HTTPException(status_code=404, detail="Firm not found")
    profile = await build_profile_for_firm(db, firm)
    return FirmPeopleResponse(firm_id=firm.id, people=profile.people)


@router.get("/health", response_model=FirmIntelHealthResponse)
async def get_health(db: AsyncSession = Depends(get_db)) -> FirmIntelHealthResponse:
    total = await _scalar_count(db, select(func.count(PifInfo.id)))
    canonical = await _scalar_count(
        db, select(func.count(PifInfo.id)).where(PifInfo.canonical_website.is_not(None))
    )
    behavioral = await _scalar_count(
        db, select(func.count(PifInfo.id)).where(PifInfo.behavioral_data.is_not(None))
    )
    icp = await _scalar_count(
        db, select(func.count(PifInfo.id)).where(PifInfo.icp_score.is_not(None))
    )

    latest_result = await db.execute(select(func.max(PifInfo.updated_at)))
    latest_updated_at = latest_result.scalar()
    age_hours = None
    if latest_updated_at:
        age_hours = round((datetime.utcnow() - latest_updated_at).total_seconds() / 3600, 2)

    coverage = {
        "canonical_website": _coverage(canonical, total),
        "behavior": _coverage(behavioral, total),
        "icp": _coverage(icp, total),
    }
    freshness = {
        "latest_updated_at": latest_updated_at.isoformat() if latest_updated_at else None,
        "freshness_age_hours": age_hours,
    }

    return FirmIntelHealthResponse(
        status="ok",
        total_firms=total,
        coverage=coverage,
        freshness=freshness,
    )


async def build_profile_for_firm(db: AsyncSession, firm: PifInfo) -> FirmProfile:
    aliases = await list_aliases_for_firm(db, firm.id)
    emails = await list_emails_for_firm(db, firm)
    autorespond_count = await count_autoresponds_for_firm(db, firm.id)
    return build_firm_profile(
        firm,
        aliases=aliases,
        emails=emails,
        autorespond_count=autorespond_count,
    )


async def get_firm_by_id(db: AsyncSession, firm_id: UUID) -> Optional[PifInfo]:
    result = await db.execute(select(PifInfo).where(PifInfo.id == firm_id))
    return result.scalars().first()


async def list_aliases_for_firm(db: AsyncSession, firm_id: UUID) -> List[FirmAlias]:
    result = await db.execute(select(FirmAlias).where(FirmAlias.firm_id == firm_id))
    return list(result.scalars().all())


async def list_emails_for_firm(db: AsyncSession, firm: PifInfo) -> List[Email]:
    conversation_ids = list(firm.conversation_ids or [])
    if not conversation_ids:
        return []
    result = await db.execute(
        select(Email)
        .where(Email.front_conversation_id.in_(conversation_ids))
        .order_by(Email.created_at.asc())
    )
    return list(result.scalars().all())


async def count_autoresponds_for_firm(db: AsyncSession, firm_id: UUID) -> int:
    result = await db.execute(
        select(func.count(AutorespondEvent.id)).where(AutorespondEvent.pif_id == firm_id)
    )
    return int(result.scalar() or 0)


async def resolve_firm_id(
    db: AsyncSession,
    *,
    website: Optional[str] = None,
    domain: Optional[str] = None,
    email: Optional[str] = None,
    legacy_pif_id: Optional[str] = None,
) -> Optional[tuple[UUID, str, str]]:
    if legacy_pif_id:
        alias = await find_alias_by_values(db, ["legacy_pif_id"], legacy_pif_id.lower())
        if alias:
            return alias.firm_id, "legacy_pif_id", legacy_pif_id

    identity_value = website or domain or email
    normalized_domain = canonical_domain(identity_value)
    if not normalized_domain:
        return None

    alias = await find_alias_by_values(
        db,
        ["domain", "email_domain", "alt_domain"],
        normalized_domain,
    )
    if alias:
        return alias.firm_id, "canonical_domain", normalized_domain

    firm_result = await db.execute(
        select(PifInfo).where(PifInfo.canonical_website == normalized_domain)
    )
    firm = firm_result.scalars().first()
    if firm:
        return firm.id, "canonical_website", normalized_domain
    return None


async def find_alias_by_values(
    db: AsyncSession,
    alias_types: List[str],
    alias_value: str,
) -> Optional[FirmAlias]:
    result = await db.execute(
        select(FirmAlias).where(
            FirmAlias.alias_type.in_(alias_types),
            FirmAlias.alias_value == alias_value.lower(),
        )
    )
    return result.scalars().first()


async def _scalar_count(db: AsyncSession, query) -> int:
    result = await db.execute(query)
    return int(result.scalar() or 0)


def _decode_cursor(cursor: Optional[str]) -> int:
    if not cursor:
        return 0
    try:
        offset = int(cursor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc
    if offset < 0:
        raise HTTPException(status_code=400, detail="Invalid cursor")
    return offset


def _coverage(count: int, total: int) -> dict:
    pct = round(count / total, 4) if total else 0.0
    return {"count": count, "percent": pct}
