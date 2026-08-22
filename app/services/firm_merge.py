"""Guarded, reversible firm merge tooling."""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.models.firm_alias import FirmAlias
from app.models.firm_merge_audit import FirmMergeAudit
from app.models.pif_info import PifInfo
from app.services.firm_dedup import cluster_firms_for_review
from app.services.firm_identity import canonical_domain


EXCLUDED_SHARED_DOMAINS = {
    "barracuda.com",
    "cloudflare.com",
    "constantcontact.com",
    "ccsend.com",
    "google.com",
    "mailchimp.com",
    "mimecast.com",
    "outlook.com",
    "proofpoint.com",
    "sendgrid.com",
    "secureserver.net",
    "squarespace.com",
    "wix.com",
    "wordpress.com",
}

LIST_FIELDS = (
    "emails",
    "phones",
    "addresses",
    "conversation_ids",
    "leadership",
    "contacts",
    "staff",
)
DICT_FIELDS = ("behavioral_data", "research_data", "job_postings", "score_breakdown")
MIN_DATETIME_FIELDS = ("first_contacted_precise_at",)
SCALAR_FIELDS = (
    "entity_type",
    "website",
    "canonical_website",
    "website_status",
    "website_source",
    "website_confidence",
    "firm_name",
    "fax",
    "extraction_notes",
    "research_status",
    "last_researched_at",
    "job_postings_research_status",
    "last_job_postings_researched_at",
    "staff_research_status",
    "icp_score",
    "icp_tier",
    "icp_scored_at",
)
MERGE_FIELDS = LIST_FIELDS + DICT_FIELDS + MIN_DATETIME_FIELDS + SCALAR_FIELDS + (
    "merged_into",
    "merge_status",
    "merged_at",
    "merged_from",
)

LEGAL_NOISE_TOKENS = {
    "a",
    "and",
    "apc",
    "attorney",
    "attorneys",
    "firm",
    "group",
    "inc",
    "injury",
    "law",
    "lawyer",
    "lawyers",
    "legal",
    "llc",
    "llp",
    "of",
    "office",
    "offices",
    "pc",
    "plc",
    "professional",
    "the",
}


@dataclass
class FirmMergePlan:
    canonical_domain: str
    action: str
    confidence: float
    survivor_id: Optional[str]
    survivor_name: Optional[str]
    loser_ids: list[str]
    member_ids: list[str]
    member_names: list[str]
    unioned_fields: dict[str, list[Any]] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    review_reasons: list[str] = field(default_factory=list)

    @property
    def auto_merge(self) -> bool:
        return self.action == "auto_merge"


@dataclass
class FirmMergeReport:
    dry_run: bool
    plans: list[FirmMergePlan]

    @property
    def auto_merge_count(self) -> int:
        return sum(1 for plan in self.plans if plan.auto_merge)

    @property
    def review_count(self) -> int:
        return sum(1 for plan in self.plans if not plan.auto_merge)


def build_firm_merge_report(firms: Iterable[PifInfo], *, dry_run: bool = True) -> FirmMergeReport:
    """Plan guarded duplicate merges from E0 dedup clusters."""
    firm_list = list(firms)
    by_id = {str(firm.id): firm for firm in firm_list}
    plans: list[FirmMergePlan] = []

    for cluster in cluster_firms_for_review(firm_list):
        members = [by_id[firm_id] for firm_id in cluster.firm_ids if firm_id in by_id]
        if len(members) < 2:
            continue
        plans.append(plan_merge_cluster(cluster.cluster_key, members))

    plans.sort(key=lambda plan: (plan.canonical_domain, plan.action))
    return FirmMergeReport(dry_run=dry_run, plans=plans)


def plan_merge_cluster(canonical_key: str, members: list[PifInfo]) -> FirmMergePlan:
    """Build one merge/review plan for a duplicate canonical-domain cluster."""
    domain = canonical_domain(canonical_key)
    review_reasons: list[str] = []
    if not domain:
        review_reasons.append("no_real_firm_domain")
        domain = canonical_key
    elif domain in EXCLUDED_SHARED_DOMAINS:
        review_reasons.append("shared_or_junk_domain")

    name_similarity = _cluster_name_similarity(members)
    if name_similarity < 0.62:
        review_reasons.append("dissimilar_firm_names")

    survivor = _choose_survivor(members)
    losers = [firm for firm in members if firm.id != survivor.id]
    unioned_fields, conflicts = _preview_merge_changes(survivor, losers)
    confidence = _merge_confidence(domain, name_similarity, review_reasons)
    action = "review" if review_reasons else "auto_merge"

    return FirmMergePlan(
        canonical_domain=domain,
        action=action,
        confidence=confidence,
        survivor_id=str(survivor.id) if not review_reasons else None,
        survivor_name=survivor.firm_name if not review_reasons else None,
        loser_ids=[str(firm.id) for firm in losers] if not review_reasons else [],
        member_ids=[str(firm.id) for firm in members],
        member_names=[firm.firm_name for firm in members],
        unioned_fields=unioned_fields,
        conflicts=conflicts,
        review_reasons=review_reasons,
    )


def apply_merge_plan_to_firms(
    plan: FirmMergePlan,
    firms: Iterable[PifInfo],
    *,
    aliases: Optional[list[FirmAlias]] = None,
    applied_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """Apply a prepared auto-merge plan to in-memory objects and return an undo payload."""
    if not plan.auto_merge or not plan.survivor_id:
        raise ValueError("Only auto_merge plans can be applied")

    now = applied_at or datetime.utcnow()
    aliases = aliases if aliases is not None else []
    by_id = {str(firm.id): firm for firm in firms}
    survivor = by_id[plan.survivor_id]
    losers = [by_id[loser_id] for loser_id in plan.loser_ids]

    before_state = {
        "survivor": _snapshot_firm(survivor),
        "losers": [_snapshot_firm(loser) for loser in losers],
        "aliases": [_snapshot_alias(alias) for alias in aliases],
    }

    merged_from = list(survivor.merged_from or [])
    for loser in losers:
        provenance = _loser_provenance(plan, survivor, loser, now)
        merged_from.append(provenance)
        _merge_lists_and_dicts(survivor, loser)
        loser.merged_into = survivor.id
        loser.merge_status = "merged"
        loser.merged_at = now

        alias = _find_alias(aliases, "legacy_pif_id", str(loser.id))
        if alias is None:
            alias = FirmAlias(
                alias_type="legacy_pif_id",
                alias_value=str(loser.id),
                firm_id=survivor.id,
                confidence=plan.confidence,
                source="merge",
            )
            aliases.append(alias)
        else:
            alias.firm_id = survivor.id
            alias.confidence = plan.confidence
            alias.source = "merge"

    survivor.merged_from = merged_from
    after_state = {
        "survivor": _snapshot_firm(survivor),
        "losers": [_snapshot_firm(loser) for loser in losers],
        "aliases": [_snapshot_alias(alias) for alias in aliases],
    }

    return {
        "canonical_domain": plan.canonical_domain,
        "survivor_id": plan.survivor_id,
        "loser_ids": plan.loser_ids,
        "confidence": plan.confidence,
        "plan": asdict(plan),
        "before_state": before_state,
        "after_state": after_state,
    }


def apply_firm_merge_plan(db: Session, plan: FirmMergePlan) -> FirmMergeAudit:
    """Apply one auto-merge plan to the database without committing the transaction."""
    if not plan.auto_merge or not plan.survivor_id:
        raise ValueError("Only auto_merge plans can be applied")

    ids = [uuid.UUID(plan.survivor_id), *(uuid.UUID(loser_id) for loser_id in plan.loser_ids)]
    firms = db.query(PifInfo).filter(PifInfo.id.in_(ids)).all()
    aliases = (
        db.query(FirmAlias)
        .filter(
            FirmAlias.alias_type == "legacy_pif_id",
            FirmAlias.alias_value.in_(plan.loser_ids),
        )
        .all()
    )
    audit_payload = apply_merge_plan_to_firms(plan, firms, aliases=aliases)
    for alias in aliases:
        db.add(alias)

    audit = FirmMergeAudit(
        canonical_domain=plan.canonical_domain,
        survivor_id=uuid.UUID(plan.survivor_id),
        loser_ids=plan.loser_ids,
        confidence=plan.confidence,
        status="applied",
        source="merge",
        plan=audit_payload["plan"],
        before_state=audit_payload["before_state"],
        after_state=audit_payload["after_state"],
    )
    db.add(audit)
    db.flush()
    return audit


def run_firm_merge(
    db: Session,
    *,
    dry_run: bool = True,
    apply: bool = False,
) -> FirmMergeReport:
    """Plan duplicate firm merges, applying only when explicitly requested."""
    if dry_run and apply:
        raise ValueError("dry_run and apply cannot both be true")

    firms = db.query(PifInfo).filter(PifInfo.merged_into.is_(None)).all()
    report = build_firm_merge_report(firms, dry_run=dry_run)
    if apply:
        for plan in report.plans:
            if plan.auto_merge:
                apply_firm_merge_plan(db, plan)
    return report


def undo_firm_merge(db: Session, audit_id: uuid.UUID) -> FirmMergeAudit:
    """Reverse a merge from its audit record without committing the transaction."""
    audit = db.get(FirmMergeAudit, audit_id)
    if audit is None:
        raise ValueError(f"Merge audit not found: {audit_id}")
    if audit.status == "undone":
        return audit

    before = audit.before_state
    snapshots = [before["survivor"], *before["losers"]]
    firm_ids = [uuid.UUID(snapshot["id"]) for snapshot in snapshots]
    firms = {str(firm.id): firm for firm in db.query(PifInfo).filter(PifInfo.id.in_(firm_ids)).all()}
    for snapshot in snapshots:
        firm = firms.get(snapshot["id"])
        if firm is not None:
            _restore_firm(firm, snapshot)

    current_aliases = (
        db.query(FirmAlias)
        .filter(
            FirmAlias.alias_type == "legacy_pif_id",
            FirmAlias.alias_value.in_(audit.loser_ids),
        )
        .all()
    )
    current_by_value = {alias.alias_value: alias for alias in current_aliases}
    original_by_value = {
        alias["alias_value"]: alias
        for alias in before.get("aliases", [])
        if alias["alias_type"] == "legacy_pif_id" and alias["alias_value"] in audit.loser_ids
    }
    for alias_value in audit.loser_ids:
        current = current_by_value.get(alias_value)
        original = original_by_value.get(alias_value)
        if original and current:
            _restore_alias(current, original)
        elif original and not current:
            db.add(_alias_from_snapshot(original))
        elif current and not original:
            db.delete(current)

    audit.status = "undone"
    audit.undone_at = datetime.utcnow()
    db.flush()
    return audit


def restore_merge_from_payload(
    payload: dict[str, Any],
    firms: Iterable[PifInfo],
    aliases: list[FirmAlias],
) -> None:
    """Fixture-safe undo helper mirroring undo_firm_merge."""
    by_id = {str(firm.id): firm for firm in firms}
    before = payload["before_state"]
    for snapshot in [before["survivor"], *before["losers"]]:
        firm = by_id.get(snapshot["id"])
        if firm is not None:
            _restore_firm(firm, snapshot)

    original = {(alias["alias_type"], alias["alias_value"]): alias for alias in before["aliases"]}
    for alias in list(aliases):
        key = (alias.alias_type, alias.alias_value)
        if key in original:
            _restore_alias(alias, original[key])
        elif alias.alias_type == "legacy_pif_id" and alias.alias_value in payload["loser_ids"]:
            aliases.remove(alias)
    for key, snapshot in original.items():
        if not _find_alias(aliases, key[0], key[1]):
            aliases.append(_alias_from_snapshot(snapshot))


def format_merge_report(report: FirmMergeReport) -> str:
    """Render a readable dry-run/apply report for CLI and task logs."""
    mode = "DRY RUN" if report.dry_run else "APPLY"
    lines = [
        f"Firm merge {mode}: {len(report.plans)} duplicate-domain clusters",
        f"Auto-merge candidates: {report.auto_merge_count}",
        f"Review required: {report.review_count}",
    ]
    for plan in report.plans:
        lines.append("")
        lines.append(f"[{plan.action}] {plan.canonical_domain} confidence={plan.confidence:.2f}")
        lines.append(f"  members: {', '.join(plan.member_names)}")
        if plan.auto_merge:
            lines.append(f"  survivor: {plan.survivor_name} ({plan.survivor_id})")
            lines.append(f"  losers: {', '.join(plan.loser_ids)}")
            if plan.unioned_fields:
                fields = ", ".join(
                    f"{field_name}+{len(values)}"
                    for field_name, values in sorted(plan.unioned_fields.items())
                )
                lines.append(f"  unioned: {fields}")
            if plan.conflicts:
                lines.append(f"  scalar conflicts: {len(plan.conflicts)} retained in merged_from")
        else:
            lines.append(f"  review reasons: {', '.join(plan.review_reasons)}")
    return "\n".join(lines)


def _choose_survivor(members: list[PifInfo]) -> PifInfo:
    return max(
        members,
        key=lambda firm: (
            1 if (firm.canonical_website or firm.website) else 0,
            len(firm.conversation_ids or []),
            1 if firm.leadership else 0,
            firm.updated_at or datetime.min,
        ),
    )


def _preview_merge_changes(
    survivor: PifInfo,
    losers: list[PifInfo],
) -> tuple[dict[str, list[Any]], list[dict[str, Any]]]:
    unioned: dict[str, list[Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for loser in losers:
        for field_name in LIST_FIELDS:
            additions = _list_additions(getattr(survivor, field_name, None), getattr(loser, field_name, None))
            if additions:
                unioned.setdefault(field_name, []).extend(additions)
        for field_name in DICT_FIELDS:
            additions, dict_conflicts = _dict_additions_and_conflicts(
                getattr(survivor, field_name, None),
                getattr(loser, field_name, None),
            )
            if additions:
                unioned.setdefault(field_name, []).extend(additions)
            for key, value in dict_conflicts:
                conflicts.append(
                    {
                        "field": f"{field_name}.{key}",
                        "survivor_value": _jsonable(value[0]),
                        "loser_id": str(loser.id),
                        "loser_value": _jsonable(value[1]),
                    }
                )
        for field_name in SCALAR_FIELDS:
            survivor_value = getattr(survivor, field_name, None)
            loser_value = getattr(loser, field_name, None)
            if survivor_value not in (None, "", []) and loser_value not in (None, "", []):
                if _jsonable(survivor_value) != _jsonable(loser_value):
                    conflicts.append(
                        {
                            "field": field_name,
                            "survivor_value": _jsonable(survivor_value),
                            "loser_id": str(loser.id),
                            "loser_value": _jsonable(loser_value),
                        }
                    )
    return unioned, conflicts


def _merge_lists_and_dicts(survivor: PifInfo, loser: PifInfo) -> None:
    for field_name in LIST_FIELDS:
        merged = _union_list(getattr(survivor, field_name, None), getattr(loser, field_name, None))
        setattr(survivor, field_name, merged)
    for field_name in DICT_FIELDS:
        merged = _merge_dict(getattr(survivor, field_name, None), getattr(loser, field_name, None))
        setattr(survivor, field_name, merged)
    for field_name in MIN_DATETIME_FIELDS:
        merged = _earliest_datetime(
            getattr(survivor, field_name, None),
            getattr(loser, field_name, None),
        )
        setattr(survivor, field_name, merged)


def _loser_provenance(
    plan: FirmMergePlan,
    survivor: PifInfo,
    loser: PifInfo,
    merged_at: datetime,
) -> dict[str, Any]:
    loser_id = str(loser.id)
    return {
        "firm_id": loser_id,
        "firm_name": loser.firm_name,
        "canonical_domain": plan.canonical_domain,
        "merged_at": merged_at.isoformat(),
        "scalar_conflicts": [
            conflict for conflict in plan.conflicts if conflict.get("loser_id") == loser_id
        ],
        "source_values": {
            field_name: _jsonable(getattr(loser, field_name, None))
            for field_name in MERGE_FIELDS
            if field_name not in {"merged_into", "merge_status", "merged_at", "merged_from"}
        },
        "survivor_before": {
            field_name: _jsonable(getattr(survivor, field_name, None))
            for field_name in SCALAR_FIELDS
        },
    }


def _cluster_name_similarity(members: list[PifInfo]) -> float:
    names = [_normalized_name(firm.firm_name) for firm in members]
    if len(names) < 2:
        return 1.0
    scores = []
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            scores.append(max(_sequence_score(left, right), _token_overlap(left, right)))
    return min(scores) if scores else 1.0


def _normalized_name(name: str) -> str:
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    filtered = [word for word in words if word not in LEGAL_NOISE_TOKENS]
    return " ".join(filtered or words)


def _sequence_score(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _token_overlap(left: str, right: str) -> float:
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def _merge_confidence(domain: str, name_similarity: float, review_reasons: list[str]) -> float:
    if review_reasons:
        return min(0.49, max(0.0, name_similarity))
    domain_score = 1.0 if domain and domain not in EXCLUDED_SHARED_DOMAINS else 0.0
    return round(min(0.99, (domain_score * 0.45) + (name_similarity * 0.55)), 2)


def _union_list(left: Any, right: Any) -> list[Any]:
    result = list(left or [])
    for item in right or []:
        if not _contains_equivalent(result, item):
            result.append(item)
    return result


def _list_additions(left: Any, right: Any) -> list[Any]:
    result = []
    existing = list(left or [])
    for item in right or []:
        if not _contains_equivalent(existing, item):
            result.append(_jsonable(item))
            existing.append(item)
    return result


def _contains_equivalent(values: list[Any], candidate: Any) -> bool:
    candidate_key = _dedup_key(candidate)
    return any(_dedup_key(value) == candidate_key for value in values)


def _dedup_key(value: Any) -> Any:
    if isinstance(value, dict):
        for key in ("email", "name", "phone", "title"):
            if value.get(key):
                return key, str(value[key]).strip().lower()
        return tuple(sorted((str(k), str(v)) for k, v in value.items()))
    if isinstance(value, str):
        return value.strip().lower()
    return _jsonable(value)


def _merge_dict(left: Any, right: Any) -> Optional[dict[str, Any]]:
    if not left and not right:
        return None
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        for key, value in right.items():
            if key not in merged or merged[key] in (None, "", [], {}):
                merged[key] = value
        return merged
    return left or right


def _earliest_datetime(left: Optional[datetime], right: Optional[datetime]) -> Optional[datetime]:
    if left and right:
        return min(left, right)
    return left or right


def _dict_additions_and_conflicts(
    left: Any,
    right: Any,
) -> tuple[list[dict[str, Any]], list[tuple[str, tuple[Any, Any]]]]:
    if not right:
        return [], []
    if not left:
        return [_jsonable(right)], []
    if not isinstance(left, dict) or not isinstance(right, dict):
        return [], [("", (left, right))] if _jsonable(left) != _jsonable(right) else []

    additions = []
    conflicts = []
    for key, value in right.items():
        if key not in left or left[key] in (None, "", [], {}):
            additions.append({key: _jsonable(value)})
        elif _jsonable(left[key]) != _jsonable(value):
            conflicts.append((key, (left[key], value)))
    return additions, conflicts


def _find_alias(aliases: list[FirmAlias], alias_type: str, alias_value: str) -> Optional[FirmAlias]:
    normalized = alias_value.lower()
    for alias in aliases:
        if alias.alias_type == alias_type and alias.alias_value.lower() == normalized:
            return alias
    return None


def _snapshot_firm(firm: PifInfo) -> dict[str, Any]:
    snapshot = {"id": str(firm.id)}
    for field_name in MERGE_FIELDS:
        snapshot[field_name] = _jsonable(getattr(firm, field_name, None))
    return snapshot


def _restore_firm(firm: PifInfo, snapshot: dict[str, Any]) -> None:
    for field_name in MERGE_FIELDS:
        value = snapshot.get(field_name)
        if field_name in {
            "last_researched_at",
            "last_job_postings_researched_at",
            "icp_scored_at",
            "merged_at",
            "first_contacted_precise_at",
        }:
            value = _parse_datetime(value)
        elif field_name == "merged_into" and value:
            value = uuid.UUID(value)
        setattr(firm, field_name, value)


def _snapshot_alias(alias: FirmAlias) -> dict[str, Any]:
    return {
        "id": str(alias.id) if alias.id else None,
        "alias_type": alias.alias_type,
        "alias_value": alias.alias_value,
        "firm_id": str(alias.firm_id),
        "confidence": alias.confidence,
        "source": alias.source,
        "created_at": _jsonable(alias.created_at),
    }


def _restore_alias(alias: FirmAlias, snapshot: dict[str, Any]) -> None:
    alias.alias_type = snapshot["alias_type"]
    alias.alias_value = snapshot["alias_value"]
    alias.firm_id = uuid.UUID(snapshot["firm_id"])
    alias.confidence = snapshot["confidence"]
    alias.source = snapshot["source"]
    alias.created_at = _parse_datetime(snapshot.get("created_at")) or alias.created_at


def _alias_from_snapshot(snapshot: dict[str, Any]) -> FirmAlias:
    alias = FirmAlias(
        alias_type=snapshot["alias_type"],
        alias_value=snapshot["alias_value"],
        firm_id=uuid.UUID(snapshot["firm_id"]),
        confidence=snapshot["confidence"],
        source=snapshot["source"],
    )
    if snapshot.get("id"):
        alias.id = uuid.UUID(snapshot["id"])
    if snapshot.get("created_at"):
        alias.created_at = _parse_datetime(snapshot["created_at"]) or datetime.utcnow()
    return alias


def _jsonable(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None
