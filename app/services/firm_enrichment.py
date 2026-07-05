"""Two-pass firm enrichment and outreach-readiness gate."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr
from typing import Any, Callable, Dict, Iterable, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.email import Email
from app.models.pif_info import PifInfo
from app.services.firm_identity import canonical_domain


EmailCorpus = List[Dict[str, Any]]
AnalyzeEmails = Callable[[EmailCorpus], Dict[str, Any]]
ExtractSignature = Callable[[str, List[str]], Dict[str, str]]
ScoreFirm = Callable[[Dict[str, Any]], Dict[str, Any]]
ResearchFirmProfile = Callable[..., Any]

DECISION_MAKER_PERSONAS = {"founder_owner", "managing_partner", "coo_ops"}
DECISION_MAKER_TITLE_KEYWORDS = (
    "owner",
    "founder",
    "partner",
    "principal",
    "president",
    "ceo",
    "coo",
    "chief operating",
    "administrator",
    "director",
)

CORE_COMPLETENESS_FIELDS = (
    "canonical_website",
    "decision_maker_with_email_persona",
    "primary_pain_point",
    "icp_tier",
    "behavioral_data",
    "relationship_recency",
    "monthly_email_volume",
    "topic_distribution",
    "sender_roles",
    "contact_profiles",
    "firmographics",
    "vendor_stack",
)

MUST_HAVE_FIELDS = (
    "canonical_website",
    "decision_maker_with_email_persona",
    "primary_pain_point",
    "icp_tier",
    "behavioral_data",
    "relationship_recency",
)


@dataclass
class CompletenessResult:
    populated_fields: List[str]
    missing_must_have: List[str]
    profile_completeness: int
    outreach_ready: bool


@dataclass
class FirmEnrichmentResult:
    pif_id: str
    firm_name: str
    status: str
    planned: bool = False
    wrote: bool = False
    skipped_reason: Optional[str] = None
    fields_updated: List[str] = field(default_factory=list)
    profile_completeness: Optional[int] = None
    outreach_ready: Optional[bool] = None


def load_firm_email_corpus(db: Session, pif: PifInfo) -> EmailCorpus:
    """Load and normalize the firm's email corpus once for all internal analyzers."""
    conv_ids = pif.conversation_ids or []
    if not conv_ids:
        return []

    rows = (
        db.execute(
            select(Email)
            .where(Email.front_conversation_id.in_(conv_ids))
            .order_by(Email.created_at.asc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "subject": email.subject or "",
            "content_text": email.content_text or "",
            "sender": email.sender or "",
            "created_at": email.created_at,
            "raw_data": email.raw_data or {},
        }
        for email in rows
    ]


def run_internal_pass(
    pif: PifInfo,
    email_corpus: EmailCorpus,
    *,
    analyze_emails: Optional[AnalyzeEmails] = None,
    extract_signature: Optional[ExtractSignature] = None,
    score_firm: Optional[ScoreFirm] = None,
) -> Dict[str, Any]:
    """Pass A: compute internal behavior, signature people, and ICP from one corpus."""
    if analyze_emails is None:
        from pifstats.src.email_analyzer import analyze_firm_emails as analyze_emails
    if extract_signature is None:
        from pifstats.src.signature_extractor import extract_signature_for_sender as extract_signature
    if score_firm is None:
        from pifstats.src.icp_scorer import score_firm as score_firm

    behavioral_data = analyze_emails(email_corpus)
    behavioral_data = dict(behavioral_data or {})
    _apply_signature_profiles(behavioral_data, email_corpus, extract_signature)

    leadership = merge_people(
        pif.leadership or [],
        _leadership_from_behavioral_profiles(behavioral_data),
    )
    pif_payload = {
        "behavioral_data": behavioral_data,
        "research_data": pif.research_data or {},
        "website": pif.canonical_website or pif.website,
        "leadership": leadership,
        "phones": pif.phones or [],
        "conversation_ids": pif.conversation_ids or [],
    }
    score_result = score_firm(pif_payload)

    return {
        "behavioral_data": behavioral_data,
        "leadership": leadership,
        "icp_score": score_result.get("icp_score"),
        "icp_tier": score_result.get("icp_tier"),
        "score_breakdown": score_result.get("score_breakdown"),
        "icp_scored_at": datetime.utcnow(),
    }


def run_external_pass(
    pif: PifInfo,
    *,
    research_firm_profile: Optional[ResearchFirmProfile] = None,
) -> Dict[str, Any]:
    """Pass B: one public web-search call for website, firmographics, people, vendors."""
    if research_firm_profile is None:
        from pifstats.src.firm_researcher import research_firm_profile_once as research_firm_profile

    location = pif.addresses[0] if pif.addresses else None
    result = research_firm_profile(
        firm_name=pif.firm_name,
        website=pif.canonical_website or pif.website,
        location=location,
    )
    if result is None:
        return {"research_status": "failed", "last_researched_at": datetime.utcnow()}

    firmographics = dict(getattr(result, "firmographics", None) or {})
    vendor_stack = dict(getattr(result, "vendor_stack", None) or {})
    competitive_context = dict(getattr(result, "competitive_context", None) or {})
    sources = list(getattr(result, "sources", None) or [])
    research_data = {
        "size_hint": firmographics.get("size_hint"),
        "firm_size": firmographics.get("size_hint"),
        "practice_areas": firmographics.get("practice_areas") or [],
        "case_mix": firmographics.get("case_mix") or {},
        "metro": firmographics.get("metro"),
        "city": firmographics.get("city"),
        "state": firmographics.get("state"),
        "office_locations": firmographics.get("office_locations") or [],
        "value_tier": firmographics.get("value_tier"),
        "competitive_context": competitive_context,
        "sources": sources,
        "last_external_enriched_at": datetime.utcnow().isoformat(),
    }
    leadership = [
        _person_to_dict(member, default_source="external_research")
        for member in list(getattr(result, "leadership", None) or [])
    ]

    updates: Dict[str, Any] = {
        "research_data": research_data,
        "leadership": merge_people(pif.leadership or [], leadership),
        "vendor_stack": vendor_stack or None,
        "research_status": "completed",
        "last_researched_at": datetime.utcnow(),
    }
    raw_website = getattr(result, "canonical_website", None)
    resolved_domain = canonical_domain(raw_website) if raw_website else None
    if resolved_domain:
        updates.update(
            {
                "canonical_website": resolved_domain,
                "website_status": "resolved",
                "website_source": "web_search",
                "website_confidence": float(getattr(result, "website_confidence", 0.0) or 0.0),
            }
        )
    return updates


def enrich_firm_profile(
    db: Session,
    pif: PifInfo,
    *,
    apply: bool,
    force: bool = False,
    corpus_loader: Callable[[Session, PifInfo], EmailCorpus] = load_firm_email_corpus,
    analyze_emails: Optional[AnalyzeEmails] = None,
    extract_signature: Optional[ExtractSignature] = None,
    score_firm: Optional[ScoreFirm] = None,
    research_firm_profile: Optional[ResearchFirmProfile] = None,
) -> FirmEnrichmentResult:
    if is_enriched(pif) and not force:
        return FirmEnrichmentResult(
            pif_id=str(pif.id),
            firm_name=pif.firm_name,
            status="skipped",
            skipped_reason="already_enriched",
            profile_completeness=pif.profile_completeness,
            outreach_ready=bool(pif.outreach_ready),
        )

    if not apply:
        return FirmEnrichmentResult(
            pif_id=str(pif.id),
            firm_name=pif.firm_name,
            status="planned",
            planned=True,
        )

    email_corpus = corpus_loader(db, pif)
    updates: Dict[str, Any] = {}
    updates.update(
        run_internal_pass(
            pif,
            email_corpus,
            analyze_emails=analyze_emails,
            extract_signature=extract_signature,
            score_firm=score_firm,
        )
    )
    apply_soft_updates(pif, updates)

    external_updates = run_external_pass(pif, research_firm_profile=research_firm_profile)
    apply_soft_updates(pif, external_updates)

    completeness = compute_profile_completeness(pif)
    gate_updates = {
        "profile_completeness": completeness.profile_completeness,
        "outreach_ready": completeness.outreach_ready,
    }
    apply_soft_updates(pif, gate_updates)
    db.add(pif)
    db.commit()
    db.refresh(pif)

    updated_fields = sorted(set(updates) | set(external_updates) | set(gate_updates))
    return FirmEnrichmentResult(
        pif_id=str(pif.id),
        firm_name=pif.firm_name,
        status="completed",
        wrote=True,
        fields_updated=updated_fields,
        profile_completeness=pif.profile_completeness,
        outreach_ready=bool(pif.outreach_ready),
    )


def apply_soft_updates(pif: PifInfo, updates: Dict[str, Any]) -> List[str]:
    """Apply updates without overwriting operator-facing populated fields."""
    changed: List[str] = []
    for field_name, value in updates.items():
        if value is None:
            continue
        existing = getattr(pif, field_name, None)
        if field_name == "behavioral_data":
            next_value = _deep_merge(existing or {}, value, prefer_new=True)
        elif field_name == "research_data":
            next_value = _deep_merge(existing or {}, value, prefer_new=False)
        elif field_name == "leadership":
            next_value = merge_people(existing or [], value or [])
        elif field_name == "vendor_stack":
            next_value = value if not _has_value(existing) else existing
        elif field_name in {
            "canonical_website",
            "website_status",
            "website_source",
            "website_confidence",
        }:
            next_value = value if not _has_value(existing) else existing
        elif field_name in {
            "icp_score",
            "icp_tier",
            "score_breakdown",
            "icp_scored_at",
            "profile_completeness",
            "outreach_ready",
            "research_status",
            "last_researched_at",
        }:
            next_value = value
        else:
            next_value = value if not _has_value(existing) else existing

        if next_value != existing:
            setattr(pif, field_name, next_value)
            changed.append(field_name)
    return changed


def compute_profile_completeness(pif: PifInfo) -> CompletenessResult:
    populated = []
    behavioral = pif.behavioral_data or {}
    research = pif.research_data or {}

    checks = {
        "canonical_website": _has_value(pif.canonical_website),
        "decision_maker_with_email_persona": has_decision_maker_with_email_persona(pif),
        "primary_pain_point": _has_value(behavioral.get("primary_pain_point")),
        "icp_tier": _has_value(pif.icp_tier),
        "behavioral_data": _has_value(behavioral),
        "relationship_recency": any(
            _has_value(behavioral.get(key))
            for key in (
                "days_since_last_contact",
                "last_contact_date",
                "last_referral_at",
                "last_records_at",
            )
        ),
        "monthly_email_volume": _has_value(behavioral.get("monthly_email_volume")),
        "topic_distribution": _has_value(behavioral.get("topic_distribution")),
        "sender_roles": _has_value(behavioral.get("sender_roles") or behavioral.get("top_sender_roles")),
        "contact_profiles": _has_value(behavioral.get("contact_profiles")),
        "firmographics": any(
            _has_value(research.get(key))
            for key in ("size_hint", "firm_size", "city", "state", "metro", "case_mix", "practice_areas")
        ),
        "vendor_stack": _has_value(pif.vendor_stack)
        or _has_value(behavioral.get("vendor_stack"))
        or _has_value(research.get("vendor_stack")),
    }
    for field_name in CORE_COMPLETENESS_FIELDS:
        if checks.get(field_name):
            populated.append(field_name)

    missing = [field_name for field_name in MUST_HAVE_FIELDS if not checks.get(field_name)]
    completeness = len(populated)
    return CompletenessResult(
        populated_fields=populated,
        missing_must_have=missing,
        profile_completeness=completeness,
        outreach_ready=not missing and completeness >= 8,
    )


def has_decision_maker_with_email_persona(pif: PifInfo) -> bool:
    people: List[Dict[str, Any]] = []
    people.extend([item for item in pif.leadership or [] if isinstance(item, dict)])
    people.extend([item for item in pif.contacts or [] if isinstance(item, dict)])
    people.extend([item for item in pif.staff or [] if isinstance(item, dict)])

    contact_profiles = (pif.behavioral_data or {}).get("contact_profiles") or {}
    if isinstance(contact_profiles, dict):
        for email, profile in contact_profiles.items():
            if isinstance(profile, dict):
                people.append({**profile, "email": email})

    for person in people:
        email = person.get("email")
        persona = person.get("persona") or person.get("role") or person.get("role_category")
        title = person.get("title") or ""
        if not _has_value(email) or not _has_value(persona):
            continue
        if person.get("is_decision_maker") or persona in DECISION_MAKER_PERSONAS:
            return True
        if any(keyword in str(title).lower() for keyword in DECISION_MAKER_TITLE_KEYWORDS):
            return True
    return False


def select_enrichment_candidates(
    db: Session,
    *,
    limit: int,
    force: bool = False,
) -> List[PifInfo]:
    stmt = (
        select(PifInfo)
        .where(or_(PifInfo.merge_status == "active", PifInfo.merge_status.is_(None)))
        .order_by(PifInfo.updated_at.asc())
    )
    if not force:
        stmt = stmt.where(
            or_(
                PifInfo.profile_completeness.is_(None),
                PifInfo.outreach_ready.is_(False),
                PifInfo.behavioral_data.is_(None),
                PifInfo.icp_tier.is_(None),
            )
        )
    if limit:
        stmt = stmt.limit(limit)
    return db.execute(stmt).scalars().all()


def coverage_metrics(db: Session) -> Dict[str, Any]:
    active_filter = or_(PifInfo.merge_status == "active", PifInfo.merge_status.is_(None))
    total = db.scalar(select(func.count(PifInfo.id)).where(active_filter)) or 0

    def count_where(condition: Any) -> int:
        return int(db.scalar(select(func.count(PifInfo.id)).where(active_filter, condition)) or 0)

    return {
        "total_active": int(total),
        "canonical_website": count_where(PifInfo.canonical_website.is_not(None)),
        "behavioral_data": count_where(PifInfo.behavioral_data.is_not(None)),
        "icp_tier": count_where(PifInfo.icp_tier.is_not(None)),
        "leadership": count_where(PifInfo.leadership.is_not(None)),
        "vendor_stack": count_where(PifInfo.vendor_stack.is_not(None)),
        "profile_completeness": count_where(PifInfo.profile_completeness.is_not(None)),
        "outreach_ready": count_where(PifInfo.outreach_ready.is_(True)),
    }


def is_enriched(pif: PifInfo) -> bool:
    return bool(
        pif.profile_completeness is not None
        and pif.behavioral_data
        and pif.icp_tier
        and (pif.research_data or pif.vendor_stack)
    )


def rate_limit_sleep(last_call_at: Optional[float], calls_per_minute: int) -> float:
    if not last_call_at or calls_per_minute <= 0:
        return time.monotonic()
    interval = 60.0 / calls_per_minute
    elapsed = time.monotonic() - last_call_at
    if elapsed < interval:
        time.sleep(interval - elapsed)
    return time.monotonic()


def _apply_signature_profiles(
    behavioral_data: Dict[str, Any],
    email_corpus: EmailCorpus,
    extract_signature: ExtractSignature,
) -> None:
    profiles = behavioral_data.setdefault("contact_profiles", {})
    bodies_by_sender: Dict[str, List[str]] = {}
    raw_sender_by_email: Dict[str, str] = {}
    for email in email_corpus:
        sender = email.get("sender") or ""
        name, sender_email = _sender_identity(sender)
        if not sender_email or "@" not in sender_email:
            continue
        raw_sender_by_email[sender_email] = sender
        profile = profiles.setdefault(
            sender_email,
            {
                "name": name,
                "role": "unknown",
                "persona": "unknown",
                "message_count": 0,
                "topic_mix": {},
            },
        )
        if name and not profile.get("name"):
            profile["name"] = name
        bodies_by_sender.setdefault(sender_email, []).append(email.get("content_text") or "")

    for sender_email, bodies in bodies_by_sender.items():
        signature = extract_signature(raw_sender_by_email.get(sender_email, sender_email), bodies)
        signature = signature or {}
        profile = profiles.setdefault(sender_email, {})
        if signature.get("name") and not profile.get("name"):
            profile["name"] = signature["name"]
        persona = signature.get("persona")
        if persona and persona != "unknown":
            profile["persona"] = persona
            profile["role"] = persona
        if signature.get("title") or signature.get("direct_phone"):
            profile["signature"] = {
                "title": signature.get("title") or "",
                "phone": signature.get("direct_phone") or "",
                "extracted_at": datetime.utcnow().isoformat(),
            }


def _leadership_from_behavioral_profiles(behavioral_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    profiles = behavioral_data.get("contact_profiles") or {}
    if not isinstance(profiles, dict):
        return []
    leaders: List[Dict[str, Any]] = []
    for email, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        persona = profile.get("persona") or profile.get("role")
        signature = profile.get("signature") or {}
        title = signature.get("title") if isinstance(signature, dict) else None
        is_decision_maker = (
            persona in DECISION_MAKER_PERSONAS
            or any(keyword in str(title or "").lower() for keyword in DECISION_MAKER_TITLE_KEYWORDS)
        )
        if not is_decision_maker:
            continue
        leaders.append(
            {
                "name": profile.get("name") or "",
                "title": title or "",
                "email": email,
                "phone": signature.get("phone") if isinstance(signature, dict) else None,
                "persona": persona,
                "is_decision_maker": True,
                "source": "internal_signature",
                "confidence": 0.75,
            }
        )
    return leaders


def merge_people(existing: Iterable[Dict[str, Any]], incoming: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for person in list(existing or []) + list(incoming or []):
        if not isinstance(person, dict):
            continue
        key = _person_key(person)
        if not key:
            continue
        if key not in by_key:
            by_key[key] = dict(person)
            order.append(key)
            continue
        merged = dict(by_key[key])
        for field_name, value in person.items():
            if not _has_value(merged.get(field_name)) and _has_value(value):
                merged[field_name] = value
            elif field_name == "is_decision_maker":
                merged[field_name] = bool(merged.get(field_name) or value)
        by_key[key] = merged
    return [by_key[key] for key in order]


def _person_to_dict(member: Any, *, default_source: str) -> Dict[str, Any]:
    if hasattr(member, "model_dump"):
        data = member.model_dump()
    elif isinstance(member, dict):
        data = dict(member)
    else:
        data = {}
    data.setdefault("source", default_source)
    if _looks_decision_maker(data):
        data["is_decision_maker"] = True
    return data


def _looks_decision_maker(person: Dict[str, Any]) -> bool:
    title = str(person.get("title") or "").lower()
    persona = person.get("persona") or person.get("role")
    return persona in DECISION_MAKER_PERSONAS or any(
        keyword in title for keyword in DECISION_MAKER_TITLE_KEYWORDS
    )


def _person_key(person: Dict[str, Any]) -> Optional[str]:
    email = person.get("email")
    if _has_value(email):
        return str(email).strip().lower()
    name = str(person.get("name") or "").strip().lower()
    title = str(person.get("title") or "").strip().lower()
    return f"{name}|{title}" if name or title else None


def _sender_identity(sender: str) -> tuple[str, str]:
    name, email = parseaddr(sender or "")
    email = email.strip().lower()
    name = (name or email.split("@")[0] if email else "").strip().strip('"')
    return name, email


def _deep_merge(existing: Dict[str, Any], incoming: Dict[str, Any], *, prefer_new: bool) -> Dict[str, Any]:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value, prefer_new=prefer_new)
        elif prefer_new or not _has_value(merged.get(key)):
            merged[key] = value
    return merged


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True
