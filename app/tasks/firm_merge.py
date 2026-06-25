"""Celery entry points for guarded firm merges."""

from typing import Any, Dict
from uuid import UUID

from celery.utils.log import get_task_logger

from app.db.session import SessionLocal
from app.services.firm_merge import format_merge_report, run_firm_merge, undo_firm_merge
from app.tasks.worker import celery_app

logger = get_task_logger(__name__)


@celery_app.task(bind=True, name="app.tasks.firm_merge.run_firm_merge_task")
def run_firm_merge_task(self, dry_run: bool = True, apply: bool = False) -> Dict[str, Any]:
    """Plan duplicate firm merges, applying only when explicitly requested."""
    db = SessionLocal()
    try:
        report = run_firm_merge(db, dry_run=dry_run, apply=apply)
        output = format_merge_report(report)
        if apply:
            db.commit()
        logger.info(output)
        return {
            "status": "success",
            "dry_run": dry_run,
            "applied": apply,
            "auto_merge_count": report.auto_merge_count,
            "review_count": report.review_count,
            "report": output,
        }
    except Exception as exc:
        db.rollback()
        logger.error("Firm merge task failed: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}
    finally:
        db.close()


@celery_app.task(bind=True, name="app.tasks.firm_merge.undo_firm_merge_task")
def undo_firm_merge_task(self, audit_id: str) -> Dict[str, Any]:
    """Undo one applied firm merge by audit id."""
    db = SessionLocal()
    try:
        audit = undo_firm_merge(db, UUID(audit_id))
        db.commit()
        return {
            "status": "success",
            "audit_id": str(audit.id),
            "merge_status": audit.status,
            "undone_at": audit.undone_at.isoformat() if audit.undone_at else None,
        }
    except Exception as exc:
        db.rollback()
        logger.error("Firm merge undo failed for %s: %s", audit_id, exc, exc_info=True)
        return {"status": "error", "audit_id": audit_id, "error": str(exc)}
    finally:
        db.close()

