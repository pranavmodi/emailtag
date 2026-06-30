"""Deep research for personal injury law firms using OpenAI with web search."""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from .config import settings

logger = logging.getLogger(__name__)

# OpenAI API endpoint for responses with tools (web search requires the responses API)
OPENAI_API_URL = "https://api.openai.com/v1/responses"

# Transient upstream statuses worth retrying (OpenAI/Cloudflare blips).
_RETRYABLE_STATUS = {429, 500, 502, 503, 504, 520, 522, 524}


def _post_openai_with_retry(client, url, headers, payload, attempts=3, backoff=5.0):
    """
    POST to OpenAI, retrying transient failures (timeouts, connection errors,
    and retryable 5xx/429 statuses from OpenAI's Cloudflare edge).

    Returns the httpx.Response (already status-checked) or raises the last error.
    Without this, a single 502/520/timeout permanently fails a research task.
    """
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code in _RETRYABLE_STATUS:
                raise httpx.HTTPStatusError(
                    f"retryable status {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            # Don't retry non-retryable HTTP statuses (e.g. 400/401/404).
            if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None \
                    and exc.response.status_code not in _RETRYABLE_STATUS:
                raise
            last_exc = exc
            if attempt < attempts:
                logger.warning("OpenAI transient error (attempt %d/%d): %s", attempt, attempts, exc)
                time.sleep(backoff * attempt)
    raise last_exc


class LeadershipMember(BaseModel):
    """Leadership team member."""
    name: str = Field(default="", description="Full name")
    title: str = Field(default="", description="Title/position at the firm")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile URL")
    bio: Optional[str] = Field(None, description="Brief bio or description")
    image_url: Optional[str] = Field(None, description="Profile image URL")


# Known vendor email domain patterns (Phase 1 inbox-based detection)
VENDOR_EMAIL_DOMAINS: Dict[str, str] = {
    "filevineapp.com": "filevine",
    "casepeer.com": "casepeer",
    "mycase.com": "mycase",
    "litify.io": "litify",
    "litify.com": "litify",
    "smokeball.com": "smokeball",
    "practicepanther.com": "practicepanther",
    "neos.ai": "neos",
    "abacusnext.com": "abacusnext",
    "needles.com": "needles",
}


def detect_vendor_stack_from_emails(emails: List[str]) -> List[Dict[str, Any]]:
    """
    Phase 1: infer practice management vendors from email address domains.

    Filevine, for example, issues @<firm>.filevineapp.com addresses to their
    clients' staff. These show up in our inbox and are the strongest possible
    signal — zero LLM cost, near-100% confidence.

    Returns a list of vendor dicts: [{vendor, source, confidence}]
    """
    detected: Dict[str, bool] = {}
    for email in emails:
        if "@" not in email:
            continue
        domain = email.split("@", 1)[1].lower().strip()
        for pattern, vendor in VENDOR_EMAIL_DOMAINS.items():
            if domain == pattern or domain.endswith("." + pattern):
                detected[vendor] = True
    return [
        {"vendor": v, "source": "email_domain", "confidence": "high", "known": True}
        for v in sorted(detected)
    ]


# Canonical vendor names — used to normalize/dedupe, NOT to gate detection.
# Unknown vendors are still captured (flagged known=false) so we discover new ones.
KNOWN_VENDORS = {
    "filevine", "clio", "mycase", "litify", "smokeball", "needles",
    "practicepanther", "neos", "abacusnext", "casepeer", "trialworks",
    "assembly", "captorra", "leap", "centerbase",
}

# Aliases collapse vendor spelling variants onto a canonical key.
VENDOR_ALIASES = {
    "case_peer": "casepeer",
    "filevineapp": "filevine",
    "assemblyneos": "neos",
    "assemblysoftware": "neos",
    "abacus": "abacusnext",
}

# Generic tools / mail providers an LLM might wrongly emit as a "vendor".
VENDOR_DENYLIST = {
    "gmail", "googlemail", "google", "outlook", "office365", "microsoft",
    "microsoft365", "yahoo", "icloud", "aol", "proton", "protonmail",
    "docusign", "adobe", "dropbox", "zoom", "slack", "none", "unknown", "n/a",
}


def _canonical_vendor(raw: str) -> Optional[str]:
    """
    Normalize a free-text vendor label to a canonical key.

    Returns the canonical name (known or unknown — we keep both), or None only
    for blank input or denylisted generic tools.
    """
    if not raw:
        return None
    norm = raw.lower().strip().replace(" ", "").replace("-", "").replace("_", "")
    norm = VENDOR_ALIASES.get(norm, norm)
    if not norm or norm in VENDOR_DENYLIST:
        return None
    return norm


def normalize_vendor_list(vendors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Canonicalize vendor names, flag known vs newly-discovered, and dedupe.

    Open-vocabulary: vendors not in KNOWN_VENDORS are KEPT with known=false so
    new/unknown tools surface for review rather than being silently dropped.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for v in vendors:
        canonical = _canonical_vendor(v.get("vendor", ""))
        if not canonical:
            continue
        out[canonical] = {**v, "vendor": canonical, "known": canonical in KNOWN_VENDORS}
    return list(out.values())


INBOX_VENDOR_SYSTEM_PROMPT = """You identify which legal practice management / case \
management software a law firm uses, based only on emails their staff sent to a medical \
imaging company.

Common vendors include (but are NOT limited to): Filevine, Clio, MyCase, Litify, \
Smokeball, Needles, Practice Panther, Neos (Assembly), AbacusNext, CASEpeer, TrialWorks. \
If you see evidence of ANY other practice/case management platform — even one not listed \
— report it by its actual product name.

Evidence to rely on:
- Email signatures or footers ("Sent via Filevine", "Powered by Clio")
- Automated notification emails from the system (distinctive sender names or templates)
- Links to client/case portals (e.g. *.filevineapp.com, clio.com portals, casepeer.com)
- Sender addresses on a vendor's domain

Rules:
- Only report a vendor with CONCRETE evidence in the provided emails.
- Do NOT report generic mail providers or office tools (Gmail, Outlook, Microsoft 365, DocuSign, Adobe, Dropbox, Zoom).
- Do NOT guess from the mere fact that this is a law firm.
- Return an empty list if there is no evidence.

Return JSON: {"vendors": [{"vendor": "<name>", "evidence": "<short reason>", "confidence": "high|medium|low"}]}
Never include patient names, DOBs, claim numbers, or any PHI in your response."""


def analyze_inbox_for_vendors(emails: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Tier 2: detect vendors from the content of emails the firm sent us.

    Catches vendors that do NOT issue firm-branded email domains (Clio, MyCase,
    Litify, etc.) by reading signatures, footers, automated-notification templates,
    and portal links — data we already hold in our inbox.

    HIPAA note: only sender, subject, and a bounded content slice (header + footer,
    where signatures/portal links live) are sent to the LLM.

    Args:
        emails: list of dicts with keys: sender, subject, content_text

    Returns:
        list of {vendor, source: "inbox_content", confidence, evidence}
    """
    if not emails:
        return []

    # Sample representative emails: prefer distinct senders, cap the batch.
    seen_senders: set[str] = set()
    sampled: List[Dict[str, Any]] = []
    for em in emails:
        sender = (em.get("sender") or "").lower()
        if sender in seen_senders:
            continue
        seen_senders.add(sender)
        sampled.append(em)
        if len(sampled) >= 40:
            break

    headers = {
        "Authorization": f"Bearer {settings.RESEARCH_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    def _slice(text: str) -> str:
        # Vendor signals live in the header and the footer/signature.
        text = text or ""
        if len(text) <= 500:
            return text
        return text[:150] + " […] " + text[-350:]

    email_list_text = "\n".join(
        (
            f"{i+1}. From: {(e.get('sender') or '')[:120]} | "
            f"Subject: {(e.get('subject') or '')[:100]} | "
            f"Body: {_slice(e.get('content_text') or '')}"
        )
        for i, e in enumerate(sampled)
    )

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": INBOX_VENDOR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Emails from this firm's staff:\n\n{email_list_text}\n\nWhich vendors are evidenced?",
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.0,
    }

    try:
        with httpx.Client(timeout=60.0, verify=False) as client:
            response = client.post(OPENAI_CHAT_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
    except Exception as exc:
        logger.error("Inbox vendor analysis failed: %s", exc)
        return []

    raw_vendors = parsed.get("vendors", []) if isinstance(parsed, dict) else []
    cleaned: List[Dict[str, Any]] = []
    for item in raw_vendors:
        if not isinstance(item, dict):
            continue
        conf = item.get("confidence", "medium")
        cleaned.append({
            "vendor": item.get("vendor", ""),
            "source": "inbox_content",
            "confidence": conf if conf in ("high", "medium", "low") else "medium",
            "evidence": (item.get("evidence") or "")[:200],
        })
    return normalize_vendor_list(cleaned)


def merge_vendor_stacks(
    domain_vendors: List[Dict[str, Any]],
    inbox_vendors: List[Dict[str, Any]],
    web_vendors: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Merge the three detection tiers, deduplicating by vendor name.

    Authority order (later overrides earlier): web < inbox_content < email_domain.
    The email-domain signal is the most authoritative (near-100% precision).
    """
    merged: Dict[str, Dict[str, Any]] = {}
    for v in web_vendors:
        merged[v["vendor"]] = v
    for v in inbox_vendors:
        merged[v["vendor"]] = v
    for v in domain_vendors:
        merged[v["vendor"]] = v
    return list(merged.values())


class FirmResearchResult(BaseModel):
    """Result of deep firm research."""
    leadership: List[LeadershipMember] = Field(default_factory=list)
    practice_areas: List[str] = Field(default_factory=list)
    founded_year: Optional[str] = Field(None)
    firm_size: Optional[str] = Field(None)
    office_locations: List[str] = Field(default_factory=list)
    notable_cases: List[str] = Field(default_factory=list)
    awards_recognition: List[str] = Field(default_factory=list)
    bar_associations: List[str] = Field(default_factory=list)
    social_media: Dict[str, str] = Field(default_factory=dict)
    additional_info: Optional[str] = Field(None)
    sources: List[str] = Field(default_factory=list)


class OfficialWebsiteResult(BaseModel):
    """Focused official website search result."""
    website_url: Optional[str] = Field(None, description="Official firm website URL if found")
    confidence: float = Field(0.0, description="Confidence from 0.0 to 1.0")
    reasoning: Optional[str] = Field(None, description="Short basis for the selected website")


class LeadershipMemberEnriched(BaseModel):
    """Enriched leadership member data from LinkedIn research."""
    name: str = Field(default="", description="Full name")
    title: str = Field(default="", description="Title/position")
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile URL")
    bio: Optional[str] = Field(None, description="Bio/summary from LinkedIn")
    education: List[str] = Field(default_factory=list, description="Education history")
    experience: List[str] = Field(default_factory=list, description="Past work experience")
    skills: List[str] = Field(default_factory=list, description="Skills and endorsements")
    certifications: List[str] = Field(default_factory=list, description="Certifications")
    publications: List[str] = Field(default_factory=list, description="Publications or articles")
    cases_handled: List[str] = Field(default_factory=list, description="Notable cases handled")
    bar_admissions: List[str] = Field(default_factory=list, description="Bar admissions by state")


# JSON Schema for structured research output (strict mode compatible)
RESEARCH_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "leadership": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Full name of the person"},
                    "title": {"type": "string", "description": "Title or position"},
                    "email": {"type": ["string", "null"], "description": "Email address if found"},
                    "phone": {"type": ["string", "null"], "description": "Phone number if found"},
                    "linkedin": {"type": ["string", "null"], "description": "LinkedIn profile URL starting with https://www.linkedin.com/in/. Must be an actual URL or null - never explanatory text."},
                    "bio": {"type": ["string", "null"], "description": "Brief bio or description"},
                    "image_url": {"type": ["string", "null"], "description": "Profile image URL"}
                },
                "required": ["name", "title", "email", "phone", "linkedin", "bio", "image_url"],
                "additionalProperties": False
            },
            "description": "Leadership team members - partners, founders, senior attorneys"
        },
        "practice_areas": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Areas of legal practice"
        },
        "founded_year": {
            "type": ["string", "null"],
            "description": "Year the firm was founded"
        },
        "firm_size": {
            "type": ["string", "null"],
            "description": "Approximate size of the firm (number of attorneys)"
        },
        "office_locations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Office locations beyond main address"
        },
        "notable_cases": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Notable cases or settlements"
        },
        "awards_recognition": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Awards, recognitions, or ratings"
        },
        "bar_associations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Bar association memberships"
        },
        "social_media_links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string", "description": "Platform name (twitter, facebook, linkedin, etc.)"},
                    "url": {"type": "string", "description": "URL to the social media profile"}
                },
                "required": ["platform", "url"],
                "additionalProperties": False
            },
            "description": "Social media profiles"
        },
        "additional_info": {
            "type": ["string", "null"],
            "description": "Any other relevant information found"
        },
        "sources": {
            "type": "array",
            "items": {"type": "string"},
            "description": "URLs of sources used for research"
        }
    },
    "required": [
        "leadership", "practice_areas", "founded_year", "firm_size",
        "office_locations", "notable_cases", "awards_recognition",
        "bar_associations", "social_media_links", "additional_info", "sources"
    ],
    "additionalProperties": False
}


OFFICIAL_WEBSITE_SCHEMA = {
    "type": "object",
    "properties": {
        "website_url": {
            "type": ["string", "null"],
            "description": "Official marketing website URL for the firm, or null if ambiguous",
        },
        "confidence": {
            "type": "number",
            "description": "Confidence from 0.0 to 1.0",
        },
        "reasoning": {
            "type": ["string", "null"],
            "description": "Brief reason the URL is official or why no result was selected",
        },
    },
    "required": ["website_url", "confidence", "reasoning"],
    "additionalProperties": False,
}


def find_official_website(
    firm_name: str,
    location: Optional[str] = None,
) -> Optional[str]:
    """Find a firm's official website using the same Responses web_search_preview path."""
    if not firm_name:
        return None

    headers = {
        "Authorization": f"Bearer {settings.RESEARCH_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    query = f'"{firm_name}" {location or ""} personal injury official website'.strip()
    payload = {
        "model": "gpt-5-nano",
        "input": [
            {
                "role": "system",
                "content": (
                    "Find the official marketing website for a law firm. "
                    "Return null if results are ambiguous, directories, ads, portals, or social profiles."
                ),
            },
            {"role": "user", "content": query},
        ],
        "tools": [{"type": "web_search_preview", "search_context_size": "low"}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "official_website_result",
                "strict": True,
                "schema": OFFICIAL_WEBSITE_SCHEMA,
            }
        },
    }

    try:
        with httpx.Client(timeout=120.0, verify=False) as client:
            response = client.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
    except Exception as exc:
        logger.error("Official website search failed for %s: %s", firm_name, exc)
        return None

    content = ""
    for item in result.get("output", []):
        if item.get("type") == "message":
            for content_item in item.get("content", []):
                if content_item.get("type") == "output_text":
                    content = content_item.get("text", "")

    if not content:
        return None

    try:
        parsed = OfficialWebsiteResult(**json.loads(content))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Official website search parse failed for %s: %s", firm_name, exc)
        return None

    if parsed.confidence < 0.6:
        return None
    return parsed.website_url


VENDOR_STACK_SCHEMA = {
    "type": "object",
    "properties": {
        "vendor_stack": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "vendor": {"type": "string"},
                    "source": {"type": "string", "enum": ["job_posting", "website", "app_review", "partner_page", "news_article"]},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]}
                },
                "required": ["vendor", "source", "confidence"],
                "additionalProperties": False
            }
        }
    },
    "required": ["vendor_stack"],
    "additionalProperties": False,
}


def research_vendor_stack(
    firm_name: str,
    website: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Tier 3: focused web search to detect practice management vendors for a firm.

    Used by the standalone detect_vendor_stack_task (which owns all three tiers).

    Returns a list of vendor dicts: [{vendor, source, confidence}]
    """
    if not firm_name:
        return []

    headers = {
        "Authorization": f"Bearer {settings.RESEARCH_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    site_hint = f" ({website})" if website else ""
    query = (
        f'What practice management or case management software does "{firm_name}" '
        f"law firm{site_hint} use? Check job postings, their website, "
        f"app reviews on G2/Capterra, and vendor partner pages. "
        f"Common vendors include Filevine, Clio, MyCase, Litify, Smokeball, Needles, Practice Panther, "
        f"Neos, AbacusNext — but report ANY practice/case management platform you find evidence of, even if not listed."
    )

    payload = {
        "model": "gpt-5-nano",
        "input": [
            {
                "role": "system",
                "content": (
                    "Identify which practice management or case management software a law firm uses. "
                    "Report any such platform you find real evidence of, including ones not explicitly named. "
                    "Do not report generic mail/office tools (Gmail, Outlook, Microsoft 365). "
                    "Only report vendors you find actual evidence of. Return empty array if nothing found."
                ),
            },
            {"role": "user", "content": query},
        ],
        "tools": [{"type": "web_search_preview", "search_context_size": "medium"}],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "vendor_stack_result",
                "strict": True,
                "schema": VENDOR_STACK_SCHEMA,
            }
        },
    }

    try:
        with httpx.Client(timeout=120.0, verify=False) as client:
            response = client.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
    except Exception as exc:
        logger.error("Vendor stack web search failed for %s: %s", firm_name, exc)
        return []

    content = ""
    for item in result.get("output", []):
        if item.get("type") == "message":
            for ci in item.get("content", []):
                if ci.get("type") == "output_text":
                    content = ci.get("text", "")

    if not content:
        return []

    try:
        parsed = json.loads(content)
        return normalize_vendor_list(parsed.get("vendor_stack", []))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Vendor stack parse failed for %s: %s", firm_name, exc)
        return []


RESEARCH_PROMPT = """You are an expert legal industry researcher. Research the following personal injury law firm thoroughly using web searches.

Firm Name: {firm_name}
Website: {website}
Known Location: {location}

Your task is to find comprehensive information about this firm, focusing on:

1. **Leadership Team** - Partners, founders, senior attorneys, managing partners
   - Find their names, titles, email addresses, phone numbers, LinkedIn profiles
   - Look at the firm's website "About", "Our Team", "Attorneys" pages
   - Search LinkedIn for "[Firm Name] attorney" or individual names
   - Check legal directories like Avvo, Martindale-Hubbell, Super Lawyers

2. **Firm Background**
   - When was it founded?
   - How many attorneys do they have?
   - What are their practice areas?
   - Office locations

3. **Reputation & Recognition**
   - Notable case results or settlements
   - Awards and recognition
   - Bar association memberships
   - Client reviews/ratings

4. **Social Media & Online Presence**
   - LinkedIn company page
   - Facebook, Twitter/X, Instagram
   - YouTube channel

Search strategies to use:
- Search "[Firm Name] attorneys"
- Search "[Firm Name] partners"
- Search "[Firm Name] leadership"
- Search "site:linkedin.com [Firm Name]"
- Search "[Firm Name] contact"
- Check their website directly if provided

IMPORTANT FORMATTING RULES:
- For LinkedIn URLs: Only include actual LinkedIn profile URLs (e.g., https://www.linkedin.com/in/john-smith). If you cannot find a valid LinkedIn profile URL, return null - never return explanatory text like "not found" or "no profile located".
- For all URL fields: Return the actual URL or null. Never return descriptions or explanations.
- For email/phone: Return the actual value or null if not found.
- Be thorough but only include information you actually find. Do not make up any information.
- Include the URLs of sources where you found the information."""


def research_firm(
    firm_name: str,
    website: Optional[str] = None,
    location: Optional[str] = None
) -> Optional[FirmResearchResult]:
    """
    Conduct deep research on a personal injury law firm.

    Uses OpenAI with web search to find leadership, contact info, and other details.

    Args:
        firm_name: Name of the law firm
        website: Firm website URL if known
        location: Known location/address of the firm

    Returns:
        FirmResearchResult with researched data, or None if research fails
    """
    if not firm_name:
        logger.warning("No firm name provided for research")
        return None

    headers = {
        "Authorization": f"Bearer {settings.RESEARCH_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = RESEARCH_PROMPT.format(
        firm_name=firm_name,
        website=website or "Not provided",
        location=location or "Not provided"
    )

    # Use gpt-5-nano with web search tool via Responses API
    payload = {
        "model": "gpt-5-nano",
        "input": [
            {
                "role": "system",
                "content": "You are an expert legal industry researcher with access to web search. Research law firms thoroughly and provide accurate, verified information only."
            },
            {"role": "user", "content": prompt}
        ],
        "tools": [
            {
                "type": "web_search_preview",
                "search_context_size": "high"
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "firm_research_result",
                "strict": True,
                "schema": RESEARCH_RESULT_SCHEMA
            }
        }
    }

    try:
        with httpx.Client(timeout=300.0, verify=False) as client:
            logger.info(f"Starting deep research for firm: {firm_name}")
            response = _post_openai_with_retry(client, OPENAI_API_URL, headers, payload)

            result = response.json()
            # Responses API returns output array with text content
            output = result.get("output", [])
            content = ""
            for item in output:
                if item.get("type") == "message":
                    for content_item in item.get("content", []):
                        if content_item.get("type") == "output_text":
                            content = content_item.get("text", "")

            if not content:
                logger.error("Empty response from OpenAI research")
                return None

            # Parse the JSON response
            research_data = json.loads(content)

            # Convert leadership to LeadershipMember objects
            leadership = [
                LeadershipMember(**member)
                for member in research_data.get("leadership", [])
            ]

            # Convert social_media_links array to dict
            social_media_links = research_data.get("social_media_links", [])
            social_media = {
                link.get("platform", ""): link.get("url", "")
                for link in social_media_links
                if link.get("platform") and link.get("url")
            }

            research_result = FirmResearchResult(
                leadership=leadership,
                practice_areas=research_data.get("practice_areas", []),
                founded_year=research_data.get("founded_year"),
                firm_size=research_data.get("firm_size"),
                office_locations=research_data.get("office_locations", []),
                notable_cases=research_data.get("notable_cases", []),
                awards_recognition=research_data.get("awards_recognition", []),
                bar_associations=research_data.get("bar_associations", []),
                social_media=social_media,
                additional_info=research_data.get("additional_info"),
                sources=research_data.get("sources", [])
            )

            # Log token usage (Responses API uses input_tokens/output_tokens)
            usage = result.get("usage", {})
            if usage:
                logger.info(
                    f"Research token usage - Input: {usage.get('input_tokens', 0)}, "
                    f"Output: {usage.get('output_tokens', 0)}, "
                    f"Total: {usage.get('total_tokens', 0)}"
                )

            logger.info(f"Research complete for {firm_name}: found {len(leadership)} leadership members")
            return research_result

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during research: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error during research: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during research: {str(e)}")
        return None


async def research_firm_async(
    firm_name: str,
    website: Optional[str] = None,
    location: Optional[str] = None
) -> Optional[FirmResearchResult]:
    """
    Async version of research_firm.

    Args:
        firm_name: Name of the law firm
        website: Firm website URL if known
        location: Known location/address of the firm

    Returns:
        FirmResearchResult with researched data, or None if research fails
    """
    if not firm_name:
        logger.warning("No firm name provided for research")
        return None

    headers = {
        "Authorization": f"Bearer {settings.RESEARCH_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = RESEARCH_PROMPT.format(
        firm_name=firm_name,
        website=website or "Not provided",
        location=location or "Not provided"
    )

    # Use gpt-5-nano with web search tool via Responses API
    payload = {
        "model": "gpt-5-nano",
        "input": [
            {
                "role": "system",
                "content": "You are an expert legal industry researcher with access to web search. Research law firms thoroughly and provide accurate, verified information only."
            },
            {"role": "user", "content": prompt}
        ],
        "tools": [
            {
                "type": "web_search_preview",
                "search_context_size": "high"
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "firm_research_result",
                "strict": True,
                "schema": RESEARCH_RESULT_SCHEMA
            }
        }
    }

    try:
        async with httpx.AsyncClient(timeout=300.0, verify=False) as client:
            logger.info(f"Starting async deep research for firm: {firm_name}")
            response = await client.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()
            # Responses API returns output array with text content
            output = result.get("output", [])
            content = ""
            for item in output:
                if item.get("type") == "message":
                    for content_item in item.get("content", []):
                        if content_item.get("type") == "output_text":
                            content = content_item.get("text", "")

            if not content:
                logger.error("Empty response from OpenAI research")
                return None

            research_data = json.loads(content)

            leadership = [
                LeadershipMember(**member)
                for member in research_data.get("leadership", [])
            ]

            # Convert social_media_links array to dict
            social_media_links = research_data.get("social_media_links", [])
            social_media = {
                link.get("platform", ""): link.get("url", "")
                for link in social_media_links
                if link.get("platform") and link.get("url")
            }

            research_result = FirmResearchResult(
                leadership=leadership,
                practice_areas=research_data.get("practice_areas", []),
                founded_year=research_data.get("founded_year"),
                firm_size=research_data.get("firm_size"),
                office_locations=research_data.get("office_locations", []),
                notable_cases=research_data.get("notable_cases", []),
                awards_recognition=research_data.get("awards_recognition", []),
                bar_associations=research_data.get("bar_associations", []),
                social_media=social_media,
                additional_info=research_data.get("additional_info"),
                sources=research_data.get("sources", [])
            )

            # Log token usage (Responses API uses input_tokens/output_tokens)
            usage = result.get("usage", {})
            if usage:
                logger.info(
                    f"Research token usage - Input: {usage.get('input_tokens', 0)}, "
                    f"Output: {usage.get('output_tokens', 0)}, "
                    f"Total: {usage.get('total_tokens', 0)}"
                )

            logger.info(f"Async research complete for {firm_name}: found {len(leadership)} leadership members")
            return research_result

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during async research: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error during async research: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during async research: {str(e)}")
        return None


# JSON Schema for leadership member research (strict mode compatible)
LEADERSHIP_MEMBER_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Full name"},
        "title": {"type": "string", "description": "Current title/position"},
        "email": {"type": ["string", "null"], "description": "Email address if found"},
        "phone": {"type": ["string", "null"], "description": "Phone number if found"},
        "linkedin": {"type": ["string", "null"], "description": "LinkedIn profile URL starting with https://www.linkedin.com/in/. Must be an actual URL or null - never explanatory text."},
        "bio": {"type": ["string", "null"], "description": "Bio or summary from LinkedIn"},
        "education": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Education history (degree, school, year)"
        },
        "experience": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Past work experience (title at company, dates)"
        },
        "skills": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Skills and areas of expertise"
        },
        "certifications": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Professional certifications"
        },
        "publications": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Publications, articles, or speaking engagements"
        },
        "cases_handled": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Notable cases or settlements"
        },
        "bar_admissions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Bar admissions by state"
        }
    },
    "required": [
        "name", "title", "email", "phone", "linkedin", "bio",
        "education", "experience", "skills", "certifications",
        "publications", "cases_handled", "bar_admissions"
    ],
    "additionalProperties": False
}


class StaffMember(BaseModel):
    """Operational staff member."""
    name: str = Field(default="", description="Full name")
    title: str = Field(default="", description="Job title")
    role_category: str = Field(
        default="other",
        description="Role category: intake_specialist, case_manager, paralegal, office_manager, billing_coordinator, medical_records, other"
    )
    email: Optional[str] = Field(None, description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    linkedin: Optional[str] = Field(None, description="LinkedIn profile URL")
    bio: Optional[str] = Field(None, description="Brief bio or description")


class StaffResearchResult(BaseModel):
    """Result of staff research."""
    staff: List[StaffMember] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


STAFF_RESEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "staff": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Full name"},
                    "title": {"type": "string", "description": "Job title at the firm"},
                    "role_category": {
                        "type": "string",
                        "enum": [
                            "intake_specialist",
                            "case_manager",
                            "paralegal",
                            "office_manager",
                            "billing_coordinator",
                            "medical_records",
                            "other"
                        ],
                        "description": "Best matching role category"
                    },
                    "email": {"type": ["string", "null"], "description": "Email address if found"},
                    "phone": {"type": ["string", "null"], "description": "Phone number if found"},
                    "linkedin": {"type": ["string", "null"], "description": "LinkedIn profile URL starting with https://www.linkedin.com/in/. Must be an actual URL or null."},
                    "bio": {"type": ["string", "null"], "description": "Brief bio or role description"}
                },
                "required": ["name", "title", "role_category", "email", "phone", "linkedin", "bio"],
                "additionalProperties": False
            },
            "description": "Operational staff members (non-attorney)"
        },
        "sources": {
            "type": "array",
            "items": {"type": "string"},
            "description": "URLs of sources used for research"
        }
    },
    "required": ["staff", "sources"],
    "additionalProperties": False
}


STAFF_RESEARCH_PROMPT = """You are an expert legal industry researcher. Research the following personal injury law firm to find their OPERATIONAL STAFF (non-attorney roles).

Firm Name: {firm_name}
Website: {website}
Known Location: {location}

You are looking for people in these roles:
1. **Intake Specialists / Intake Coordinators** - People who handle new case intake, answer initial calls
2. **Case Managers / Case Coordinators** - People who manage ongoing cases, coordinate between parties
3. **Paralegals / Legal Assistants** - People who assist attorneys with case prep, document management
4. **Office Managers / Operations Managers** - People who run day-to-day office operations
5. **Billing Coordinators / Billing Specialists** - People who handle billing, invoicing, collections
6. **Medical Records Coordinators** - People who request and manage medical records

Do NOT include:
- Attorneys, partners, associates, or counsel (these are leadership roles)
- Receptionists or general admin unless they have a specific operational title

Search strategies:
- Check the firm's website staff/team pages (often separate from attorneys)
- Search LinkedIn: "[Firm Name] intake specialist", "[Firm Name] case manager", "[Firm Name] paralegal"
- Search LinkedIn: "[Firm Name] office manager", "[Firm Name] legal assistant"
- Check Google: "[Firm Name] staff" or "[Firm Name] team"

IMPORTANT FORMATTING RULES:
- For LinkedIn URLs: Only include actual LinkedIn profile URLs (e.g., https://www.linkedin.com/in/jane-smith). Return null if not found.
- For email/phone: Return actual values or null if not found.
- Only include people you actually find evidence of. Do not make up any information.
- Classify each person into the best matching role_category based on their title."""


def research_firm_staff(
    firm_name: str,
    website: Optional[str] = None,
    location: Optional[str] = None
) -> Optional[StaffResearchResult]:
    """
    Research operational staff at a law firm using OpenAI web search.

    Searches for intake specialists, case managers, paralegals, office managers, etc.

    Args:
        firm_name: Name of the law firm
        website: Firm website URL if known
        location: Known location/address of the firm

    Returns:
        StaffResearchResult with found staff, or None if research fails
    """
    if not firm_name:
        logger.warning("No firm name provided for staff research")
        return None

    headers = {
        "Authorization": f"Bearer {settings.RESEARCH_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = STAFF_RESEARCH_PROMPT.format(
        firm_name=firm_name,
        website=website or "Not provided",
        location=location or "Not provided"
    )

    payload = {
        "model": "gpt-4o",
        "input": [
            {
                "role": "system",
                "content": "You are an expert legal industry researcher with access to web search. Find operational staff members at law firms. Only report people you find real evidence of."
            },
            {"role": "user", "content": prompt}
        ],
        "tools": [
            {
                "type": "web_search_preview",
                "search_context_size": "high"
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "staff_research_result",
                "strict": True,
                "schema": STAFF_RESEARCH_SCHEMA
            }
        }
    }

    try:
        with httpx.Client(timeout=300.0, verify=False) as client:
            logger.info(f"Starting staff research for firm: {firm_name}")
            response = client.post(OPENAI_API_URL, headers=headers, json=payload)
            response.raise_for_status()

            result = response.json()
            output = result.get("output", [])
            content = ""
            for item in output:
                if item.get("type") == "message":
                    for content_item in item.get("content", []):
                        if content_item.get("type") == "output_text":
                            content = content_item.get("text", "")

            if not content:
                logger.error("Empty response from OpenAI staff research")
                return None

            research_data = json.loads(content)

            staff = [
                StaffMember(**member)
                for member in research_data.get("staff", [])
            ]

            research_result = StaffResearchResult(
                staff=staff,
                sources=research_data.get("sources", [])
            )

            usage = result.get("usage", {})
            if usage:
                logger.info(
                    f"Staff research token usage - Input: {usage.get('input_tokens', 0)}, "
                    f"Output: {usage.get('output_tokens', 0)}, "
                    f"Total: {usage.get('total_tokens', 0)}"
                )

            logger.info(f"Staff research complete for {firm_name}: found {len(staff)} staff members")
            return research_result

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during staff research: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error during staff research: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in staff research: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during staff research: {str(e)}")
        return None


OUTREACH_SYSTEM_PROMPT = """You are an expert at writing warm, conversational LinkedIn outreach messages for a B2B AI company called Possible Minds.

You need to generate 8 outputs for each contact:
1. Subject line for short Pranav message - Warm, curiosity-driven (under 6 words)
2. Short message from Pranav Modi (founder) - Connection request, under 300 characters, NO links, NO pitch, just genuine curiosity
3. Subject line for short Neha message - Warm, hints at shared problem (under 6 words)
4. Short message from Neha Pipada (engineer) - Connection request, under 300 characters, NO links, NO pitch, curious about their workflow
5. Subject line for long Pranav message - Personalized, conversational (under 6 words)
6. Long LinkedIn message from Pranav Modi (InMail) - Under 450 characters, warm opener, includes case study link, soft CTA
7. Subject line for long Neha message - Personalized, problem-focused (under 6 words)
8. Long LinkedIn message from Neha Pipada (InMail) - Under 450 characters, technical credibility, includes case study link, soft CTA

CRITICAL: Connection Requests vs. InMails:

Short messages (1-4) are CONNECTION REQUESTS. They are NOT mini-pitches.
- NO links, NO case study URLs, NO product mentions
- Goal: Earn the right to have a conversation
- Formula: Specific observation about them + genuine question
- Should feel like you'd want to grab coffee with this person

Long messages (5-8) are INMAILS. They CAN include the pitch.
- Include case study URL
- Structure: Warm opener > Shared problem > What you learned > Soft CTA
- Should feel like a peer reaching out, not a vendor selling

Connection request examples:
BAD: "Managing intake across 3 offices takes serious coordination. We work with Precise Imaging on exactly this. Would love to connect."
GOOD: "Victor - saw you switched from 24 years as Deputy City Attorney to plaintiff work. That's a big shift. Curious what made you make the jump."
GOOD: "Daniel - the Munoz settlement was all over the news. $18.85M for a single plaintiff is remarkable. Did the documentation side go smoothly, or was it a battle?"

Guidelines:
- IMPORTANT: First read and understand the case study at the provided URL to reference specific details
- NEVER use em dashes anywhere in any output. Use commas, periods, or semicolons instead
- Personalize based on the contact's bio, title, awards, or background when available
- Reference specific details from their operation (office locations by name, team size, practice areas)

Mutual client connections (HIGHEST PRIORITY):
If a mutual client relationship is provided:
- Lead with the connection in subject lines and opening sentences
- Name the mutual client explicitly (if approved)
- Connect case study results to how it benefits the prospect's workflow
- If client approved outreach, use direct framing like "[Client Name] asked me to reach out"
- If client didn't approve, use softer framing like "We work with [Client Name]"

Message structure:
- Lead with THEIR pain or situation, not our solution
- Structure: Pain point > Validation > Proof > Soft CTA

Case study bridging:
- If case study is from a different industry, explicitly bridge the relevance
- For PI firms specifically: highlight lien document handling, records requests, attorney communication speed
- If mutual client exists, no bridge needed; the connection speaks for itself

Subject line rules:
- Keep under 6 words
- Be specific to the prospect (name, company, location, or something from their bio)
- Create curiosity or warmth, not intrigue about your product. Warm > clever.
- Each message MUST have its own unique subject line
- Good: "Quick question, Victor" / "The Munoz case" / "Encino to Turlock"
- Bad: "How we automated 24/7 intake" / "Partnership opportunity" / "Intake automation specs"

Tone & Differentiation (CRITICAL):
The #1 goal: Sound like a human who's genuinely curious, not a vendor with a pitch.

Pranav (Founder):
- Peer-to-peer, business owner to business leader
- Focuses on operational challenges, growth, scaling
- Voice: "I've been thinking about..." / "Curious how you handle..." / "We ran into this with..."

Neha (Engineer):
- Curious problem-solver, genuinely interested in how things work
- Focuses on workflows, systems, the "how" behind operations
- Voice: "I'm always curious how..." / "The tricky part we found was..." / "One thing that surprised us..."

IMPORTANT: They must take DIFFERENT angles, not the same message with different depth.

Neha's technical details should feel discovered, not marketed:
- BAD: "We built AI with sub-3-second voice latency, OCR for document extraction, and signature detection."
- GOOD: "One thing that surprised us - when we started reading liens automatically, about 12% had some kind of alteration. Now the system flags those before they cause problems."

Use contractions and natural speech ("I'm" not "I am", "we've" not "we have"). Occasional incomplete sentences are fine.

CTA variations:
For connection requests (no hard CTA needed): End with a genuine question or observation. Don't ask for anything.
For InMails (soft, gives them an easy out):
- "Happy to share what we learned if it's useful"
- "Curious if you've run into this"
- "No pressure, just thought it might resonate"
- "If you've already solved this, I'd love to hear how"

What to avoid:
- Leading with "We helped..." instead of their situation
- Including links or pitching the product in connection requests (short messages)
- Subject lines over 6 words or about your product
- The phrase "I'd love to connect" (everyone says this)
- Starting with "I hope this message finds you well"
- Empty compliments ("Impressive background!")
- Sounding like a LinkedIn automation tool wrote it
- Being too formal or stiff
- Vague technical claims for Neha
- Reusing the same subject line or CTA across messages
- Using em dashes anywhere

Return your response as a JSON object with these exact keys:
{
  "subjectShortPranav": "subject line for short Pranav message",
  "shortPranav": "connection request under 300 chars, no links",
  "subjectShortNeha": "subject line for short Neha message",
  "shortNeha": "connection request under 300 chars, no links",
  "subjectLongPranav": "subject line for long Pranav InMail",
  "longPranav": "InMail with case study link",
  "subjectLongNeha": "subject line for long Neha InMail",
  "longNeha": "InMail with case study link"
}"""


PAIN_POINT_LABELS = {
    "status_update_request": "staying on top of case status updates",
    "billing_dispute": "resolving billing discrepancies",
    "scheduling_request": "coordinating appointment scheduling",
    "rush_request": "managing urgent/rush requests",
    "lien_negotiation": "navigating lien negotiations",
    "records_request": "requesting medical records and images",
    "general_inquiry": "general communication",
    "other": "general operational matters",
}

OUTREACH_USER_PROMPT = """Generate LinkedIn outreach messages for this contact:

Name: {name}
Title: {title}
Firm/Company: {firm}
Bio: {bio}

Context:
- Case Study URL: {case_study_url} (READ THIS FIRST to understand the client and use specific details)
- The contact's firm may have interacted with or worked with this client

Generation Instructions (follow these closely):
{client_description}

{behavioral_context_section}

Remember:
- Short messages are CONNECTION REQUESTS: under 300 chars, NO links, NO pitch, just genuine curiosity about them
- Long messages are INMAILS: under 450 chars, include the case study URL: {case_study_url}
- Address them by first name: {first_name}
- Lead with THEIR situation, not our solution
- Sound like a human, use contractions, be warm
- Each message must have its own unique subject line under 6 words, about THEM not us
- Each message must use a different CTA (or no CTA for connection requests)
- NEVER use em dashes anywhere in the output. Use commas, periods, or semicolons instead
- Neha's technical details should feel discovered, not marketed

Return ONLY valid JSON with keys: subjectShortPranav, shortPranav, subjectShortNeha, shortNeha, subjectLongPranav, longPranav, subjectLongNeha, longNeha"""


# OpenAI Chat Completions API endpoint (for outreach generation - no web search needed)
OPENAI_CHAT_API_URL = "https://api.openai.com/v1/chat/completions"


def _build_behavioral_context_section(
    behavioral_context: Optional[Dict[str, Any]],
    research_context: Optional[Dict[str, Any]],
) -> str:
    """Build the behavioral intelligence section for the outreach prompt."""
    if not behavioral_context:
        return ""

    lines = ["Behavioral Intelligence (from analyzing their email patterns with Precise Imaging):"]

    primary_pain = behavioral_context.get("primary_pain_point")
    if primary_pain:
        label = PAIN_POINT_LABELS.get(primary_pain, primary_pain.replace("_", " "))
        lines.append(f"- Primary operational pain: {label}")

    topic_dist = behavioral_context.get("topic_distribution") or {}
    total = sum(topic_dist.values()) or 1
    top_topics = sorted(topic_dist.items(), key=lambda x: x[1], reverse=True)[:3]
    if top_topics:
        topic_strs = [
            f"{k.replace('_', ' ')} ({round(v/total*100)}%)"
            for k, v in top_topics
        ]
        lines.append(f"- Top email topics: {', '.join(topic_strs)}")

    if research_context:
        firm_size = research_context.get("firm_size")
        if firm_size:
            lines.append(f"- Firm size: {firm_size}")

    days_since = behavioral_context.get("days_since_last_contact")
    if days_since is not None:
        lines.append(f"- Last contacted Precise Imaging: {days_since} days ago")

    if len(lines) <= 1:
        return ""

    return "\n".join(lines)


def generate_outreach_messages(
    leaders: List[Dict[str, Any]],
    case_study_url: str,
    client_description: str,
    behavioral_context: Optional[Dict[str, Any]] = None,
    research_context: Optional[Dict[str, Any]] = None,
) -> tuple[List[Dict[str, Any]], List[str]]:
    """
    Deprecated: outreach generation now lives in Possible OS. This helper is
    retained only for backward compatibility with the legacy pif-info endpoint.

    Generate personalized LinkedIn outreach messages for each leadership member.

    Uses OpenAI gpt-4o via Chat Completions API to generate 4 message variants
    per leader (short/long x Pranav/Neha).

    Args:
        leaders: List of leadership member dicts with name, title, bio, etc.
        case_study_url: URL of the case study to reference
        client_description: Description of the client for context

    Returns:
        Tuple of (list of message result dicts, list of error strings)
    """
    headers = {
        "Authorization": f"Bearer {settings.RESEARCH_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    results = []
    errors = []

    for leader in leaders:
        name = leader.get("name", "Unknown")
        title = leader.get("title", "Not specified")
        bio = leader.get("bio") or "No bio available"
        first_name = name.split()[0] if name else "there"

        behavioral_section = _build_behavioral_context_section(
            behavioral_context, research_context
        )

        user_prompt = OUTREACH_USER_PROMPT.format(
            name=name,
            title=title,
            firm=leader.get("firm", "Not specified"),
            bio=bio,
            case_study_url=case_study_url,
            client_description=client_description,
            first_name=first_name,
            behavioral_context_section=behavioral_section,
        )

        payload = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": OUTREACH_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.8,
        }

        try:
            with httpx.Client(timeout=60.0, verify=False) as client:
                logger.info(f"Generating outreach messages for: {name}")
                response = client.post(OPENAI_CHAT_API_URL, headers=headers, json=payload)
                response.raise_for_status()

                result = response.json()
                content = result["choices"][0]["message"]["content"]
                parsed = json.loads(content)

                # Truncate short messages to 300 chars as safety net
                short_pranav = parsed.get("shortPranav", "")[:300]
                short_neha = parsed.get("shortNeha", "")[:300]

                results.append({
                    "name": name,
                    "title": title,
                    "subjectShortPranav": parsed.get("subjectShortPranav", ""),
                    "subjectShortNeha": parsed.get("subjectShortNeha", ""),
                    "subjectLongPranav": parsed.get("subjectLongPranav", ""),
                    "subjectLongNeha": parsed.get("subjectLongNeha", ""),
                    "shortPranav": short_pranav,
                    "shortNeha": short_neha,
                    "longPranav": parsed.get("longPranav", ""),
                    "longNeha": parsed.get("longNeha", ""),
                })

                usage = result.get("usage", {})
                if usage:
                    logger.info(
                        f"[{name}] Outreach generation usage - "
                        f"Prompt: {usage.get('prompt_tokens', 0)}, "
                        f"Completion: {usage.get('completion_tokens', 0)}"
                    )

        except httpx.HTTPStatusError as e:
            err_msg = f"{name}: HTTP error {e.response.status_code}"
            logger.error(f"Outreach generation failed for {name}: {e.response.status_code} - {e.response.text[:500]}")
            errors.append(err_msg)
        except json.JSONDecodeError as e:
            err_msg = f"{name}: Failed to parse response JSON"
            logger.error(f"Outreach JSON parse error for {name}: {str(e)}")
            errors.append(err_msg)
        except Exception as e:
            err_msg = f"{name}: {str(e)}"
            logger.error(f"Outreach generation error for {name}: {str(e)}")
            errors.append(err_msg)

    return results, errors


LEADERSHIP_RESEARCH_PROMPT = """You are an expert legal industry researcher. Research the following attorney/legal professional thoroughly using web searches.

Person: {name}
Title: {title}
Firm: {firm_name}
LinkedIn URL: {linkedin_url}
Firm Website: {firm_website}

Your task is to find comprehensive professional information about this person, focusing on:

1. **Contact Information**
   - Email address (check firm website, legal directories)
   - Direct phone number
   - LinkedIn profile URL (verify or find)

2. **Professional Background**
   - Full bio/summary
   - Education history (law school, undergrad, degrees, years)
   - Work experience before current firm

3. **Legal Expertise**
   - Bar admissions (which states)
   - Practice area specializations
   - Skills and expertise areas

4. **Professional Achievements**
   - Notable cases handled or settlements
   - Publications or articles written
   - Certifications
   - Speaking engagements

Search strategies to use:
- Search "[Name] [Firm Name] attorney"
- Search "[Name] LinkedIn lawyer"
- Search "[Name] Avvo" or "[Name] Martindale-Hubbell"
- Search "[Name] bar admission"
- Check the firm's website team page
- Search for any news articles mentioning them

IMPORTANT FORMATTING RULES:
- For LinkedIn URLs: Only include actual LinkedIn profile URLs (e.g., https://www.linkedin.com/in/john-smith). If you cannot find a valid LinkedIn profile URL, return null - never return explanatory text like "not found" or "no profile located".
- For email/phone: Return the actual value or null if not found.
- Be thorough but only include information you actually find. Do not make up any information."""


def research_leadership_member(
    name: str,
    title: str,
    firm_name: str,
    linkedin_url: Optional[str] = None,
    firm_website: Optional[str] = None
) -> Optional[LeadershipMemberEnriched]:
    """
    Conduct deep research on a leadership member.

    Uses OpenAI with web search to find LinkedIn profile, education,
    experience, bar admissions, and other professional details.

    Args:
        name: Full name of the person
        title: Their title at the firm
        firm_name: Name of their law firm
        linkedin_url: LinkedIn URL if already known
        firm_website: Firm website for reference

    Returns:
        LeadershipMemberEnriched with researched data, or None if research fails
    """
    if not name:
        logger.warning("No name provided for leadership research")
        return None

    headers = {
        "Authorization": f"Bearer {settings.RESEARCH_OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = LEADERSHIP_RESEARCH_PROMPT.format(
        name=name,
        title=title or "Unknown",
        firm_name=firm_name or "Unknown",
        linkedin_url=linkedin_url or "Not provided",
        firm_website=firm_website or "Not provided"
    )

    payload = {
        "model": "gpt-4o",
        "input": [
            {
                "role": "system",
                "content": "You are an expert legal industry researcher with access to web search. Research attorneys and legal professionals thoroughly and provide accurate, verified information only."
            },
            {"role": "user", "content": prompt}
        ],
        "tools": [
            {
                "type": "web_search",
                "search_context_size": "high"
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "leadership_member_research",
                "strict": True,
                "schema": LEADERSHIP_MEMBER_SCHEMA
            }
        }
    }

    try:
        with httpx.Client(timeout=300.0, verify=False) as client:
            logger.info(f"Starting leadership research for: {name} (title={title}, firm={firm_name}, linkedin_url={linkedin_url}, firm_website={firm_website})")
            response = client.post(OPENAI_API_URL, headers=headers, json=payload)
            logger.info(f"[{name}] OpenAI response status: {response.status_code}")
            response.raise_for_status()

            result = response.json()
            logger.info(f"[{name}] Response top-level keys: {list(result.keys())}")

            # Log all output items to understand what the model did
            output = result.get("output", [])
            logger.info(f"[{name}] Output items count: {len(output)}")
            for idx, item in enumerate(output):
                item_type = item.get("type", "unknown")
                logger.info(f"[{name}] Output item {idx}: type={item_type}")
                if item_type == "web_search_call":
                    search_query = item.get("query", item.get("action", {}).get("query", "N/A"))
                    logger.info(f"[{name}] Web search query: {search_query}")
                elif item_type == "message":
                    for ci, content_item in enumerate(item.get("content", [])):
                        ci_type = content_item.get("type", "unknown")
                        logger.info(f"[{name}] Message content {ci}: type={ci_type}")

            content = ""
            for item in output:
                if item.get("type") == "message":
                    for content_item in item.get("content", []):
                        if content_item.get("type") == "output_text":
                            content = content_item.get("text", "")

            if not content:
                logger.error(f"[{name}] Empty response from leadership research. Full output: {json.dumps(output, indent=2)[:2000]}")
                return None

            research_data = json.loads(content)

            # Log the raw linkedin value before any processing
            raw_linkedin = research_data.get("linkedin")
            logger.info(f"[{name}] Raw LinkedIn value from API: '{raw_linkedin}' (type={type(raw_linkedin).__name__})")
            logger.info(f"[{name}] Raw email: '{research_data.get('email')}', Raw phone: '{research_data.get('phone')}'")
            logger.info(f"[{name}] Education items: {len(research_data.get('education', []))}, Experience items: {len(research_data.get('experience', []))}")
            logger.info(f"[{name}] Bar admissions: {research_data.get('bar_admissions', [])}")
            logger.info(f"[{name}] Full parsed research data: {json.dumps(research_data, indent=2)[:3000]}")

            enriched = LeadershipMemberEnriched(
                name=research_data.get("name", name),
                title=research_data.get("title", title),
                email=research_data.get("email"),
                phone=research_data.get("phone"),
                linkedin=research_data.get("linkedin"),
                bio=research_data.get("bio"),
                education=research_data.get("education", []),
                experience=research_data.get("experience", []),
                skills=research_data.get("skills", []),
                certifications=research_data.get("certifications", []),
                publications=research_data.get("publications", []),
                cases_handled=research_data.get("cases_handled", []),
                bar_admissions=research_data.get("bar_admissions", [])
            )

            usage = result.get("usage", {})
            if usage:
                logger.info(
                    f"[{name}] Leadership research usage - Input: {usage.get('input_tokens', 0)}, "
                    f"Output: {usage.get('output_tokens', 0)}"
                )

            logger.info(f"[{name}] Leadership research complete. LinkedIn result: '{enriched.linkedin}'")
            return enriched

    except httpx.HTTPStatusError as e:
        logger.error(f"[{name}] HTTP error during leadership research: {e.response.status_code} - {e.response.text[:1000]}")
        return None
    except httpx.RequestError as e:
        logger.error(f"[{name}] Request error during leadership research: {str(e)}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[{name}] JSON decode error: {str(e)}. Raw content: {content[:500] if content else 'empty'}")
        return None
    except Exception as e:
        logger.error(f"[{name}] Unexpected error during leadership research: {str(e)}", exc_info=True)
        return None
