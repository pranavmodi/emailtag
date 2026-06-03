"""Extraction and reply helpers for Bill Offer Phase 1."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.classification_service import get_openai_client

logger = logging.getLogger(__name__)

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

SOURCE_TYPES = [
    "email_body",
    "prior_thread_message",
    "ocr_text",
    "attachment_document",
    "subject",
    "user_correction",
]

BILL_OFFER_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "object",
            "properties": {
                field: {
                    "type": "object",
                    "properties": {
                        "value": {"type": ["number", "string", "null"]},
                        "evidence": {"type": "string"},
                        "source": {"type": "string", "enum": SOURCE_TYPES},
                        "source_id": {"type": "string"},
                        "confidence": {"type": "number"},
                        "is_ambiguous": {"type": "boolean"},
                        "ambiguity_notes": {"type": "string"},
                    },
                    "required": [
                        "value",
                        "evidence",
                        "source",
                        "source_id",
                        "confidence",
                        "is_ambiguous",
                        "ambiguity_notes",
                    ],
                    "additionalProperties": False,
                }
                for field in REQUIRED_FIELDS
            },
            "required": REQUIRED_FIELDS,
            "additionalProperties": False,
        },
        "document_facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "document_id": {"type": "string"},
                    "filename": {"type": "string"},
                    "document_type": {"type": "string"},
                    "page": {"type": ["integer", "null"]},
                    "extracted_fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "value": {"type": ["number", "string", "null"]},
                                "evidence": {"type": "string"},
                                "confidence": {"type": "number"},
                                "ambiguity_notes": {"type": "string"},
                            },
                            "required": [
                                "field",
                                "value",
                                "evidence",
                                "confidence",
                                "ambiguity_notes",
                            ],
                            "additionalProperties": False,
                        },
                    },
                    "patient_identifiers": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "notes": {"type": "string"},
                },
                "required": [
                    "document_id",
                    "filename",
                    "document_type",
                    "page",
                    "extracted_fields",
                    "patient_identifiers",
                    "notes",
                ],
                "additionalProperties": False,
            },
        },
        "conflicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "description": {"type": "string"},
                    "sources": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["field", "description", "sources"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["facts", "document_facts", "conflicts", "summary"],
    "additionalProperties": False,
}


@dataclass
class ExtractedValue:
    value: Any
    evidence: str
    source: str
    confidence: float
    source_id: str = ""
    is_ambiguous: bool = False
    ambiguity_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "evidence": self.evidence,
            "source": self.source,
            "source_id": self.source_id,
            "confidence": self.confidence,
            "is_ambiguous": self.is_ambiguous,
            "ambiguity_notes": self.ambiguity_notes,
        }


def _truncate(value: Any, limit: int = 4000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


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


def _message_source_type(index: int, total: int) -> str:
    return "email_body" if index == total - 1 else "prior_thread_message"


def _attachment_summary(raw_data: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_data, dict):
        return []

    candidates: List[Any] = []
    candidates.extend(raw_data.get("attachments") or [])
    candidates.extend(raw_data.get("_attachments") or [])
    target_data = raw_data.get("target", {}).get("data", {}) if isinstance(raw_data.get("target"), dict) else {}
    if isinstance(target_data, dict):
        candidates.extend(target_data.get("attachments") or [])

    attachments: List[Dict[str, Any]] = []
    seen = set()
    for index, attachment in enumerate(candidates):
        if not isinstance(attachment, dict):
            continue
        attachment_id = str(attachment.get("id") or attachment.get("uid") or f"attachment_{index}")
        if attachment_id in seen:
            continue
        seen.add(attachment_id)
        attachments.append(
            {
                "id": attachment_id,
                "filename": attachment.get("filename") or attachment.get("name") or "",
                "content_type": attachment.get("content_type") or attachment.get("type") or "",
                "size": attachment.get("size"),
            }
        )
    return attachments


def _extract_ocr_documents(ocr_results: Any) -> List[Dict[str, Any]]:
    documents: List[Dict[str, Any]] = []
    if not ocr_results:
        return documents

    items = ocr_results if isinstance(ocr_results, list) else [ocr_results]
    for index, item in enumerate(items):
        if isinstance(item, dict):
            filename = (
                item.get("filename")
                or item.get("file_name")
                or item.get("attachment_name")
                or item.get("name")
                or f"ocr_item_{index + 1}"
            )
            text_chunks = []
            for key in ("text", "extracted_text", "ocr_text", "content", "summary"):
                if item.get(key):
                    text_chunks.append(str(item[key]))
            pages = []
            raw_pages = item.get("pages") or item.get("page_results") or []
            if isinstance(raw_pages, list):
                for page_index, page in enumerate(raw_pages):
                    if not isinstance(page, dict):
                        continue
                    page_text = page.get("text") or page.get("extracted_text") or page.get("ocr_text") or ""
                    if page_text:
                        pages.append(
                            {
                                "page": page.get("page") or page.get("page_number") or page_index + 1,
                                "text": _truncate(page_text, 2500),
                            }
                        )
                        text_chunks.append(str(page_text))
            document_analysis = item.get("document_analysis") or item.get("analysis") or {}
            enhanced_lien = (
                item.get("enhanced_lien_processing")
                or item.get("enhanced_lien_processing_split")
                or item.get("enhanced_lien_analysis")
                or {}
            )
            documents.append(
                {
                    "document_id": str(item.get("id") or item.get("attachment_id") or f"ocr_{index + 1}"),
                    "filename": filename,
                    "document_type": (
                        item.get("document_type")
                        or item.get("detected_type")
                        or document_analysis.get("document_type")
                        or document_analysis.get("type")
                        or ""
                    ),
                    "text": _truncate("\n".join(text_chunks), 6000),
                    "pages": pages[:20],
                    "document_analysis": document_analysis,
                    "enhanced_lien": enhanced_lien,
                }
            )
        else:
            documents.append(
                {
                    "document_id": f"ocr_{index + 1}",
                    "filename": f"ocr_item_{index + 1}",
                    "document_type": "",
                    "text": _truncate(item, 6000),
                    "pages": [],
                    "document_analysis": {},
                    "enhanced_lien": {},
                }
            )
    return documents


def build_bill_offer_context(
    *,
    front_conversation_id: str,
    current_email_content: str,
    structured_history_messages: Optional[List[Dict[str, Any]]],
    ocr_results: Any,
    raw_data: Any,
    email_subject: Optional[str],
    email_sender: Optional[str],
    extracted_patient_ids: Optional[List[str]],
) -> Dict[str, Any]:
    """Build structured LLM/review context from full thread and available documents."""
    messages: List[Dict[str, Any]] = []
    structured_history_messages = structured_history_messages or []
    has_distinct_current = bool(current_email_content) and not any(
        (msg.get("body") or msg.get("text_body") or msg.get("content") or "") == current_email_content
        for msg in structured_history_messages
        if isinstance(msg, dict)
    )

    for index, msg in enumerate(structured_history_messages):
        body = msg.get("body") or msg.get("text_body") or msg.get("content") or ""
        if not body:
            continue
        messages.append(
            {
                "id": str(msg.get("id") or f"message_{index + 1}"),
                "source": "prior_thread_message"
                if has_distinct_current
                else _message_source_type(index, len(structured_history_messages)),
                "sender": msg.get("author_email") or msg.get("from") or msg.get("sender") or msg.get("author_name") or "Unknown",
                "author_role": msg.get("author_role") or "",
                "created_at": msg.get("created_at") or "",
                "recipients_to": msg.get("recipients_to") or msg.get("to") or "",
                "recipients_cc": msg.get("recipients_cc") or msg.get("cc") or "",
                "body": _truncate(body, 6000),
            }
        )

    if has_distinct_current:
        messages.append(
            {
                "id": "current_email",
                "source": "email_body",
                "sender": email_sender or "Unknown",
                "author_role": "user",
                "created_at": "",
                "recipients_to": "",
                "recipients_cc": "",
                "body": _truncate(current_email_content, 6000),
            }
        )

    documents = _extract_ocr_documents(ocr_results)
    attachments = _attachment_summary(raw_data)

    thread_text_parts = []
    if email_subject:
        thread_text_parts.append(f"Subject: {email_subject}")
    for message in messages:
        thread_text_parts.append(
            "\n".join(
                [
                    f"Message ID: {message['id']}",
                    f"Source: {message['source']}",
                    f"From: {message['sender']}",
                    f"Date: {message['created_at']}",
                    f"Body: {message['body']}",
                ]
            )
        )
    for document in documents:
        if document.get("text"):
            thread_text_parts.append(
                "\n".join(
                    [
                        f"Document ID: {document['document_id']}",
                        f"Filename: {document['filename']}",
                        f"Document Type: {document.get('document_type') or 'unknown'}",
                        f"OCR Text: {document['text']}",
                    ]
                )
            )

    return {
        "front_conversation_id": front_conversation_id,
        "subject": email_subject or "",
        "original_sender_email": email_sender or "",
        "messages": messages,
        "attachments": attachments,
        "documents": documents,
        "extracted_patient_ids": extracted_patient_ids or [],
        "context_sources": {
            "structured_messages": len(messages),
            "ocr_documents": len(documents),
            "attachments": len(attachments),
            "fallback_current_body_only": not bool(structured_history_messages),
        },
        "thread_text": "\n\n---\n\n".join(thread_text_parts),
    }


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
                source="email_body",
                confidence=confidence,
            )
    return None


def extract_bill_offer_facts(text: str) -> Dict[str, Dict[str, Any]]:
    """Fallback deterministic extraction for tests and LLM failure cases."""
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
                    source="email_body",
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
                    source="email_body",
                    confidence=0.95,
                )
                break
    if offer:
        facts["precise_offer_amount"] = offer.to_dict()

    medpay = extract_medpay_status(text)
    if medpay:
        facts["medpay_status"] = medpay.to_dict()

    return facts


def _coerce_field_fact(field: str, raw_fact: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_fact, dict):
        return None
    value = raw_fact.get("value")
    if field in {"settlement_amount", "total_medical_bills", "precise_offer_amount"}:
        if isinstance(value, str):
            value = normalize_money(value) if value.strip() else None
        elif isinstance(value, (int, float)):
            value = float(value)
        else:
            value = None

    confidence = raw_fact.get("confidence")
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    if value in (None, "") and not raw_fact.get("evidence") and not raw_fact.get("ambiguity_notes"):
        return None

    return {
        "value": value,
        "evidence": str(raw_fact.get("evidence") or "")[:1000],
        "source": raw_fact.get("source") if raw_fact.get("source") in SOURCE_TYPES else "email_body",
        "source_id": str(raw_fact.get("source_id") or ""),
        "confidence": confidence,
        "is_ambiguous": bool(raw_fact.get("is_ambiguous")),
        "ambiguity_notes": str(raw_fact.get("ambiguity_notes") or "")[:1000],
        "extraction_method": "llm",
    }


def _looks_like_lien_offer_not_case_settlement(fact: Dict[str, Any]) -> bool:
    """Detect when a lien/bill offer was incorrectly used as the gross settlement."""
    text = " ".join(
        str(fact.get(key) or "") for key in ("evidence", "ambiguity_notes")
    ).lower()
    if not text:
        return False

    strong_lien_offer_phrases = [
        "settle this lien",
        "settle the lien",
        "settle your lien",
        "settle lien",
        "settle this bill",
        "settle the bill",
        "full and final payment",
        "full and final satisfaction",
        "full and complete satisfaction",
        "toward precise imaging",
        "precise imaging's lien",
        "your medical lien",
        "your lien",
    ]
    if any(phrase in text for phrase in strong_lien_offer_phrases):
        return True

    mentions_lien_or_bill = any(
        term in text
        for term in [
            "lien",
            "bill",
            "balance",
            "account",
            "provider",
            "precise imaging",
            "your office",
        ]
    )
    mentions_offer_payment = any(
        term in text
        for term in [
            "accept $",
            "offer $",
            "offered $",
            "proposed",
            "proposal",
            "payment",
            "pay $",
        ]
    )
    return mentions_lien_or_bill and mentions_offer_payment


def _guard_settlement_amount(facts: Dict[str, Any]) -> None:
    settlement_fact = facts.get("settlement_amount")
    if not isinstance(settlement_fact, dict):
        return
    if not _looks_like_lien_offer_not_case_settlement(settlement_fact):
        return

    logger.warning(
        "Bill Offer extraction rejected settlement_amount that appears to be a lien offer: "
        "source=%s evidence=%s",
        settlement_fact.get("source_id"),
        _truncate(settlement_fact.get("evidence"), 160),
    )
    settlement_fact["value"] = None
    settlement_fact["confidence"] = min(float(settlement_fact.get("confidence") or 0), 0.35)
    settlement_fact["is_ambiguous"] = True
    existing_notes = str(settlement_fact.get("ambiguity_notes") or "").strip()
    guard_note = (
        "Rejected as total settlement amount because the evidence appears to describe "
        "a lien/bill payment offer, not the gross case settlement."
    )
    settlement_fact["ambiguity_notes"] = (
        f"{existing_notes} {guard_note}".strip() if existing_notes else guard_note
    )


def _normalize_llm_response(response_data: Dict[str, Any]) -> Dict[str, Any]:
    raw_facts = response_data.get("facts") if isinstance(response_data, dict) else {}
    facts: Dict[str, Any] = {}
    for field in REQUIRED_FIELDS:
        fact = _coerce_field_fact(field, raw_facts.get(field) if isinstance(raw_facts, dict) else None)
        if fact:
            facts[field] = fact

    _guard_settlement_amount(facts)

    document_facts = response_data.get("document_facts") or []
    facts["_document_facts"] = document_facts if isinstance(document_facts, list) else []
    facts["_conflicts"] = response_data.get("conflicts") if isinstance(response_data.get("conflicts"), list) else []
    facts["_meta"] = {
        "extraction_method": "llm",
        "summary": response_data.get("summary") or "",
    }
    return facts


def _build_llm_prompt(context: Dict[str, Any]) -> str:
    compact_context = {
        "front_conversation_id": context.get("front_conversation_id"),
        "subject": context.get("subject"),
        "original_sender_email": context.get("original_sender_email"),
        "extracted_patient_ids": context.get("extracted_patient_ids"),
        "messages": context.get("messages", []),
        "attachments": context.get("attachments", []),
        "documents": context.get("documents", []),
    }
    return (
        "Extract Phase 1 Bill Offer intake facts for Precise Imaging.\n\n"
        "Rules:\n"
        "- Use the complete chronological email conversation and available OCR/document context.\n"
        "- Extract only facts that are supported by evidence in the provided context.\n"
        "- The Precise Imaging offer amount is critical. If an amount is not clearly an offer toward "
        "Precise Imaging's lien/bill, return null for precise_offer_amount and mark it ambiguous.\n"
        "- settlement_amount means the total/gross case settlement only. Do not use lien/bill/provider "
        "settlement language such as 'settle this lien', 'full and final payment', 'accept $X as full "
        "payment', or an amount offered toward Precise Imaging's lien as settlement_amount. If the only "
        "settlement-like amount is a lien/bill offer, return null for settlement_amount with notes.\n"
        "- Total medical bills means all providers, not only Precise Imaging.\n"
        "- Med-pay status can be text, such as 'No med-pay available' or 'Med-pay exhausted'.\n"
        "- Preserve document-derived facts in document_facts even when they are not selected as final facts.\n"
        "- If sources conflict, include the conflict and mark the affected selected fact ambiguous when needed.\n\n"
        "Context JSON:\n"
        f"{json.dumps(compact_context, default=str)[:60000]}"
    )


def call_llm_for_bill_offer_extraction(context: Dict[str, Any]) -> Dict[str, Any]:
    """Primary LLM extraction path with deterministic fallback handled by caller."""
    model = settings.OPENAI_CLASSIFICATION_MODEL or settings.OPENAI_MODEL_VERSION or "gpt-4o-2024-08-06"
    client = get_openai_client()
    api_params: Dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a medical billing intake extraction specialist. "
                    "Return only JSON matching the schema."
                ),
            },
            {"role": "user", "content": _build_llm_prompt(context)},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "bill_offer_intake_extraction",
                "strict": True,
                "schema": BILL_OFFER_EXTRACTION_SCHEMA,
            },
        },
    }
    if "gpt-5" in model.lower():
        api_params["reasoning_effort"] = "medium"
        api_params["max_completion_tokens"] = 8000
    else:
        api_params["temperature"] = 0.0
        api_params["max_tokens"] = 2500

    logger.info(
        "Running Bill Offer LLM extraction: model=%s messages=%s documents=%s attachments=%s",
        model,
        len(context.get("messages", [])),
        len(context.get("documents", [])),
        len(context.get("attachments", [])),
    )
    response = client.chat.completions.create(**api_params)
    response_text = response.choices[0].message.content or "{}"
    parsed = json.loads(response_text)
    return _normalize_llm_response(parsed)


def extract_bill_offer_facts_structured(context: Dict[str, Any]) -> Dict[str, Any]:
    """Extract facts with LLM first, falling back to deterministic extraction on failure."""
    try:
        facts = call_llm_for_bill_offer_extraction(context)
        facts["_meta"] = {
            **facts.get("_meta", {}),
            "fallback_used": False,
            "context_sources": context.get("context_sources", {}),
        }
        return facts
    except Exception as exc:
        logger.error("Bill Offer LLM extraction failed; using deterministic fallback: %s", exc, exc_info=True)
        facts = extract_bill_offer_facts(context.get("thread_text", ""))
        for fact in facts.values():
            if isinstance(fact, dict):
                fact["extraction_method"] = "deterministic_fallback"
        facts["_document_facts"] = []
        facts["_conflicts"] = []
        facts["_meta"] = {
            "extraction_method": "deterministic_fallback",
            "fallback_used": True,
            "fallback_reason": str(exc),
            "context_sources": context.get("context_sources", {}),
        }
        return facts


def extract_medpay_status(text: str) -> Optional[ExtractedValue]:
    for sentence in _sentences(text):
        lower = sentence.lower()
        if not any(term in lower for term in ["med-pay", "med pay", "medpay", "medical payments"]):
            continue
        return ExtractedValue(
            value=sentence[:250],
            evidence=sentence[:500],
            source="email_body",
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
        is_ambiguous = bool(value_obj.get("is_ambiguous")) if isinstance(value_obj, dict) else False
        if value is None or value == "":
            missing.append(field)
        elif field == "precise_offer_amount" and is_ambiguous:
            missing.append(field)
    if "precise_offer_amount" in missing:
        missing.remove("precise_offer_amount")
        missing.insert(0, "precise_offer_amount")
    return missing


def confidence_summary(facts: Dict[str, Any]) -> Dict[str, Any]:
    values = [
        fact.get("confidence")
        for field, fact in facts.items()
        if field in REQUIRED_FIELDS
        and isinstance(fact, dict)
        and isinstance(fact.get("confidence"), (int, float))
    ]
    fields = {
        field: fact.get("confidence")
        for field, fact in facts.items()
        if field in REQUIRED_FIELDS and isinstance(fact, dict)
    }
    return {
        "average": round(sum(values) / len(values), 3) if values else None,
        "fields": fields,
        "ambiguous_fields": [
            field
            for field, fact in facts.items()
            if field in REQUIRED_FIELDS and isinstance(fact, dict) and fact.get("is_ambiguous")
        ],
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
