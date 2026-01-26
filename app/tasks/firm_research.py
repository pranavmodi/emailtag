"""Firm research background tasks using Celery."""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID

from celery import Task
from celery.utils.log import get_task_logger

from app.tasks.worker import celery_app
from app.db.session import SessionLocal

logger = get_task_logger(__name__)


class ResearchTask(Task):
    """Base task class for research tasks with error handling."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = 2


@celery_app.task(bind=True, base=ResearchTask, name="app.tasks.firm_research.research_firm_task")
def research_firm_task(self, pif_id: str) -> Dict[str, Any]:
    """
    Background task to research a firm and its leadership.

    Steps:
    1. Initial firm research (leadership, practice areas, etc.)
    2. Deep research on each leadership member's LinkedIn profile

    Args:
        pif_id: UUID of the PIF record to research

    Returns:
        Dict with research results and status
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

    from pifstats.src.firm_researcher import research_firm, research_leadership_member
    from app.crud.sync.pif_info import pif_info as pif_info_crud_sync

    db = SessionLocal()

    try:
        # Get the PIF record
        pif = pif_info_crud_sync.get(db, id=UUID(pif_id))
        if not pif:
            logger.error(f"PIF not found: {pif_id}")
            return {"status": "failed", "message": "PIF not found"}

        # Update status to in_progress
        pif_info_crud_sync.update(
            db,
            db_obj=pif,
            obj_in={"research_status": "in_progress"}
        )
        db.commit()

        logger.info(f"Starting research for firm: {pif.firm_name}")

        # Get location from addresses
        location = pif.addresses[0] if pif.addresses else None

        # Step 1: Initial firm research
        logger.info(f"Step 1: Initial firm research for {pif.firm_name}")
        result = research_firm(
            firm_name=pif.firm_name,
            website=pif.website,
            location=location
        )

        if result is None:
            pif_info_crud_sync.update(
                db,
                db_obj=pif,
                obj_in={
                    "research_status": "failed",
                    "last_researched_at": datetime.utcnow()
                }
            )
            db.commit()
            return {
                "status": "failed",
                "pif_id": pif_id,
                "message": "Initial research failed - no results returned"
            }

        # Convert leadership to dicts
        leadership_dicts = [member.model_dump() for member in result.leadership]

        # Step 2: Deep research on each leadership member with LinkedIn
        logger.info(f"Step 2: Deep research on {len(leadership_dicts)} leadership members")

        enriched_leadership = []
        for i, leader in enumerate(leadership_dicts):
            if leader.get("name"):
                logger.info(f"Researching leader {i+1}/{len(leadership_dicts)}: {leader.get('name')}")
                try:
                    enriched = research_leadership_member(
                        name=leader.get("name", ""),
                        title=leader.get("title", ""),
                        firm_name=pif.firm_name,
                        linkedin_url=leader.get("linkedin"),
                        firm_website=pif.website
                    )
                    if enriched:
                        # Merge enriched data with original
                        leader.update({
                            "email": enriched.email or leader.get("email"),
                            "phone": enriched.phone or leader.get("phone"),
                            "linkedin": enriched.linkedin or leader.get("linkedin"),
                            "bio": enriched.bio or leader.get("bio"),
                            "education": enriched.education,
                            "experience": enriched.experience,
                            "skills": enriched.skills,
                            "certifications": enriched.certifications,
                            "publications": enriched.publications,
                            "cases_handled": enriched.cases_handled,
                            "bar_admissions": enriched.bar_admissions,
                        })
                except Exception as e:
                    logger.warning(f"Failed to research leader {leader.get('name')}: {str(e)}")

                enriched_leadership.append(leader)

        # Prepare research data
        research_data = {
            "practice_areas": result.practice_areas,
            "founded_year": result.founded_year,
            "firm_size": result.firm_size,
            "office_locations": result.office_locations,
            "notable_cases": result.notable_cases,
            "awards_recognition": result.awards_recognition,
            "bar_associations": result.bar_associations,
            "social_media": result.social_media,
            "additional_info": result.additional_info,
            "sources": result.sources
        }

        # Update the PIF record
        pif_info_crud_sync.update(
            db,
            db_obj=pif,
            obj_in={
                "leadership": enriched_leadership,
                "research_data": research_data,
                "research_status": "completed",
                "last_researched_at": datetime.utcnow()
            }
        )
        db.commit()

        logger.info(f"Research completed for {pif.firm_name}: {len(enriched_leadership)} leaders")

        return {
            "status": "completed",
            "pif_id": pif_id,
            "firm_name": pif.firm_name,
            "leadership_count": len(enriched_leadership),
            "message": f"Research completed. Found {len(enriched_leadership)} leadership members."
        }

    except Exception as e:
        logger.error(f"Research task error for {pif_id}: {str(e)}")
        try:
            pif = pif_info_crud_sync.get(db, id=UUID(pif_id))
            if pif:
                pif_info_crud_sync.update(
                    db,
                    db_obj=pif,
                    obj_in={
                        "research_status": "failed",
                        "last_researched_at": datetime.utcnow()
                    }
                )
                db.commit()
        except Exception:
            pass

        return {
            "status": "failed",
            "pif_id": pif_id,
            "message": f"Research failed: {str(e)}"
        }
    finally:
        db.close()
