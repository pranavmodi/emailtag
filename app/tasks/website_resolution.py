"""Celery task for tiered firm website resolution."""

from typing import Any, Dict
from uuid import UUID

from celery.utils.log import get_task_logger

from app.db.session import SessionLocal
from app.models.pif_info import PifInfo
from app.services.website_resolution import (
    WebsiteResolutionResult,
    apply_website_resolution,
    persist_aliases_for_firm,
    resolve_firm_website,
)
from app.tasks.worker import celery_app

logger = get_task_logger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.website_resolution.resolve_firm_website_task",
    rate_limit="10/m",
)
def resolve_firm_website_task(self, pif_id: str) -> Dict[str, Any]:
    """Resolve and persist the canonical website for one PIF firm."""
    db = SessionLocal()
    try:
        pif = db.query(PifInfo).filter(PifInfo.id == UUID(pif_id)).first()
        if not pif:
            return {"status": "failed", "message": "PIF not found", "pif_id": pif_id}

        if pif.website_status == "resolved" and pif.canonical_website:
            return {
                "status": "skipped",
                "message": "Website already resolved",
                "pif_id": pif_id,
                "canonical_website": pif.canonical_website,
            }

        result = resolve_firm_website(pif)
        if result.canonical_website:
            owner = (
                db.query(PifInfo)
                .filter(
                    PifInfo.canonical_website == result.canonical_website,
                    PifInfo.id != pif.id,
                )
                .first()
            )
            if owner:
                result = WebsiteResolutionResult(
                    canonical_website=None,
                    website_status="pending",
                    website_source="human",
                    website_confidence=0.0,
                    review_reason="canonical_domain_owned_by_another_firm",
                    review_candidate=result.canonical_website,
                )

        apply_website_resolution(pif, result)
        persist_aliases_for_firm(db, pif)
        db.add(pif)
        db.commit()
        db.refresh(pif)

        return {
            "status": result.website_status,
            "pif_id": pif_id,
            "canonical_website": result.canonical_website,
            "website_source": result.website_source,
            "website_confidence": result.website_confidence,
            "review_reason": result.review_reason,
        }
    except Exception as exc:
        db.rollback()
        logger.error("Website resolution failed for %s: %s", pif_id, exc, exc_info=True)
        return {"status": "error", "pif_id": pif_id, "error": str(exc)}
    finally:
        db.close()
