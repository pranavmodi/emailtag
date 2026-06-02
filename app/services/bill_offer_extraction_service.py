"""Deterministic extraction and reply helpers for Bill Offer Phase 1."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


REQUIRED_FIELDS = [
    "settlement_amount",
    "total_medical_bills",
    "medpay_status",
    "precise_offer_amount",
]

MISSING_FIELD_LABELS = {
    "precise_offer_amount": "Offer amount toward Precise Imaging's bill",
    "settlement_amount": "Total settlement amount",
    "total_medical_bills": "Total medical bills across all providers",
    "medpay_status": "Med-pay coverage status",
}


@dataclass
class ExtractedValue:
    value: Any
    evidence: str
    source: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "evidence": self.evidence,
            "source": self.source,
            "confidence": self.confidence,
        }


def normalize_money(raw_value: str) -> Optional[float]:
    """Convert a money-like string to a float."""
    if not raw_value:
        return None
    cleaned = raw_value.replace("$", "").replace(",", "").strip()
    cleaned = re.sub(r"[^0-9.]", "", cleaned)
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def format_money(value: Any) -> str:
    """Format money for email display."""
    if value is None or value == "":
        return ""
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _sentences(text: str) -> List[str]:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    if not normalized:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", normalized) if s.strip()]


def _first_money_in_text(text: str) -> Optional[str]:
    match = re.search(r"\$\s?\d[\d,]*(?:\.\d{2})?|\b\d[\d,]{2,}(?:\.\d{2})?\b", text)
    return match.group(0) if match else None


def _field_from_sentences(
    text: str,
    *,
    include_terms: List[str],
    exclude_terms: Optional[List[str]] = None,
    confidence: float = 0.88,
) -> Optional[ExtractedValue]:
    exclude_terms = exclude_terms or []
    for sentence in _sentences(text):
        lower = sentence.lower()
        if not all(term.lower() in lower for term in include_terms):
            continue
        if any(term.lower() in lower for term in exclude_terms):
            continue
        raw_money = _first_money_in_text(sentence)
        value = normalize_money(raw_money or "")
        if value is not None:
            return ExtractedValue(
                value=value,
                evidence=sentence[:500],
                source="thread_text",
                confidence=confidence,
            )
    return None


def extract_bill_offer_facts(text: str) -> Dict[str, Dict[str, Any]]:
    """Extract the four Bill Offer facts from thread text and OCR text."""
    facts: Dict[str, Dict[str, Any]] = {}

    settlement = (
        _field_from_sentences(text, include_terms=["settlement"], confidence=0.9)
        or _field_from_sentences(text, include_terms=["gross"], exclude_terms=["bill"], confidence=0.75)
    )
    if settlement:
        facts["settlement_amount"] = settlement.to_dict()

    total_bills = None
    for sentence in _sentences(text):
        lower = sentence.lower()
        if (
            ("total" in lower and "medical" in lower and "bill" in lower)
            or ("all providers" in lower and "bill" in lower)
            or ("medical bills" in lower and "providers" in lower)
        ):
            raw_money = _first_money_in_text(sentence)
            value = normalize_money(raw_money or "")
            if value is not None:
                total_bills = ExtractedValue(
                    value=value,
                    evidence=sentence[:500],
                    source="thread_text",
                    confidence=0.9,
                )
                break
    if total_bills:
        facts["total_medical_bills"] = total_bills.to_dict()

    offer = None
    for sentence in _sentences(text):
        lower = sentence.lower()
        mentions_precise = "precise" in lower or "your lien" in lower or "imaging" in lower
        mentions_offer = any(term in lower for term in ["offer", "offering", "offered", "pay", "toward"])
        if mentions_precise and mentions_offer:
            raw_money = _first_money_in_text(sentence)
            value = normalize_money(raw_money or "")
            if value is not None:
                offer = ExtractedValue(
                    value=value,
                    evidence=sentence[:500],
                    source="thread_text",
                    confidence=0.95,
                )
                break
    if offer:
        facts["precise_offer_amount"] = offer.to_dict()

    medpay = extract_medpay_status(text)
    if medpay:
        facts["medpay_status"] = medpay.to_dict()

    return facts


def extract_medpay_status(text: str) -> Optional[ExtractedValue]:
    for sentence in _sentences(text):
        lower = sentence.lower()
        if not any(term in lower for term in ["med-pay", "med pay", "medpay", "medical payments"]):
            continue
        return ExtractedValue(
            value=sentence[:250],
            evidence=sentence[:500],
            source="thread_text",
            confidence=0.88,
        )
    return None


def merge_effective_facts(
    extracted_facts: Optional[Dict[str, Any]],
    corrected_facts: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Use corrected facts over extracted facts while preserving evidence metadata."""
    effective = dict(extracted_facts or {})
    for field, corrected in (corrected_facts or {}).items():
        if isinstance(corrected, dict) and "value" in corrected:
            effective[field] = {
                **effective.get(field, {}),
                **corrected,
                "source": corrected.get("source") or "user_correction",
            }
        else:
            effective[field] = {
                **effective.get(field, {}),
                "value": corrected,
                "source": "user_correction",
                "confidence": 1.0,
            }
    return effective


def compute_missing_fields(effective_facts: Dict[str, Any]) -> List[str]:
    missing = []
    for field in REQUIRED_FIELDS:
        value_obj = effective_facts.get(field)
        value = value_obj.get("value") if isinstance(value_obj, dict) else value_obj
        if value is None or value == "":
            missing.append(field)
    if "precise_offer_amount" in missing:
        missing.remove("precise_offer_amount")
        missing.insert(0, "precise_offer_amount")
    return missing


def confidence_summary(facts: Dict[str, Any]) -> Dict[str, Any]:
    values = [
        fact.get("confidence")
        for fact in facts.values()
        if isinstance(fact, dict) and isinstance(fact.get("confidence"), (int, float))
    ]
    return {
        "average": round(sum(values) / len(values), 3) if values else None,
        "fields": {
            field: fact.get("confidence")
            for field, fact in facts.items()
            if isinstance(fact, dict)
        },
    }


def build_missing_items_html(missing_fields: List[str]) -> str:
    items = [
        f"<li>{MISSING_FIELD_LABELS.get(field, field)}</li>"
        for field in missing_fields
    ]
    return "<ol>" + "".join(items) + "</ol>"


def build_studies_table(studies: List[Dict[str, Any]]) -> str:
    if not studies:
        return "<p>No study details available.</p>"

    rows = []
    total = 0.0
    for study in studies:
        description = (
            study.get("description")
            or study.get("studyDescription")
            or study.get("study")
            or study.get("modality")
            or "Study"
        )
        date = study.get("date") or study.get("studyDate") or study.get("dos") or ""
        billed = (
            study.get("billedAmount")
            or study.get("billed_amount")
            or study.get("billAmount")
            or study.get("amount")
            or 0
        )
        billed_value = normalize_money(str(billed)) if not isinstance(billed, (int, float)) else float(billed)
        total += billed_value or 0
        rows.append(
            "<tr>"
            f"<td style=\"border:1px solid #ccc;padding:6px;\">{description}</td>"
            f"<td style=\"border:1px solid #ccc;padding:6px;\">{date}</td>"
            f"<td style=\"border:1px solid #ccc;padding:6px;text-align:right;\">{format_money(billed_value)}</td>"
            "</tr>"
        )

    rows.append(
        "<tr>"
        "<td colspan=\"2\" style=\"border:1px solid #ccc;padding:6px;font-weight:bold;\">Total</td>"
        f"<td style=\"border:1px solid #ccc;padding:6px;text-align:right;font-weight:bold;\">{format_money(total)}</td>"
        "</tr>"
    )

    return (
        '<table border="1" cellpadding="6" cellspacing="0" '
        'style="border-collapse:collapse;margin:10px 0;">'
        "<thead><tr>"
        '<th style="border:1px solid #ccc;padding:6px;text-align:left;">Study</th>'
        '<th style="border:1px solid #ccc;padding:6px;text-align:left;">Date</th>'
        '<th style="border:1px solid #ccc;padding:6px;text-align:right;">Billed Amount</th>'
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def build_patient_block(patient_data: Dict[str, Any]) -> str:
    patient_name = patient_data.get("patient_name") or "Unknown"
    patient_id = patient_data.get("patient_id") or ""
    dob = patient_data.get("dob") or "Unknown"
    doi = patient_data.get("doi") or "Unknown"
    return (
        '<div style="background-color:#FFD700;font-weight:bold;padding:8px;margin:10px 0;">'
        f"Patient Name: {patient_name} &nbsp; "
        f"Patient ID: {patient_id} &nbsp; "
        f"Date of Birth: {dob} &nbsp; "
        f"Date of Injury: {doi}"
        "</div>"
    )


def build_reply_draft(
    *,
    patient_found: bool,
    patient_data: Optional[Dict[str, Any]],
    missing_fields: List[str],
    effective_facts: Dict[str, Any],
) -> str:
    if not patient_found:
        return (
            "Hi,<br/><br/>"
            "Thank you for reaching out to Precise Imaging. We received your message but "
            "weren't able to locate a patient record based on the information provided."
            "<br/><br/>"
            "To pull up the file, could you please provide one of the following:"
            "<ul>"
            "<li>Patient ID, if you have it on file with us</li>"
            "<li>First name, last name, and date of birth</li>"
            "<li>First name, last name, and date of injury</li>"
            "</ul>"
            "Once we locate the patient we'll follow up right away. Thank you."
        )

    patient_data = patient_data or {}
    offer_obj = effective_facts.get("precise_offer_amount") or {}
    offer_value = offer_obj.get("value") if isinstance(offer_obj, dict) else offer_obj
    top = "Hi,<br/><br/>"
    if offer_value not in (None, ""):
        top += (
            f"We have received your offer of {format_money(offer_value)} toward our "
            "Precise Imaging lien.<br/><br/>"
        )

    if missing_fields:
        if offer_value in (None, ""):
            top += "Before we can evaluate and respond, we need the following:"
        else:
            top += "Before we can evaluate and respond, we still need the following:"
        top += build_missing_items_html(missing_fields)
    else:
        top += "We have the required offer details and are preparing this intake for review."

    lien_total = patient_data.get("lien_total")
    studies = patient_data.get("studies") or []
    return (
        top
        + build_patient_block(patient_data)
        + f"<p><strong>Outstanding lien total:</strong> {format_money(lien_total)}</p>"
        + build_studies_table(studies)
        + "<p>Thank you.</p>"
    )

