"""Email behavior analysis for PI law firms.

Classifies emails by topic and computes behavioral metrics.
HIPAA note: Only email subjects and first 300 chars of content are sent to the LLM.
Patient names, DOBs, and claim numbers are not specifically extracted or transmitted.
"""

import json
import re
import logging
from email.utils import parseaddr
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

PERSONA_KEYS = [
    "founder_owner",
    "managing_partner",
    "coo_ops",
    "intake",
    "records",
    "case_manager",
    "lien_settlement",
    "marketing",
    "attorney",
    "paralegal",
    "unknown",
]

LEGACY_ROLE_MAP = {
    "attorney": "attorney",
    "paralegal": "paralegal",
    "case_manager": "case_manager",
    "legal_assistant": "case_manager",
    "intake_specialist": "intake",
    "medical_records": "records",
    "office_manager": "coo_ops",
    "billing_coordinator": "lien_settlement",
    "other": "unknown",
    "unknown": "unknown",
}

CONSUMER_EMAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "ymail.com",
    "rocketmail.com",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
}

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

Also classify the sender persona into exactly one of these keys:
- founder_owner
- managing_partner
- coo_ops
- intake
- records
- case_manager
- lien_settlement
- marketing
- attorney
- paralegal
- unknown

Return a JSON object with a "classifications" array, one object per email in the
same order as input. Each object must have "category" and "sender_persona".
Example: {"classifications": [{"category": "status_update_request", "sender_persona": "case_manager"}]}
Never include patient names, DOBs, claim numbers, or any PHI in your response."""


def normalize_sender_persona(value: Optional[str]) -> str:
    """Normalize LLM or legacy role labels into the current persona taxonomy."""
    if not value:
        return "unknown"
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    normalized = LEGACY_ROLE_MAP.get(normalized, normalized)
    return normalized if normalized in PERSONA_KEYS else "unknown"


def detect_sender_role(content_text: str, sender_name: str) -> str:
    """
    Deterministic persona fallback from email text and sender name.

    Returns a key from PERSONA_KEYS.
    """
    text = f"{sender_name} {content_text or ''}".lower()

    checks = [
        ("founder_owner", ("founder", "owner", "principal", "chief executive", " ceo")),
        ("managing_partner", ("managing partner", "founding partner", "senior partner")),
        ("coo_ops", ("chief operating", " coo", "operations", "office manager", "administrator")),
        ("intake", ("intake", "new client", "client services")),
        ("records", ("medical records", "records coordinator", "records department", "records request")),
        ("case_manager", ("case manager", "case coordinator", "legal assistant", "case assistant")),
        ("lien_settlement", ("lien", "settlement", "negotiator", "billing coordinator")),
        ("marketing", ("marketing", "business development", "outreach", "partnership")),
        ("attorney", ("esq", "attorney at law", " attorney", "esquire", "counsel", "lawyer")),
        ("paralegal", ("paralegal",)),
    ]
    for persona, keywords in checks:
        for keyword in keywords:
            # Boundary match so short tokens cannot hit substrings
            # (plain " coo" in "coordinator" misrouted intake staff).
            if re.search(rf"(?<![a-z]){re.escape(keyword.strip())}(?![a-z])", text):
                return persona
    return "unknown"


def extract_sender_identity(sender: str) -> tuple[str, str]:
    """Return display name and normalized email address from a sender header."""
    name, email = parseaddr(sender or "")
    email = email.strip().lower()
    name = (name or email.split("@")[0] if email else "").strip().strip('"')
    return name, email


def is_consumer_email(email: str) -> bool:
    """Return True for common patient/personal mailbox domains."""
    domain = email.lower().rsplit("@", 1)[-1] if "@" in email else ""
    return domain in CONSUMER_EMAIL_DOMAINS


def is_firm_staff_sender(sender: str) -> bool:
    """Firm staff profiles require a parseable non-consumer email address."""
    _name, email = extract_sender_identity(sender)
    return bool(email and "@" in email and not is_consumer_email(email))


def classify_emails_batch(
    email_snippets: List[Dict[str, str]],
    include_persona: bool = False,
) -> List[Any]:
    """
    Classify a batch of emails by topic using gpt-4o-mini.

    Args:
        email_snippets: list of {"subject": str, "snippet": str} dicts
                       snippet = first 300 chars of content only

    Returns:
        List of category strings, one per input email by default.
        If include_persona=True, returns dicts with category and sender_persona.
        Falls back to "other" on failure.
    """
    if not email_snippets:
        return []

    headers = {
        "Authorization": f"Bearer {settings.RESEARCH_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    # Build a numbered list so the model can reference position
    email_list_text = "\n".join(
        (
            f"{i+1}. Sender: {e.get('sender', '')[:120]} | "
            f"Subject: {e.get('subject', '')[:100]} | "
            f"Snippet: {e.get('snippet', '')[:300]}"
        )
        for i, e in enumerate(email_snippets)
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Classify these {len(email_snippets)} emails:\n\n{email_list_text}\n\nReturn exactly {len(email_snippets)} classifications.",
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

            # The model returns {"classifications": [...]} or legacy category arrays.
            if isinstance(parsed, list):
                raw_items = parsed
            elif isinstance(parsed, dict):
                # Try common keys
                for key in ("classifications", "categories", "results"):
                    if key in parsed and isinstance(parsed[key], list):
                        raw_items = parsed[key]
                        break
                else:
                    # Fallback: take first list value
                    raw_items = next(
                        (v for v in parsed.values() if isinstance(v, list)),
                        [],
                    )
            else:
                raw_items = []

            # Validate and fill missing entries
            valid = TOPIC_CATEGORIES
            result_list = []
            for i in range(len(email_snippets)):
                item = raw_items[i] if i < len(raw_items) else {}
                if isinstance(item, dict):
                    cat = item.get("category") or item.get("topic") or "other"
                    persona = normalize_sender_persona(
                        item.get("sender_persona") or item.get("persona") or item.get("role")
                    )
                else:
                    cat = item
                    persona = "unknown"

                category = cat if cat in valid else "other"
                if persona == "unknown":
                    snippet = email_snippets[i]
                    persona = detect_sender_role(
                        snippet.get("snippet", "") or "",
                        snippet.get("sender", "") or "",
                    )
                result_list.append({"category": category, "sender_persona": persona})

            if include_persona:
                return result_list
            return [item["category"] for item in result_list]

    except Exception as e:
        logger.error(f"Email batch classification failed: {e}")
        if include_persona:
            return [
                {
                    "category": "other",
                    "sender_persona": detect_sender_role(
                        snippet.get("snippet", "") or "",
                        snippet.get("sender", "") or "",
                    ),
                }
                for snippet in email_snippets
            ]
        return ["other"] * len(email_snippets)


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
            "contact_profiles": {},
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

    # Topic classification in batches of 20
    snippets = [
        {
            "subject": em.get("subject", "") or "",
            "snippet": (em.get("content_text", "") or "")[:300],
            "sender": em.get("sender", "") or "",
        }
        for em in parsed_emails
    ]

    categories: List[str] = []
    personas: List[str] = []
    batch_size = 20
    for i in range(0, len(snippets), batch_size):
        batch = snippets[i : i + batch_size]
        batch_results = classify_emails_batch(batch, include_persona=True)
        for item in batch_results:
            if isinstance(item, dict):
                categories.append(item.get("category", "other"))
                personas.append(normalize_sender_persona(item.get("sender_persona")))
            else:
                categories.append(item if item in TOPIC_CATEGORIES else "other")
                personas.append("unknown")

    while len(categories) < len(parsed_emails):
        categories.append("other")
    while len(personas) < len(parsed_emails):
        idx = len(personas)
        personas.append(
            detect_sender_role(
                snippets[idx].get("snippet", "") or "",
                snippets[idx].get("sender", "") or "",
            )
        )

    # Sender roles, now using the persona taxonomy.
    sender_roles = dict(Counter(personas[: len(parsed_emails)]))

    topic_distribution = dict(Counter(categories))

    contact_accumulator: Dict[str, Dict[str, Any]] = {}
    for em, category, persona in zip(parsed_emails, categories, personas):
        sender = em.get("sender", "") or ""
        if not is_firm_staff_sender(sender):
            continue

        name, email = extract_sender_identity(sender)
        if not email:
            continue

        profile = contact_accumulator.setdefault(
            email,
            {
                "name": name,
                "role": normalize_sender_persona(persona),
                "message_count": 0,
                "topic_counter": Counter(),
                "after_hours_count": 0,
                "first_seen_dt": em["_dt"],
                "last_seen_dt": em["_dt"],
            },
        )
        if name and not profile.get("name"):
            profile["name"] = name
        if profile.get("role") == "unknown" and normalize_sender_persona(persona) != "unknown":
            profile["role"] = normalize_sender_persona(persona)
        profile["message_count"] += 1
        profile["topic_counter"][category] += 1
        if em["_dt"].hour < 9 or em["_dt"].hour >= 18:
            profile["after_hours_count"] += 1
        if em["_dt"] < profile["first_seen_dt"]:
            profile["first_seen_dt"] = em["_dt"]
        if em["_dt"] > profile["last_seen_dt"]:
            profile["last_seen_dt"] = em["_dt"]

    contact_profiles = {}
    for email, profile in contact_accumulator.items():
        count = profile["message_count"] or 1
        contact_profiles[email] = {
            "name": profile.get("name", ""),
            "role": profile.get("role", "unknown"),
            "persona": profile.get("role", "unknown"),
            "message_count": profile["message_count"],
            "topic_mix": dict(profile["topic_counter"]),
            "after_hours_ratio": round(profile["after_hours_count"] / count, 3),
            "first_seen": profile["first_seen_dt"].isoformat(),
            "last_seen": profile["last_seen_dt"].isoformat(),
        }

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
        "contact_profiles": contact_profiles,
        "analyzed_at": now.isoformat(),
    }
