"""Read-only Front inbox viewer endpoints for PIFStats."""

import asyncio
import base64
import json
import logging
import re
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urljoin, urlparse

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

FRONT_MIN_REQUEST_INTERVAL_SECONDS = 2.0
FRONT_MAX_RETRIES = 4
FRONT_DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 10.0
MAX_EXPORT_DAYS = 7
MAX_EXPORT_CONVERSATIONS = 250
EXPORT_DIR = Path("data/pif_inbox_exports")

_front_request_lock = asyncio.Lock()
_front_last_request_at = 0.0
_export_jobs: Dict[str, Dict[str, Any]] = {}


class InboxExportRequest(BaseModel):
    inbox_id: str
    inbox_name: Optional[str] = None
    date_from: str = Field(..., description="Start date in YYYY-MM-DD, UTC")
    date_to: str = Field(..., description="End date in YYYY-MM-DD, UTC inclusive")


def _front_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Accept": "application/json",
    }


def _front_base_url() -> str:
    return settings.FRONT_API_BASE_URL.rstrip("/")


def _encode_cursor(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> str:
    try:
        url = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination cursor",
        ) from exc

    parsed = urlparse(url)
    configured = urlparse(_front_base_url())
    allowed_hosts = {configured.netloc, "api2.frontapp.com"}
    is_front_workspace_host = parsed.netloc.endswith(".api.frontapp.com")
    if parsed.scheme != "https" or (parsed.netloc not in allowed_hosts and not is_front_workspace_host):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination cursor",
        )
    return url


def _normalize_front_url(path_or_url: Optional[str]) -> Optional[str]:
    if not path_or_url:
        return None
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    base = _front_base_url().rstrip("/")
    if not path_or_url.startswith("/"):
        path_or_url = f"/{path_or_url}"
    return urljoin(base + "/", path_or_url.lstrip("/"))


def _validate_front_url(url: str) -> None:
    parsed = urlparse(url)
    configured = urlparse(_front_base_url())
    allowed_hosts = {configured.netloc, "api2.frontapp.com"}
    is_front_workspace_host = parsed.netloc.endswith(".api.frontapp.com")
    if parsed.scheme != "https" or (parsed.netloc not in allowed_hosts and not is_front_workspace_host):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Front URL",
        )


def _extract_attachment_url(attachment: Dict[str, Any]) -> Optional[str]:
    candidate = attachment.get("url")
    if candidate:
        return _normalize_front_url(candidate)

    links = attachment.get("_links") or {}
    related = links.get("related") or {}
    for key in ("download", "self"):
        candidate = related.get(key) or links.get(key)
        if candidate:
            return _normalize_front_url(candidate)
    return None


def _timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
    return str(value)


def _recipient_label(recipient: Optional[Dict[str, Any]]) -> str:
    if not recipient:
        return ""
    return recipient.get("name") or recipient.get("handle") or ""


def _normalize_recipients(recipients: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [
        {
            "name": item.get("name") or "",
            "handle": item.get("handle") or "",
            "role": item.get("role") or "",
        }
        for item in recipients or []
    ]


def _normalize_tags(tags: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [
        {
            "id": item.get("id") or "",
            "name": item.get("name") or "",
            "highlight": item.get("highlight") or "",
        }
        for item in tags or []
    ]


def _normalize_conversation(conversation: Dict[str, Any]) -> Dict[str, Any]:
    conversation_id = conversation.get("id") or ""
    return {
        "id": conversation_id,
        "subject": conversation.get("subject") or "(No subject)",
        "status": conversation.get("status") or "",
        "status_category": conversation.get("status_category") or "",
        "assignee_name": _recipient_label(conversation.get("assignee")),
        "recipient_name": _recipient_label(conversation.get("recipient")),
        "recipient_handle": (conversation.get("recipient") or {}).get("handle") or "",
        "tags": _normalize_tags(conversation.get("tags") or []),
        "created_at": _timestamp(conversation.get("created_at")),
        "updated_at": _timestamp(conversation.get("updated_at")),
        "waiting_since": _timestamp(conversation.get("waiting_since")),
        "front_url": f"https://app.frontapp.com/open/{conversation_id}",
    }


def _normalize_message(message: Dict[str, Any]) -> Dict[str, Any]:
    author = message.get("author") or {}
    recipients = _normalize_recipients(message.get("recipients") or [])
    sender = next((item for item in recipients if item.get("role") == "from"), None)
    return {
        "id": message.get("id") or "",
        "type": message.get("type") or "",
        "is_inbound": bool(message.get("is_inbound")),
        "created_at": _timestamp(message.get("created_at")),
        "subject": message.get("subject") or "",
        "author_name": author.get("name") or (sender or {}).get("name") or "",
        "author_handle": author.get("email") or author.get("handle") or (sender or {}).get("handle") or "",
        "recipients": recipients,
        "text": message.get("text") or "",
        "body": message.get("body") or "",
        "blurb": message.get("blurb") or "",
        "attachments": [
            {
                "id": item.get("id") or "",
                "filename": item.get("filename") or item.get("name") or "",
                "content_type": item.get("content_type") or "",
                "size": item.get("size"),
            }
            for item in message.get("attachments") or []
        ],
    }


async def _front_get(url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    global _front_last_request_at

    async with _front_request_lock:
        for attempt in range(FRONT_MAX_RETRIES):
            elapsed = time.monotonic() - _front_last_request_at
            wait_seconds = FRONT_MIN_REQUEST_INTERVAL_SECONDS - elapsed
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            try:
                async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                    response = await client.get(url, headers=_front_headers(), params=params)
                _front_last_request_at = time.monotonic()

                if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                    retry_after = _retry_after_seconds(response)
                    logger.warning(
                        "Front API rate limit hit for %s; backing off %.1fs before retry %s/%s",
                        url,
                        retry_after,
                        attempt + 1,
                        FRONT_MAX_RETRIES,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                raise HTTPException(
                    status_code=exc.response.status_code,
                    detail=exc.response.text[:500] or "Front API request failed",
                ) from exc
            except httpx.RequestError as exc:
                _front_last_request_at = time.monotonic()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Front API request failed: {exc}",
                ) from exc

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Front API is rate limited; please retry shortly.",
    )


def _retry_after_seconds(response: httpx.Response) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), FRONT_MIN_REQUEST_INTERVAL_SECONDS)
        except ValueError:
            pass
    return FRONT_DEFAULT_RATE_LIMIT_BACKOFF_SECONDS


def _parse_export_dates(date_from: str, date_to: str) -> tuple[datetime, datetime]:
    try:
        start = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dates must use YYYY-MM-DD",
        ) from exc

    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_to must be on or after date_from",
        )
    if (end - start).days + 1 > MAX_EXPORT_DAYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Export range is capped at {MAX_EXPORT_DAYS} days to protect Front API limits.",
        )
    return start, end + timedelta(days=1)


def _safe_filename(value: str, fallback: str = "file") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "").strip("._")
    return cleaned[:160] or fallback


def _set_export_status(export_id: str, **updates: Any) -> None:
    current = _export_jobs.get(export_id, {})
    current.update(updates)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    _export_jobs[export_id] = current


def _event_matches_inbox(event: Dict[str, Any], inbox_id: str) -> bool:
    source = event.get("source") or {}
    inboxes = source.get("data") or []
    if isinstance(inboxes, dict):
        inboxes = [inboxes]
    return any((inbox or {}).get("id") == inbox_id for inbox in inboxes)


async def _collect_export_conversation_ids(
    inbox_id: str,
    start: datetime,
    end_exclusive: datetime,
) -> List[str]:
    url = f"{_front_base_url()}/events"
    params: Optional[Dict[str, Any]] = {
        "q[types]": "inbound",
        "q[after]": int(start.timestamp()),
        "q[before]": int(end_exclusive.timestamp()),
    }
    conversation_ids: List[str] = []
    seen: set[str] = set()
    pages = 0

    while url and pages < 100:
        data = await _front_get(url, params=params)
        params = None
        pages += 1

        for event in data.get("_results") or []:
            conversation_id = ((event.get("conversation") or {}).get("id") or "").strip()
            if not conversation_id or conversation_id in seen:
                continue
            if not _event_matches_inbox(event, inbox_id):
                continue
            seen.add(conversation_id)
            conversation_ids.append(conversation_id)
            if len(conversation_ids) > MAX_EXPORT_CONVERSATIONS:
                raise RuntimeError(
                    f"Export found more than {MAX_EXPORT_CONVERSATIONS} conversations. "
                    "Choose a smaller date range."
                )

        url = (data.get("_pagination") or {}).get("next")

    if pages >= 100 and url:
        raise RuntimeError("Export pagination exceeded 100 Front event pages. Choose a smaller date range.")
    return conversation_ids


def _conversation_text(conversation: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
    parts = [
        f"Conversation: {conversation.get('id')}",
        f"Subject: {conversation.get('subject') or ''}",
        f"Status: {conversation.get('status') or ''}",
        f"Front URL: https://app.frontapp.com/open/{conversation.get('id') or ''}",
        "",
    ]
    for message in messages:
        recipients = _normalize_recipients(message.get("recipients") or [])
        sender = next((item for item in recipients if item.get("role") == "from"), {})
        to = [item.get("handle") or item.get("name") for item in recipients if item.get("role") == "to"]
        cc = [item.get("handle") or item.get("name") for item in recipients if item.get("role") == "cc"]
        parts.extend(
            [
                "-" * 72,
                f"Message: {message.get('id')}",
                f"Time: {_timestamp(message.get('created_at')) or ''}",
                f"Direction: {'inbound' if message.get('is_inbound') else 'outbound'}",
                f"From: {sender.get('handle') or sender.get('name') or ''}",
                f"To: {', '.join(filter(None, to))}",
                f"Cc: {', '.join(filter(None, cc))}",
                "",
                strip_html(message.get("text") or message.get("body") or message.get("blurb") or ""),
                "",
            ]
        )
    return "\n".join(parts)


def strip_html(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", value)).strip()


async def _run_inbox_export(export_id: str, request: InboxExportRequest) -> None:
    try:
        start, end_exclusive = _parse_export_dates(request.date_from, request.date_to)
        export_dir = EXPORT_DIR / export_id
        export_dir.mkdir(parents=True, exist_ok=True)
        zip_path = EXPORT_DIR / f"{export_id}.zip"

        _set_export_status(export_id, status="running", message="Finding conversations in Front events...")
        conversation_ids = await _collect_export_conversation_ids(
            request.inbox_id,
            start,
            end_exclusive,
        )
        _set_export_status(
            export_id,
            total_conversations=len(conversation_ids),
            processed_conversations=0,
            message=f"Exporting {len(conversation_ids)} conversations...",
        )

        manifest: Dict[str, Any] = {
            "export_id": export_id,
            "inbox_id": request.inbox_id,
            "inbox_name": request.inbox_name,
            "date_from": request.date_from,
            "date_to": request.date_to,
            "conversation_count": len(conversation_ids),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "conversations": [],
        }

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for index, conversation_id in enumerate(conversation_ids, start=1):
                _set_export_status(
                    export_id,
                    processed_conversations=index - 1,
                    message=f"Exporting conversation {index}/{len(conversation_ids)}...",
                )
                conversation = await _front_get(f"{_front_base_url()}/conversations/{conversation_id}")
                messages_data = await _front_get(f"{_front_base_url()}/conversations/{conversation_id}/messages")
                messages = messages_data.get("_results") or []
                messages.reverse()

                conversation_folder = f"conversations/{_safe_filename(conversation_id)}"
                archive.writestr(
                    f"{conversation_folder}/conversation.json",
                    json.dumps(conversation, indent=2, default=str),
                )
                archive.writestr(
                    f"{conversation_folder}/messages.json",
                    json.dumps(messages, indent=2, default=str),
                )
                archive.writestr(
                    f"{conversation_folder}/conversation.txt",
                    _conversation_text(conversation, messages),
                )

                attachment_count = 0
                for message in messages:
                    for attachment in message.get("attachments") or []:
                        download_url = _extract_attachment_url(attachment)
                        if not download_url:
                            continue
                        download = await _front_download(download_url)
                        filename = _safe_filename(
                            attachment.get("filename") or attachment.get("name") or attachment.get("id") or "attachment",
                            fallback="attachment",
                        )
                        attachment_path = (
                            f"{conversation_folder}/attachments/"
                            f"{_safe_filename(message.get('id') or 'message')}/"
                            f"{filename}"
                        )
                        archive.writestr(attachment_path, download.content)
                        attachment_count += 1

                manifest["conversations"].append(
                    {
                        "id": conversation_id,
                        "subject": conversation.get("subject"),
                        "message_count": len(messages),
                        "attachment_count": attachment_count,
                        "front_url": f"https://app.frontapp.com/open/{conversation_id}",
                    }
                )
                _set_export_status(export_id, processed_conversations=index)

            archive.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))

        _set_export_status(
            export_id,
            status="completed",
            message="Export completed.",
            download_url=f"/api/v1/pif-inbox/exports/{export_id}/download",
            file_size=zip_path.stat().st_size,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("PIF inbox export %s failed", export_id)
        _set_export_status(export_id, status="failed", message=str(exc))


async def _front_download(url: str) -> httpx.Response:
    global _front_last_request_at

    _validate_front_url(url)
    async with _front_request_lock:
        for attempt in range(FRONT_MAX_RETRIES):
            elapsed = time.monotonic() - _front_last_request_at
            wait_seconds = FRONT_MIN_REQUEST_INTERVAL_SECONDS - elapsed
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            try:
                async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
                    response = await client.get(url, headers={**_front_headers(), "Accept": "*/*"})
                _front_last_request_at = time.monotonic()

                if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                    retry_after = _retry_after_seconds(response)
                    logger.warning(
                        "Front API rate limit hit while downloading %s; backing off %.1fs before retry %s/%s",
                        url,
                        retry_after,
                        attempt + 1,
                        FRONT_MAX_RETRIES,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                raise HTTPException(
                    status_code=exc.response.status_code,
                    detail=exc.response.text[:500] or "Front attachment download failed",
                ) from exc
            except httpx.RequestError as exc:
                _front_last_request_at = time.monotonic()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Front attachment download failed: {exc}",
                ) from exc

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Front API is rate limited; please retry shortly.",
    )


@router.get("/inboxes")
async def list_inboxes() -> Dict[str, Any]:
    """List Front inboxes visible to the configured API token."""
    data = await _front_get(f"{_front_base_url()}/inboxes")
    inboxes = [
        {
            "id": item.get("id") or "",
            "name": item.get("name") or "",
            "type": item.get("type") or "",
            "address": item.get("address") or item.get("send_as") or "",
            "is_private": bool(item.get("is_private")),
        }
        for item in data.get("_results") or []
    ]
    inboxes.sort(key=lambda item: item["name"].lower())
    return {"items": inboxes, "total": len(inboxes)}


@router.get("/inboxes/{inbox_id}/conversations")
async def list_inbox_conversations(
    inbox_id: str,
    limit: int = Query(15, ge=1, le=30),
    cursor: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """List conversations for a Front inbox."""
    if cursor:
        data = await _front_get(_decode_cursor(cursor))
    else:
        data = await _front_get(
            f"{_front_base_url()}/inboxes/{inbox_id}/conversations",
            params={"limit": limit},
        )

    next_url = (data.get("_pagination") or {}).get("next")
    return {
        "items": [_normalize_conversation(item) for item in data.get("_results") or []],
        "next_cursor": _encode_cursor(next_url),
    }


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> Dict[str, Any]:
    """Fetch a Front conversation and its messages."""
    conversation_data = await _front_get(f"{_front_base_url()}/conversations/{conversation_id}")
    messages_data = await _front_get(f"{_front_base_url()}/conversations/{conversation_id}/messages")
    messages = [_normalize_message(item) for item in messages_data.get("_results") or []]
    messages.reverse()
    return {
        "conversation": _normalize_conversation(conversation_data),
        "messages": messages,
        "message_count": len(messages),
    }


@router.post("/exports")
async def start_export(
    request: InboxExportRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """Start a paced ZIP export for one inbox and date range."""
    _parse_export_dates(request.date_from, request.date_to)
    export_id = uuid.uuid4().hex
    _set_export_status(
        export_id,
        status="queued",
        message="Export queued.",
        inbox_id=request.inbox_id,
        inbox_name=request.inbox_name,
        date_from=request.date_from,
        date_to=request.date_to,
        total_conversations=0,
        processed_conversations=0,
        download_url=None,
        file_size=None,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    background_tasks.add_task(_run_inbox_export, export_id, request)
    return {
        "export_id": export_id,
        "status": "queued",
        "message": "Export queued.",
    }


@router.get("/exports/{export_id}")
async def get_export_status(export_id: str) -> Dict[str, Any]:
    """Get status for a paced inbox export."""
    job = _export_jobs.get(export_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )
    return job


@router.get("/exports/{export_id}/download")
async def download_export(export_id: str) -> FileResponse:
    """Download a completed inbox export ZIP."""
    job = _export_jobs.get(export_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export not found",
        )
    if job.get("status") != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Export is not completed yet",
        )
    zip_path = EXPORT_DIR / f"{export_id}.zip"
    if not zip_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export file not found",
        )
    filename = _safe_filename(
        f"{job.get('inbox_name') or job.get('inbox_id')}_{job.get('date_from')}_{job.get('date_to')}.zip",
        fallback=f"{export_id}.zip",
    )
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=filename,
    )


@router.get("/messages/{message_id}/attachments/{attachment_id}/download")
async def download_attachment(message_id: str, attachment_id: str) -> Response:
    """Download a Front message attachment through the backend."""
    message = await _front_get(f"{_front_base_url()}/messages/{message_id}")
    attachment = next(
        (item for item in message.get("attachments") or [] if item.get("id") == attachment_id),
        None,
    )
    if not attachment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found on message",
        )

    download_url = _extract_attachment_url(attachment)
    if not download_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment has no downloadable URL",
        )

    response = await _front_download(download_url)
    filename = attachment.get("filename") or attachment.get("name") or attachment_id
    content_type = (
        attachment.get("content_type")
        or response.headers.get("Content-Type")
        or "application/octet-stream"
    )
    quoted_filename = quote(filename)
    return Response(
        content=response.content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}",
            "Content-Length": str(len(response.content)),
        },
    )
