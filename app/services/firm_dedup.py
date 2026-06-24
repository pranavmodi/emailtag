"""Dedup review clustering for firm identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.pif_info import PifInfo
from app.services.firm_identity import canonical_domain


@dataclass(frozen=True)
class DedupReviewCluster:
    cluster_key: str
    firm_ids: list[str]
    firm_names: list[str]
    review_required: bool = True
    action: str = "review_only"


def cluster_firms_for_review(firms: Iterable[PifInfo]) -> list[DedupReviewCluster]:
    """Group firms by canonical domain and flag multi-firm clusters for review only."""
    grouped: dict[str, list[PifInfo]] = {}
    for firm in firms:
        domain = _firm_domain(firm)
        if not domain:
            continue
        grouped.setdefault(domain, []).append(firm)

    clusters = []
    for domain, members in grouped.items():
        if len(members) <= 1:
            continue
        clusters.append(
            DedupReviewCluster(
                cluster_key=domain,
                firm_ids=[str(member.id) for member in members],
                firm_names=[member.firm_name for member in members],
            )
        )
    return clusters


def find_dedup_review_clusters(db: Session) -> list[DedupReviewCluster]:
    """Load all firms and return duplicate-domain review clusters. Does not merge."""
    return cluster_firms_for_review(db.query(PifInfo).all())


def _firm_domain(firm: PifInfo) -> Optional[str]:
    return (
        canonical_domain(firm.canonical_website)
        or canonical_domain(firm.website)
        or _first_email_domain(firm)
    )


def _first_email_domain(firm: PifInfo) -> Optional[str]:
    for email in firm.emails or []:
        domain = canonical_domain(email)
        if domain:
            return domain
    return None
