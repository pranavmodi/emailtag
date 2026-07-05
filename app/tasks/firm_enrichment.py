"""Celery orchestration for two-pass firm enrichment."""

from __future__ import annotations

from typing import Any, Dict
from uuid import UUID

from celery.utils.log import get_task_logger

from app.db.session import SessionLocal
from app.models.pif_info import PifInfo
from app.services.firm_enrichment import enrich_firm_profile, select_enrichment_candidates
from app.tasks.worker import celery_app

logger = get_task_logger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.firm_enrichment.enrich_firm_profile_task",
    rate_limit="10/m",
)
def enrich_firm_profile_task(self, pif_id: str, force: bool = False) -> Dict[str, Any]:
    """Run the full two-pass enrichment for one active firm."""
    db = SessionLocal()
    try:
        pif = db.get(PifInfo, UUID(pif_id))
        if not pif:
            return {"status": "failed", "pif_id": pif_id, "message": "PIF not found"}
        if pif.merge_status == "merged":
            return {"status": "skipped", "pif_id": pif_id, "message": "firm is merged"}

        result = enrich_firm_profile(db, pif, apply=True, force=force)
        return {
            "status": result.status,
            "pif_id": result.pif_id,
            "firm_name": result.firm_name,
            "fields_updated": result.fields_updated,
            "profile_completeness": result.profile_completeness,
            "outreach_ready": result.outreach_ready,
            "skipped_reason": result.skipped_reason,
        }
    except Exception as exc:
        logger.error("Firm enrichment failed for %s: %s", pif_id, exc, exc_info=True)
        db.rollback()
        return {"status": "failed", "pif_id": pif_id, "message": str(exc)}
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.tasks.firm_enrichment.dispatch_firm_enrichment_task",
    rate_limit="2/m",
)
def dispatch_firm_enrichment_task(self, limit: int = 25, force: bool = False) -> Dict[str, Any]:
    """Queue a bounded enrichment batch on the research queue."""
    db = SessionLocal()
    try:
        candidates = select_enrichment_candidates(db, limit=limit, force=force)
        task_ids = []
        for pif in candidates:
            task = enrich_firm_profile_task.apply_async(args=[str(pif.id)], kwargs={"force": force})
            task_ids.append({"pif_id": str(pif.id), "task_id": task.id})
        return {"status": "dispatched", "total": len(candidates), "items": task_ids}
    finally:
        db.close()
