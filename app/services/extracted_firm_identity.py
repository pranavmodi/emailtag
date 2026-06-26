"""Map extracted email firm data onto canonical firm identity records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Optional
from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.firm_alias import FirmAlias
from app.models.pif_info import PifInfo
from app.services.firm_identity import canonical_domain
from app.services.firm_merge import FirmMergePlan, apply_firm_merge_plan
from app.services.website_resolution import (
    WebsiteResolutionResult,
    apply_website_resolution,
    persist_aliases_for_firm,
    resolve_firm_website,
)


@dataclass(frozen=True)
class ExtractedFirmIdentityResult:
    """Outcome of mapping one extracted organization into the firm identity table."""

    pif: PifInfo
    is_new: bool
    action: str
    mapped_via: str
    website_result: Optional[WebsiteResolutionResult] = None
    merged_pif_id: Optional[UUID] = None


def resolve_extracted_firm_identity(
    db: Session,
    *,
    firm_name: str,
    website: Optional[str],
    emails: list[str],
    phones: list[str],
    fax: Optional[str],
    addresses: list[str],
    contacts: list[dict[str, Any]],
    conversation_id: str,
    extraction_notes: Optional[str] = None,
    entity_type: str = "pi_law_firm",
    http_get: Optional[Callable[[str], Any]] = None,
    search: Optional[Callable[[str, Optional[str]], Optional[str]]] = None,
) -> ExtractedFirmIdentityResult:
    """
    Resolve an extracted firm to an existing active row or create one, then resolve its website.

    Matching is intentionally domain-first. Firm names are useful as a final fallback, but the
    canonical website/alias spine is the stable identity boundary for FirmIntel.
    """
    domains = extracted_identity_domains(website=website, emails=emails, contacts=contacts)
    pif, mapped_via = _find_existing_firm(db, firm_name=firm_name, domains=domains)
    is_new = pif is None

    if pif is None:
        pif = PifInfo(
            firm_name=firm_name,
            entity_type=entity_type,
            website=website,
            emails=[],
            phones=[],
            fax=None,
            addresses=[],
            contacts=[],
            conversation_ids=[],
            extraction_notes=extraction_notes,
            merge_status="active",
        )
        db.add(pif)
        mapped_via = "created"

    merge_extracted_firm_data(
        pif,
        firm_name=firm_name,
        website=website,
        emails=emails,
        phones=phones,
        fax=fax,
        addresses=addresses,
        contacts=contacts,
        conversation_id=conversation_id,
        extraction_notes=extraction_notes,
        entity_type=entity_type,
    )
    db.add(pif)
    db.flush()

    if pif.canonical_website:
        _ensure_resolved_status(pif)
        persist_aliases_for_firm(db, pif)
        db.flush()
        return ExtractedFirmIdentityResult(
            pif=pif,
            is_new=is_new,
            action="created" if is_new else "updated",
            mapped_via=mapped_via,
        )

    website_result = resolve_firm_website(pif, http_get=http_get, search=search)
    if website_result.canonical_website:
        owner = _find_domain_owner(
            db,
            website_result.canonical_website,
            exclude_id=pif.id,
        )
        if owner is not None:
            merged_id = pif.id
            if not owner.canonical_website:
                apply_website_resolution(owner, website_result)
                db.add(owner)
                db.flush()
            _auto_merge_domain_clash(
                db,
                winner=owner,
                loser=pif,
                domain=website_result.canonical_website,
            )
            persist_aliases_for_firm(db, owner)
            db.flush()
            return ExtractedFirmIdentityResult(
                pif=owner,
                is_new=False,
                action="merged",
                mapped_via="resolved_domain_owner",
                website_result=website_result,
                merged_pif_id=merged_id,
            )

    apply_website_resolution(pif, website_result)
    persist_aliases_for_firm(db, pif)
    db.flush()

    return ExtractedFirmIdentityResult(
        pif=pif,
        is_new=is_new,
        action="created" if is_new else "updated",
        mapped_via=mapped_via,
        website_result=website_result,
    )


def extracted_identity_domains(
    *,
    website: Optional[str],
    emails: Iterable[str],
    contacts: Iterable[dict[str, Any]],
) -> list[str]:
    """Return ordered, non-consumer domains observed in extracted website/email data."""
    domains: list[str] = []

    for value in [website, *(emails or [])]:
        _append_domain(domains, value)

    for contact in contacts or []:
        if isinstance(contact, dict):
            _append_domain(domains, contact.get("email"))

    return domains


def merge_extracted_firm_data(
    pif: PifInfo,
    *,
    firm_name: str,
    website: Optional[str],
    emails: list[str],
    phones: list[str],
    fax: Optional[str],
    addresses: list[str],
    contacts: list[dict[str, Any]],
    conversation_id: str,
    extraction_notes: Optional[str] = None,
    entity_type: str = "pi_law_firm",
) -> None:
    """Merge extracted fields into an existing/new PIF row without committing."""
    if firm_name and not pif.firm_name:
        pif.firm_name = firm_name
    if entity_type and (not pif.entity_type or pif.entity_type == "pi_law_firm"):
        pif.entity_type = entity_type
    if website and not pif.website:
        pif.website = website
    if fax and not pif.fax:
        pif.fax = fax
    if extraction_notes and not pif.extraction_notes:
        pif.extraction_notes = extraction_notes

    pif.emails = _merge_ordered(pif.emails or [], emails or [])
    pif.phones = _merge_ordered(pif.phones or [], phones or [])
    pif.addresses = _merge_ordered(pif.addresses or [], addresses or [])
    pif.conversation_ids = _merge_ordered(pif.conversation_ids or [], [conversation_id])
    pif.contacts = merge_contacts(pif.contacts or [], contacts or [])
    pif.updated_at = datetime.utcnow()


def merge_contacts(
    existing_contacts: list[dict[str, Any]],
    new_contacts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge contacts, deduplicating by email when present, otherwise name."""
    contacts_by_key: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []

    for contact in [*(existing_contacts or []), *(new_contacts or [])]:
        if not isinstance(contact, dict):
            continue
        key = _contact_key(contact)
        if not key:
            continue
        if key not in contacts_by_key:
            contacts_by_key[key] = dict(contact)
            ordered_keys.append(key)
            continue

        existing = contacts_by_key[key]
        for field in ("name", "title", "persona", "email", "phone", "extension"):
            if contact.get(field) and not existing.get(field):
                existing[field] = contact[field]

    return [contacts_by_key[key] for key in ordered_keys]


def _find_existing_firm(
    db: Session,
    *,
    firm_name: str,
    domains: list[str],
) -> tuple[Optional[PifInfo], str]:
    for domain in domains:
        firm = _find_by_canonical_domain(db, domain)
        if firm is not None:
            return firm, "canonical_website"

        firm = _find_by_domain_alias(db, domain)
        if firm is not None:
            return firm, "firm_alias"

        firm = _find_by_legacy_website_domain(db, domain)
        if firm is not None:
            return firm, "legacy_website"

    if firm_name:
        firm = _find_by_firm_name(db, firm_name)
        if firm is not None:
            return firm, "firm_name"

    return None, "created"


def _find_by_canonical_domain(
    db: Session,
    domain: str,
    *,
    exclude_id: Optional[UUID] = None,
) -> Optional[PifInfo]:
    query = db.query(PifInfo).filter(
        _active_firm_filter(),
        PifInfo.canonical_website == domain,
    )
    if exclude_id:
        query = query.filter(PifInfo.id != exclude_id)
    return query.first()


def _find_by_domain_alias(db: Session, domain: str) -> Optional[PifInfo]:
    return _find_by_domain_alias_excluding(db, domain)


def _find_domain_owner(
    db: Session,
    domain: str,
    *,
    exclude_id: Optional[UUID] = None,
) -> Optional[PifInfo]:
    return (
        _find_by_canonical_domain(db, domain, exclude_id=exclude_id)
        or _find_by_domain_alias_excluding(db, domain, exclude_id=exclude_id)
        or _find_by_legacy_website_domain(db, domain, exclude_id=exclude_id)
    )


def _find_by_domain_alias_excluding(
    db: Session,
    domain: str,
    *,
    exclude_id: Optional[UUID] = None,
) -> Optional[PifInfo]:
    alias = (
        db.query(FirmAlias)
        .filter(
            FirmAlias.alias_type.in_(("domain", "alt_domain", "email_domain", "vanity_domain")),
            FirmAlias.alias_value == domain,
        )
        .first()
    )
    if alias is None:
        return None
    firm = db.get(PifInfo, alias.firm_id)
    if firm is None or _is_merged(firm) or (exclude_id and firm.id == exclude_id):
        return None
    return firm


def _find_by_legacy_website_domain(
    db: Session,
    domain: str,
    *,
    exclude_id: Optional[UUID] = None,
) -> Optional[PifInfo]:
    firms = (
        db.query(PifInfo)
        .filter(_active_firm_filter(), PifInfo.website.isnot(None))
        .all()
    )
    for firm in firms:
        if exclude_id and firm.id == exclude_id:
            continue
        if canonical_domain(firm.website) == domain:
            return firm
    return None


def _find_by_firm_name(db: Session, firm_name: str) -> Optional[PifInfo]:
    return (
        db.query(PifInfo)
        .filter(
            _active_firm_filter(),
            func.lower(PifInfo.firm_name) == firm_name.lower(),
        )
        .first()
    )


def _active_firm_filter():
    return or_(PifInfo.merge_status.is_(None), PifInfo.merge_status != "merged")


def _is_merged(firm: PifInfo) -> bool:
    return firm.merge_status == "merged" or firm.merged_into is not None


def _auto_merge_domain_clash(db: Session, *, winner: PifInfo, loser: PifInfo, domain: str) -> None:
    plan = FirmMergePlan(
        canonical_domain=domain,
        action="auto_merge",
        confidence=0.95,
        survivor_id=str(winner.id),
        survivor_name=winner.firm_name,
        loser_ids=[str(loser.id)],
        member_ids=[str(winner.id), str(loser.id)],
        member_names=[winner.firm_name, loser.firm_name],
    )
    apply_firm_merge_plan(db, plan)


def _ensure_resolved_status(pif: PifInfo) -> None:
    pif.website_status = pif.website_status or "resolved"
    pif.website_source = pif.website_source or "email_verified"
    pif.website_confidence = pif.website_confidence or 0.9
    pif.website_candidate = None


def _append_domain(domains: list[str], value: Optional[str]) -> None:
    domain = canonical_domain(value)
    if domain and domain not in domains:
        domains.append(domain)


def _merge_ordered(existing: list[Any], new_values: list[Any]) -> list[Any]:
    merged = list(existing or [])
    seen = {_dedupe_key(value) for value in merged}
    for value in new_values or []:
        key = _dedupe_key(value)
        if key not in seen:
            merged.append(value)
            seen.add(key)
    return merged


def _dedupe_key(value: Any) -> str:
    return str(value).strip().lower()


def _contact_key(contact: dict[str, Any]) -> Optional[str]:
    key = contact.get("email") or contact.get("name")
    return str(key).strip().lower() if key else None
