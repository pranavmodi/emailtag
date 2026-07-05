"""Outcome feedback persistence, attribution, and neutral scoring helpers."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.firm_event import FirmEvent
from app.models.firm_outcome import FirmOutcome, POSITIVE_OUTCOME_EVENTS
from app.models.pif_info import PifInfo


CORE_ATTRIBUTION_FIELDS = (
    "canonical_website",
    "metro",
    "state",
    "size_hint",
    "case_mix",
    "value_tier",
    "volume_proxy",
    "warm_score_neutral",
    "total_email_count",
    "primary_pain_point",
    "case_mgmt",
    "decision_maker",
)

SNAPSHOT_FIELD_PATHS = {
    "canonical_website": (("canonical_website",),),
    "metro": (("metro",), ("identity", "metro")),
    "state": (("state",), ("identity", "state")),
    "size_hint": (("size_hint",), ("identity", "size_hint")),
    "case_mix": (("case_mix",), ("identity", "case_mix")),
    "value_tier": (("value_tier",), ("identity", "value_tier")),
    "volume_proxy": (("volume_proxy",), ("identity", "volume_proxy")),
    "warm_score_neutral": (
        ("warm_score_neutral",),
        ("relationship", "warm_score_neutral"),
    ),
    "total_email_count": (("total_email_count",), ("relationship", "total_email_count")),
    "primary_pain_point": (("primary_pain_point",), ("behavior", "primary_pain_point")),
    "case_mgmt": (("case_mgmt",), ("vendor_stack", "case_mgmt")),
    "decision_maker": (
        ("decision_maker",),
        ("has_decision_maker",),
        ("people",),
    ),
}


async def get_outcome_by_idempotency_key(
    db: AsyncSession,
    idempotency_key: str,
) -> Optional[FirmOutcome]:
    result = await db.execute(
        select(FirmOutcome).where(FirmOutcome.idempotency_key == idempotency_key)
    )
    return result.scalars().first()


async def get_firm_event_by_id(db: AsyncSession, event_id: UUID) -> Optional[FirmEvent]:
    result = await db.execute(select(FirmEvent).where(FirmEvent.id == event_id))
    return result.scalars().first()


async def create_firm_outcome(
    db: AsyncSession,
    *,
    firm_id: UUID,
    event: str,
    occurred_at: datetime,
    channel: str,
    detail: Dict[str, Any],
    firm_event_id: Optional[UUID],
    attribution_snapshot: Dict[str, Any],
    idempotency_key: str,
) -> tuple[FirmOutcome, bool]:
    existing = await get_outcome_by_idempotency_key(db, idempotency_key)
    if existing:
        return existing, False

    outcome = FirmOutcome(
        firm_id=firm_id,
        event=event,
        occurred_at=occurred_at,
        channel=channel,
        detail=detail,
        firm_event_id=firm_event_id,
        attribution_snapshot=attribution_snapshot,
        idempotency_key=idempotency_key,
        created_at=datetime.utcnow(),
    )
    db.add(outcome)
    return outcome, True


def mark_linked_event_for_outcome(firm_event: FirmEvent, outcome: FirmOutcome) -> None:
    """Mark the trigger as delivered and converted when feedback confirms conversion."""
    if firm_event.delivered_at is None:
        firm_event.delivered_at = outcome.occurred_at
    if outcome.event in POSITIVE_OUTCOME_EVENTS and firm_event.converted_at is None:
        firm_event.converted_at = outcome.occurred_at


def apply_positive_outcome_to_scorer_input(firm: PifInfo, outcome: FirmOutcome) -> bool:
    """Record supervised positive feedback in scorer-only inputs and recompute ICP."""
    if outcome.event not in POSITIVE_OUTCOME_EVENTS:
        return False

    behavioral = dict(firm.behavioral_data or {})
    positive_outcomes = dict(behavioral.get("positive_outcomes") or {})
    event_counts = dict(positive_outcomes.get("event_counts") or {})
    event_counts[outcome.event] = int(event_counts.get(outcome.event) or 0) + 1

    positive_outcomes["event_counts"] = event_counts
    positive_outcomes["total"] = sum(int(value or 0) for value in event_counts.values())
    positive_outcomes["last_outcome_at"] = outcome.occurred_at.isoformat()
    behavioral["positive_outcomes"] = positive_outcomes
    firm.behavioral_data = behavioral

    from pifstats.src.icp_scorer import score_firm

    score_result = score_firm(
        {
            "behavioral_data": firm.behavioral_data,
            "research_data": firm.research_data,
            "website": firm.website,
            "leadership": firm.leadership,
            "phones": firm.phones,
            "conversation_ids": firm.conversation_ids,
        }
    )
    firm.icp_score = score_result["icp_score"]
    firm.icp_tier = score_result["icp_tier"]
    firm.score_breakdown = score_result["score_breakdown"]
    firm.icp_scored_at = datetime.utcnow()
    return True


async def load_outcomes_for_attribution(
    db: AsyncSession,
) -> List[tuple[FirmOutcome, Optional[FirmEvent]]]:
    result = await db.execute(
        select(FirmOutcome, FirmEvent)
        .outerjoin(FirmEvent, FirmOutcome.firm_event_id == FirmEvent.id)
        .order_by(FirmOutcome.occurred_at.asc(), FirmOutcome.created_at.asc())
    )
    return list(result.all())


def build_attribution_report(
    rows: Iterable[tuple[FirmOutcome, Optional[FirmEvent]]],
) -> Dict[str, Any]:
    trigger_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "success": 0})
    field_counts: dict[str, dict[bool, dict[str, int]]] = {
        field: {
            True: {"total": 0, "success": 0},
            False: {"total": 0, "success": 0},
        }
        for field in CORE_ATTRIBUTION_FIELDS
    }

    for outcome, firm_event in rows:
        success = outcome.event in {"booked", "qualified"}
        trigger_type = firm_event.event_type if firm_event else "none"
        trigger_counts[trigger_type]["total"] += 1
        trigger_counts[trigger_type]["success"] += int(success)

        snapshot = outcome.attribution_snapshot or {}
        for field in CORE_ATTRIBUTION_FIELDS:
            present = _snapshot_has_field(snapshot, field)
            field_counts[field][present]["total"] += 1
            field_counts[field][present]["success"] += int(success)

    return {
        "by_trigger_type": [
            {
                "trigger_type": trigger_type,
                **_metric(counts["total"], counts["success"]),
            }
            for trigger_type, counts in sorted(trigger_counts.items())
        ],
        "by_core_field_presence": [
            {
                "field": field,
                "present": _metric(counts[True]["total"], counts[True]["success"]),
                "absent": _metric(counts[False]["total"], counts[False]["success"]),
            }
            for field, counts in field_counts.items()
        ],
    }


def _metric(total: int, success: int) -> Dict[str, Any]:
    return {
        "total_count": total,
        "booked_or_qualified_count": success,
        "booked_or_qualified_rate": round(success / total, 4) if total else 0.0,
    }


def _snapshot_has_field(snapshot: Dict[str, Any], field: str) -> bool:
    for path in SNAPSHOT_FIELD_PATHS[field]:
        value = _nested_get(snapshot, path)
        if _is_present(value):
            return True
    return False


def _nested_get(payload: Dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True
