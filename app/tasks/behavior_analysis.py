"""Behavior analysis and ICP scoring Celery tasks."""

import logging
import sys
import os
from datetime import datetime
from typing import Any, Dict
from uuid import UUID

from celery.utils.log import get_task_logger

from app.tasks.worker import celery_app
from app.db.session import SessionLocal

logger = get_task_logger(__name__)


def _get_project_root() -> str:
    """Return the project root directory."""
    # __file__ = app/tasks/behavior_analysis.py, go up 2 levels
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


@celery_app.task(bind=True, name="app.tasks.behavior_analysis.analyze_firm_behavior_task")
def analyze_firm_behavior_task(self, pif_id: str) -> Dict[str, Any]:
    """
    Analyze email behavior for a firm and compute ICP score.

    Steps:
    1. Load pif from DB
    2. Query emails for this firm's conversation IDs
    3. Run email_analyzer.analyze_firm_emails()
    4. Run icp_scorer.score_firm()
    5. Update pif record with results

    Args:
        pif_id: UUID string of the pif_info record

    Returns:
        Dict with status, icp_score, icp_tier
    """
    project_root = _get_project_root()
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from pifstats.src.email_analyzer import analyze_firm_emails
    from pifstats.src.icp_scorer import score_firm
    from app.crud.sync.pif_info import pif_info as pif_info_crud_sync
    from sqlalchemy import select, text
    from app.models.email import Email

    db = SessionLocal()
    try:
        pif = pif_info_crud_sync.get(db, id=UUID(pif_id))
        if not pif:
            logger.error(f"PIF not found: {pif_id}")
            return {"status": "failed", "message": "PIF not found"}

        firm_name = pif.firm_name
        conv_ids = pif.conversation_ids or []

        logger.info(f"Analyzing behavior for firm: {firm_name} ({len(conv_ids)} conversations)")

        # Query emails for these conversation IDs
        if conv_ids:
            result = db.execute(
                select(Email).where(Email.front_conversation_id.in_(conv_ids))
            )
            email_rows = result.scalars().all()
        else:
            email_rows = []

        logger.info(f"Found {len(email_rows)} emails for {firm_name}")

        emails_for_analysis = [
            {
                "subject": em.subject or "",
                "content_text": em.content_text or "",
                "sender": em.sender or "",
                "created_at": em.created_at,
            }
            for em in email_rows
        ]

        # Run behavioral analysis
        behavioral_data = analyze_firm_emails(emails_for_analysis)

        # Prepare pif dict for scoring
        pif_dict = {
            "behavioral_data": behavioral_data,
            "research_data": pif.research_data or {},
            "website": pif.website,
            "leadership": pif.leadership or [],
            "phones": pif.phones or [],
            "conversation_ids": conv_ids,
        }

        # Run ICP scoring
        score_result = score_firm(pif_dict)

        # Update DB
        pif_info_crud_sync.update(
            db,
            db_obj=pif,
            obj_in={
                "behavioral_data": behavioral_data,
                "icp_score": score_result["icp_score"],
                "icp_tier": score_result["icp_tier"],
                "score_breakdown": score_result["score_breakdown"],
                "icp_scored_at": datetime.utcnow(),
            },
        )
        db.commit()

        logger.info(
            f"Behavior analysis complete for {firm_name}: "
            f"score={score_result['icp_score']} tier={score_result['icp_tier']}"
        )

        return {
            "status": "completed",
            "pif_id": pif_id,
            "firm_name": firm_name,
            "icp_score": score_result["icp_score"],
            "icp_tier": score_result["icp_tier"],
            "total_emails_analyzed": len(email_rows),
        }

    except Exception as e:
        logger.error(f"Behavior analysis failed for {pif_id}: {e}", exc_info=True)
        return {"status": "failed", "pif_id": pif_id, "message": str(e)}
    finally:
        db.close()


@celery_app.task(bind=True, name="app.tasks.behavior_analysis.analyze_all_firms_task")
def analyze_all_firms_task(self) -> Dict[str, Any]:
    """
    Dispatch analyze_firm_behavior_task for every firm in the database.

    Returns:
        Dict with total and dispatched counts
    """
    from app.crud.sync.pif_info import pif_info as pif_info_crud_sync
    from sqlalchemy import select
    from app.models.pif_info import PifInfo

    db = SessionLocal()
    try:
        result = db.execute(select(PifInfo.id))
        pif_ids = [str(row[0]) for row in result.fetchall()]

        logger.info(f"Dispatching behavior analysis for {len(pif_ids)} firms")

        dispatched = 0
        for pif_id in pif_ids:
            try:
                analyze_firm_behavior_task.delay(pif_id)
                dispatched += 1
            except Exception as e:
                logger.error(f"Failed to dispatch task for {pif_id}: {e}")

        return {"status": "dispatched", "total": len(pif_ids), "dispatched": dispatched}

    finally:
        db.close()


@celery_app.task(bind=True, name="app.tasks.behavior_analysis.score_all_firms_task")
def score_all_firms_task(self) -> Dict[str, Any]:
    """
    Re-score all firms that already have behavioral_data (synchronously in one task).

    Returns:
        Dict with scored count
    """
    project_root = _get_project_root()
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from pifstats.src.icp_scorer import score_firm
    from app.crud.sync.pif_info import pif_info as pif_info_crud_sync
    from sqlalchemy import select
    from app.models.pif_info import PifInfo

    db = SessionLocal()
    try:
        result = db.execute(
            select(PifInfo).where(PifInfo.behavioral_data.is_not(None))
        )
        pifs = result.scalars().all()

        logger.info(f"Scoring {len(pifs)} firms with existing behavioral data")

        scored = 0
        for pif in pifs:
            try:
                pif_dict = {
                    "behavioral_data": pif.behavioral_data or {},
                    "research_data": pif.research_data or {},
                    "website": pif.website,
                    "leadership": pif.leadership or [],
                    "phones": pif.phones or [],
                }
                score_result = score_firm(pif_dict)
                pif_info_crud_sync.update(
                    db,
                    db_obj=pif,
                    obj_in={
                        "icp_score": score_result["icp_score"],
                        "icp_tier": score_result["icp_tier"],
                        "score_breakdown": score_result["score_breakdown"],
                        "icp_scored_at": datetime.utcnow(),
                    },
                )
                scored += 1
            except Exception as e:
                logger.error(f"Failed to score firm {pif.id}: {e}")

        db.commit()
        return {"status": "completed", "scored": scored, "total": len(pifs)}

    finally:
        db.close()
