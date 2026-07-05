"""V2 firm intelligence contract endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.autorespond_event import AutorespondEvent
from app.models.email import Email
from app.models.firm_alias import FirmAlias
from app.models.pif_info import PifInfo
from app.schemas.firm_event import (
    ExternalFirmSignalIn,
    ExternalFirmSignalResponse,
    FirmEventCatalogResponse,
    FirmEventListResponse,
    FirmEventRead,
)
from app.schemas.firm_intel import (
    CandidateFirmIn,
    CandidateFirmResponse,
    FirmDeltaResponse,
    FirmIntelHealthResponse,
    FirmPeopleResponse,
    FirmProfile,
    FirmResolveResponse,
)
from app.schemas.firm_outcome import (
    FirmAttributionResponse,
    FirmOutcomeIn,
    FirmOutcomeResponse,
)
from app.services.firm_event_detectors import detect_engagement_event
from app.services.firm_events import (
    FirmEventCandidate,
    build_dedup_key,
    create_firm_event,
    list_recent_events_for_firm,
)
from app.services.firm_identity import canonical_domain
from app.services.firm_intel import build_firm_profile
from app.services.firm_outcomes import (
    apply_positive_outcome_to_scorer_input,
    build_attribution_report,
    create_firm_outcome,
    get_firm_event_by_id,
    load_outcomes_for_attribution,
    mark_linked_event_for_outcome,
)


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


@router.post("/firms", response_model=CandidateFirmResponse, status_code=201)
async def create_candidate_firm(
    candidate: CandidateFirmIn,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> CandidateFirmResponse:
    domain_aliases = _candidate_domain_aliases(candidate)
    canonical_website = _first_domain_alias_value(domain_aliases)

    if canonical_website:
        resolved = await resolve_domain_identity(db, canonical_website)
        if resolved:
            firm_id, matched_by, matched_value = resolved
            response.status_code = status.HTTP_200_OK
            return CandidateFirmResponse(
                firm_id=firm_id,
                created=False,
                matched_by=_candidate_match_label(matched_by),
                canonical_website=matched_value,
            )
    else:
        name_match = await find_active_firm_by_exact_name(db, candidate.firm_name)
        if name_match:
            response.status_code = status.HTTP_200_OK
            return CandidateFirmResponse(
                firm_id=name_match.id,
                created=False,
                matched_by="name",
                canonical_website=name_match.canonical_website,
            )

    firm = await insert_candidate_firm(
        db,
        candidate,
        canonical_website=canonical_website,
        domain_aliases=domain_aliases,
    )
    return CandidateFirmResponse(
        firm_id=firm.id,
        created=True,
        matched_by="none",
        canonical_website=firm.canonical_website,
    )


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


@router.get("/firms/{firm_id}/events", response_model=FirmEventListResponse)
async def get_firm_events(
    firm_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> FirmEventListResponse:
    firm = await get_firm_by_id(db, firm_id)
    if not firm:
        raise HTTPException(status_code=404, detail="Firm not found")
    events = await list_recent_events_for_firm(db, firm_id, limit=limit, mark_delivered=True)
    return FirmEventListResponse(
        firm_id=firm_id,
        items=[FirmEventRead.model_validate(event) for event in events],
        total=len(events),
    )


@router.get("/events/catalog", response_model=FirmEventCatalogResponse)
async def get_event_catalog() -> FirmEventCatalogResponse:
    return FirmEventCatalogResponse()


@router.post("/events/external", response_model=ExternalFirmSignalResponse, status_code=201)
async def ingest_external_event(
    signal: ExternalFirmSignalIn,
    db: AsyncSession = Depends(get_db),
) -> ExternalFirmSignalResponse:
    resolved = await resolve_external_signal_firm(db, signal)
    if not resolved:
        raise HTTPException(status_code=404, detail="Firm alias not found")
    firm_id, matched_by, matched_value = resolved

    occurred_at = signal.occurred_at or datetime.utcnow()
    detail = {
        **signal.detail,
        "vendor": signal.vendor,
        "sensor_signal_type": signal.signal_type,
        "matched_by": matched_by,
        "matched_value": matched_value,
    }
    if signal.signal_type in {"link_opened", "link_clicked"}:
        source = "engagement"
        source_id = signal.dedup_key or _external_signal_material(signal)
        candidate = detect_engagement_event(
            firm_id=firm_id,
            event_type=signal.signal_type,
            occurred_at=occurred_at,
            source_id=f"{signal.vendor}:{source_id}",
            detail=detail,
            score=signal.score,
        )
    else:
        source = f"external:{signal.vendor}"
        dedup_key = signal.dedup_key or build_dedup_key(
            source=source,
            event_type=signal.signal_type,
            firm_id=firm_id,
            material=_external_signal_material(signal),
        )
        candidate = FirmEventCandidate(
            firm_id=firm_id,
            event_type=signal.signal_type,
            occurred_at=occurred_at,
            source=source,
            detail=detail,
            score=signal.score,
            dedup_key=dedup_key.lower(),
        )

    event, created = await create_firm_event(db, candidate)
    return ExternalFirmSignalResponse(
        event=FirmEventRead.model_validate(event),
        created=created,
        matched_by=matched_by,
        matched_value=matched_value,
    )


@router.post("/outcomes", response_model=FirmOutcomeResponse, status_code=201)
async def ingest_outcome(
    payload: FirmOutcomeIn,
    db: AsyncSession = Depends(get_db),
) -> FirmOutcomeResponse:
    resolved = await resolve_outcome_firm(db, payload)
    if not resolved:
        raise HTTPException(status_code=404, detail="Firm alias not found")
    firm_id, matched_by, matched_value = resolved

    firm_event = None
    if payload.firm_event_id:
        firm_event = await get_firm_event_by_id(db, payload.firm_event_id)
        if not firm_event:
            raise HTTPException(status_code=404, detail="Firm event not found")
        if firm_event.firm_id != firm_id:
            raise HTTPException(
                status_code=400,
                detail="Firm event does not belong to resolved firm",
            )

    occurred_at = payload.occurred_at or datetime.utcnow()
    outcome, created = await create_firm_outcome(
        db,
        firm_id=firm_id,
        event=payload.event,
        occurred_at=occurred_at,
        channel=payload.channel,
        detail=payload.detail,
        firm_event_id=payload.firm_event_id,
        attribution_snapshot=payload.attribution_snapshot,
        idempotency_key=payload.idempotency_key,
    )

    if created:
        if firm_event:
            mark_linked_event_for_outcome(firm_event, outcome)
        firm = await get_firm_by_id(db, firm_id)
        if not firm:
            raise HTTPException(status_code=404, detail="Firm not found")
        apply_positive_outcome_to_scorer_input(firm, outcome)
        await db.commit()
        await db.refresh(outcome)

    return FirmOutcomeResponse(
        outcome=outcome,
        created=created,
        matched_by=matched_by,
        matched_value=matched_value,
    )


@router.get("/attribution", response_model=FirmAttributionResponse)
async def get_attribution(db: AsyncSession = Depends(get_db)) -> FirmAttributionResponse:
    rows = await load_outcomes_for_attribution(db)
    return FirmAttributionResponse(**build_attribution_report(rows))


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

    return await resolve_domain_identity(db, normalized_domain)


async def resolve_domain_identity(
    db: AsyncSession,
    normalized_domain: str,
) -> Optional[tuple[UUID, str, str]]:
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


async def resolve_external_signal_firm(
    db: AsyncSession,
    signal: ExternalFirmSignalIn,
) -> Optional[tuple[UUID, str, str]]:
    if signal.alias_type and signal.alias_value:
        alias = await find_alias_by_values(db, [signal.alias_type], signal.alias_value.lower())
        if alias:
            return alias.firm_id, signal.alias_type, signal.alias_value

    return await resolve_firm_id(
        db,
        website=signal.website,
        domain=signal.domain,
        email=signal.email,
        legacy_pif_id=signal.legacy_pif_id,
    )


async def resolve_outcome_firm(
    db: AsyncSession,
    outcome: FirmOutcomeIn,
) -> Optional[tuple[UUID, str, str]]:
    if outcome.alias_type and outcome.alias_value:
        alias = await find_alias_by_values(
            db,
            [outcome.alias_type],
            outcome.alias_value.lower(),
        )
        if alias:
            return alias.firm_id, outcome.alias_type, outcome.alias_value

    return await resolve_firm_id(
        db,
        website=outcome.website,
        domain=outcome.domain,
        email=outcome.email,
        legacy_pif_id=outcome.legacy_pif_id,
    )


async def find_active_firm_by_exact_name(db: AsyncSession, firm_name: str) -> Optional[PifInfo]:
    normalized = " ".join(firm_name.strip().lower().split())
    result = await db.execute(
        select(PifInfo).where(
            func.lower(func.trim(PifInfo.firm_name)) == normalized,
            PifInfo.merge_status == "active",
        )
    )
    return result.scalars().first()


async def insert_candidate_firm(
    db: AsyncSession,
    candidate: CandidateFirmIn,
    *,
    canonical_website: Optional[str],
    domain_aliases: List[tuple[str, str]],
) -> PifInfo:
    research_data = {
        key: value
        for key, value in {
            "metro": candidate.metro,
            "city": candidate.city,
            "state": candidate.state,
            "candidate_source": candidate.source,
            "candidate_detail": candidate.detail,
        }.items()
        if value not in (None, {}, [])
    }
    firm = PifInfo(
        firm_name=candidate.firm_name,
        entity_type="pi_law_firm",
        canonical_website=canonical_website,
        emails=[],
        phones=[],
        addresses=[],
        contacts=[],
        conversation_ids=[],
        extraction_notes=f"candidate created via {candidate.source}",
        research_data=research_data or None,
    )
    db.add(firm)
    await db.flush()

    for alias_type, alias_value in domain_aliases:
        db.add(
            FirmAlias(
                alias_type=alias_type,
                alias_value=alias_value,
                firm_id=firm.id,
                confidence=1.0,
                source=candidate.source,
            )
        )

    await db.commit()
    await db.refresh(firm)
    return firm


def _candidate_domain_aliases(candidate: CandidateFirmIn) -> List[tuple[str, str]]:
    observed = [
        ("domain", candidate.website),
        ("domain", candidate.domain),
        ("email_domain", candidate.email),
    ]
    aliases: List[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for alias_type, raw_value in observed:
        domain = canonical_domain(raw_value)
        if not domain:
            continue
        key = (alias_type, domain)
        if key in seen:
            continue
        seen.add(key)
        aliases.append(key)
    return aliases


def _first_domain_alias_value(domain_aliases: List[tuple[str, str]]) -> Optional[str]:
    for alias_type, alias_value in domain_aliases:
        if alias_type == "domain":
            return alias_value
    return domain_aliases[0][1] if domain_aliases else None


def _candidate_match_label(resolve_matched_by: str) -> str:
    if resolve_matched_by == "canonical_website":
        return "domain"
    if resolve_matched_by == "canonical_domain":
        return "alias"
    return "none"


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


def _external_signal_material(signal: ExternalFirmSignalIn) -> str:
    for key in ("sensor_event_id", "event_id", "url", "posting_url", "news_url"):
        value = signal.detail.get(key)
        if value:
            return str(value)
    identity = signal.alias_value or signal.website or signal.domain or signal.email or signal.legacy_pif_id
    occurred = signal.occurred_at.isoformat() if signal.occurred_at else "unknown-time"
    return f"{identity}:{signal.signal_type}:{occurred}"
