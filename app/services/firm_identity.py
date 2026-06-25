"""Canonical firm identity helpers."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlsplit

try:
    from publicsuffix2 import get_sld
except ImportError:  # pragma: no cover - dependency is declared in requirements.txt
    get_sld = None


CONSUMER_DOMAINS = {
    "aol.com",
    "gmail.com",
    "googlemail.com",
    "hotmail.com",
    "icloud.com",
    "live.com",
    "me.com",
    "msn.com",
    "outlook.com",
    "proton.me",
    "protonmail.com",
    "yahoo.com",
    "ymail.com",
}

PORTAL_DOMAINS = {
    "casepeer.com",
    "filevineapp.com",
    "litify.com",
    "smartadvocate.com",
    "smartadvocate.net",
}


def canonical_domain(value: Optional[str]) -> Optional[str]:
    """Return the registrable firm domain for a URL/email, or None for non-identity domains."""
    host = _extract_host(value)
    if not host:
        return None

    host = _strip_www(host)
    if not host or "." not in host:
        return None

    registrable = _registrable_domain(host)
    if not registrable:
        return None

    if _is_consumer_domain(registrable) or _is_portal_domain(host, registrable):
        return None

    return registrable


def observed_domain(value: Optional[str]) -> Optional[str]:
    """Return a normalized host/domain without rejecting vendor or consumer domains."""
    host = _extract_host(value)
    return _strip_www(host) if host else None


def is_portal_or_consumer_domain(value: Optional[str]) -> bool:
    """Return True when a value is a known non-identity portal or consumer domain."""
    host = observed_domain(value)
    if not host:
        return False
    registrable = _registrable_domain(host)
    if not registrable:
        return False
    return _is_consumer_domain(registrable) or _is_portal_domain(host, registrable)


def _extract_host(value: Optional[str]) -> Optional[str]:
    if not value:
        return None

    candidate = str(value).strip().lower()
    if not candidate:
        return None

    candidate = candidate.strip("<>()[]{}'\"")
    if "@" in candidate and not candidate.startswith(("http://", "https://")):
        candidate = candidate.rsplit("@", 1)[1]

    if not re.match(r"^[a-z][a-z0-9+.-]*://", candidate):
        candidate = f"//{candidate}"

    parsed = urlsplit(candidate)
    host = parsed.hostname or parsed.path.split("/", 1)[0]
    if not host:
        return None

    return host.rstrip(".")


def _strip_www(host: str) -> str:
    while host.startswith("www."):
        host = host[4:]
    return host


def _registrable_domain(host: str) -> Optional[str]:
    if get_sld is None:
        return _fallback_registrable_domain(host)
    domain = get_sld(host, strict=True)
    return domain.lower() if domain else None


def _fallback_registrable_domain(host: str) -> Optional[str]:
    """Small local fallback for test environments before requirements are installed."""
    parts = host.split(".")
    if len(parts) < 2:
        return None
    two_part_suffixes = {"co.uk", "com.au", "com.br", "co.nz", "co.jp"}
    suffix = ".".join(parts[-2:])
    if len(parts) >= 3 and suffix in two_part_suffixes:
        return ".".join(parts[-3:])
    return suffix


def _is_consumer_domain(registrable: str) -> bool:
    return registrable in CONSUMER_DOMAINS


def _is_portal_domain(host: str, registrable: str) -> bool:
    if registrable in PORTAL_DOMAINS:
        return True
    return "smartadvocate" in host
