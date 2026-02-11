"""
Credential screening service for RX document provider validation.

Screens provider credentials from RX attachments against allowed/disallowed lists.
When only disallowed credentials are found, the referral is flagged for manual review
by applying a 'credential review' tag instead of auto-scheduling.
"""

import logging
import re
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def normalize_credential(raw: str) -> str:
    """
    Normalize a credential string for comparison.

    - Uppercase
    - Remove dots (e.g., "M.D." -> "MD")
    - Remove spaces
    - Strip common suffixes like -C, -BC (e.g., "PA-C" -> "PA", "PMHNP-BC" -> "PMHNP")

    Args:
        raw: Raw credential string

    Returns:
        Normalized credential string
    """
    normalized = raw.upper().strip()
    normalized = normalized.replace(".", "").replace(" ", "")
    # Strip common board-certification suffixes: -C, -BC, -S, etc.
    normalized = re.sub(r"-(C|BC|S|CSS)$", "", normalized)
    return normalized


def screen_credentials(
    credentials: List[str],
    allowed: Set[str],
    disallowed: Set[str],
) -> Dict:
    """
    Screen a list of credentials against allowed/disallowed sets.

    Logic:
    - Normalize each credential
    - If ANY allowed credential is found, the provider is cleared (short-circuit)
    - If ONLY disallowed credentials are found, requires review
    - Unknown credentials (not in either list) do NOT clear the provider

    Args:
        credentials: Raw credential strings extracted from the document
        allowed: Set of normalized allowed credentials
        disallowed: Set of normalized disallowed credentials

    Returns:
        Dict with keys:
            requires_review: bool
            allowed_found: list of matched allowed credentials
            disallowed_found: list of matched disallowed credentials
            unknown_found: list of credentials not in either list
    """
    allowed_found = []
    disallowed_found = []
    unknown_found = []

    for raw_cred in credentials:
        normalized = normalize_credential(raw_cred)
        if not normalized:
            continue

        if normalized in allowed:
            allowed_found.append(normalized)
        elif normalized in disallowed:
            disallowed_found.append(normalized)
        else:
            unknown_found.append(normalized)

    # If any allowed credential was found, provider is cleared
    requires_review = len(allowed_found) == 0 and (len(disallowed_found) > 0 or len(unknown_found) > 0)

    return {
        "requires_review": requires_review,
        "allowed_found": allowed_found,
        "disallowed_found": disallowed_found,
        "unknown_found": unknown_found,
    }


async def check_rx_provider_credentials(
    ocr_results: List[dict],
    db,
) -> Dict:
    """
    Orchestrator: scan OCR results for RX provider credentials and screen them.

    Args:
        ocr_results: List of OCR result dicts from email_obj.ocr_results
        db: AsyncSession for loading credential lists from tag_settings

    Returns:
        Dict with screening results including requires_review flag
    """
    from app.crud.tag_settings import tag_settings_crud

    # Load credential lists from tag_settings for "RX"
    rx_settings = await tag_settings_crud.get_settings_dict(db, "RX", default={})

    if not rx_settings.get("credential_screening_enabled", False):
        logger.debug("RX credential screening is disabled in tag_settings")
        return {"requires_review": False, "reason": "screening_disabled_in_tag_settings"}

    allowed = set(rx_settings.get("allowed_credentials", []))
    disallowed = set(rx_settings.get("disallowed_credentials", []))

    if not allowed and not disallowed:
        logger.warning("RX credential screening: no allowed/disallowed lists configured in tag_settings")
        return {"requires_review": False, "reason": "no_credential_lists_configured"}

    # Scan OCR results for provider_credential_analysis entries
    all_credentials = []
    provider_info = {}

    for ocr_result in ocr_results:
        if not isinstance(ocr_result, dict):
            continue

        cred_analysis = ocr_result.get("provider_credential_analysis")
        if not cred_analysis:
            continue

        raw_creds = cred_analysis.get("raw_credentials", [])
        if raw_creds:
            all_credentials.extend(raw_creds)
            # Capture the last provider info found
            provider_info = {
                "provider_name": cred_analysis.get("provider_name", ""),
                "nameprefix": cred_analysis.get("nameprefix", ""),
                "namesuffix": cred_analysis.get("namesuffix", ""),
            }

    if not all_credentials:
        logger.info("RX credential screening: no credentials found in OCR results")
        return {"requires_review": False, "reason": "no_credentials_in_ocr"}

    # Run screening
    result = screen_credentials(all_credentials, allowed, disallowed)
    result["provider_info"] = provider_info
    result["raw_credentials"] = all_credentials

    if result["requires_review"]:
        logger.info(
            f"RX credential screening: REVIEW REQUIRED - "
            f"provider={provider_info.get('provider_name', 'unknown')}, "
            f"disallowed={result['disallowed_found']}, "
            f"unknown={result['unknown_found']}"
        )
    else:
        logger.info(
            f"RX credential screening: CLEARED - "
            f"provider={provider_info.get('provider_name', 'unknown')}, "
            f"allowed={result['allowed_found']}"
        )

    return result
