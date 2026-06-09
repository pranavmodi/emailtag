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
import re
from typing import Any, Dict, List, Optional

import httpx
from celery.utils.log import get_task_logger

from app.core.config import settings
from app.crud.inbox_audit import (
    create_misses_sync,
    create_run_sync,
    get_processed_conversation_ids_sync,
)
from app.db.session import SessionLocal
from app.models.email import Email
from app.models.inbox_audit import MissState, RunStatus
from app.models.processing_trace import StepTypes, TraceStatus
from app.services.trace_service import create_tracer
from app.services.front_api_helpers.inbox_audit_helpers import (
    build_front_url,
    extract_inbound_records,
    list_all_inboxes,
    list_inbound_events_since,
)
from app.tasks.email import process_email
from app.tasks.worker import celery_app

logger = get_task_logger(__name__)

DEFAULT_LOOKBACK_HOURS = settings.INBOX_AUDIT_LOOKBACK_HOURS
FRONT_RATE_LIMIT_RETRY_SECONDS = 60
FRONT_RATE_LIMIT_MAX_RETRY_SECONDS = 15 * 60


def _retry_after_seconds(response: httpx.Response) -> Optional[int]:
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return max(1, int(float(retry_after)))
    except ValueError:
        return None


def _front_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Accept": "application/json",
    }


def _clean_message_body(raw_body: Optional[str]) -> str:
    if not raw_body:
        return ""
    return re.sub("<[^>]*>", "", raw_body).strip()


def _fetch_front_conversation(conversation_id: str) -> Dict[str, Any]:
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        raise ValueError("Missing required Front configuration")

    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}"
    with httpx.Client(verify=False, timeout=30.0) as client:
        response = client.get(url, headers=_front_headers())
        response.raise_for_status()
        return response.json()


def _fetch_front_messages(conversation_id: str) -> List[Dict[str, Any]]:
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        raise ValueError("Missing required Front configuration")

    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/messages"
    messages: List[Dict[str, Any]] = []
    with httpx.Client(verify=False, timeout=30.0) as client:
        while url:
            response = client.get(url, headers=_front_headers())
            response.raise_for_status()
            payload = response.json()
            messages.extend(payload.get("_results") or [])
            pagination = payload.get("_pagination") or {}
            url = pagination.get("next")

    return sorted(messages, key=lambda item: item.get("created_at") or 0)


def _message_sender(message: Dict[str, Any], conversation: Dict[str, Any]) -> str:
    author = message.get("author") or {}
    if author.get("email"):
        return author["email"]
    if author.get("handle"):
        return author["handle"]

    for recipient in message.get("recipients") or []:
        if recipient.get("role") == "from" and recipient.get("handle"):
            return recipient["handle"]

    return (
        ((conversation.get("recipient") or {}).get("handle"))
        or "unknown@inbox-audit.local"
    )


def _message_recipients(message: Dict[str, Any]) -> List[str]:
    recipients: List[str] = []
    for recipient in message.get("recipients") or []:
        if recipient.get("role") not in {"to", "cc"}:
            continue
        handle = recipient.get("handle") or recipient.get("email")
        if handle:
            recipients.append(handle)
    return recipients


def _is_inbound_message(message: Dict[str, Any]) -> bool:
    if message.get("is_inbound") is not None:
        return message.get("is_inbound") is True
    if message.get("direction"):
        return message.get("direction") == "inbound"
    for recipient in message.get("recipients") or []:
        if recipient.get("role") == "from" and recipient.get("handle"):
            return True
    return False


def _latest_processable_message(messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    inbound_messages = [message for message in messages if _is_inbound_message(message)]
    candidates = inbound_messages or messages
    return candidates[-1] if candidates else None


def _classify_audit_conversations(
    conversation_ids: List[str],
    *,
    stored_conversations: set,
    seen_conversations: set,
    processed_conversations: set,
) -> Dict[str, List[str]]:
    """Classify Front conversations by where they stopped in our pipeline."""
    processed_ids = [
        cid
        for cid in conversation_ids
        if cid in stored_conversations and cid in processed_conversations
    ]
    never_received_ids = [
        cid
        for cid in conversation_ids
        if cid not in stored_conversations and cid not in seen_conversations
    ]
    received_but_failed_ids = [
        cid
        for cid in conversation_ids
        if cid not in processed_ids and cid not in never_received_ids
    ]
    return {
        "processed": processed_ids,
        "never_received": never_received_ids,
        "received_but_failed": received_but_failed_ids,
    }


@celery_app.task(
    bind=True,
    name="app.tasks.inbox_audit.queue_conversation_for_processing",
    max_retries=8,
)
def queue_conversation_for_processing(self, conversation_id: str) -> Dict[str, Any]:
    """Create a local email record from Front and queue the normal email pipeline."""
    tracer = create_tracer(front_conversation_id=conversation_id)
    db = SessionLocal()
    try:
        tracer.log_step(
            step_name="inbox_audit_recovery_started",
            step_type=StepTypes.TASK_QUEUE,
            status=TraceStatus.COMPLETED,
            input_data={"conversation_id": conversation_id},
        )

        conversation = _fetch_front_conversation(conversation_id)
        messages = _fetch_front_messages(conversation_id)
        latest_message = _latest_processable_message(messages)
        if not latest_message:
            tracer.log_step(
                step_name="inbox_audit_recovery_failed",
                step_type=StepTypes.API_CALL,
                status=TraceStatus.FAILED,
                error_data={"error_message": "No Front messages found"},
            )
            return {
                "status": "error",
                "conversation_id": conversation_id,
                "message": "No Front messages found",
            }

        subject = latest_message.get("subject") or conversation.get("subject") or ""
        raw_body = latest_message.get("body") or latest_message.get("text") or ""
        content_text = _clean_message_body(raw_body)
        attachments = latest_message.get("attachments") or []

        email_obj = Email(
            front_conversation_id=conversation_id,
            subject=subject,
            sender=_message_sender(latest_message, conversation),
            recipients=_message_recipients(latest_message),
            content_text=content_text,
            content_html=raw_body,
            has_attachments=bool(attachments),
            raw_data={
                "source": "inbox_audit_recovery",
                "conversation": conversation,
                "target": {"data": latest_message},
            },
        )
        db.add(email_obj)
        db.commit()
        db.refresh(email_obj)

        process_result = process_email.apply_async(args=[str(email_obj.id)], queue="emails")
        tracer.log_step(
            step_name="inbox_audit_recovery_queued",
            step_type=StepTypes.TASK_QUEUE,
            status=TraceStatus.COMPLETED,
            output_data={
                "email_id": str(email_obj.id),
                "process_task_id": process_result.id,
                "conversation_id": conversation_id,
                "attachments": len(attachments),
            },
        )
        logger.info(
            "Inbox audit recovery queued conversation %s as email %s with %s attachment(s)",
            conversation_id,
            email_obj.id,
            len(attachments),
        )
        return {
            "status": "queued",
            "conversation_id": conversation_id,
            "email_id": str(email_obj.id),
            "process_task_id": process_result.id,
            "attachments": len(attachments),
        }
    except httpx.HTTPStatusError as exc:
        db.rollback()
        if exc.response.status_code == 429:
            retry_after = _retry_after_seconds(exc.response)
            fallback_delay = min(
                FRONT_RATE_LIMIT_MAX_RETRY_SECONDS,
                FRONT_RATE_LIMIT_RETRY_SECONDS * (2 ** self.request.retries),
            )
            countdown = retry_after or fallback_delay
            logger.warning(
                "Front rate limited inbox audit recovery for %s; retrying in %ss",
                conversation_id,
                countdown,
            )
            raise self.retry(exc=exc, countdown=countdown)

        logger.exception("Inbox audit recovery failed for %s: %s", conversation_id, exc)
        tracer.log_step(
            step_name="inbox_audit_recovery_failed",
            step_type=StepTypes.ERROR_HANDLING,
            status=TraceStatus.FAILED,
            error_data={"error_type": type(exc).__name__, "error_message": str(exc)},
        )
        return {
            "status": "error",
            "conversation_id": conversation_id,
            "message": str(exc),
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Inbox audit recovery failed for %s: %s", conversation_id, exc)
        tracer.log_step(
            step_name="inbox_audit_recovery_failed",
            step_type=StepTypes.ERROR_HANDLING,
            status=TraceStatus.FAILED,
            error_data={"error_type": type(exc).__name__, "error_message": str(exc)},
        )
        return {
            "status": "error",
            "conversation_id": conversation_id,
            "message": str(exc),
        }
    finally:
        db.close()


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
        in_email, seen_by_webhook, with_success_trace = get_processed_conversation_ids_sync(
            db, conversation_ids
        )

        classified = _classify_audit_conversations(
            conversation_ids,
            stored_conversations=in_email,
            seen_conversations=seen_by_webhook,
            processed_conversations=with_success_trace,
        )
        never_received_ids = classified["never_received"]
        received_but_failed_ids = classified["received_but_failed"]
        processed_count = len(classified["processed"])
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
                    "reason": "Inbound message in Front but no webhook trace or email row exists.",
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
                    "reason": (
                        "Webhook/email was received, but processing did not reach a "
                        "downstream completion step."
                    ),
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
