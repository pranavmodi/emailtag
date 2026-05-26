"""Front API helpers for the daily inbox audit.

Strategy: a single paginated call to /events filtered to type=inbound gives us
every inbound message Front received in the window. Each event tells us:
  - which conversation it belongs to
  - which inbox(es) it landed in
  - the message subject

This is semantically correct (we only ever process inbound messages via webhook)
and far cheaper than per-inbox conversation listings, which include outbound
activity that produces massive false-positive miss counts.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


FRONT_WEB_URL_BASE = "https://app.frontapp.com/open"


def build_front_url(conversation_id: str) -> str:
    return f"{FRONT_WEB_URL_BASE}/{conversation_id}"


def _get(url: str) -> Optional[Dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}",
        "Accept": "application/json",
    }
    try:
        with httpx.Client(verify=False, timeout=30.0) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(
            f"Front API HTTP error {e.response.status_code} on {url}: {e.response.text[:300]}"
        )
    except httpx.RequestError as e:
        logger.error(f"Front API request error on {url}: {e}")
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Unexpected error on {url}: {e}")
    return None


def _get_endpoint(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    base = settings.FRONT_API_BASE_URL.rstrip("/")
    url = f"{base}/{endpoint.lstrip('/')}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        if query:
            url = f"{url}?{query}"
    return _get(url)


def _paginate(
    first_response: Optional[Dict[str, Any]],
    max_pages: int = 200,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    page = first_response
    pages_walked = 0
    while page and pages_walked < max_pages:
        results.extend(page.get("_results") or [])
        next_url = ((page.get("_pagination") or {}).get("next")) if page else None
        if not next_url:
            break
        page = _get(next_url)
        pages_walked += 1
    if pages_walked >= max_pages:
        logger.warning(
            f"Stopped paginating after {max_pages} pages; results may be truncated."
        )
    return results


def list_all_inboxes() -> List[Dict[str, Any]]:
    """List every inbox the Front API token can see."""
    first = _get_endpoint("inboxes")
    return _paginate(first)


def list_inbound_events_since(after_unix: int, max_pages: int = 200) -> List[Dict[str, Any]]:
    """Return all inbound message events emitted after `after_unix`.

    Each event includes the originating inbox(es), the conversation, and the
    message itself. We use this to enumerate every inbound message Front
    received in the window, grouped later by inbox.
    """
    first = _get_endpoint(
        "events",
        params={"q[types]": "inbound", "q[after]": after_unix},
    )
    return _paginate(first, max_pages=max_pages)


def extract_inbound_records(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten raw Front events into one record per (inbox, conversation) pair.

    A single inbound message may land in multiple inboxes (CC); we emit a row
    for each inbox so the per-inbox audit sees the conversation.

    Returns a list of {inbox_id, conversation_id, subject}.
    """
    records: List[Dict[str, Any]] = []
    for event in events:
        target = event.get("target") or {}
        message = target.get("data") or {}
        if not message.get("is_inbound"):
            continue
        conversation = event.get("conversation") or {}
        conversation_id = conversation.get("id")
        if not conversation_id:
            continue
        subject = message.get("subject")

        source = event.get("source") or {}
        inboxes = source.get("data") or []
        if isinstance(inboxes, dict):
            inboxes = [inboxes]
        for inbox in inboxes:
            inbox_id = (inbox or {}).get("id")
            if not inbox_id:
                continue
            records.append(
                {
                    "inbox_id": inbox_id,
                    "conversation_id": conversation_id,
                    "subject": subject,
                }
            )
    return records
