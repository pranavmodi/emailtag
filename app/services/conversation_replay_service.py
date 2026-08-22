"""Helpers for replaying Front conversations via SMTP."""
from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from app.core.config import settings
from app.services.frontapp_service import get_conversation_async

logger = logging.getLogger(__name__)


@dataclass
class DownloadedAttachment:
    """Container for an attachment that has been downloaded from Front."""

    filename: str
    content: bytes
    content_type: str


def _require_front_credentials() -> None:
    if not settings.FRONT_AUTH_TOKEN or not settings.FRONT_API_BASE_URL:
        raise ValueError("Front API credentials are not configured")


def _require_smtp_credentials() -> Dict[str, Any]:
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    username = settings.SMTP_USERNAME or settings.SENDER_EMAIL
    password = settings.SMTP_PASSWORD or settings.SENDER_PASSWORD
    envelope_from = settings.SENDER_EMAIL or username

    if not all([host, port, username, password, envelope_from]):
        raise ValueError("SMTP configuration (host/port/username/password/sender) is incomplete")

    return {
        "host": host,
        "port": int(port),
        "username": username,
        "password": password,
        "envelope_from": envelope_from,
    }


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return re.sub(r"<[^>]+>", "", html)


def _format_timestamp(timestamp: Any) -> Optional[str]:
    if timestamp is None:
        return None
    try:
        ts_float = float(timestamp)
        dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return None


def _extract_author_details(message: Dict[str, Any]) -> Dict[str, Optional[str]]:
    author = message.get("author") or {}
    name = (
        author.get("name")
        or " ".join(filter(None, [author.get("first_name"), author.get("last_name")])).strip()
    )
    handle = author.get("handle")
    email = author.get("email") or handle

    if not name and email:
        name = email

    return {
        "name": name or None,
        "handle": handle,
        "email": email,
    }


def _transform_attachment(raw_attachment: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": raw_attachment.get("id"),
        "filename": raw_attachment.get("filename") or raw_attachment.get("name"),
        "content_type": raw_attachment.get("content_type"),
        "size": raw_attachment.get("size"),
        "download_url": _extract_attachment_url(raw_attachment),
    }


def _extract_attachment_url(raw_attachment: Dict[str, Any]) -> Optional[str]:
    url = raw_attachment.get("url")
    if url:
        return _normalize_front_url(url)

    links = raw_attachment.get("_links") or {}
    related_links = links.get("related") or {}
    for key in ("download", "self"):
        candidate = related_links.get(key) or links.get(key)
        if candidate:
            return _normalize_front_url(candidate)
    return None


def _normalize_front_url(path_or_url: Optional[str]) -> Optional[str]:
    """Ensure attachment URLs point to the Front API host."""
    if not path_or_url:
        return None
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    base = settings.FRONT_API_BASE_URL.rstrip("/")
    if not path_or_url.startswith("/"):
        path_or_url = f"/{path_or_url}"
    return urljoin(base + "/", path_or_url.lstrip("/"))


async def _fetch_conversation_messages(conversation_id: str) -> List[Dict[str, Any]]:
    _require_front_credentials()

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/conversations/{conversation_id}/messages"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 404:
            raise LookupError(f"Conversation {conversation_id} not found when fetching messages")
        response.raise_for_status()
        data = response.json()

    api_messages = data.get("_results", [])
    api_messages.reverse()  # Convert to chronological order

    replay_messages: List[Dict[str, Any]] = []
    for message in api_messages:
        author_details = _extract_author_details(message)
        attachments = [_transform_attachment(att) for att in message.get("attachments", [])]

        replay_messages.append(
            {
                "id": message.get("id"),
                "author_name": author_details.get("name"),
                "author_email": author_details.get("email"),
                "author_handle": author_details.get("handle"),
                "direction": "inbound" if message.get("is_inbound") else "outbound",
                "is_inbound": message.get("is_inbound"),
                "created_at": _format_timestamp(message.get("created_at")),
                "body": message.get("body"),
                "text_body": message.get("text"),
                "subject": message.get("subject"),
                "attachments": attachments,
            }
        )

    return replay_messages


async def fetch_conversation_messages(conversation_id: str) -> List[Dict[str, Any]]:
    """Public read-only wrapper shared by replay and evaluation tooling."""
    return await _fetch_conversation_messages(conversation_id)


async def _fetch_message_details(message_id: str) -> Dict[str, Any]:
    _require_front_credentials()

    auth_header = f"Bearer {settings.FRONT_AUTH_TOKEN}"
    url = f"{settings.FRONT_API_BASE_URL}/messages/{message_id}"
    headers = {
        "Authorization": auth_header,
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 404:
            raise LookupError(f"Message {message_id} not found")
        response.raise_for_status()
        return response.json()


async def _download_attachment(attachment: Dict[str, Any]) -> Optional[DownloadedAttachment]:
    download_url = attachment.get("download_url") or _extract_attachment_url(attachment)
    if not download_url:
        return None

    _require_front_credentials()
    headers = {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Accept": "*/*",
    }

    async with httpx.AsyncClient(verify=False, timeout=60.0) as client:
        response = await client.get(download_url, headers=headers)
        if response.status_code == 404:
            logger.warning("Attachment %s not found at %s", attachment.get("id"), download_url)
            return None
        response.raise_for_status()
        content_type = attachment.get("content_type") or response.headers.get("Content-Type", "application/octet-stream")
        filename = attachment.get("filename") or attachment.get("id") or "attachment"
        return DownloadedAttachment(filename=filename, content=response.content, content_type=content_type)


def _send_email_via_smtp_sync(
    subject: str,
    html_body: str,
    text_body: str,
    sender_header: str,
    sender_display: Optional[str],
    recipient: str,
    attachments: List[DownloadedAttachment],
) -> None:
    smtp_config = _require_smtp_credentials()
    recipient_list = [recipient]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((sender_display or sender_header, sender_header))
    msg["To"] = recipient

    plain_part = text_body or _strip_html(html_body)
    msg.set_content(plain_part or " ")

    if html_body:
        msg.add_alternative(html_body, subtype="html")

    for attachment in attachments:
        maintype, subtype = ("application", "octet-stream")
        if attachment.content_type and "/" in attachment.content_type:
            maintype, subtype = attachment.content_type.split("/", 1)

        msg.add_attachment(
            attachment.content,
            maintype=maintype,
            subtype=subtype,
            filename=attachment.filename,
        )

    context = ssl.create_default_context()
    use_ssl = settings.SMTP_USE_SSL or (smtp_config["port"] == 465 and not settings.SMTP_USE_TLS)

    if use_ssl:
        with smtplib.SMTP_SSL(smtp_config["host"], smtp_config["port"], context=context) as server:
            server.login(smtp_config["username"], smtp_config["password"])
            server.send_message(msg, from_addr=smtp_config["envelope_from"], to_addrs=recipient_list)
    else:
        with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
            server.ehlo()
            if settings.SMTP_USE_TLS:
                server.starttls(context=context)
            server.login(smtp_config["username"], smtp_config["password"])
            server.send_message(msg, from_addr=smtp_config["envelope_from"], to_addrs=recipient_list)


async def fetch_conversation_for_replay(conversation_id: str) -> Dict[str, Any]:
    """
    Retrieve conversation metadata and structured messages for the replay UI.
    """
    conversation_meta = await get_conversation_async(conversation_id)
    if not conversation_meta:
        raise LookupError(f"Conversation {conversation_id} not found")

    messages = await _fetch_conversation_messages(conversation_id)
    return {
        "conversation_id": conversation_id,
        "subject": conversation_meta.get("subject"),
        "message_count": len(messages),
        "messages": messages,
    }


async def send_replay_message(
    conversation_id: str,
    message_id: str,
    recipient_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a single message from the conversation replay to the configured recipient.
    """
    recipient = recipient_override or settings.DEFAULT_RECIPIENT_EMAIL
    if not recipient:
        raise ValueError("DEFAULT_RECIPIENT_EMAIL is not configured")

    conversation_meta = await get_conversation_async(conversation_id)
    if not conversation_meta:
        raise LookupError(f"Conversation {conversation_id} not found")

    message = await _fetch_message_details(message_id)
    author_details = _extract_author_details(message)

    subject = (
        message.get("subject")
        or conversation_meta.get("subject")
        or f"Conversation {conversation_id}"
    )
    html_body = message.get("body") or message.get("text") or ""
    text_body = message.get("text") or _strip_html(html_body)

    downloaded_attachments: List[DownloadedAttachment] = []
    for attachment in message.get("attachments", []):
        transformed = _transform_attachment(attachment)
        downloaded = await _download_attachment(transformed)
        if downloaded:
            downloaded_attachments.append(downloaded)

    header_from = (
        author_details.get("email")
        or author_details.get("handle")
        or settings.SENDER_EMAIL
        or settings.SMTP_USERNAME
        or "replay@example.com"
    )
    sender_display = author_details.get("name")

    logger.info(
        "Sending replay message %s from conversation %s to %s",
        message_id,
        conversation_id,
        recipient,
    )

    await asyncio.to_thread(
        _send_email_via_smtp_sync,
        subject,
        html_body or text_body,
        text_body,
        header_from,
        sender_display,
        recipient,
        downloaded_attachments,
    )

    return {
        "status": "sent",
        "message_id": message_id,
        "subject": subject,
        "sent_to": recipient,
        "sender": header_from,
    }
