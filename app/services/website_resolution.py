"""Tiered website resolution for PIF firms."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

from app.models.firm_alias import FirmAlias
from app.models.pif_info import PifInfo
from app.services.firm_identity import (
    canonical_domain,
    is_portal_or_consumer_domain,
    observed_domain,
)

HttpGet = Callable[[str], Any]
WebsiteSearch = Callable[[str, Optional[str]], Optional[str]]

PARKED_PAGE_PHRASES = (
    "domain for sale",
    "buy this domain",
    "this domain is parked",
    "parkingcrew",
    "sedo domain parking",
)

LEGAL_STOPWORDS = {
    "a",
    "and",
    "apc",
    "attorney",
    "attorneys",
    "group",
    "inc",
    "injury",
    "law",
    "lawyer",
    "lawyers",
    "legal",
    "llc",
    "llp",
    "office",
    "offices",
    "pc",
    "pllc",
    "the",
}


@dataclass(frozen=True)
class WebsiteResolutionResult:
    canonical_website: Optional[str]
    website_status: str
    website_source: Optional[str]
    website_confidence: Optional[float]
    review_reason: Optional[str] = None


def resolve_firm_website(
    firm: PifInfo,
    *,
    http_get: Optional[HttpGet] = None,
    search: Optional[WebsiteSearch] = None,
) -> WebsiteResolutionResult:
    """Resolve a firm's canonical website using seed, HTTP verification, search, then review."""
    http_get = http_get or _default_http_get
    search = search or _default_search

    for seed in _seed_domains(firm):
        verified = verify_firm_website(seed, firm.firm_name, http_get=http_get)
        if verified:
            return WebsiteResolutionResult(
                canonical_website=verified,
                website_status="resolved",
                website_source="email_verified",
                website_confidence=0.9,
            )

    search_candidate = None
    if firm.firm_name:
        search_candidate = search(firm.firm_name, _location_hint(firm.addresses or []))

    if search_candidate:
        verified = verify_firm_website(search_candidate, firm.firm_name, http_get=http_get)
        if verified:
            return WebsiteResolutionResult(
                canonical_website=verified,
                website_status="resolved",
                website_source="web_search",
                website_confidence=0.78,
            )

    return queue_website_human_review_stub(
        firm,
        reason="no_verified_website" if search_candidate else "no_search_result",
    )


def verify_firm_website(
    candidate: str,
    firm_name: str,
    *,
    http_get: HttpGet,
) -> Optional[str]:
    """HTTP-verify that a candidate looks like the firm's marketing site."""
    domain = canonical_domain(candidate)
    if not domain:
        return None

    for url in _candidate_urls(domain):
        try:
            response = http_get(url)
        except Exception:
            continue

        status_code = getattr(response, "status_code", 0) or 0
        if status_code >= 400:
            continue

        final_url = str(getattr(response, "url", url))
        final_domain = canonical_domain(final_url)
        if not final_domain or is_portal_or_consumer_domain(final_domain):
            continue

        text = str(getattr(response, "text", "") or "")
        if _looks_parked(text):
            continue

        if _name_matches(firm_name, text) or _name_matches(firm_name, final_domain):
            return final_domain

    return None


def apply_website_resolution(pif: PifInfo, result: WebsiteResolutionResult) -> None:
    """Apply a resolution result to a PIF record without committing."""
    pif.canonical_website = result.canonical_website
    pif.website_status = result.website_status
    pif.website_source = result.website_source
    pif.website_confidence = result.website_confidence


def resolve_and_persist_firm_website(
    db: Session,
    pif: PifInfo,
    *,
    http_get: Optional[HttpGet] = None,
    search: Optional[WebsiteSearch] = None,
) -> WebsiteResolutionResult:
    """Resolve and persist website fields plus observed aliases for one firm."""
    result = resolve_firm_website(pif, http_get=http_get, search=search)
    apply_website_resolution(pif, result)
    persist_aliases_for_firm(db, pif)
    db.add(pif)
    return result


def persist_aliases_for_firm(db: Session, pif: PifInfo) -> None:
    """Persist aliases observed on one firm. This is intentionally per-firm, not a backfill."""
    _upsert_alias_sync(
        db,
        alias_type="legacy_pif_id",
        alias_value=str(pif.id),
        firm_id=pif.id,
        confidence=1.0,
        source="emailtag",
    )

    if pif.canonical_website:
        _upsert_alias_sync(
            db,
            alias_type="domain",
            alias_value=pif.canonical_website,
            firm_id=pif.id,
            confidence=pif.website_confidence or 1.0,
            source=pif.website_source or "website_resolution",
        )

    _persist_domain_alias(db, pif, pif.website, source="pif_info.website")
    for email in pif.emails or []:
        _persist_domain_alias(db, pif, email, source="pif_info.emails")
    for contact in pif.contacts or []:
        if isinstance(contact, dict):
            _persist_domain_alias(db, pif, contact.get("email"), source="pif_info.contacts")


def queue_website_human_review_stub(
    firm: PifInfo,
    *,
    reason: str,
) -> WebsiteResolutionResult:
    """Human-review queue stub for E0. No ticket is created in this packet."""
    status = "pending" if firm.firm_name else "none"
    return WebsiteResolutionResult(
        canonical_website=None,
        website_status=status,
        website_source="human",
        website_confidence=0.0,
        review_reason=reason,
    )


def _persist_domain_alias(db: Session, pif: PifInfo, value: Optional[str], *, source: str) -> None:
    host = observed_domain(value)
    if not host:
        return

    canonical = canonical_domain(value)
    if canonical:
        alias_type = "email_domain" if "@" in str(value) else "alt_domain"
        alias_value = canonical
        confidence = 0.85
    elif is_portal_or_consumer_domain(value):
        alias_type = "vanity_domain"
        alias_value = host
        confidence = 0.8
    else:
        return

    _upsert_alias_sync(
        db,
        alias_type=alias_type,
        alias_value=alias_value,
        firm_id=pif.id,
        confidence=confidence,
        source=source,
    )


def _upsert_alias_sync(
    db: Session,
    *,
    alias_type: str,
    alias_value: str,
    firm_id: Any,
    confidence: float,
    source: str,
) -> FirmAlias:
    normalized = alias_value.lower()
    alias = (
        db.query(FirmAlias)
        .filter(FirmAlias.alias_type == alias_type, FirmAlias.alias_value == normalized)
        .first()
    )
    if alias:
        alias.firm_id = firm_id
        alias.confidence = confidence
        alias.source = source
    else:
        alias = FirmAlias(
            alias_type=alias_type,
            alias_value=normalized,
            firm_id=firm_id,
            confidence=confidence,
            source=source,
        )
    db.add(alias)
    # Flush immediately so subsequent calls in the same session see this row and
    # don't create a duplicate object for the same (alias_type, alias_value) pair.
    db.flush()
    return alias


def _seed_domains(firm: PifInfo) -> list[str]:
    seeds = []
    if firm.website:
        seeds.append(firm.website)
    for email in firm.emails or []:
        domain = canonical_domain(email)
        if domain and domain not in seeds:
            seeds.append(domain)
    return seeds


def _candidate_urls(domain: str) -> Iterable[str]:
    yield f"https://{domain}"
    yield f"http://{domain}"


def _default_http_get(url: str) -> httpx.Response:
    with httpx.Client(timeout=10.0, follow_redirects=True) as client:
        return client.get(url)


def _default_search(firm_name: str, location: Optional[str]) -> Optional[str]:
    from pifstats.src.firm_researcher import find_official_website

    return find_official_website(firm_name, location=location)


def _location_hint(addresses: list[str]) -> Optional[str]:
    return addresses[0] if addresses else None


def _looks_parked(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in PARKED_PAGE_PHRASES)


def _name_matches(firm_name: str, text: str) -> bool:
    tokens = _firm_name_tokens(firm_name)
    if not tokens:
        return True

    haystack = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return any(token in haystack for token in tokens)


def _firm_name_tokens(firm_name: str) -> set[str]:
    raw_tokens = re.findall(r"[a-z0-9]+", firm_name.lower())
    return {token for token in raw_tokens if len(token) > 2 and token not in LEGAL_STOPWORDS}
