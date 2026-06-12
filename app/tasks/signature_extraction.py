"""Signature extraction tasks for PIF contact profiles."""

import logging
import os
import sys
from typing import Any, Dict
from uuid import UUID

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.email import Email
from app.tasks.worker import celery_app

logger = get_task_logger(__name__)


def _get_project_root() -> str:
    """Return the project root directory."""
    return os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


@celery_app.task(
    bind=True,
    name="app.tasks.signature_extraction.extract_signatures_task",
    rate_limit="10/m",
)
def extract_signatures_task(self, pif_id: str) -> Dict[str, Any]:
    """
    Extract firm-staff signature metadata into behavioral_data.contact_profiles.

    Only non-consumer sender domains are considered. Patient/case-looking values
    are dropped by the pifstats post-filter before persistence.
    """
    project_root = _get_project_root()
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from app.crud.sync.pif_info import pif_info as pif_info_crud_sync
    from pifstats.src.email_analyzer import (
        detect_sender_role,
        extract_sender_identity,
        is_firm_staff_sender,
        normalize_sender_persona,
    )
    from pifstats.src.signature_extractor import (
        extract_signature_for_sender,
        signature_profile_update,
    )

    db = SessionLocal()
    try:
        pif = pif_info_crud_sync.get(db, id=UUID(pif_id))
        if not pif:
            logger.error(f"PIF not found for signature extraction: {pif_id}")
            return {"status": "failed", "message": "PIF not found", "pif_id": pif_id}

        conv_ids = pif.conversation_ids or []
        if not conv_ids:
            return {"status": "skipped", "message": "No conversations", "pif_id": pif_id}

        result = db.execute(
            select(Email)
            .where(Email.front_conversation_id.in_(conv_ids))
            .order_by(Email.created_at.desc())
        )
        email_rows = result.scalars().all()

        bodies_by_sender: Dict[str, Dict[str, Any]] = {}
        for em in email_rows:
            sender = em.sender or ""
            if not is_firm_staff_sender(sender):
                continue
            _name, email = extract_sender_identity(sender)
            if not email:
                continue
            sender_bucket = bodies_by_sender.setdefault(
                email,
                {"sender": sender, "bodies": [], "latest_email": em},
            )
            if len(sender_bucket["bodies"]) < 2:
                sender_bucket["bodies"].append(em.content_text or em.content_html or "")

        behavioral_data = dict(pif.behavioral_data or {})
        contact_profiles = dict(behavioral_data.get("contact_profiles") or {})
        extracted = 0

        for email, payload in bodies_by_sender.items():
            signature = extract_signature_for_sender(payload["sender"], payload["bodies"])
            signature_update = signature_profile_update(signature)
            profile = dict(contact_profiles.get(email) or {})
            name, _email = extract_sender_identity(payload["sender"])
            profile.setdefault("name", name)
            profile.setdefault(
                "role",
                normalize_sender_persona(signature.get("persona"))
                if signature.get("persona")
                else detect_sender_role("", payload["sender"]),
            )
            profile.setdefault("persona", profile.get("role", "unknown"))
            profile.setdefault("message_count", len(payload["bodies"]))
            profile.setdefault("topic_mix", {})
            profile.setdefault("after_hours_ratio", 0.0)
            latest = payload["latest_email"].created_at
            if latest:
                profile.setdefault("first_seen", latest.isoformat())
                profile.setdefault("last_seen", latest.isoformat())
            profile["signature"] = signature_update
            contact_profiles[email] = profile
            extracted += 1

        behavioral_data["contact_profiles"] = contact_profiles
        pif_info_crud_sync.update(db, db_obj=pif, obj_in={"behavioral_data": behavioral_data})
        db.commit()

        return {
            "status": "completed",
            "pif_id": pif_id,
            "firm_name": pif.firm_name,
            "contacts_processed": extracted,
        }

    except Exception as exc:
        logger.error(f"Signature extraction failed for {pif_id}: {exc}", exc_info=True)
        return {"status": "failed", "pif_id": pif_id, "message": str(exc)}
    finally:
        db.close()
