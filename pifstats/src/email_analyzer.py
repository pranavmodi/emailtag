"""Email behavior analysis for PI law firms.

Classifies emails by topic and computes behavioral metrics.
HIPAA note: Only email subjects and first 300 chars of content are sent to the LLM.
Patient names, DOBs, and claim numbers are not specifically extracted or transmitted.
"""

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from .config import settings

logger = logging.getLogger(__name__)

OPENAI_CHAT_API_URL = "https://api.openai.com/v1/chat/completions"

TOPIC_CATEGORIES = [
    "status_update_request",
    "billing_dispute",
    "scheduling_request",
    "rush_request",
    "lien_negotiation",
    "records_request",
    "general_inquiry",
    "other",
]

CLASSIFICATION_SYSTEM_PROMPT = """You are an email classifier for a medical imaging company.
Classify each email into exactly one of these categories:
- status_update_request: asking for status on a case, report, or record
- billing_dispute: disputing a bill, questioning charges, or billing errors
- scheduling_request: requesting to schedule, confirm, or inquire about appointments
- rush_request: urgently requesting expedited service or rush processing
- lien_negotiation: negotiating lien amounts, settlement offers, or lien modifications
- records_request: requesting medical records, images, CDs, or reports
- general_inquiry: general questions or information requests
- other: anything that doesn't fit the above categories

Return a JSON array of category strings, one per email, in the same order as input.
Example: ["status_update_request", "records_request", "other"]
Never include patient names, DOBs, claim numbers, or any PHI in your response."""


def classify_emails_batch(email_snippets: List[Dict[str, str]]) -> List[str]:
    """
    Classify a batch of emails by topic using gpt-4o-mini.

    Args:
        email_snippets: list of {"subject": str, "snippet": str} dicts
                       snippet = first 300 chars of content only

    Returns:
        List of category strings, one per input email.
        Falls back to "other" on failure.
    """
    if not email_snippets:
        return []

    headers = {
        "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    # Build a numbered list so the model can reference position
    email_list_text = "\n".join(
        f"{i+1}. Subject: {e.get('subject', '')[:100]} | Snippet: {e.get('snippet', '')[:300]}"
        for i, e in enumerate(email_snippets)
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Classify these {len(email_snippets)} emails:\n\n{email_list_text}\n\nReturn a JSON array with exactly {len(email_snippets)} category strings.",
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }

    try:
        with httpx.Client(timeout=60.0, verify=False) as client:
            response = client.post(OPENAI_CHAT_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            # The model returns {"categories": [...]} or just an array
            if isinstance(parsed, list):
                categories = parsed
            elif isinstance(parsed, dict):
                # Try common keys
                for key in ("categories", "results", "classifications"):
                    if key in parsed and isinstance(parsed[key], list):
                        categories = parsed[key]
                        break
                else:
                    # Fallback: take first list value
                    categories = next(
                        (v for v in parsed.values() if isinstance(v, list)),
                        [],
                    )
            else:
                categories = []

            # Validate and fill missing entries
            valid = TOPIC_CATEGORIES
            result_list = []
            for i in range(len(email_snippets)):
                cat = categories[i] if i < len(categories) else "other"
                result_list.append(cat if cat in valid else "other")

            return result_list

    except Exception as e:
        logger.error(f"Email batch classification failed: {e}")
        return ["other"] * len(email_snippets)


def detect_sender_role(content_text: str, sender_name: str) -> str:
    """
    Heuristic role detection from email text and sender name.

    Returns: attorney / paralegal / case_manager / unknown
    """
    text = f"{sender_name} {content_text or ''}".lower()

    if any(kw in text for kw in ("esq", "attorney at law", " attorney", "esquire")):
        return "attorney"
    if "paralegal" in text:
        return "paralegal"
    if any(kw in text for kw in ("case manager", "casemanager")):
        return "case_manager"
    if "legal assistant" in text:
        return "case_manager"
    return "unknown"


def _month_key(dt: datetime) -> str:
    """Return YYYY-MM string for a datetime."""
    return dt.strftime("%Y-%m")


def analyze_firm_emails(emails: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Main entry point: analyze email behavior for a firm.

    Args:
        emails: list of email dicts with keys:
                subject, content_text, sender, created_at (datetime or ISO string)

    Returns:
        behavioral_data dict:
          - total_email_count
          - monthly_email_volume (list of ints, last 3 calendar months, oldest first)
          - last_contact_date (ISO string or None)
          - days_since_last_contact (int or None)
          - topic_distribution {category: count}
          - primary_pain_point (str or None)
          - sender_roles {role: count}
          - peak_contact_days (list of day names)
          - after_hours_ratio (float 0-1)
          - analyzed_at (ISO timestamp)
    """
    if not emails:
        return {
            "total_email_count": 0,
            "monthly_email_volume": [0, 0, 0],
            "last_contact_date": None,
            "days_since_last_contact": None,
            "topic_distribution": {},
            "primary_pain_point": None,
            "sender_roles": {},
            "peak_contact_days": [],
            "after_hours_ratio": 0.0,
            "analyzed_at": datetime.utcnow().isoformat(),
        }

    # Parse created_at to datetime objects
    parsed_emails = []
    for em in emails:
        created_at = em.get("created_at")
        if isinstance(created_at, str):
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                # Normalize to naive UTC
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
            except ValueError:
                dt = datetime.utcnow()
        elif isinstance(created_at, datetime):
            dt = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
        else:
            dt = datetime.utcnow()
        parsed_emails.append({**em, "_dt": dt})

    # Sort by date
    parsed_emails.sort(key=lambda x: x["_dt"])

    now = datetime.utcnow()

    # Monthly volume: last 3 calendar months
    months = []
    for offset in range(2, -1, -1):
        # Go back offset months from current month
        month_num = now.month - offset
        year = now.year
        while month_num <= 0:
            month_num += 12
            year -= 1
        months.append(f"{year}-{month_num:02d}")

    monthly_counts: Dict[str, int] = {m: 0 for m in months}
    for em in parsed_emails:
        mk = _month_key(em["_dt"])
        if mk in monthly_counts:
            monthly_counts[mk] += 1

    monthly_email_volume = [monthly_counts[m] for m in months]

    # Last contact date
    last_dt = parsed_emails[-1]["_dt"]
    last_contact_date = last_dt.isoformat()
    days_since = (now - last_dt).days

    # After-hours ratio (before 9am or after 6pm)
    after_hours_count = sum(
        1 for em in parsed_emails if em["_dt"].hour < 9 or em["_dt"].hour >= 18
    )
    after_hours_ratio = round(after_hours_count / len(parsed_emails), 3)

    # Peak contact days
    day_counts = Counter(em["_dt"].strftime("%A") for em in parsed_emails)
    if day_counts:
        max_count = max(day_counts.values())
        peak_contact_days = [day for day, cnt in day_counts.items() if cnt == max_count]
    else:
        peak_contact_days = []

    # Sender roles
    role_counter: Counter = Counter()
    for em in parsed_emails:
        role = detect_sender_role(
            em.get("content_text", "") or "",
            em.get("sender", "") or "",
        )
        role_counter[role] += 1
    sender_roles = dict(role_counter)

    # Topic classification in batches of 20
    snippets = [
        {
            "subject": em.get("subject", "") or "",
            "snippet": (em.get("content_text", "") or "")[:300],
        }
        for em in parsed_emails
    ]

    categories: List[str] = []
    batch_size = 20
    for i in range(0, len(snippets), batch_size):
        batch = snippets[i : i + batch_size]
        batch_categories = classify_emails_batch(batch)
        categories.extend(batch_categories)

    topic_distribution = dict(Counter(categories))

    # Primary pain point = most common topic (excluding "other" if possible)
    non_other = {k: v for k, v in topic_distribution.items() if k != "other"}
    if non_other:
        primary_pain_point = max(non_other, key=lambda k: non_other[k])
    elif topic_distribution:
        primary_pain_point = max(topic_distribution, key=lambda k: topic_distribution[k])
    else:
        primary_pain_point = None

    return {
        "total_email_count": len(parsed_emails),
        "monthly_email_volume": monthly_email_volume,
        "last_contact_date": last_contact_date,
        "days_since_last_contact": days_since,
        "topic_distribution": topic_distribution,
        "primary_pain_point": primary_pain_point,
        "sender_roles": sender_roles,
        "peak_contact_days": peak_contact_days,
        "after_hours_ratio": after_hours_ratio,
        "analyzed_at": now.isoformat(),
    }
