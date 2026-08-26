"""Serializer helpers for the v2 firm intelligence contract."""

from __future__ import annotations

import re
import uuid
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from app.models.autorespond_event import AutorespondEvent
from app.models.email import Email
from app.models.firm_alias import FirmAlias
from app.models.pif_info import PifInfo
from app.schemas.firm_intel import (
    FirmAliases,
    FirmBehavior,
    FirmIcp,
    FirmIdentity,
    FirmPerson,
    FirmPersonFreshness,
    FirmProfile,
    FirmProvenance,
    FirmRelationship,
    FirmResearch,
    VendorEvidence,
    VendorStack,
)

PROFILE_VERSION = 1

INTERNAL_SCORER_KEYS = {"positive_outcomes"}
INTERNAL_SCORER_KEY_PREFIXES = ("outcome_supervision",)

PHI_DENY_KEY_FRAGMENTS = (
    "patient",
    "dob",
    "date_of_birth",
    "birthdate",
    "ssn",
    "medical",
    "diagnosis",
    "study",
    "accession",
    "message_body",
    "email_body",
    "body",
    "content_text",
    "content_html",
    "raw_data",
    "conversation_text",
    "ocr",
)

DECISION_MAKER_TITLE_RE = re.compile(
    r"\b(owner|founder|partner|managing partner|principal|president|ceo|coo|"
    r"chief operating|administrator|director)\b",
    re.IGNORECASE,
)


def build_firm_profile(
    pif: PifInfo,
    *,
    aliases: Optional[List[FirmAlias]] = None,
    emails: Optional[List[Email]] = None,
    autorespond_count: int = 0,
) -> FirmProfile:
    """Build the published non-PHI firm profile from stored aggregate data."""
    aliases = aliases or []
    emails = emails or []
    behavioral_data = _safe_dict(pif.behavioral_data)
    research_data = _safe_dict(pif.research_data)
    inbox_breakdown = _build_inbox_breakdown(behavioral_data, emails)
    last_seen_at = _max_datetime(
        _parse_datetime(behavioral_data.get("last_contact_date")),
        _max_datetime(*(email.created_at for email in emails)),
        pif.updated_at,
    )
    last_referral_at = _parse_datetime(
        behavioral_data.get("last_referral_at")
        or _last_seen_for_inbox(inbox_breakdown, "inb_qfq9")
    )
    last_records_at = _parse_datetime(
        behavioral_data.get("last_records_at")
        or _last_seen_for_inbox(inbox_breakdown, "inb_rcld")
    )

    return FirmProfile(
        firm_id=pif.id,
        canonical_website=pif.canonical_website,
        website_status=pif.website_status or ("resolved" if pif.canonical_website else None),
        firm_name=pif.firm_name,
        source_record=serialize_pif_source_record(pif),
        aliases=_serialize_aliases(pif, aliases),
        identity=_serialize_identity(pif, research_data),
        people=_serialize_people(pif, behavioral_data),
        relationship=FirmRelationship(
            warm_score_neutral=_safe_number(
                _first_present(
                    behavioral_data.get("warm_score_neutral"),
                    behavioral_data.get("warm_score"),
                )
            ),
            trajectory=_safe_string(behavioral_data.get("trajectory")),
            last_referral_at=last_referral_at,
            last_records_at=last_records_at,
            last_seen_at=last_seen_at,
            monthly_email_volume=_safe_int_list(behavioral_data.get("monthly_email_volume")),
            total_email_count=_safe_int(
                behavioral_data.get("total_email_count"), fallback=len(emails)
            ),
            inbox_breakdown=inbox_breakdown,
            autorespond_seen=autorespond_count > 0,
        ),
        behavior=FirmBehavior(
            primary_pain_point=_safe_string(behavioral_data.get("primary_pain_point")),
            topic_distribution=_safe_int_dict(behavioral_data.get("topic_distribution")),
            sender_roles=_safe_int_dict(
                behavioral_data.get("sender_roles") or behavioral_data.get("top_sender_roles")
            ),
            after_hours_ratio=float(behavioral_data.get("after_hours_ratio") or 0.0),
            peak_contact_days=_safe_string_list(behavioral_data.get("peak_contact_days")),
        ),
        vendor_stack=_serialize_vendor_stack(pif.vendor_stack, behavioral_data, research_data, aliases),
        icp=FirmIcp(
            score=pif.icp_score,
            tier=pif.icp_tier,
            score_breakdown=_public_score_breakdown(pif.score_breakdown),
        ),
        research=FirmResearch(
            summary=_safe_string(research_data.get("summary") or research_data.get("description")),
            practice_areas=_safe_string_list(research_data.get("practice_areas")),
            sources=_safe_sources(research_data.get("sources")),
            founded_year=_safe_int(research_data.get("founded_year"), fallback=None),
            firm_size=_safe_string(research_data.get("firm_size")),
            office_locations=_safe_public_list(research_data.get("office_locations")),
            notable_cases=_safe_public_list(research_data.get("notable_cases")),
            awards_recognition=_safe_public_list(research_data.get("awards_recognition")),
            bar_associations=_safe_public_list(research_data.get("bar_associations")),
            social_media=_safe_dict(research_data.get("social_media")),
            research_status=_map_research_status(pif.research_status),
            last_researched_at=pif.last_researched_at,
            job_postings=_safe_dict(pif.job_postings),
            job_postings_research_status=pif.job_postings_research_status,
            last_job_postings_researched_at=pif.last_job_postings_researched_at,
        ),
        provenance=FirmProvenance(
            profile_version=PROFILE_VERSION,
            refined_at=pif.updated_at,
            raw_observed_through=last_seen_at,
            freshness_age_hours=_freshness_hours(last_seen_at),
            source="emailtag",
        ),
    )


def serialize_pif_source_record(pif: PifInfo) -> Dict[str, Any]:
    """Serialize every pif_info DB column for downstream mirrors.

    This intentionally follows the SQLAlchemy mapper instead of a curated field list so future
    pif_info columns are mirrored without needing to update the v2 FirmIntel contract code.
    Internal outcome-derived scorer inputs are excluded from nested JSON fields because they are
    supervision state, not published firm facts.
    """
    return {
        column.key: _json_safe_source_value(getattr(pif, column.key))
        for column in PifInfo.__mapper__.columns
    }


def _json_safe_source_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _json_safe_source_value(item)
            for key, item in value.items()
            if not _is_internal_scorer_key(str(key))
        }
    if isinstance(value, list):
        return [_json_safe_source_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_source_value(item) for item in value]
    return _json_safe(value)


def _is_internal_scorer_key(key: str) -> bool:
    return key in INTERNAL_SCORER_KEYS or key.startswith(INTERNAL_SCORER_KEY_PREFIXES)


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _serialize_aliases(pif: PifInfo, aliases: List[FirmAlias]) -> FirmAliases:
    legacy_ids: List[str] = []
    domains: List[str] = []
    vanity_domains: List[str] = []

    if pif.canonical_website:
        domains.append(pif.canonical_website.lower())

    for alias in aliases:
        value = alias.alias_value.lower()
        if alias.alias_type == "legacy_pif_id":
            legacy_ids.append(value)
        elif alias.alias_type == "vanity_domain":
            vanity_domains.append(value)
        elif alias.alias_type in {"domain", "alt_domain", "email_domain"}:
            domains.append(value)

    return FirmAliases(
        legacy_pif_ids=_dedupe(legacy_ids),
        domains=_dedupe(domains),
        vanity_domains=_dedupe(vanity_domains),
    )


def _serialize_identity(pif: PifInfo, research_data: Dict[str, Any]) -> FirmIdentity:
    location = _safe_dict(research_data.get("location"))
    office_location = _first_office_location(research_data.get("office_locations"))
    return FirmIdentity(
        metro=_safe_string(
            research_data.get("metro") or location.get("metro") or office_location.get("metro")
        ),
        city=_safe_string(
            research_data.get("city") or location.get("city") or office_location.get("city")
        ),
        state=_safe_string(
            research_data.get("state") or location.get("state") or office_location.get("state")
        ),
        size_hint=_safe_string(research_data.get("size_hint") or research_data.get("firm_size")),
        icp_tier=pif.icp_tier,
        case_mix=_safe_dict(research_data.get("case_mix")),
        value_tier=_safe_string(research_data.get("value_tier")),
        volume_proxy=_safe_int(research_data.get("volume_proxy"), fallback=None),
    )


def _serialize_people(pif: PifInfo, behavioral_data: Dict[str, Any]) -> List[FirmPerson]:
    people_by_key: "OrderedDict[str, FirmPerson]" = OrderedDict()

    for item in pif.contacts or []:
        _upsert_person(
            people_by_key,
            pif,
            item,
            source="contact",
            freshness_source="extraction",
            confidence=0.7,
        )

    for item in pif.leadership or []:
        _upsert_person(
            people_by_key,
            pif,
            item,
            source="leadership",
            freshness_source="research",
            confidence=0.85,
            default_decision_maker=True,
        )

    for item in pif.staff or []:
        _upsert_person(
            people_by_key,
            pif,
            item,
            source="staff",
            freshness_source="research_staff",
            confidence=0.75,
        )

    contact_profiles = _safe_dict(behavioral_data.get("contact_profiles"))
    for email, profile in contact_profiles.items():
        if not isinstance(profile, dict):
            continue
        signature = _safe_dict(profile.get("signature"))
        _upsert_person(
            people_by_key,
            pif,
            {
                "name": profile.get("name"),
                "title": signature.get("title"),
                "email": email,
                "phone": signature.get("phone"),
                "persona": profile.get("persona") or profile.get("role"),
                "last_seen_at": profile.get("last_seen"),
            },
            source="behavioral_profile",
            freshness_source="sender",
            confidence=0.65,
        )

    return list(people_by_key.values())


def _upsert_person(
    people_by_key: "OrderedDict[str, FirmPerson]",
    pif: PifInfo,
    item: Dict[str, Any],
    *,
    source: str,
    freshness_source: str,
    confidence: float,
    default_decision_maker: bool = False,
) -> None:
    email = _safe_string(item.get("email"))
    name = _safe_string(item.get("name"))
    title = _safe_string(item.get("title"))
    phone = _safe_string(item.get("phone"))
    linkedin = _safe_string(item.get("linkedin"))
    bio = _safe_string(item.get("bio"))
    persona = _safe_string(item.get("persona") or item.get("role_category") or item.get("role"))
    if not any([email, name, title, phone, linkedin, bio]):
        return

    key = (email or f"{name}|{title}|{source}").lower()
    existing = people_by_key.get(key)
    is_decision_maker = bool(item.get("is_decision_maker")) or default_decision_maker
    if title and DECISION_MAKER_TITLE_RE.search(title):
        is_decision_maker = True

    last_seen_at = _parse_datetime(item.get("last_seen_at") or item.get("last_seen"))
    person = FirmPerson(
        person_id=_stable_person_id(pif.id, key),
        name=name,
        title=title,
        email=email,
        phone=phone,
        linkedin=linkedin,
        bio=bio,
        publications=_safe_public_list(item.get("publications")),
        cases_handled=_safe_public_list(item.get("cases_handled")),
        bar_admissions=_safe_public_list(item.get("bar_admissions")),
        persona=persona,
        is_decision_maker=is_decision_maker,
        freshness=FirmPersonFreshness(last_seen_at=last_seen_at, source=freshness_source),
        confidence=confidence,
    )

    if existing is None:
        people_by_key[key] = person
        return

    people_by_key[key] = FirmPerson(
        person_id=existing.person_id,
        name=existing.name or person.name,
        title=existing.title or person.title,
        email=existing.email or person.email,
        phone=existing.phone or person.phone,
        linkedin=existing.linkedin or person.linkedin,
        bio=existing.bio or person.bio,
        publications=existing.publications or person.publications,
        cases_handled=existing.cases_handled or person.cases_handled,
        bar_admissions=existing.bar_admissions or person.bar_admissions,
        persona=existing.persona or person.persona,
        is_decision_maker=existing.is_decision_maker or person.is_decision_maker,
        freshness=person.freshness
        if person.freshness.last_seen_at
        else existing.freshness,
        confidence=max(existing.confidence, person.confidence),
    )


def _serialize_vendor_stack(
    stored_vendor_stack: Any,
    behavioral_data: Dict[str, Any],
    research_data: Dict[str, Any],
    aliases: List[FirmAlias],
) -> VendorStack:
    tech_signals = _safe_dict(behavioral_data.get("tech_signals") or research_data.get("tech_signals"))
    vendor_stack = _coerce_vendor_stack(
        stored_vendor_stack
        or behavioral_data.get("vendor_stack")
        or research_data.get("vendor_stack")
    )
    case_mgmt = _safe_string(vendor_stack.get("case_mgmt") or tech_signals.get("case_mgmt"))
    other = _safe_dict(vendor_stack.get("other"))
    evidence = _safe_vendor_evidence(vendor_stack.get("evidence") or tech_signals.get("evidence"))

    for alias in aliases:
        if alias.alias_type == "vanity_domain":
            vendor = _vendor_from_domain(alias.alias_value)
            if vendor and not case_mgmt:
                case_mgmt = vendor
            evidence.append(
                VendorEvidence(signal=f"domain:{alias.alias_value}", confidence=alias.confidence)
            )

    return VendorStack(case_mgmt=case_mgmt, other=other, evidence=evidence)


def _coerce_vendor_stack(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return _safe_dict(value)
    if not isinstance(value, list):
        return {}

    case_mgmt: Optional[str] = None
    evidence: List[Dict[str, Any]] = []
    other: Dict[str, Any] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        vendor = _safe_string(item.get("vendor") or item.get("case_mgmt"))
        if vendor and not case_mgmt:
            case_mgmt = vendor
        signal = _safe_string(item.get("evidence") or item.get("source"))
        confidence = _confidence_to_float(item.get("confidence"))
        if signal:
            evidence.append({"signal": signal, "confidence": confidence})
        if vendor and item.get("known") is False:
            other[vendor] = item
    return {"case_mgmt": case_mgmt, "other": other, "evidence": evidence}


def _build_inbox_breakdown(
    behavioral_data: Dict[str, Any],
    emails: List[Email],
) -> Dict[str, Dict[str, Any]]:
    existing = _safe_dict(behavioral_data.get("inbox_breakdown"))
    breakdown: Dict[str, Dict[str, Any]] = {
        str(k): _sanitize_public_dict(v) for k, v in existing.items() if isinstance(v, dict)
    }

    for email in emails:
        inbox_id = _extract_inbox_id(email.raw_data)
        if not inbox_id:
            continue
        bucket = breakdown.setdefault(
            inbox_id,
            {"total_email_count": 0, "last_seen_at": None, "monthly_email_volume": []},
        )
        bucket["total_email_count"] = int(bucket.get("total_email_count") or 0) + 1
        current_last_seen = _parse_datetime(bucket.get("last_seen_at"))
        if email.created_at and (current_last_seen is None or email.created_at > current_last_seen):
            bucket["last_seen_at"] = email.created_at.isoformat()

    return breakdown


def _extract_inbox_id(raw_data: Any) -> Optional[str]:
    if not isinstance(raw_data, dict):
        return None
    candidates = [
        raw_data.get("inbox_id"),
        _nested_get(raw_data, ["inbox", "id"]),
        _nested_get(raw_data, ["target", "data", "inbox", "id"]),
        _nested_get(raw_data, ["target", "data", "inbox_id"]),
        _nested_get(raw_data, ["conversation", "inbox", "id"]),
    ]
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return None


def _sanitize_public_dict(value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    cleaned: Dict[str, Any] = {}
    for key, child in value.items():
        key_str = str(key)
        if _is_phi_key(key_str):
            continue
        if isinstance(child, dict):
            cleaned[key_str] = _sanitize_public_dict(child)
        elif isinstance(child, list):
            cleaned[key_str] = [
                _sanitize_public_dict(item) if isinstance(item, dict) else item
                for item in child
                if not isinstance(item, (bytes, bytearray))
            ]
        elif not isinstance(child, (bytes, bytearray)):
            cleaned[key_str] = child
    return cleaned


def _public_score_breakdown(value: Any) -> Dict[str, Any]:
    breakdown = _safe_dict(value)
    return {
        key: child
        for key, child in breakdown.items()
        if not str(key).startswith("outcome_supervision")
    }


def _safe_vendor_evidence(value: Any) -> List[VendorEvidence]:
    evidence: List[VendorEvidence] = []
    if not isinstance(value, list):
        return evidence
    for item in value:
        if not isinstance(item, dict):
            continue
        signal = _safe_string(item.get("signal"))
        if not signal:
            continue
        evidence.append(
            VendorEvidence(signal=signal, confidence=_confidence_to_float(item.get("confidence")))
        )
    return evidence


def _first_office_location(value: Any) -> Dict[str, Any]:
    if not isinstance(value, list) or not value:
        return {}
    first = value[0]
    if isinstance(first, dict):
        return _safe_dict(first)
    if isinstance(first, str):
        return {"city": first}
    return {}


def _safe_public_list(value: Any) -> List[Any]:
    if not isinstance(value, list):
        return []
    result: List[Any] = []
    for item in value:
        if isinstance(item, dict):
            result.append(_sanitize_public_dict(item))
        elif isinstance(item, list):
            result.append(_safe_public_list(item))
        elif not isinstance(item, (bytes, bytearray)):
            result.append(item)
    return result


def _confidence_to_float(value: Any) -> float:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "high":
            return 0.9
        if normalized == "medium":
            return 0.6
        if normalized == "low":
            return 0.3
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _safe_sources(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    sources: List[str] = []
    for item in value:
        if isinstance(item, str):
            sources.append(item)
        elif isinstance(item, dict):
            source = item.get("url") or item.get("source") or item.get("title")
            if source:
                sources.append(str(source))
    return _dedupe(sources)


def _map_research_status(status_value: Optional[str]) -> Optional[str]:
    if status_value == "completed":
        return "done"
    if status_value in {"pending", "in_progress", "queued"}:
        return "pending"
    if status_value:
        return status_value
    return None


def _vendor_from_domain(domain: str) -> Optional[str]:
    lowered = domain.lower()
    if "filevine" in lowered:
        return "filevine"
    if "casepeer" in lowered:
        return "casepeer"
    if "litify" in lowered:
        return "litify"
    if "smartadvocate" in lowered:
        return "smartadvocate"
    return None


def _last_seen_for_inbox(inbox_breakdown: Dict[str, Dict[str, Any]], inbox_id: str) -> Optional[str]:
    bucket = inbox_breakdown.get(inbox_id) or {}
    value = bucket.get("last_seen_at") or bucket.get("last_contact_at")
    return str(value) if value else None


def _safe_dict(value: Any) -> Dict[str, Any]:
    return _sanitize_public_dict(value) if isinstance(value, dict) else {}


def _safe_int_dict(value: Any) -> Dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: Dict[str, int] = {}
    for key, child in value.items():
        if _is_phi_key(str(key)):
            continue
        try:
            result[str(key)] = int(child)
        except (TypeError, ValueError):
            continue
    return result


def _safe_int_list(value: Any) -> List[int]:
    if not isinstance(value, list):
        return []
    result: List[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _safe_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and not isinstance(item, dict)]


def _safe_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _safe_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _safe_int(value: Any, *, fallback: Optional[int] = 0) -> Optional[int]:
    if value is None:
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if not value:
        return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            return None
    return None


def _max_datetime(*values: Optional[datetime]) -> Optional[datetime]:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _freshness_hours(value: Optional[datetime]) -> Optional[float]:
    if not value:
        return None
    return round((datetime.utcnow() - value).total_seconds() / 3600, 2)


def _stable_person_id(firm_id: uuid.UUID, key: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"emailtag:firm-person:{firm_id}:{key}")


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = OrderedDict()
    for value in values:
        if value:
            seen[str(value).lower()] = str(value).lower()
    return list(seen.values())


def _nested_get(value: Dict[str, Any], path: List[str]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _is_phi_key(key: str) -> bool:
    lowered = key.lower()
    return any(fragment in lowered for fragment in PHI_DENY_KEY_FRAGMENTS)
