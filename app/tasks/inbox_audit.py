"""Daily inbox audit Celery tasks.

Architecture:
  1. `audit_all_inboxes` does ONE paginated Front `/events?q[types]=inbound`
     query, groups the resulting messages by inbox, and dispatches a
     `audit_single_inbox` task per inbox with the conversation list pre-baked.
  2. `audit_single_inbox` performs the DB diff and persists the run + misses.

Only inbound messages are considered — outbound activity from teammates is
never expected to flow through our webhook pipeline, so including it would
produce massive false-positive "missed" counts.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from celery.utils.log import get_task_logger

from app.crud.inbox_audit import (
    create_misses_sync,
    create_run_sync,
    get_processed_conversation_ids_sync,
)
from app.db.session import SessionLocal
from app.models.inbox_audit import MissState, RunStatus
from app.services.front_api_helpers.inbox_audit_helpers import (
    build_front_url,
    extract_inbound_records,
    list_all_inboxes,
    list_inbound_events_since,
)
from app.tasks.worker import celery_app

logger = get_task_logger(__name__)

DEFAULT_LOOKBACK_HOURS = 24


@celery_app.task(name="app.tasks.inbox_audit.audit_all_inboxes")
def audit_all_inboxes(lookback_hours: int = DEFAULT_LOOKBACK_HOURS) -> Dict[str, Any]:
    """Fetch inbound events once, group by inbox, fan out per-inbox sub-tasks."""
    lookback_end = datetime.utcnow()
    lookback_start = lookback_end - timedelta(hours=lookback_hours)
    after_unix = int(lookback_start.timestamp())

    inboxes = list_all_inboxes()
    inbox_meta: Dict[str, Dict[str, Optional[str]]] = {
        i["id"]: {"name": i.get("name"), "address": i.get("address")}
        for i in inboxes
        if i.get("id")
    }
    logger.info(f"Inbox audit: {len(inbox_meta)} inboxes visible to Front token")

    events = list_inbound_events_since(after_unix)
    records = extract_inbound_records(events)
    logger.info(
        f"Inbox audit: fetched {len(events)} inbound events, "
        f"{len(records)} (inbox, conversation) records"
    )

    by_inbox: Dict[str, Dict[str, Optional[str]]] = defaultdict(dict)
    for r in records:
        by_inbox[r["inbox_id"]][r["conversation_id"]] = r.get("subject")

    dispatched: List[str] = []
    for inbox_id, meta in inbox_meta.items():
        conv_subjects = by_inbox.get(inbox_id, {})
        audit_single_inbox.delay(
            inbox_id=inbox_id,
            inbox_name=meta["name"],
            inbox_address=meta["address"],
            lookback_start_iso=lookback_start.isoformat(),
            lookback_end_iso=lookback_end.isoformat(),
            conv_subjects=conv_subjects,
        )
        dispatched.append(inbox_id)

    return {
        "dispatched_inboxes": len(dispatched),
        "total_events": len(events),
        "total_records": len(records),
    }


@celery_app.task(name="app.tasks.inbox_audit.audit_single_inbox")
def audit_single_inbox(
    inbox_id: str,
    inbox_name: Optional[str],
    inbox_address: Optional[str],
    lookback_start_iso: str,
    lookback_end_iso: str,
    conv_subjects: Dict[str, Optional[str]],
) -> Dict[str, Any]:
    """Diff one inbox's inbound conversations against our DB and persist."""
    lookback_start = datetime.fromisoformat(lookback_start_iso)
    lookback_end = datetime.fromisoformat(lookback_end_iso)
    conversation_ids = list(conv_subjects.keys())
    total_received = len(conversation_ids)

    db = SessionLocal()
    try:
        in_email, with_success_trace = get_processed_conversation_ids_sync(
            db, conversation_ids
        )

        never_received_ids = [cid for cid in conversation_ids if cid not in in_email]
        received_but_failed_ids = [
            cid
            for cid in conversation_ids
            if cid in in_email and cid not in with_success_trace
        ]
        processed_count = len(
            [cid for cid in conversation_ids if cid in in_email and cid in with_success_trace]
        )
        missed_count = len(never_received_ids) + len(received_but_failed_ids)

        run = create_run_sync(
            db,
            inbox_id=inbox_id,
            inbox_name=inbox_name,
            inbox_address=inbox_address,
            lookback_start=lookback_start,
            lookback_end=lookback_end,
            total_received=total_received,
            total_processed=processed_count,
            total_missed=missed_count,
            status=RunStatus.SUCCESS,
        )

        miss_rows: List[Dict[str, Any]] = []
        for cid in never_received_ids:
            miss_rows.append(
                {
                    "conversation_id": cid,
                    "front_url": build_front_url(cid),
                    "inbox_id": inbox_id,
                    "inbox_name": inbox_name,
                    "state": MissState.NEVER_RECEIVED,
                    "reason": "Inbound message in Front but no row in email table — webhook did not deliver.",
                    "subject": conv_subjects.get(cid),
                }
            )
        for cid in received_but_failed_ids:
            miss_rows.append(
                {
                    "conversation_id": cid,
                    "front_url": build_front_url(cid),
                    "inbox_id": inbox_id,
                    "inbox_name": inbox_name,
                    "state": MissState.RECEIVED_BUT_FAILED,
                    "reason": "Email row exists but no processing trace reached 'completed'.",
                    "subject": conv_subjects.get(cid),
                }
            )

        created = create_misses_sync(db, audit_run_id=run.id, misses=miss_rows)
        logger.info(
            f"Inbox {inbox_id} ({inbox_name}): received={total_received} "
            f"processed={processed_count} missed={missed_count} (persisted {created} miss rows)"
        )

        return {
            "inbox_id": inbox_id,
            "status": "success",
            "total_received": total_received,
            "total_processed": processed_count,
            "total_missed": missed_count,
        }
    finally:
        db.close()
