"""Phase 1 Bill Offer intake agent."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from celery.utils.log import get_task_logger

from app.crud import bill_offer as bill_offer_crud
from app.db.session import AsyncSessionLocal
from app.mcp import call_mcp_tool
from app.models.bill_offer import (
    BillOfferAgentStepStatus,
    BillOfferIntakeStatus,
)
from app.schemas.bill_offer import BillOfferAgentLogCreate
from app.services import frontapp_service
from app.services.bill_offer_extraction_service import (
    build_bill_offer_context,
    build_reply_draft,
    compute_missing_fields,
    confidence_summary,
    extract_bill_offer_facts_structured,
    merge_effective_facts,
)

logger = get_task_logger(__name__)

WAITING_PENDING_OFFER_DETAILS_TAG = "Waiting > Pending Offer Details"
HUMAN_REVIEW_TAG = "AI: Human review required"


class BillOfferRunLogger:
    """Small DB-backed logger for agent steps."""

    def __init__(
        self,
        *,
        front_conversation_id: str,
        email_id: Optional[uuid.UUID],
        run_id: str,
    ) -> None:
        self.front_conversation_id = front_conversation_id
        self.email_id = email_id
        self.run_id = run_id
        self.intake_id: Optional[uuid.UUID] = None

    async def log(
        self,
        step_name: str,
        step_status: str,
        *,
        input_snapshot: Optional[Dict[str, Any]] = None,
        output_snapshot: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        try:
            async with AsyncSessionLocal() as db:
                await bill_offer_crud.create_log(
                    db,
                    obj_in=BillOfferAgentLogCreate(
                        front_conversation_id=self.front_conversation_id,
                        email_id=self.email_id,
                        intake_id=self.intake_id,
                        run_id=self.run_id,
                        step_name=step_name,
                        step_status=step_status,
                        input_snapshot=input_snapshot,
                        output_snapshot=output_snapshot,
                        message=message,
                        error=error,
                    ),
                )
        except Exception as exc:
            logger.error(f"Failed to write Bill Offer agent log: {exc}", exc_info=True)


def _extract_patient_ids(text: str) -> List[str]:
    matches = re.findall(r"\b(PRE\d{6,8}|PI[-\s]?\d{3,8})\b", text or "", re.IGNORECASE)
    numeric_matches = re.findall(
        r"\b(?:patient\s*id|patient\s*id#|patient\s*id\s*#|patient\s*#|pt\s*id)\s*[:#]?\s*(\d{6,8})\b",
        text or "",
        re.IGNORECASE,
    )
    normalized = []
    for match in matches:
        value = match.upper().replace(" ", "")
        if value not in normalized:
            normalized.append(value)
    for match in numeric_matches:
        value = f"PRE{match}"
        if value not in normalized:
            normalized.append(value)
    return normalized


def _clean_name_part(value: Any) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    cleaned = cleaned.strip(" \t\r\n:;,./\\()[]{}<>")
    cleaned = cleaned.strip("-–—")
    return cleaned


def _clean_name_value(value: Any) -> str:
    parts = [_clean_name_part(part) for part in str(value or "").split()]
    return " ".join(part for part in parts if part)


def _extract_name_dates(text: str) -> Dict[str, Optional[str]]:
    normalized = re.sub(r"\s+", " ", text or "")
    patient_match = re.search(
        r"(?:client\s*/\s*patient|patient\s*/\s*client|patient|client)\s*[:\-]\s*"
        r"([A-Z][a-zA-Z'’-]+)\s+([A-Z][a-zA-Z'’-]+)",
        normalized,
        re.IGNORECASE,
    )
    name_match = patient_match or re.search(
        r"\b([A-Z][a-zA-Z'’-]+)\s+([A-Z][a-zA-Z'’-]+)\b.{0,100}\b"
        r"(?:DOB|date of birth|DOI|date of injury|DOL|date of loss)\b",
        normalized,
    )
    dob_match = re.search(
        r"\b(?:DOB|date of birth)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})",
        normalized,
        re.IGNORECASE,
    )
    doi_match = re.search(
        r"\b(?:DOI|date of injury|DOL|date of loss)\s*[:\-]?\s*"
        r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})",
        normalized,
        re.IGNORECASE,
    )
    return {
        "first_name": _clean_name_part(name_match.group(1)) if name_match else None,
        "last_name": _clean_name_part(name_match.group(2)) if name_match else None,
        "dob": _to_db_date(dob_match.group(1)) if dob_match else None,
        "doi": _to_db_date(doi_match.group(1)) if doi_match else None,
    }


def _split_patient_name(value: Any) -> Dict[str, Optional[str]]:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    cleaned = re.sub(
        r"^(?:client|patient|client\s*/\s*patient)\s*[:\-]\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    parts = [_clean_name_part(part) for part in cleaned.split()]
    parts = [part for part in parts if part]
    if len(parts) < 2:
        return {"first_name": None, "last_name": None}
    return {"first_name": parts[0], "last_name": " ".join(parts[1:])}


def _name_candidates_from_tokens(tokens: List[str]) -> List[Dict[str, Optional[str]]]:
    if len(tokens) < 2:
        return []

    tokens = [_clean_name_part(token) for token in tokens]
    tokens = [token for token in tokens if token]
    if len(tokens) < 2:
        return []

    candidates = [{"first_name": tokens[0], "last_name": " ".join(tokens[1:])}]
    if len(tokens) > 2:
        candidates.append({"first_name": tokens[0], "last_name": tokens[-1]})
        candidates.append({"first_name": tokens[0], "last_name": tokens[1]})

    deduped: List[Dict[str, Optional[str]]] = []
    seen = set()
    for candidate in candidates:
        key = (
            str(candidate.get("first_name") or "").lower(),
            str(candidate.get("last_name") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _subject_patient_name_candidates(thread_text: str) -> List[Dict[str, Optional[str]]]:
    """Extract likely patient names from subject lines for date-constrained lookup."""
    subject_lines = re.findall(r"(?im)^Subject:\s*(.+)$", thread_text or "")
    candidates: List[Dict[str, Optional[str]]] = []
    seen = set()
    stop_words = {
        "external",
        "re",
        "fw",
        "fwd",
        "lien",
        "reduction",
        "negotiation",
        "request",
        "precise",
        "imaging",
        "bill",
        "billing",
        "offer",
        "client",
        "patient",
        "dob",
        "doi",
        "dol",
        "date",
        "loss",
        "law",
        "group",
        "firm",
        "office",
        "apc",
        "llp",
        "pllc",
    }

    for subject in subject_lines:
        cleaned = re.sub(r"\b(?:EXTERNAL|RE|FW|FWD)\s*:\s*", "", subject, flags=re.IGNORECASE)
        cleaned = re.split(r"\b(?:DOB|DOI|DOL|date of birth|date of loss|date of injury)\b", cleaned, flags=re.IGNORECASE)[0]
        segments = [segment.strip(" :;,") for segment in re.split(r"\s+-\s+|\s+\|\s+|/", cleaned)]
        if cleaned.strip(" :;,") not in segments:
            segments.insert(0, cleaned.strip(" :;,"))

        for segment in segments:
            if "@" in segment:
                continue
            tokens = re.findall(r"[A-Za-z][A-Za-z'’-]+", segment)
            if not 2 <= len(tokens) <= 4:
                continue
            lowered = {token.lower() for token in tokens}
            if lowered & stop_words:
                continue
            for candidate in _name_candidates_from_tokens(tokens):
                key = (
                    str(candidate.get("first_name") or "").lower(),
                    str(candidate.get("last_name") or "").lower(),
                )
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(candidate)

    return candidates


def _canonical_document_field_name(field_name: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(field_name or "").lower()).strip("_")
    for suffix in ("_ocr", "_extracted", "_from_ocr", "_from_document"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
    return normalized


def _document_patient_candidates(
    extracted_facts: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Pull patient lookup candidates from LLM-normalized document facts."""
    candidates: List[Dict[str, Any]] = []
    document_facts = (extracted_facts or {}).get("_document_facts") or []
    if not isinstance(document_facts, list):
        return candidates

    for document in document_facts:
        if not isinstance(document, dict):
            continue
        candidate: Dict[str, Any] = {
            "first_name": None,
            "last_name": None,
            "dob": None,
            "doi": None,
            "source": {
                "document_id": document.get("document_id"),
                "filename": document.get("filename"),
            },
        }

        extracted_fields = document.get("extracted_fields") or []
        if isinstance(extracted_fields, list):
            for field_fact in extracted_fields:
                if not isinstance(field_fact, dict):
                    continue
                field_name = _canonical_document_field_name(field_fact.get("field"))
                value = field_fact.get("value")
                if field_name in {
                    "patient_name",
                    "client_name",
                    "client_patient",
                    "patient_client",
                    "name",
                }:
                    candidate.update(_split_patient_name(value))
                elif (
                    field_name
                    in {
                        "patient_dob",
                        "client_dob",
                        "dob",
                        "date_of_birth",
                        "birth_date",
                    }
                    and value
                ):
                    candidate["dob"] = _to_db_date(str(value))
                elif field_name in {
                    "patient_doi",
                    "client_doi",
                    "doi",
                    "date_of_injury",
                    "date_of_loss",
                    "dol",
                    "loss_date",
                } and value:
                    candidate["doi"] = _to_db_date(str(value))

        identifiers = document.get("patient_identifiers") or []
        if isinstance(identifiers, list):
            identifier_text = "\n".join(str(item) for item in identifiers)
            parsed = _extract_name_dates(identifier_text)
            for key in ("first_name", "last_name", "dob", "doi"):
                candidate[key] = candidate.get(key) or parsed.get(key)

            for identifier in identifiers:
                text = str(identifier)
                if not candidate.get("first_name") or not candidate.get("last_name"):
                    if not re.search(
                        r"\b(?:DOB|date of birth|DOI|DOL|date of injury|date of loss)\b",
                        text,
                        re.IGNORECASE,
                    ):
                        candidate.update(_split_patient_name(text))

        if document.get("notes"):
            parsed = _extract_name_dates(str(document.get("notes")))
            for key in ("first_name", "last_name", "dob", "doi"):
                candidate[key] = candidate.get(key) or parsed.get(key)

        if candidate.get("first_name") and candidate.get("last_name") and (
            candidate.get("dob") or candidate.get("doi")
        ):
            candidates.append(candidate)

    return candidates


def _to_db_date(value: str) -> Optional[str]:
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%m-%d-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


def _format_date(value: Any) -> str:
    if not value:
        return "Unknown"
    value_str = str(value)
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value_str[:10], fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return value_str


def _extract_patients_from_mcp_response(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(response, dict):
        return []
    candidates = [
        response.get("patients"),
        response.get("data", {}).get("patients") if isinstance(response.get("data"), dict) else None,
        response.get("result", {}).get("patients") if isinstance(response.get("result"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, list):
            return [item for item in candidate if isinstance(item, dict)]
    return []


async def resolve_patient(
    *,
    thread_text: str,
    extracted_patient_ids: Optional[List[str]],
    run_logger: BillOfferRunLogger,
    extracted_facts: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Resolve patient according to the Phase 1 lookup order."""
    existing_ids = [pid for pid in (extracted_patient_ids or []) if pid]
    if existing_ids:
        await run_logger.log(
            "patient_lookup_existing_ids",
            BillOfferAgentStepStatus.COMPLETED,
            output_snapshot={"patient_ids": existing_ids},
            message="Using pre-extracted patient IDs",
        )
        return existing_ids[0], {
            "method": "existing_extracted_patient_ids",
            "candidates": existing_ids,
        }

    text_ids = _extract_patient_ids(thread_text)
    if text_ids:
        await run_logger.log(
            "patient_lookup_text_ids",
            BillOfferAgentStepStatus.COMPLETED,
            output_snapshot={"patient_ids": text_ids},
            message="Found patient IDs in thread text",
        )
        return text_ids[0], {"method": "thread_text_patient_id", "candidates": text_ids}

    document_ids = _extract_patient_ids(
        str((extracted_facts or {}).get("_document_facts") or "")
    )
    if document_ids:
        await run_logger.log(
            "patient_lookup_document_ids",
            BillOfferAgentStepStatus.COMPLETED,
            output_snapshot={"patient_ids": document_ids},
            message="Found patient IDs in document facts",
        )
        return document_ids[0], {"method": "document_fact_patient_id", "candidates": document_ids}

    subject_name_candidates = _subject_patient_name_candidates(thread_text)
    for document_candidate in _document_patient_candidates(extracted_facts):
        for subject_name in subject_name_candidates:
            combined_candidate = {
                **document_candidate,
                **subject_name,
                "source": {
                    **(document_candidate.get("source") or {}),
                    "name_source": "subject",
                },
            }
            await run_logger.log(
                "patient_lookup_subject_name_document_dates_extracted",
                BillOfferAgentStepStatus.COMPLETED,
                output_snapshot=combined_candidate,
                message="Combined subject name with document date candidates",
            )
            patient_id, patient_match = await _lookup_patient_by_name_dates(
                name_dates=combined_candidate,
                run_logger=run_logger,
                source_method="subject_document_fact",
            )
            if patient_id:
                return patient_id, patient_match

        await run_logger.log(
            "patient_lookup_document_name_dates_extracted",
            BillOfferAgentStepStatus.COMPLETED,
            output_snapshot=document_candidate,
            message="Extracted name/date candidates from document facts",
        )
        patient_id, patient_match = await _lookup_patient_by_name_dates(
            name_dates=document_candidate,
            run_logger=run_logger,
            source_method="document_fact",
        )
        if patient_id:
            return patient_id, patient_match

    name_dates = _extract_name_dates(thread_text)
    for subject_name in subject_name_candidates:
        subject_candidate = {
            **name_dates,
            **subject_name,
            "source": {"name_source": "subject", "date_source": "thread_text"},
        }
        if not subject_candidate.get("dob") and not subject_candidate.get("doi"):
            continue
        await run_logger.log(
            "patient_lookup_subject_name_thread_dates_extracted",
            BillOfferAgentStepStatus.COMPLETED,
            output_snapshot=subject_candidate,
            message="Combined subject name with thread date candidates",
        )
        patient_id, patient_match = await _lookup_patient_by_name_dates(
            name_dates=subject_candidate,
            run_logger=run_logger,
            source_method="subject_thread",
        )
        if patient_id:
            return patient_id, patient_match

    await run_logger.log(
        "patient_lookup_name_dates_extracted",
        BillOfferAgentStepStatus.COMPLETED,
        output_snapshot=name_dates,
        message="Extracted name/date candidates for lookup",
    )

    return await _lookup_patient_by_name_dates(
        name_dates=name_dates,
        run_logger=run_logger,
        source_method="name_date_lookup",
    )


async def _lookup_patient_by_name_dates(
    *,
    name_dates: Dict[str, Any],
    run_logger: BillOfferRunLogger,
    source_method: str,
) -> Tuple[Optional[str], Dict[str, Any]]:
    first_name = _clean_name_value(name_dates.get("first_name"))
    last_name = _clean_name_value(name_dates.get("last_name"))
    if not first_name or not last_name:
        return None, {"method": source_method, "reason": "missing_name"}

    lookup_attempts = []
    if name_dates.get("dob"):
        lookup_attempts.append(
            (
                "fetch_patient_by_name_and_dob",
                {"firstName": first_name, "lastName": last_name, "dob": name_dates["dob"]},
                "name_dob",
            )
        )
    if name_dates.get("doi"):
        lookup_attempts.append(
            (
                "fetch_patient_by_name_and_doi",
                {"firstName": first_name, "lastName": last_name, "doi": name_dates["doi"]},
                "name_doi",
            )
        )

    for tool_name, arguments, method in lookup_attempts:
        try:
            await run_logger.log(
                "patient_lookup_attempt",
                BillOfferAgentStepStatus.STARTED,
                input_snapshot={"tool": tool_name, "arguments": arguments},
            )
            response = await call_mcp_tool(tool_name=tool_name, arguments=arguments)
            patients = _extract_patients_from_mcp_response(response)
            await run_logger.log(
                "patient_lookup_attempt",
                BillOfferAgentStepStatus.COMPLETED,
                input_snapshot={"tool": tool_name, "arguments": arguments},
                output_snapshot={"patients_count": len(patients)},
            )
            if patients:
                if method == "name_dob" and len(patients) > 1:
                    continue
                patient_id = patients[0].get("patient_id") or patients[0].get("patientId")
                if patient_id:
                    return patient_id, {
                        "method": (
                            method
                            if source_method == "name_date_lookup"
                            else f"{source_method}_{method}"
                        ),
                        "patient": patients[0],
                        "candidate": name_dates,
                    }
        except Exception as exc:
            await run_logger.log(
                "patient_lookup_attempt",
                BillOfferAgentStepStatus.FAILED,
                input_snapshot={"tool": tool_name, "arguments": arguments},
                error=str(exc),
            )
    return None, {"method": source_method, "reason": "no_match", "candidate": name_dates}


async def fetch_patient_context(
    patient_id: str,
    *,
    run_logger: BillOfferRunLogger,
) -> Dict[str, Any]:
    await run_logger.log(
        "patient_context_fetch",
        BillOfferAgentStepStatus.STARTED,
        input_snapshot={"patient_id": patient_id},
    )
    patient_info_response = await call_mcp_tool(
        tool_name="fetch_patient_info", arguments={"patient_id": patient_id}
    )
    bill_response = await call_mcp_tool(
        tool_name="get_patient_lien_bill_balance", arguments={"patient_id": patient_id}
    )

    def mcp_response_succeeded(response: Any) -> bool:
        if not isinstance(response, dict):
            return False
        if response.get("success") is False or response.get("error"):
            return False
        return bool(response)

    patient_name = "Unknown"
    dob = "Unknown"
    doi = "Unknown"
    patients = _extract_patients_from_mcp_response(patient_info_response)
    if patients:
        patient = patients[0]
        first = patient.get("first_name") or patient.get("firstName") or ""
        last = patient.get("last_name") or patient.get("lastName") or ""
        patient_name = f"{first} {last}".strip() or patient.get("patient_name") or "Unknown"
        dob = _format_date(patient.get("birth_date") or patient.get("dob") or patient.get("dateOfBirth"))
        doi = _format_date(patient.get("doi") or patient.get("dateOfInjury"))

    result = {}
    if isinstance(bill_response, dict):
        if isinstance(bill_response.get("data"), dict):
            result = bill_response.get("data", {}).get("result", {}) or {}
        elif isinstance(bill_response.get("result"), dict):
            result = bill_response.get("result", {})
    if isinstance(result, str):
        result = {}

    studies = result.get("patientStudyDetails") or result.get("studies") or []
    lien_total = result.get("patientBillBalance") or result.get("lienTotal") or 0
    patient_data = {
        "patient_id": patient_id,
        "patient_name": patient_name,
        "dob": dob,
        "doi": doi,
        "lien_total": lien_total,
        "studies": studies if isinstance(studies, list) else [],
        "mcp": {
            "patient_info_success": mcp_response_succeeded(patient_info_response),
            "bill_balance_success": mcp_response_succeeded(bill_response),
        },
    }
    await run_logger.log(
        "patient_context_fetch",
        BillOfferAgentStepStatus.COMPLETED,
        output_snapshot={
            "patient_name": patient_name,
            "study_count": len(patient_data["studies"]),
            "lien_total": lien_total,
        },
    )
    return patient_data


async def handle_bill_offer_request(
    *,
    front_conversation_id: str,
    current_email_content: str,
    structured_history_messages: Optional[List[Dict[str, Any]]] = None,
    email_sender: Optional[str] = None,
    email_subject: Optional[str] = None,
    extracted_patient_ids: Optional[List[str]] = None,
    ocr_results: Any = None,
    raw_data: Any = None,
    email_id: Optional[uuid.UUID] = None,
    send_reply: bool = False,
    triggered_by: Optional[str] = None,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    run_id = run_id or str(uuid.uuid4())
    run_logger = BillOfferRunLogger(
        front_conversation_id=front_conversation_id,
        email_id=email_id,
        run_id=run_id,
    )
    await run_logger.log(
        "intake_started",
        BillOfferAgentStepStatus.STARTED,
        input_snapshot={
            "email_id": str(email_id) if email_id else None,
            "email_subject": email_subject,
            "triggered_by": triggered_by,
            "send_reply": send_reply,
        },
    )

    try:
        bill_offer_context = build_bill_offer_context(
            front_conversation_id=front_conversation_id,
            current_email_content=current_email_content,
            structured_history_messages=structured_history_messages,
            ocr_results=ocr_results,
            raw_data=raw_data,
            email_subject=email_subject,
            email_sender=email_sender,
            extracted_patient_ids=extracted_patient_ids,
        )
        thread_text = bill_offer_context.get("thread_text", "")
        context_meta = bill_offer_context.get("context_sources", {})
        await run_logger.log(
            "thread_loaded",
            BillOfferAgentStepStatus.COMPLETED,
            output_snapshot={
                "thread_chars": len(thread_text),
                "message_count": len(bill_offer_context.get("messages", [])),
                "document_count": len(bill_offer_context.get("documents", [])),
                "attachment_count": len(bill_offer_context.get("attachments", [])),
                **context_meta,
            },
        )

        async with AsyncSessionLocal() as db:
            intake = await bill_offer_crud.upsert_intake_for_conversation(
                db,
                front_conversation_id=front_conversation_id,
                values={
                    "email_id": email_id,
                    "original_sender_email": email_sender,
                    "last_run_id": run_id,
                    "last_agent_run_status": "running",
                    "last_agent_action": "started",
                },
            )
            run_logger.intake_id = intake.id

        extracted_facts = extract_bill_offer_facts_structured(bill_offer_context)
        await run_logger.log(
            "offer_facts_extracted",
            BillOfferAgentStepStatus.COMPLETED,
            output_snapshot={
                "fields": [field for field in extracted_facts.keys() if not field.startswith("_")],
                "document_facts_count": len(extracted_facts.get("_document_facts") or []),
                "conflicts_count": len(extracted_facts.get("_conflicts") or []),
                "meta": extracted_facts.get("_meta", {}),
                "facts": extracted_facts,
            },
        )

        patient_id, patient_match = await resolve_patient(
            thread_text=thread_text,
            extracted_patient_ids=extracted_patient_ids,
            run_logger=run_logger,
            extracted_facts=extracted_facts,
        )

        patient_data = None
        if patient_id:
            patient_data = await fetch_patient_context(patient_id, run_logger=run_logger)
            patient_match = {**patient_match, "patient_id": patient_id}
        else:
            await run_logger.log(
                "patient_not_found",
                BillOfferAgentStepStatus.COMPLETED,
                output_snapshot=patient_match,
                message="Could not resolve patient",
            )

        async with AsyncSessionLocal() as db:
            intake = await bill_offer_crud.get_intake_by_conversation(db, front_conversation_id)
            corrected_facts = intake.corrected_facts if intake else None

        effective_facts = merge_effective_facts(extracted_facts, corrected_facts)
        missing_fields = compute_missing_fields(effective_facts) if patient_id else []
        status = (
            BillOfferIntakeStatus.PENDING_PATIENT
            if not patient_id
            else BillOfferIntakeStatus.PENDING_DETAILS
            if missing_fields
            else BillOfferIntakeStatus.READY_FOR_PHASE_2
        )

        reply_draft = build_reply_draft(
            patient_found=bool(patient_id),
            patient_data=patient_data,
            missing_fields=missing_fields,
            effective_facts=effective_facts,
        )
        await run_logger.log(
            "completeness_checked",
            BillOfferAgentStepStatus.COMPLETED,
            output_snapshot={"status": status, "missing_fields": missing_fields},
        )
        await run_logger.log(
            "reply_draft_generated",
            BillOfferAgentStepStatus.COMPLETED,
            output_snapshot={"reply_chars": len(reply_draft)},
        )

        reply_sent = False
        if send_reply and status in {
            BillOfferIntakeStatus.PENDING_PATIENT,
            BillOfferIntakeStatus.PENDING_DETAILS,
        }:
            from app.agents.agent_helpers import send_reply_to_front_direct

            await send_reply_to_front_direct(
                conversation_id=front_conversation_id,
                reply_text=reply_draft,
                tags_to_add=[WAITING_PENDING_OFFER_DETAILS_TAG],
            )
            reply_sent = True
            await run_logger.log(
                "front_reply_sent",
                BillOfferAgentStepStatus.COMPLETED,
                output_snapshot={"tags_to_add": [WAITING_PENDING_OFFER_DETAILS_TAG]},
            )
        else:
            await run_logger.log(
                "front_reply_skipped",
                BillOfferAgentStepStatus.SKIPPED,
                message="Reply sending disabled or not needed for status",
                output_snapshot={"send_reply": send_reply, "status": status},
            )

        async with AsyncSessionLocal() as db:
            intake = await bill_offer_crud.get_intake_by_conversation(db, front_conversation_id)
            intake = await bill_offer_crud.update_intake(
                db,
                intake=intake,
                obj_in={
                    "email_id": email_id,
                    "status": status,
                    "patient_id": patient_id,
                    "patient_match": patient_match,
                    "patient_data": patient_data,
                    "extracted_facts": extracted_facts,
                    "missing_fields": missing_fields,
                    "confidence": confidence_summary(effective_facts),
                    "original_sender_email": email_sender,
                    "last_agent_action": "reply_sent" if reply_sent else "drafted",
                    "last_run_id": run_id,
                    "last_agent_run_status": "completed",
                    "reply_draft": reply_draft,
                    "reply_sent_at": datetime.utcnow() if reply_sent else None,
                },
            )

        await run_logger.log(
            "intake_completed",
            BillOfferAgentStepStatus.COMPLETED,
            output_snapshot={"status": status, "reply_sent": reply_sent},
        )
        return {
            "agent_handled": True,
            "processed_flag": True,
            "run_id": run_id,
            "intake_id": str(intake.id),
            "details": {
                "status": status,
                "missing_fields": missing_fields,
                "reply_sent": reply_sent,
            },
        }
    except Exception as exc:
        logger.error(f"Bill Offer agent failed for {front_conversation_id}: {exc}", exc_info=True)
        await run_logger.log(
            "intake_failed",
            BillOfferAgentStepStatus.FAILED,
            error=str(exc),
        )
        try:
            frontapp_service.add_conversation_tags(front_conversation_id, [HUMAN_REVIEW_TAG])
        except Exception:
            logger.exception("Failed to add human review tag after Bill Offer failure")
        async with AsyncSessionLocal() as db:
            intake = await bill_offer_crud.get_intake_by_conversation(db, front_conversation_id)
            if intake:
                await bill_offer_crud.update_intake(
                    db,
                    intake=intake,
                    obj_in={
                        "status": BillOfferIntakeStatus.MANUAL_REVIEW,
                        "last_agent_action": "failed",
                        "last_run_id": run_id,
                        "last_agent_run_status": "failed",
                    },
                )
        return {
            "agent_handled": False,
            "processed_flag": False,
            "run_id": run_id,
            "details": {"reason": str(exc)},
        }
