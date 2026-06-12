"""Firm-staff email signature extraction for behavioral contact profiles."""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List

import httpx

from .config import settings
from .email_analyzer import normalize_sender_persona

logger = logging.getLogger(__name__)

OPENAI_CHAT_API_URL = "https://api.openai.com/v1/chat/completions"

PATIENT_CONTEXT_PATTERN = re.compile(
    # No trailing \b: alternatives ending in '#' sit before a space, where
    # there is no word boundary, so '\b' silently disabled those branches.
    r"\b("
    r"dob|d\.o\.b\.?|date of birth|dol|d\.o\.l\.?|date of loss|"
    r"mrn|medical record|patient|claim\s*(?:#|no\.?|number)|"
    r"case\s*(?:#|no\.?|number)|ssn|social security"
    r")(?![a-z])",
    re.IGNORECASE,
)

SIGNATURE_SYSTEM_PROMPT = """You extract firm-staff signature data from law firm emails.
Use only the sender's signature block, footer, or closing lines. Never extract patient
information, case facts, DOB, DOL, MRN, claim numbers, case numbers, or medical details.

Return JSON with exactly these keys:
{
  "name": "firm staff sender name or empty string",
  "title": "firm staff job title or empty string",
  "direct_phone": "direct firm-staff phone number or empty string",
  "persona": "one of founder_owner, managing_partner, coo_ops, intake, records, case_manager, lien_settlement, marketing, attorney, paralegal, unknown"
}

If a value might be patient information, return an empty string for that value."""


def contains_patient_context(value: Any) -> bool:
    """Return True when a signature value appears to contain patient/case context."""
    if not isinstance(value, str):
        return False
    return bool(PATIENT_CONTEXT_PATTERN.search(value))


def filter_signature_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    """Drop any extracted signature values that look like patient/case context."""
    safe: Dict[str, str] = {}
    for key in ("name", "title", "direct_phone", "persona"):
        raw_value = payload.get(key, "")
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        if contains_patient_context(value):
            value = ""
        safe[key] = value

    safe["persona"] = normalize_sender_persona(safe.get("persona"))
    return safe


def extract_signature_for_sender(
    sender: str,
    message_bodies: List[str],
) -> Dict[str, str]:
    """Extract signature metadata for one firm-staff sender using gpt-4o-mini."""
    bodies = [body for body in message_bodies if body]
    if not sender or not bodies:
        return filter_signature_payload({})

    headers = {
        "Authorization": f"Bearer {settings.RESEARCH_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body_text = "\n\n--- MESSAGE ---\n\n".join(body[:2500] for body in bodies[:2])
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SIGNATURE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Sender: {sender}\n\n"
                    "Extract only firm-staff signature data from these recent messages:\n\n"
                    f"{body_text}"
                ),
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
            if not isinstance(parsed, dict):
                return filter_signature_payload({})
            return filter_signature_payload(parsed)
    except Exception as exc:
        logger.error(f"Signature extraction failed for {sender}: {exc}")
        return filter_signature_payload({})


def signature_profile_update(signature: Dict[str, str]) -> Dict[str, Any]:
    """Build the contact_profiles[email].signature payload."""
    return {
        "title": signature.get("title") or "",
        "phone": signature.get("direct_phone") or "",
        "extracted_at": datetime.utcnow().isoformat(),
    }
