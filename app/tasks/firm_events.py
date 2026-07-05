"""Celery wrappers for firm trigger detectors."""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.email import Email
from app.models.pif_info import PifInfo
from app.services.firm_event_detectors import detect_internal_firm_events
from app.services.firm_events import create_firm_event_sync
from app.tasks.worker import celery_app

logger = get_task_logger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.firm_events.detect_firm_events_task",
    rate_limit="10/m",
)
def detect_firm_events_task(self, pif_id: str, dry_run: bool = False) -> Dict[str, Any]:
    """Run internal detectors for one firm. This task is safe to mock in tests."""

    db = SessionLocal()
    try:
        firm = db.get(PifInfo, UUID(pif_id))
        if not firm:
            return {"status": "failed", "message": "PIF not found", "pif_id": pif_id}

        emails = []
        if firm.conversation_ids:
            emails = list(
                db.execute(
                    select(Email).where(Email.front_conversation_id.in_(firm.conversation_ids))
                ).scalars().all()
            )

        candidates = detect_internal_firm_events(firm, emails)
        if dry_run:
            return {
                "status": "dry_run",
                "pif_id": pif_id,
                "detected": len(candidates),
                "event_types": [candidate.event_type for candidate in candidates],
            }

        created = 0
        for candidate in candidates:
            _, was_created = create_firm_event_sync(db, candidate)
            if was_created:
                created += 1
        return {"status": "completed", "pif_id": pif_id, "detected": len(candidates), "created": created}
    except Exception as exc:
        logger.error("Firm event detection failed for %s: %s", pif_id, exc, exc_info=True)
        return {"status": "failed", "pif_id": pif_id, "message": str(exc)}
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.tasks.firm_events.detect_all_firm_events_task",
    rate_limit="10/m",
)
def detect_all_firm_events_task(self, dry_run: bool = True) -> Dict[str, Any]:
    """Queue detector tasks for all firms. Defaults to dry-run to prevent accidental firing."""

    db = SessionLocal()
    try:
        ids = [str(row[0]) for row in db.execute(select(PifInfo.id)).fetchall()]
    finally:
        db.close()

    dispatched = 0
    for pif_id in ids:
        detect_firm_events_task.delay(pif_id, dry_run=dry_run)
        dispatched += 1
    return {"status": "dispatched", "total": len(ids), "dispatched": dispatched, "dry_run": dry_run}
