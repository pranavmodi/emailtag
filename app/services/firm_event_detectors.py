"""Detectors that turn existing EmailTag firm data into trigger candidates."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from email.utils import parseaddr
from typing import Any, Iterable, Optional
from uuid import UUID

from app.models.email import Email
from app.models.pif_info import PifInfo
from app.services.firm_events import FirmEventCandidate, build_dedup_key

REFERRAL_INBOX_ID = "inb_qfq9"
RECORDS_INBOX_ID = "inb_rcld"
SENIOR_TITLE_RE = re.compile(
    r"\b(owner|founder|partner|managing partner|principal|president|ceo|coo|"
    r"chief|director|vp|vice president|operations)\b",
    re.IGNORECASE,
)


def detect_internal_firm_events(
    firm: PifInfo,
    emails: Iterable[Email],
    *,
    now: Optional[datetime] = None,
    warm_threshold: float = 50.0,
    quiet_days: int = 45,
    records_surge_count: int = 10,
    records_surge_window_days: int = 7,
    previous_behavioral_data: Optional[dict[str, Any]] = None,
) -> list[FirmEventCandidate]:
    now = now or datetime.utcnow()
    email_list = list(emails)
    candidates: list[FirmEventCandidate] = []
    candidates.extend(_detect_first_interaction(firm, email_list))
    candidates.extend(_detect_new_referrals(firm, email_list))
    records_surge = _detect_records_surge(
        firm,
        email_list,
        now=now,
        threshold=records_surge_count,
        window_days=records_surge_window_days,
    )
    if records_surge:
        candidates.append(records_surge)

    became_warm = _detect_became_warm(
        firm,
        threshold=warm_threshold,
        previous_behavioral_data=previous_behavioral_data,
        now=now,
    )
    if became_warm:
        candidates.append(became_warm)

    went_quiet = detect_went_quiet(firm, now=now, quiet_days=quiet_days)
    if went_quiet:
        candidates.append(went_quiet)

    candidates.extend(_detect_decision_makers(firm, now=now))
    candidates.extend(_detect_vendor_events(firm, now=now, previous_behavioral_data=previous_behavioral_data))
    return candidates


def detect_went_quiet(
    firm: PifInfo,
    *,
    now: Optional[datetime] = None,
    quiet_days: int = 45,
) -> Optional[FirmEventCandidate]:
    now = now or datetime.utcnow()
    behavior = firm.behavioral_data or {}
    total_email_count = _int_or_zero(behavior.get("total_email_count")) or len(firm.conversation_ids or [])
    if total_email_count <= 0:
        return None

    last_seen = _parse_datetime(
        behavior.get("last_contact_date")
        or behavior.get("last_seen_at")
        or behavior.get("last_referral_at")
        or behavior.get("last_records_at")
        or firm.updated_at
    )
    if not last_seen:
        return None

    quiet_for_days = (now - last_seen).days
    if quiet_for_days <= quiet_days:
        return None

    last_seen_day = last_seen.date().isoformat()
    return FirmEventCandidate(
        firm_id=firm.id,
        event_type="went_quiet",
        occurred_at=now,
        source="precise_stream",
        detail={
            "last_seen_at": last_seen.isoformat(),
            "quiet_for_days": quiet_for_days,
            "threshold_days": quiet_days,
            "total_email_count": total_email_count,
        },
        score=min(100.0, 40.0 + quiet_for_days / 2),
        dedup_key=build_dedup_key(
            source="precise_stream",
            event_type="went_quiet",
            firm_id=firm.id,
            material=f"{quiet_days}:{last_seen_day}",
        ),
    )


def detect_engagement_event(
    *,
    firm_id: UUID,
    event_type: str,
    occurred_at: datetime,
    source_id: str,
    detail: Optional[dict[str, Any]] = None,
    score: float = 65.0,
) -> FirmEventCandidate:
    if event_type not in {"link_opened", "link_clicked"}:
        raise ValueError("engagement event_type must be link_opened or link_clicked")
    return FirmEventCandidate(
        firm_id=firm_id,
        event_type=event_type,
        occurred_at=occurred_at,
        source="engagement",
        detail=detail or {},
        score=score,
        dedup_key=build_dedup_key(
            source="engagement",
            event_type=event_type,
            firm_id=firm_id,
            material=source_id,
        ),
    )


def _detect_first_interaction(firm: PifInfo, emails: list[Email]) -> list[FirmEventCandidate]:
    if not emails:
        return []
    first_email = min(emails, key=lambda email: email.created_at or datetime.utcnow())
    first_sender = parseaddr(first_email.sender or "")[1] or first_email.sender
    return [
        FirmEventCandidate(
            firm_id=firm.id,
            event_type="first_interaction",
            occurred_at=first_email.created_at or firm.created_at,
            source="precise_stream",
            detail={
                "sender": first_sender,
                "conversation_id": first_email.front_conversation_id,
                "email_id": str(first_email.id),
            },
            score=55.0,
            dedup_key=build_dedup_key(
                source="precise_stream",
                event_type="first_interaction",
                firm_id=firm.id,
                material=str(first_email.id or first_email.front_conversation_id),
            ),
        )
    ]


def _detect_new_referrals(firm: PifInfo, emails: list[Email]) -> list[FirmEventCandidate]:
    candidates = []
    for email in emails:
        if _email_inbox_id(email) != REFERRAL_INBOX_ID:
            continue
        material = str(email.id or email.front_conversation_id)
        candidates.append(
            FirmEventCandidate(
                firm_id=firm.id,
                event_type="new_referral",
                occurred_at=email.created_at or datetime.utcnow(),
                source="precise_stream",
                detail={
                    "conversation_id": email.front_conversation_id,
                    "email_id": str(email.id),
                    "inbox_id": REFERRAL_INBOX_ID,
                },
                score=90.0,
                dedup_key=build_dedup_key(
                    source="precise_stream",
                    event_type="new_referral",
                    firm_id=firm.id,
                    material=material,
                ),
            )
        )
    return candidates


def _detect_records_surge(
    firm: PifInfo,
    emails: list[Email],
    *,
    now: datetime,
    threshold: int,
    window_days: int,
) -> Optional[FirmEventCandidate]:
    window_start = now - timedelta(days=window_days)
    recent_records = [
        email
        for email in emails
        if _email_inbox_id(email) == RECORDS_INBOX_ID
        and email.created_at
        and email.created_at >= window_start
    ]
    if len(recent_records) < threshold:
        return None
    return FirmEventCandidate(
        firm_id=firm.id,
        event_type="records_surge",
        occurred_at=now,
        source="precise_stream",
        detail={
            "records_count": len(recent_records),
            "window_days": window_days,
            "threshold": threshold,
            "inbox_id": RECORDS_INBOX_ID,
        },
        score=min(100.0, 65.0 + len(recent_records)),
        dedup_key=build_dedup_key(
            source="precise_stream",
            event_type="records_surge",
            firm_id=firm.id,
            material=f"{window_days}:{now.date().isoformat()}",
        ),
    )


def _detect_became_warm(
    firm: PifInfo,
    *,
    threshold: float,
    previous_behavioral_data: Optional[dict[str, Any]],
    now: datetime,
) -> Optional[FirmEventCandidate]:
    current = _float_or_none((firm.behavioral_data or {}).get("warm_score"))
    if current is None:
        current = _float_or_none((firm.behavioral_data or {}).get("warm_score_neutral"))
    if current is None or current < threshold:
        return None

    previous = None
    if previous_behavioral_data:
        previous = _float_or_none(
            previous_behavioral_data.get("warm_score")
            or previous_behavioral_data.get("warm_score_neutral")
        )
    if previous is not None and previous >= threshold:
        return None

    return FirmEventCandidate(
        firm_id=firm.id,
        event_type="became_warm",
        occurred_at=now,
        source="precise_stream",
        detail={"warm_score": current, "threshold": threshold, "previous_warm_score": previous},
        score=min(100.0, current),
        dedup_key=build_dedup_key(
            source="precise_stream",
            event_type="became_warm",
            firm_id=firm.id,
            material=str(int(threshold)),
        ),
    )


def _detect_decision_makers(firm: PifInfo, *, now: datetime) -> list[FirmEventCandidate]:
    candidates = []
    for person in list(firm.contacts or []) + list(firm.leadership or []):
        title = str(person.get("title") or "")
        name = str(person.get("name") or person.get("email") or "").strip()
        if not name or not SENIOR_TITLE_RE.search(title):
            continue
        material = (person.get("email") or f"{name}:{title}").lower()
        candidates.append(
            FirmEventCandidate(
                firm_id=firm.id,
                event_type="new_decision_maker",
                occurred_at=now,
                source="precise_stream",
                detail={
                    "name": name,
                    "title": title,
                    "email": person.get("email"),
                    "persona": person.get("persona"),
                },
                score=80.0,
                dedup_key=build_dedup_key(
                    source="precise_stream",
                    event_type="new_decision_maker",
                    firm_id=firm.id,
                    material=str(material),
                ),
            )
        )
    return candidates


def _detect_vendor_events(
    firm: PifInfo,
    *,
    now: datetime,
    previous_behavioral_data: Optional[dict[str, Any]],
) -> list[FirmEventCandidate]:
    current_vendor = _case_mgmt_vendor(firm.behavioral_data or {})
    if not current_vendor:
        return []
    previous_vendor = _case_mgmt_vendor(previous_behavioral_data or {})
    event_type = "vendor_changed" if previous_vendor and previous_vendor != current_vendor else "vendor_detected"
    material = f"{previous_vendor or 'none'}:{current_vendor}"
    return [
        FirmEventCandidate(
            firm_id=firm.id,
            event_type=event_type,
            occurred_at=now,
            source="precise_stream",
            detail={"case_mgmt": current_vendor, "previous_case_mgmt": previous_vendor},
            score=70.0 if event_type == "vendor_detected" else 82.0,
            dedup_key=build_dedup_key(
                source="precise_stream",
                event_type=event_type,
                firm_id=firm.id,
                material=material,
            ),
        )
    ]


def _case_mgmt_vendor(behavior: dict[str, Any]) -> Optional[str]:
    tech_signals = behavior.get("tech_signals") or {}
    vendor = tech_signals.get("case_mgmt") or behavior.get("case_mgmt")
    return str(vendor).lower() if vendor else None


def _email_inbox_id(email: Email) -> Optional[str]:
    raw = email.raw_data or {}
    return (
        raw.get("target", {})
        .get("data", {})
        .get("inbox", {})
        .get("id")
    ) or raw.get("inbox_id")


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _float_or_none(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
