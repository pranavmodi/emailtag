"""ICP (Ideal Customer Profile) scoring for PI law firms.

Pure deterministic scoring - no LLM calls.
Scores firms 0-100 based on email behavior and research data.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Tier thresholds
TIER_THRESHOLDS = {
    "A": 75,
    "B": 50,
    "C": 25,
    "D": 0,
}


def parse_firm_size(firm_size_str: Optional[str]) -> Optional[int]:
    """
    Extract approximate attorney count from a size string.

    Examples:
        "10-30 attorneys" -> 20
        "5 attorneys" -> 5
        "50+" -> 50
    """
    if not firm_size_str:
        return None

    text = firm_size_str.lower()

    # Try range pattern like "10-30"
    range_match = re.search(r"(\d+)\s*[-–]\s*(\d+)", text)
    if range_match:
        low = int(range_match.group(1))
        high = int(range_match.group(2))
        return (low + high) // 2

    # Try "50+" pattern
    plus_match = re.search(r"(\d+)\+", text)
    if plus_match:
        return int(plus_match.group(1))

    # Try single number
    single_match = re.search(r"(\d+)", text)
    if single_match:
        return int(single_match.group(1))

    return None


def score_firm(pif_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Score a firm using deterministic criteria. No LLM required.

    Args:
        pif_data: pif_info record as dict, may include:
                  behavioral_data, research_data, website, leadership,
                  phones, conversation_ids

    Returns:
        {icp_score: int, icp_tier: str, score_breakdown: dict}
    """
    behavioral = pif_data.get("behavioral_data") or {}
    research = pif_data.get("research_data") or {}
    score_breakdown: Dict[str, Any] = {}

    # --- Email Volume Score (30 pts) ---
    monthly_volumes = behavioral.get("monthly_email_volume") or []
    if monthly_volumes:
        avg_vol = sum(monthly_volumes) / len(monthly_volumes)
    else:
        avg_vol = 0.0

    if avg_vol >= 20:
        vol_score, vol_reason = 30, f"Avg {avg_vol:.1f} emails/month (≥20)"
    elif avg_vol >= 10:
        vol_score, vol_reason = 20, f"Avg {avg_vol:.1f} emails/month (10-19)"
    elif avg_vol >= 5:
        vol_score, vol_reason = 12, f"Avg {avg_vol:.1f} emails/month (5-9)"
    elif avg_vol >= 2:
        vol_score, vol_reason = 6, f"Avg {avg_vol:.1f} emails/month (2-4)"
    else:
        vol_score, vol_reason = 0, f"Avg {avg_vol:.1f} emails/month (<2)"

    score_breakdown["email_volume_score"] = vol_score
    score_breakdown["email_volume_reason"] = vol_reason

    # --- Recency Score (20 pts) ---
    days_since = behavioral.get("days_since_last_contact")
    if days_since is None:
        rec_score, rec_reason = 0, "No contact data"
    elif days_since <= 7:
        rec_score, rec_reason = 20, f"Last contact {days_since} days ago (≤7)"
    elif days_since <= 30:
        rec_score, rec_reason = 15, f"Last contact {days_since} days ago (≤30)"
    elif days_since <= 90:
        rec_score, rec_reason = 8, f"Last contact {days_since} days ago (≤90)"
    elif days_since <= 180:
        rec_score, rec_reason = 3, f"Last contact {days_since} days ago (≤180)"
    else:
        rec_score, rec_reason = 0, f"Last contact {days_since} days ago (>180)"

    score_breakdown["recency_score"] = rec_score
    score_breakdown["recency_reason"] = rec_reason

    # --- Pain Signals Score (25 pts) ---
    topic_dist = behavioral.get("topic_distribution") or {}
    total_emails = sum(topic_dist.values()) or 1
    pain_score = 0
    pain_reasons = []

    status_pct = (topic_dist.get("status_update_request", 0) / total_emails) * 100
    rush_pct = (topic_dist.get("rush_request", 0) / total_emails) * 100
    billing_pct = (topic_dist.get("billing_dispute", 0) / total_emails) * 100

    if status_pct > 30:
        pain_score += 10
        pain_reasons.append(f"Status updates {status_pct:.0f}% (>30%)")
    if rush_pct > 15:
        pain_score += 8
        pain_reasons.append(f"Rush requests {rush_pct:.0f}% (>15%)")
    if billing_pct > 20:
        pain_score += 7
        pain_reasons.append(f"Billing disputes {billing_pct:.0f}% (>20%)")

    score_breakdown["pain_signals_score"] = pain_score
    score_breakdown["pain_signals_reason"] = "; ".join(pain_reasons) if pain_reasons else "No strong pain signals"

    # --- Firm Size Score (15 pts) ---
    firm_size_str = research.get("firm_size")
    attorney_count = parse_firm_size(firm_size_str)

    if attorney_count is None:
        size_score, size_reason = 0, "Firm size unknown"
    elif 10 <= attorney_count <= 30:
        size_score, size_reason = 15, f"{attorney_count} attorneys (10-30, sweet spot)"
    elif 5 <= attorney_count <= 9:
        size_score, size_reason = 10, f"{attorney_count} attorneys (5-9)"
    elif 31 <= attorney_count <= 50:
        size_score, size_reason = 8, f"{attorney_count} attorneys (31-50)"
    elif 1 <= attorney_count <= 4:
        size_score, size_reason = 4, f"{attorney_count} attorneys (1-4)"
    else:
        size_score, size_reason = 3, f"{attorney_count}+ attorneys (large firm)"

    score_breakdown["firm_size_score"] = size_score
    score_breakdown["firm_size_reason"] = size_reason

    # --- Completeness Score (10 pts) ---
    comp_score = 0
    comp_reasons = []

    if pif_data.get("website"):
        comp_score += 2
        comp_reasons.append("website")
    if pif_data.get("leadership"):
        comp_score += 3
        comp_reasons.append("leadership")
    # Check any LinkedIn URL in leadership
    leadership = pif_data.get("leadership") or []
    if any(
        m.get("linkedin") for m in leadership
        if isinstance(m, dict)
    ):
        comp_score += 3
        comp_reasons.append("LinkedIn URLs")
    if pif_data.get("phones"):
        comp_score += 2
        comp_reasons.append("phone")

    score_breakdown["completeness_score"] = comp_score
    score_breakdown["completeness_reason"] = (
        f"Has: {', '.join(comp_reasons)}" if comp_reasons else "Missing key data"
    )

    # --- Supervised Outcome Signal (10 pts) ---
    # Private GTM feedback sharpens the neutral score without becoming a published fact.
    positive_outcomes = behavioral.get("positive_outcomes") or {}
    positive_total = int(positive_outcomes.get("total") or 0)
    if positive_total >= 3:
        outcome_score, outcome_reason = 10, f"{positive_total} positive outcomes"
    elif positive_total == 2:
        outcome_score, outcome_reason = 7, "2 positive outcomes"
    elif positive_total == 1:
        outcome_score, outcome_reason = 4, "1 positive outcome"
    else:
        outcome_score, outcome_reason = 0, "No positive outcome feedback"

    score_breakdown["outcome_supervision_score"] = outcome_score
    score_breakdown["outcome_supervision_reason"] = outcome_reason

    # --- Total ---
    total = vol_score + rec_score + pain_score + size_score + comp_score + outcome_score
    total = max(0, min(100, total))

    # Determine tier
    if total >= 75:
        tier = "A"
    elif total >= 50:
        tier = "B"
    elif total >= 25:
        tier = "C"
    else:
        tier = "D"

    score_breakdown["total"] = total
    score_breakdown["scored_at"] = datetime.utcnow().isoformat()

    logger.info(f"ICP Score for firm: {total} (Tier {tier}) - vol={vol_score}, rec={rec_score}, pain={pain_score}, size={size_score}, comp={comp_score}")

    return {
        "icp_score": total,
        "icp_tier": tier,
        "score_breakdown": score_breakdown,
    }
