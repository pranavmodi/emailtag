"""Build a read-only model-evaluation pilot from Front and EmailTag data."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.core.config import settings
from app.models.autorespond_event import AutorespondEvent
from app.models.classification_trace import ClassificationTrace
from app.models.email import Email, Tag
from app.models.processing_trace import EmailProcessingTrace


ACTION_STEPS = {
    "front_tags_applied": ("tag_applied", "Tags applied"),
    "front_tags_removed": ("tag_removed", "Tags removed"),
    "conversation_split": ("conversation_split", "Conversation split"),
    "status_updated": ("status_updated", "Conversation status updated"),
    "agent_selected": ("agent_selected", "Agent selected"),
    "agent_execution": ("agent_execution", "Agent executed"),
    "response_generated": ("response_generated", "Response generated"),
    "response_sent": ("response_sent", "Response sent"),
    "autorespond_completed": ("autorespond_completed", "Autorespond completed"),
    "archive_check": ("archive_decision", "Archive decision"),
}

VISIBLE_DETAIL_KEYS = {
    "agent",
    "agent_handled",
    "applied_tags",
    "archived",
    "chosen_option",
    "final_status",
    "new_status",
    "reason",
    "removed_tags",
    "response_sent",
    "status",
    "tag_names",
    "tags",
    "target_inbox",
    "triggered_tags",
}

PILOT_CACHE_TTL_SECONDS = 3600
_pilot_cache: Dict[tuple[int, bool], tuple[float, Dict[str, Any]]] = {}
_pilot_cache_lock = asyncio.Lock()


async def fetch_front_tagged_conversation_ids(tag_name: str) -> set[str]:
    """Fetch all current Front conversation IDs for a tag with a few bulk calls."""
    headers = {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(
        verify=False, timeout=30.0, follow_redirects=True
    ) as client:
        response = await client.get(f"{settings.FRONT_API_BASE_URL}/tags", headers=headers)
        response.raise_for_status()
        tags = response.json().get("_results", [])
        matching = next(
            (tag for tag in tags if (tag.get("name") or "").lower() == tag_name.lower()),
            None,
        )
        if not matching:
            return set()

        url: Optional[str] = (
            f"{settings.FRONT_API_BASE_URL}/tags/{matching['id']}/conversations"
        )
        params: Dict[str, Any] = {"limit": 100}
        conversation_ids: set[str] = set()
        pages_fetched = 0
        while url and pages_fetched < 5:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            payload = response.json()
            conversation_ids.update(
                conversation["id"]
                for conversation in payload.get("_results", [])
                if conversation.get("id")
            )
            url = (payload.get("_pagination") or {}).get("next")
            params = {}
            pages_fetched += 1
        return conversation_ids


def configured_benchmark_tags(hierarchy: Dict[str, Any]) -> List[str]:
    """Return actual classifier outputs, excluding hierarchy-only headings."""
    tags: List[str] = []

    def add(tag: str) -> None:
        if tag and tag not in tags:
            tags.append(tag)

    def visit(value: Any, path: Sequence[str]) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                # Lien processing intentionally applies signer type plus document type.
                if key in {"PSL", "ASL"} and "Liens" in path:
                    add(key)
                if isinstance(child, str):
                    add(child)
                else:
                    visit(child, [*path, key])
        elif isinstance(value, list):
            for child in value:
                if isinstance(child, str):
                    add(child)
                else:
                    visit(child, path)
        elif isinstance(value, str):
            add(value)

    visit(hierarchy, [])
    return tags


async def fetch_tag_quota_candidates(
    db: AsyncSession,
    *,
    tag_names: Sequence[str],
    candidates_per_tag: int = 30,
) -> tuple[List[Dict[str, Any]], Dict[str, set[str]]]:
    """Load recent one-email DB candidates for every configured output tag."""
    candidates_by_id: Dict[str, Dict[str, Any]] = {}
    candidate_ids_by_tag: Dict[str, List[str]] = {tag: [] for tag in tag_names}
    comparison_email = aliased(Email)
    email_count = (
        select(func.count(comparison_email.id))
        .where(comparison_email.front_conversation_id == Email.front_conversation_id)
        .correlate(Email)
        .scalar_subquery()
    )

    for tag_name in tag_names:
        query = (
            select(Email)
            .where(email_count == 1)
            .where(
                exists().where(
                    ClassificationTrace.front_conversation_id
                    == Email.front_conversation_id
                )
            )
            .where(~Email.tags.any(func.lower(Tag.name) == "ai:training"))
            .options(selectinload(Email.tags))
            .order_by(Email.created_at.desc())
            .limit(candidates_per_tag)
        )
        if tag_name == "No Tag":
            query = query.where(
                exists().where(
                    (ClassificationTrace.front_conversation_id == Email.front_conversation_id)
                    & (func.lower(ClassificationTrace.chosen_option) == "no tag")
                )
            )
        else:
            query = query.where(Email.tags.any(func.lower(Tag.name) == tag_name.lower()))

        result = await db.execute(query)
        for email in result.scalars().all():
            conversation_id = email.front_conversation_id
            if not conversation_id:
                continue
            candidate_ids_by_tag[tag_name].append(conversation_id)
            candidate = candidates_by_id.setdefault(
                conversation_id,
                {
                    "id": conversation_id,
                    "sample_tags": set(),
                    "subject": email.subject,
                    "created_at": email.created_at.timestamp() if email.created_at else None,
                    "status": email.status,
                    "assignee": None,
                    "tags": [
                        {"name": tag.name} for tag in (email.tags or []) if tag.name
                    ],
                    "messages": [
                        {
                            "id": str(email.id),
                            "author_name": None,
                            "author_email": email.sender,
                            "author_handle": email.sender,
                            "direction": "inbound",
                            "is_inbound": True,
                            "created_at": email.created_at.isoformat()
                            if email.created_at
                            else None,
                            "body": email.content_html,
                            "text_body": email.content_text,
                            "subject": email.subject,
                            "attachments": [],
                        }
                    ],
                },
            )
            candidate["sample_tags"].add(tag_name)

    ordered_candidates: List[Dict[str, Any]] = []
    added: set[str] = set()
    max_candidates = max((len(ids) for ids in candidate_ids_by_tag.values()), default=0)
    for index in range(max_candidates):
        for tag_name in tag_names:
            ids = candidate_ids_by_tag[tag_name]
            if index >= len(ids) or ids[index] in added:
                continue
            conversation_id = ids[index]
            added.add(conversation_id)
            candidate = candidates_by_id[conversation_id]
            candidate["sample_tags"] = sorted(candidate["sample_tags"])
            ordered_candidates.append(candidate)

    return ordered_candidates, {
        tag_name: set(ids) for tag_name, ids in candidate_ids_by_tag.items()
    }


def _group_by_conversation(
    records: Iterable[Any],
    attribute: str = "front_conversation_id",
) -> Dict[str, List[Any]]:
    grouped: Dict[str, List[Any]] = defaultdict(list)
    for record in records:
        conversation_id = getattr(record, attribute, None)
        if conversation_id:
            grouped[conversation_id].append(record)
    return grouped


def _compact_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 500 else f"{value[:497]}..."
    if isinstance(value, list):
        return [_compact_value(item) for item in value[:25]]
    if isinstance(value, dict):
        return {
            str(key): _compact_value(item)
            for key, item in value.items()
            if key in VISIBLE_DETAIL_KEYS
        }
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _compact_trace_details(trace: EmailProcessingTrace) -> Dict[str, Any]:
    details: Dict[str, Any] = {}
    for payload in (trace.input_data or {}, trace.output_data or {}, trace.error_data or {}):
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if key in VISIBLE_DETAIL_KEYS:
                details[key] = _compact_value(value)
    details["trace_status"] = trace.status
    return details


def derive_actions(
    messages: Sequence[Dict[str, Any]],
    processing_traces: Sequence[EmailProcessingTrace],
    autorespond_events: Sequence[AutorespondEvent],
) -> List[Dict[str, Any]]:
    """Derive a compact chronological action timeline."""
    actions: List[Dict[str, Any]] = []

    for message in messages:
        if message.get("is_inbound") is False:
            actions.append(
                {
                    "action_type": "outbound_reply",
                    "label": "Outbound reply sent",
                    "source": "front",
                    "timestamp": message.get("created_at"),
                    "details": {"message_id": message.get("id")},
                }
            )

    for trace in processing_traces:
        action_definition = ACTION_STEPS.get(trace.step_name)
        if not action_definition:
            continue
        action_type, label = action_definition
        actions.append(
            {
                "action_type": action_type,
                "label": label,
                "source": "emailtag_trace",
                "timestamp": trace.completed_at or trace.started_at or trace.created_at,
                "details": _compact_trace_details(trace),
            }
        )

    for event in autorespond_events:
        actions.append(
            {
                "action_type": "autorespond_sent" if event.response_sent else "autorespond_skipped",
                "label": "Autorespond sent" if event.response_sent else "Autorespond not sent",
                "source": "autorespond_event",
                "timestamp": event.created_at,
                "details": {
                    "agent": event.agent_type,
                    "response_sent": event.response_sent,
                    "tags": list(event.tags or []),
                    "test_mode": event.test_mode,
                },
            }
        )

    def sort_key(action: Dict[str, Any]) -> str:
        timestamp = action.get("timestamp")
        if isinstance(timestamp, datetime):
            return timestamp.isoformat()
        return str(timestamp or "")

    actions.sort(key=sort_key)
    return actions


def _assignee_label(conversation: Dict[str, Any]) -> Optional[str]:
    assignee = conversation.get("assignee") or {}
    return (
        assignee.get("name")
        or " ".join(
            filter(None, [assignee.get("first_name"), assignee.get("last_name")])
        ).strip()
        or assignee.get("email")
        or None
    )


def _front_timestamp(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc) if value else None
    except (TypeError, ValueError, OSError):
        return None


async def _hydrate_candidate_safely(
    candidate: Dict[str, Any],
    semaphore: asyncio.Semaphore,
    single_message_only: bool,
) -> tuple[str, Optional[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    conversation_id = candidate.get("id") or ""
    try:
        async with semaphore:
            messages = candidate.get("messages") or []
            if single_message_only and not is_single_inbound_message(messages):
                return conversation_id, None, messages, "Not a single inbound message"
        conversation = dict(candidate)
        conversation["sample_tags"] = candidate.get("sample_tags") or []
        return conversation_id, conversation, messages, None
    except Exception as exc:
        return conversation_id, None, [], str(exc)


def is_single_inbound_message(messages: Sequence[Dict[str, Any]]) -> bool:
    """Return whether a conversation is a single inbound-message classification case."""
    return len(messages) == 1 and messages[0].get("is_inbound") is True


async def _select_front_conversations(
    candidates: Sequence[Dict[str, Any]],
    *,
    examples_per_tag: int,
    tag_names: Sequence[str],
    candidate_ids_by_tag: Dict[str, set[str]],
    single_message_only: bool,
) -> tuple[
    List[Dict[str, Any]],
    Dict[str, tuple[List[Dict[str, Any]], Optional[str]]],
    int,
    Dict[str, int],
]:
    """Fetch candidates until every tag quota is filled or exhausted."""
    selected: List[Dict[str, Any]] = []
    messages_by_conversation: Dict[
        str, tuple[List[Dict[str, Any]], Optional[str]]
    ] = {}
    semaphore = asyncio.Semaphore(3)
    candidates_scanned = 0
    coverage = {tag_name: 0 for tag_name in tag_names}
    remaining = {
        tag_name: set(conversation_ids)
        for tag_name, conversation_ids in candidate_ids_by_tag.items()
    }

    for start in range(0, len(candidates), 20):
        batch = candidates[start : start + 20]
        hydrated_results = await asyncio.gather(
            *[
                _hydrate_candidate_safely(candidate, semaphore, single_message_only)
                for candidate in batch
            ]
        )
        hydrated_by_id = {
            conversation_id: (conversation, messages, error)
            for conversation_id, conversation, messages, error in hydrated_results
        }

        for candidate in batch:
            candidates_scanned += 1
            conversation_id = candidate.get("id") or ""
            for tag_name in candidate.get("sample_tags", []):
                remaining[tag_name].discard(conversation_id)
            conversation, messages, error = hydrated_by_id.get(
                conversation_id, (None, [], "Conversation not loaded")
            )
            if error or not conversation:
                continue
            if single_message_only and not is_single_inbound_message(messages):
                continue
            current_tags = {
                (tag.get("name") or "").lower() for tag in conversation.get("tags", [])
            }
            if "ai:training" in current_tags:
                continue

            credited_tags = [
                tag_name
                for tag_name in candidate.get("sample_tags", [])
                if coverage[tag_name] < examples_per_tag
            ]
            if not credited_tags:
                continue
            conversation["sample_tags"] = credited_tags
            selected.append(conversation)
            for tag_name in credited_tags:
                coverage[tag_name] += 1
            messages_by_conversation[conversation_id] = (messages, None)
        if all(
            coverage[tag_name] >= examples_per_tag or not remaining[tag_name]
            for tag_name in tag_names
        ):
            break

    return selected, messages_by_conversation, candidates_scanned, coverage


async def _build_model_evaluation_pilot(
    db: AsyncSession,
    *,
    examples_per_tag: int = 5,
    single_message_only: bool = True,
) -> Dict[str, Any]:
    """Join five examples per configured output tag with EmailTag history."""
    tag_names = configured_benchmark_tags(settings.EMAIL_CATEGORIES)
    candidates, candidate_ids_by_tag = await fetch_tag_quota_candidates(
        db,
        tag_names=tag_names,
    )
    excluded_training_ids = await fetch_front_tagged_conversation_ids("AI:Training")
    if excluded_training_ids:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.get("id") not in excluded_training_ids
        ]
        candidate_ids_by_tag = {
            tag_name: conversation_ids - excluded_training_ids
            for tag_name, conversation_ids in candidate_ids_by_tag.items()
        }
    (
        front_conversations,
        messages_by_conversation,
        candidates_scanned,
        coverage,
    ) = await _select_front_conversations(
        candidates,
        examples_per_tag=examples_per_tag,
        tag_names=tag_names,
        candidate_ids_by_tag=candidate_ids_by_tag,
        single_message_only=single_message_only,
    )
    conversation_ids = [item["id"] for item in front_conversations if item.get("id")]

    email_result = await db.execute(
        select(Email)
        .where(Email.front_conversation_id.in_(conversation_ids))
        .options(selectinload(Email.tags))
        .order_by(Email.created_at.asc())
    )
    trace_result = await db.execute(
        select(EmailProcessingTrace)
        .where(EmailProcessingTrace.front_conversation_id.in_(conversation_ids))
        .order_by(EmailProcessingTrace.started_at.asc())
    )
    classification_result = await db.execute(
        select(ClassificationTrace)
        .where(ClassificationTrace.front_conversation_id.in_(conversation_ids))
        .order_by(ClassificationTrace.started_at.asc(), ClassificationTrace.step_order.asc())
    )
    autorespond_result = await db.execute(
        select(AutorespondEvent)
        .where(AutorespondEvent.conversation_id.in_(conversation_ids))
        .order_by(AutorespondEvent.created_at.asc())
    )

    emails_by_conversation = _group_by_conversation(email_result.scalars().all())
    traces_by_conversation = _group_by_conversation(trace_result.scalars().all())
    classifications_by_conversation = _group_by_conversation(
        classification_result.scalars().all()
    )
    autoresponds_by_conversation = _group_by_conversation(
        autorespond_result.scalars().all(), attribute="conversation_id"
    )

    records: List[Dict[str, Any]] = []
    for conversation in front_conversations:
        conversation_id = conversation["id"]
        emails = emails_by_conversation.get(conversation_id, [])
        processing_traces = traces_by_conversation.get(conversation_id, [])
        classification_traces = classifications_by_conversation.get(conversation_id, [])
        autorespond_events = autoresponds_by_conversation.get(conversation_id, [])
        messages, load_error = messages_by_conversation.get(conversation_id, ([], None))

        stored_tags = sorted(
            {
                tag.name
                for email in emails
                for tag in (email.tags or [])
                if getattr(tag, "name", None)
            }
        )
        emailtag_statuses = list(
            dict.fromkeys(email.status for email in emails if email.status)
        )
        current_tags = sorted(
            {
                tag.get("name")
                for tag in conversation.get("tags", [])
                if tag.get("name")
            }
        )
        classifications = [
            {
                "step_name": trace.step_name,
                "step_order": trace.step_order,
                "classification_path": trace.classification_path,
                "chosen_option": trace.chosen_option,
                "classification_reason": trace.classification_reason,
                "llm_model": trace.llm_model,
                "total_tokens": trace.total_tokens,
                "created_at": trace.created_at,
            }
            for trace in classification_traces
        ]
        attachment_count = sum(len(message.get("attachments") or []) for message in messages)
        ocr_result_count = sum(len(email.ocr_results or []) for email in emails)
        outbound_reply_count = sum(message.get("is_inbound") is False for message in messages)

        records.append(
            {
                "conversation_id": conversation_id,
                "sample_tags": conversation.get("sample_tags") or [],
                "subject": conversation.get("subject"),
                "front_url": f"https://app.frontapp.com/open/{conversation_id}",
                "created_at": _front_timestamp(conversation.get("created_at")),
                "status": conversation.get("status"),
                "assignee": _assignee_label(conversation),
                "current_tags": current_tags,
                "stored_tags": stored_tags,
                "emailtag_statuses": emailtag_statuses,
                "messages": messages,
                "classifications": classifications,
                "actions": derive_actions(messages, processing_traces, autorespond_events),
                "email_record_count": len(emails),
                "outbound_reply_count": outbound_reply_count,
                "attachment_count": attachment_count,
                "ocr_result_count": ocr_result_count,
                "ground_truth": {"status": "unreviewed"},
                "load_error": load_error,
            }
        )

    failed_count = sum(bool(record["load_error"]) for record in records)
    return {
        "source_population": "recent_emailtag_classifications",
        "selection_criteria": (
            "five_per_configured_tag_exactly_one_inbound_excluding_ai_training"
            if single_message_only
            else "five_per_configured_tag_excluding_ai_training"
        ),
        "candidates_scanned": candidates_scanned,
        "examples_per_tag": examples_per_tag,
        "configured_tag_count": len(tag_names),
        "requested_example_count": len(tag_names) * examples_per_tag,
        "tag_coverage": [
            {
                "tag_name": tag_name,
                "requested": examples_per_tag,
                "found": coverage[tag_name],
                "missing": max(0, examples_per_tag - coverage[tag_name]),
            }
            for tag_name in tag_names
        ],
        "conversation_count": len(records),
        "loaded_count": len(records) - failed_count,
        "failed_count": failed_count,
        "generated_at": datetime.now(timezone.utc),
        "conversations": records,
    }


async def build_model_evaluation_pilot(
    db: AsyncSession,
    *,
    examples_per_tag: int = 5,
    single_message_only: bool = True,
    refresh: bool = False,
) -> Dict[str, Any]:
    """Return a cached pilot, rebuilding only when requested or expired."""
    cache_key = (examples_per_tag, single_message_only)
    cached = _pilot_cache.get(cache_key)
    if not refresh and cached and monotonic() - cached[0] < PILOT_CACHE_TTL_SECONDS:
        return cached[1]

    async with _pilot_cache_lock:
        cached = _pilot_cache.get(cache_key)
        if not refresh and cached and monotonic() - cached[0] < PILOT_CACHE_TTL_SECONDS:
            return cached[1]
        payload = await _build_model_evaluation_pilot(
            db,
            examples_per_tag=examples_per_tag,
            single_message_only=single_message_only,
        )
        _pilot_cache[cache_key] = (monotonic(), payload)
        return payload
