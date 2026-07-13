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


def is_valid_linkedin_url(url: str | None) -> bool:
    """Check if a string is a valid LinkedIn profile URL."""
    if not url:
        return False
    lower = url.lower().strip()
    return (
        lower.startswith("https://linkedin.com") or
        lower.startswith("https://www.linkedin.com") or
        lower.startswith("http://linkedin.com") or
        lower.startswith("http://www.linkedin.com") or
        lower.startswith("linkedin.com/in/") or
        lower.startswith("www.linkedin.com/in/")
    )


def sanitize_linkedin_url(url: str | None) -> str | None:
    """Return the URL if valid, otherwise return None."""
    if is_valid_linkedin_url(url):
        # Ensure it has https://
        if url and not url.lower().startswith("http"):
            return f"https://{url}"
        return url
    return None


def strip_nul(obj):
    """
    Recursively remove NUL (\\u0000) characters from researched data.

    PostgreSQL cannot store NUL in text/JSONB columns and raises
    UntranslatableCharacter. LLM responses occasionally contain them, so we
    scrub before persisting any researched payload.
    """
    if isinstance(obj, str):
        return obj.replace("\x00", "")
    if isinstance(obj, dict):
        return {k: strip_nul(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [strip_nul(v) for v in obj]
    return obj


def _fetch_firm_emails(db, pif, limit: int = 200) -> list[dict]:
    """
    Fetch a bounded sample of inbound emails for a firm, for vendor scanning.

    Returns the most recent `limit` emails (sender/subject/content_text) across
    the firm's conversation_ids. Bounded to keep memory/latency in check on
    high-volume firms.
    """
    from sqlalchemy import select, desc
    from app.models.email import Email

    conv_ids = pif.conversation_ids or []
    if not conv_ids:
        return []
    rows = db.execute(
        select(Email)
        .where(Email.front_conversation_id.in_(conv_ids))
        .order_by(desc(Email.created_at))
        .limit(limit)
    ).scalars().all()
    return [
        {
            "sender": em.sender or "",
            "recipients": em.recipients or [],
            "subject": em.subject or "",
            "content_text": em.content_text or "",
            "content_html": em.content_html or "",
        }
        for em in rows
    ]


class ResearchTask(Task):
    """Base task class for research tasks with error handling."""

    autoretry_for = (Exception,)
    rate_limit = "10/m"
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True
    max_retries = 2


@celery_app.task(
    bind=True,
    base=ResearchTask,
    name="app.tasks.firm_research.research_firm_task",
    rate_limit="10/m",
)
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
    # Add project root to path so pifstats module can be found
    # __file__ is app/tasks/firm_research.py, go up 2 levels to get to project root
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from pifstats.src.firm_researcher import research_firm, research_leadership_member
    from app.crud.sync.pif_info import pif_info as pif_info_crud_sync
    from app.models.pif_info import PifInfo
    from app.services.website_resolution import (
        WebsiteResolutionResult,
        apply_website_resolution,
        persist_aliases_for_firm,
        resolve_firm_website,
    )

    db = SessionLocal()

    try:
        # Get the PIF record
        pif = pif_info_crud_sync.get(db, id=UUID(pif_id))
        if not pif:
            logger.error(f"PIF not found: {pif_id}")
            return {"status": "failed", "message": "PIF not found"}

        if not pif.canonical_website:
            logger.info(f"Resolving website before research for firm: {pif.firm_name}")
            website_result = resolve_firm_website(pif)
            if website_result.canonical_website:
                owner = (
                    db.query(PifInfo)
                    .filter(
                        PifInfo.canonical_website == website_result.canonical_website,
                        PifInfo.id != pif.id,
                    )
                    .first()
                )
                if owner:
                    website_result = WebsiteResolutionResult(
                        canonical_website=None,
                        website_status="pending",
                        website_source="human",
                        website_confidence=0.0,
                        review_reason="canonical_domain_owned_by_another_firm",
                        review_candidate=website_result.canonical_website,
                    )

            apply_website_resolution(pif, website_result)
            persist_aliases_for_firm(db, pif)
            db.add(pif)
            db.commit()
            db.refresh(pif)

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
            website=pif.canonical_website or pif.website,
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

        # Convert leadership to dicts and sanitize LinkedIn URLs
        leadership_dicts = []
        for member in result.leadership:
            member_dict = member.model_dump()
            raw_linkedin = member_dict.get("linkedin")
            sanitized_linkedin = sanitize_linkedin_url(raw_linkedin)
            logger.info(f"[Step1] {member_dict.get('name')}: raw LinkedIn from firm research = '{raw_linkedin}' -> sanitized = '{sanitized_linkedin}'")
            member_dict["linkedin"] = sanitized_linkedin
            leadership_dicts.append(member_dict)

        # Step 2: Deep research on each leadership member with LinkedIn
        logger.info(f"Step 2: Deep research on {len(leadership_dicts)} leadership members")

        enriched_leadership = []
        for i, leader in enumerate(leadership_dicts):
            if leader.get("name"):
                logger.info(f"Researching leader {i+1}/{len(leadership_dicts)}: {leader.get('name')} (existing linkedin={leader.get('linkedin')})")
                try:
                    enriched = research_leadership_member(
                        name=leader.get("name", ""),
                        title=leader.get("title", ""),
                        firm_name=pif.firm_name,
                        linkedin_url=leader.get("linkedin"),
                        firm_website=pif.canonical_website or pif.website
                    )
                    if enriched:
                        # Merge enriched data with original, sanitizing LinkedIn URL
                        enriched_linkedin_raw = enriched.linkedin
                        enriched_linkedin = sanitize_linkedin_url(enriched.linkedin)
                        existing_linkedin = sanitize_linkedin_url(leader.get("linkedin"))
                        logger.info(
                            f"[Step2] {leader.get('name')}: enriched LinkedIn raw = '{enriched_linkedin_raw}' "
                            f"-> sanitized = '{enriched_linkedin}', existing sanitized = '{existing_linkedin}', "
                            f"final = '{enriched_linkedin or existing_linkedin}'"
                        )
                        leader.update({
                            "email": enriched.email or leader.get("email"),
                            "phone": enriched.phone or leader.get("phone"),
                            "linkedin": enriched_linkedin or existing_linkedin,
                            "bio": enriched.bio or leader.get("bio"),
                            "education": enriched.education,
                            "experience": enriched.experience,
                            "skills": enriched.skills,
                            "certifications": enriched.certifications,
                            "publications": enriched.publications,
                            "cases_handled": enriched.cases_handled,
                            "bar_admissions": enriched.bar_admissions,
                        })
                    else:
                        logger.warning(f"[Step2] {leader.get('name')}: research_leadership_member returned None")
                except Exception as e:
                    logger.warning(f"Failed to research leader {leader.get('name')}: {str(e)}", exc_info=True)

                enriched_leadership.append(leader)

        # Vendor stack detection is its own chain step (detect_vendor_stack_task),
        # so it runs independently even if firm research degrades.

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
                "leadership": strip_nul(enriched_leadership),
                "research_data": strip_nul(research_data),
                "research_status": "completed",
                "last_researched_at": datetime.utcnow()
            }
        )
        db.commit()

        # Auto-trigger leadership email history analysis
        try:
            analyze_leadership_emails_task.delay(pif_id)
            logger.info(f"Queued leadership email history analysis for {pif.firm_name}")
        except Exception as e:
            logger.warning(f"Failed to queue leadership email history analysis: {e}")

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
            db.rollback()
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


def analyze_leadership_email_history(pif_id: str) -> Dict[str, Any]:
    """
    Analyze whether leadership members of a researched PIF firm have personally
    sent emails to Precise Imaging, and what kind of emails they were.

    Args:
        pif_id: UUID string of the PIF record

    Returns:
        Dict with analysis results per leadership member
    """
    from sqlalchemy import select
    from app.models.email import Email
    from app.crud.sync.pif_info import pif_info as pif_info_crud_sync

    FOUNDER_TITLES = ("founder", "managing partner", "owner", "principal", "founding", "partner", "ceo")

    db = SessionLocal()
    try:
        pif = pif_info_crud_sync.get(db, id=UUID(pif_id))
        if not pif:
            logger.error(f"PIF not found for leadership email history: {pif_id}")
            return {"status": "failed", "message": "PIF not found"}

        leadership = pif.leadership or []
        if not leadership:
            logger.info(f"No leadership data for {pif.firm_name}, skipping email history analysis")
            return {"status": "skipped", "message": "No leadership data available"}

        # Extract firm email domains from the firm's emails list
        firm_domains = set()
        for email_addr in (pif.emails or []):
            if "@" in email_addr:
                firm_domains.add(email_addr.split("@")[1].lower())

        logger.info(
            f"Analyzing leadership email history for {pif.firm_name}: "
            f"{len(leadership)} leaders, firm domains: {firm_domains}"
        )

        results = []

        for leader in leadership:
            leader_name = leader.get("name", "").strip()
            leader_title = leader.get("title", "")
            leader_email = leader.get("email", "")

            if not leader_name:
                continue

            # Determine if this person is a "founder" type
            is_founder = any(
                ft in (leader_title or "").lower()
                for ft in FOUNDER_TITLES
            )

            matched_emails = []
            matched_by = None

            # Strategy 1: Match by email address
            if leader_email and "@" in leader_email:
                stmt = select(Email).where(
                    Email.sender.ilike(f"%{leader_email}%")
                )
                result = db.execute(stmt)
                email_matches = result.scalars().all()
                if email_matches:
                    matched_emails = email_matches
                    matched_by = "email"

            # Strategy 2: Match by name + firm domain (if no email match found)
            if not matched_emails and leader_name and firm_domains:
                name_parts = leader_name.split()
                if len(name_parts) >= 2:
                    first_name = name_parts[0]
                    last_name = name_parts[-1]

                    # Search for emails where sender matches name pattern
                    # and cross-reference with firm's known email domains
                    stmt = select(Email).where(
                        Email.sender.ilike(f"%{first_name}%{last_name}%")
                    )
                    result = db.execute(stmt)
                    name_matches = result.scalars().all()

                    # Filter: sender must contain one of the firm's domains
                    domain_filtered = []
                    for em in name_matches:
                        sender_lower = (em.sender or "").lower()
                        if any(domain in sender_lower for domain in firm_domains):
                            domain_filtered.append(em)

                    if domain_filtered:
                        matched_emails = domain_filtered
                        matched_by = "name"

            if not matched_emails:
                # No emails found for this leader
                results.append({
                    "name": leader_name,
                    "title": leader_title,
                    "email": leader_email,
                    "is_founder": is_founder,
                    "total_emails": 0,
                    "first_contact": None,
                    "last_contact": None,
                    "tag_distribution": {},
                    "recent_subjects": [],
                    "matched_by": None,
                })
                continue

            # Aggregate email data
            tag_distribution: Dict[str, int] = {}
            dates = []
            subjects = []

            for em in matched_emails:
                # Collect tags
                for tag in em.tags:
                    tag_name = tag.name
                    tag_distribution[tag_name] = tag_distribution.get(tag_name, 0) + 1

                # Collect dates
                if em.created_at:
                    dates.append(em.created_at)

                # Collect subjects
                if em.subject:
                    subjects.append({
                        "subject": em.subject,
                        "date": em.created_at.isoformat() if em.created_at else None,
                        "conversation_id": em.front_conversation_id,
                    })

            # Sort dates
            dates.sort()
            first_contact = dates[0].isoformat() if dates else None
            last_contact = dates[-1].isoformat() if dates else None

            # Get last 5 subjects (most recent first)
            subjects.sort(key=lambda x: x.get("date") or "", reverse=True)
            recent_subjects = [s["subject"] for s in subjects[:5]]

            results.append({
                "name": leader_name,
                "title": leader_title,
                "email": leader_email,
                "is_founder": is_founder,
                "total_emails": len(matched_emails),
                "first_contact": first_contact,
                "last_contact": last_contact,
                "tag_distribution": tag_distribution,
                "recent_subjects": recent_subjects,
                "matched_by": matched_by,
            })

        # Store results in research_data under 'leadership_email_history'
        research_data = dict(pif.research_data) if pif.research_data else {}
        research_data["leadership_email_history"] = results

        pif_info_crud_sync.update(
            db,
            db_obj=pif,
            obj_in={"research_data": research_data}
        )
        db.commit()

        # Summary stats
        leaders_with_emails = sum(1 for r in results if r["total_emails"] > 0)
        total_matched = sum(r["total_emails"] for r in results)

        logger.info(
            f"Leadership email history completed for {pif.firm_name}: "
            f"{leaders_with_emails}/{len(results)} leaders have sent emails, "
            f"{total_matched} total emails matched"
        )

        return {
            "status": "completed",
            "pif_id": pif_id,
            "firm_name": pif.firm_name,
            "leaders_analyzed": len(results),
            "leaders_with_emails": leaders_with_emails,
            "total_emails_matched": total_matched,
        }

    except Exception as e:
        logger.error(f"Leadership email history error for {pif_id}: {str(e)}", exc_info=True)
        return {
            "status": "failed",
            "pif_id": pif_id,
            "message": f"Leadership email history failed: {str(e)}"
        }
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=ResearchTask,
    name="app.tasks.firm_research.analyze_leadership_emails_task",
    rate_limit="10/m",
)
def analyze_leadership_emails_task(self, pif_id: str) -> Dict[str, Any]:
    """
    Celery task to analyze leadership email history for a PIF firm.

    Args:
        pif_id: UUID string of the PIF record

    Returns:
        Dict with analysis results
    """
    logger.info(f"Starting leadership email history analysis for pif_id={pif_id}")
    return analyze_leadership_email_history(pif_id)


@celery_app.task(
    bind=True,
    base=ResearchTask,
    name="app.tasks.firm_research.research_staff_task",
    rate_limit="10/m",
)
def research_staff_task(self, pif_id: str) -> Dict[str, Any]:
    """
    Background task to research operational staff at a firm.

    Searches for intake specialists, case managers, paralegals, office managers, etc.

    Args:
        pif_id: UUID of the PIF record

    Returns:
        Dict with research results and status
    """
    logger.warning(f"🔬 research_staff_task PICKED UP by worker for pif_id={pif_id}, celery_task_id={self.request.id}")
    import sys
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from pifstats.src.firm_researcher import research_firm_staff
    from app.crud.sync.pif_info import pif_info as pif_info_crud_sync

    db = SessionLocal()

    try:
        pif = pif_info_crud_sync.get(db, id=UUID(pif_id))
        if not pif:
            logger.error(f"PIF not found: {pif_id}")
            return {"status": "failed", "message": "PIF not found"}

        pif_info_crud_sync.update(
            db,
            db_obj=pif,
            obj_in={"staff_research_status": "in_progress"}
        )
        db.commit()

        logger.info(f"Starting staff research for firm: {pif.firm_name}")

        location = pif.addresses[0] if pif.addresses else None

        result = research_firm_staff(
            firm_name=pif.firm_name,
            website=pif.website,
            location=location
        )

        if result is None:
            pif_info_crud_sync.update(
                db,
                db_obj=pif,
                obj_in={"staff_research_status": "failed"}
            )
            db.commit()
            return {
                "status": "failed",
                "pif_id": pif_id,
                "message": "Staff research failed - no results returned"
            }

        # Sanitize LinkedIn URLs
        staff_dicts = []
        for member in result.staff:
            member_dict = member.model_dump()
            member_dict["linkedin"] = sanitize_linkedin_url(member_dict.get("linkedin"))
            staff_dicts.append(member_dict)

        pif_info_crud_sync.update(
            db,
            db_obj=pif,
            obj_in={
                "staff": strip_nul(staff_dicts),
                "staff_research_status": "completed"
            }
        )
        db.commit()

        logger.info(f"Staff research completed for {pif.firm_name}: {len(staff_dicts)} staff members")

        return {
            "status": "completed",
            "pif_id": pif_id,
            "firm_name": pif.firm_name,
            "staff_count": len(staff_dicts),
            "message": f"Staff research completed. Found {len(staff_dicts)} staff members."
        }

    except Exception as e:
        logger.error(f"Staff research task error for {pif_id}: {str(e)}")
        try:
            # Roll back the poisoned transaction first, else the status update
            # below also fails and leaves staff_research_status stuck mid-flight.
            db.rollback()
            pif = pif_info_crud_sync.get(db, id=UUID(pif_id))
            if pif:
                pif_info_crud_sync.update(
                    db,
                    db_obj=pif,
                    obj_in={"staff_research_status": "failed"}
                )
                db.commit()
        except Exception:
            pass

        return {
            "status": "failed",
            "pif_id": pif_id,
            "message": f"Staff research failed: {str(e)}"
        }
    finally:
        db.close()


@celery_app.task(
    bind=True,
    base=ResearchTask,
    name="app.tasks.firm_research.detect_vendor_stack_task",
    rate_limit="30/m",
)
def detect_vendor_stack_task(self, pif_id: str) -> Dict[str, Any]:
    """
    Standalone vendor stack detection for a single firm.

    Runs both detection phases and merges results:
      Phase 1 (inbox): pattern-match known vendor domains in pif.emails — free, high confidence.
      Phase 2 (web):   ask gpt-5-nano+web_search to find vendor mentions in job postings,
                       website, app reviews, partner pages — costs one search call.

    Safe to run on already-researched firms; never clobbers research_status.
    """
    import sys
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from pifstats.src.firm_researcher import (
        detect_vendor_stack_from_emails,
        detect_vendor_stack_from_email_messages,
        analyze_inbox_for_vendors,
        research_vendor_stack,
        merge_vendor_stacks,
    )
    from app.crud.sync.pif_info import pif_info as pif_info_crud_sync

    db = SessionLocal()
    try:
        pif = pif_info_crud_sync.get(db, id=UUID(pif_id))
        if not pif:
            return {"status": "failed", "message": "PIF not found", "pif_id": pif_id}

        # Tier 1: inbox email domains (free, high precision)
        domain_vendors = detect_vendor_stack_from_emails(pif.emails or [])

        # Tier 2a: deterministic scan of message sender/recipient domains and body URLs.
        inbox_emails = _fetch_firm_emails(db, pif)
        message_vendors = detect_vendor_stack_from_email_messages(inbox_emails)

        # Tier 2b: LLM over our own inbox content (catches self-domain vendors)
        inbox_vendors = analyze_inbox_for_vendors(inbox_emails)

        # Tier 3: web research (public signals)
        web_vendors = research_vendor_stack(
            firm_name=pif.firm_name,
            website=pif.canonical_website or pif.website,
        )

        deterministic_vendors = merge_vendor_stacks(domain_vendors, message_vendors, [])
        vendor_stack = merge_vendor_stacks(deterministic_vendors, inbox_vendors, web_vendors)

        pif_info_crud_sync.update(
            db,
            db_obj=pif,
            obj_in={"vendor_stack": vendor_stack or None},
        )
        db.commit()

        logger.info(
            f"Vendor stack detection complete for {pif.firm_name}: "
            f"{[v['vendor'] for v in vendor_stack]}"
        )
        return {
            "status": "completed",
            "pif_id": pif_id,
            "firm_name": pif.firm_name,
            "vendors": [v["vendor"] for v in vendor_stack],
            "domain_detected": [v["vendor"] for v in deterministic_vendors],
            "inbox_detected": [v["vendor"] for v in inbox_vendors],
            "web_detected": [v["vendor"] for v in web_vendors],
        }

    except Exception as e:
        logger.error(f"Vendor stack detection failed for {pif_id}: {e}", exc_info=True)
        return {"status": "failed", "pif_id": pif_id, "message": str(e)}
    finally:
        db.close()
