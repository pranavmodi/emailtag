"""Read-only selection and secure streaming for vision evaluation documents."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.email import Email
from app.models.model_evaluation_run import ModelEvaluationCaseReview, ModelEvaluationRun


OBJECTIVES = {
    "rx": {
        "description": "Structured RX fields, handwriting, laterality, boxes, and signatures",
        "metrics": ["field accuracy", "laterality accuracy", "checkbox accuracy", "signature accuracy"],
    },
    "lien": {
        "description": "Lien barcode, patient ID, lien type, signer, and modification extraction",
        "metrics": ["barcode accuracy", "patient ID accuracy", "lien type accuracy", "signer accuracy"],
    },
}


def rx_output_needs_schema_refresh(output: Any) -> bool:
    """Return whether a completed RX output predates required diagnosis/address fields."""
    if not isinstance(output, dict):
        return False
    patient = output.get("patient")
    return (
        "diagnosis_codes" not in output
        or not isinstance(patient, dict)
        or "address" not in patient
    )


async def find_legacy_rx_cases(
    db: AsyncSession,
    allowed_model_keys: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """Find evaluated RX cases with completed active-model outputs using the old schema."""
    query = select(ModelEvaluationRun).where(
        ModelEvaluationRun.case_type == "vision",
        ModelEvaluationRun.objective == "rx",
        ModelEvaluationRun.status == "completed",
    )
    if allowed_model_keys is not None:
        if not allowed_model_keys:
            return []
        query = query.where(ModelEvaluationRun.model_key.in_(allowed_model_keys))
    result = await db.execute(query.order_by(ModelEvaluationRun.created_at.desc()))
    cases: Dict[str, Dict[str, Any]] = {}
    for run in result.scalars().all():
        if not rx_output_needs_schema_refresh(run.output):
            continue
        case = cases.setdefault(
            run.case_id,
            {
                "case_id": run.case_id,
                "email_id": str(run.email_id) if run.email_id else None,
                "result_index": run.result_index,
                "legacy_model_keys": [],
            },
        )
        case["legacy_model_keys"].append(run.model_key)
    return [
        case
        for case in cases.values()
        if case["email_id"] and case["result_index"] is not None
    ]


def _normalize_evaluation_value(value: Any) -> str:
    if isinstance(value, list):
        return " | ".join(sorted(_normalize_evaluation_value(item) for item in value))
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str)
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _flatten_evaluation_output(value: Any, prefix: str = "") -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {prefix: value} if prefix else {}
    flattened: Dict[str, Any] = {}
    for key, child in value.items():
        if key in {"steps", "classification_path", "notes"}:
            continue
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, list) and any(isinstance(item, dict) for item in child):
            for index, item in enumerate(child):
                flattened.update(_flatten_evaluation_output(item, f"{path}[{index}]"))
        elif isinstance(child, dict):
            flattened.update(_flatten_evaluation_output(child, path))
        else:
            flattened[path] = child
    return flattened


def field_accuracy(reference: Any, candidate: Any) -> Optional[float]:
    """Return field-level accuracy using the same comparison rules as the UI."""
    if not isinstance(reference, dict) or not isinstance(candidate, dict):
        return None
    expected = _flatten_evaluation_output(reference)
    if not expected:
        return None
    actual = _flatten_evaluation_output(candidate)
    matches = sum(
        _normalize_evaluation_value(expected[field])
        == _normalize_evaluation_value(actual.get(field))
        for field in expected
    )
    return matches / len(expected) * 100


def build_vision_rankings(
    latest_by_case_model: Dict[tuple[str, str], ModelEvaluationRun],
    references: Dict[str, Dict[str, Any]],
    objectives_by_case: Dict[str, str],
    allowed_model_keys: Optional[set[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Aggregate latest-run accuracy and cost independently for RX and lien."""
    buckets: Dict[tuple[str, str], Dict[str, Any]] = {}
    for (case_id, model_key), run in latest_by_case_model.items():
        if allowed_model_keys is not None and model_key not in allowed_model_keys:
            continue
        objective = objectives_by_case.get(case_id) or run.objective
        if objective not in OBJECTIVES:
            continue
        bucket = buckets.setdefault(
            (objective, model_key),
            {
                "model_key": model_key,
                "provider": run.provider,
                "model": run.model,
                "attempted_cases": 0,
                "completed_cases": 0,
                "scored_cases": 0,
                "accuracy_total": 0.0,
                "cost_total_usd": 0.0,
                "pages_total": 0,
            },
        )
        bucket["attempted_cases"] += 1
        bucket["cost_total_usd"] += float(run.cost_usd or 0)
        pages_sent = int((getattr(run, "request_metadata", None) or {}).get("pages_sent") or 0)
        bucket["pages_total"] += pages_sent
        output_incomplete = isinstance(run.output, dict) and bool(run.output.get("parse_error"))
        if run.status != "completed" or output_incomplete or not isinstance(run.output, dict):
            continue
        bucket["completed_cases"] += 1
        accuracy = field_accuracy(references.get(case_id), run.output)
        if accuracy is not None:
            bucket["scored_cases"] += 1
            bucket["accuracy_total"] += accuracy

    rankings: Dict[str, List[Dict[str, Any]]] = {objective: [] for objective in OBJECTIVES}
    for (objective, _), bucket in buckets.items():
        attempted = bucket.pop("attempted_cases")
        completed = bucket.pop("completed_cases")
        scored = bucket.pop("scored_cases")
        accuracy_total = bucket.pop("accuracy_total")
        cost_total = bucket.pop("cost_total_usd")
        pages_total = bucket.pop("pages_total")
        rankings[objective].append(
            {
                **bucket,
                "attempted_cases": attempted,
                "completed_cases": completed,
                "scored_cases": scored,
                "average_accuracy": round(accuracy_total / scored, 2) if scored else None,
                "average_cost_usd": round(cost_total / attempted, 8) if attempted else None,
                "average_cost_per_page_usd": round(cost_total / pages_total, 8) if pages_total else None,
                "completion_rate": round(completed / attempted * 100, 2) if attempted else 0,
            }
        )
    for rows in rankings.values():
        rows.sort(
            key=lambda row: (
                -(row["average_accuracy"] if row["average_accuracy"] is not None else -1),
                row["average_cost_usd"] if row["average_cost_usd"] is not None else float("inf"),
            )
        )
    return rankings


async def get_vision_model_rankings(
    db: AsyncSession,
    allowed_model_keys: Optional[set[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build rankings from every persisted vision evaluation case."""
    run_result = await db.execute(
        select(ModelEvaluationRun)
        .where(ModelEvaluationRun.case_type == "vision")
        .order_by(ModelEvaluationRun.created_at.desc())
    )
    latest_by_case_model: Dict[tuple[str, str], ModelEvaluationRun] = {}
    objectives_by_case: Dict[str, str] = {}
    for run in run_result.scalars().all():
        latest_by_case_model.setdefault((run.case_id, run.model_key), run)
        if run.objective in OBJECTIVES:
            objectives_by_case[run.case_id] = run.objective

    if not latest_by_case_model:
        return {objective: [] for objective in OBJECTIVES}

    case_ids = list(objectives_by_case)
    review_result = await db.execute(
        select(ModelEvaluationCaseReview).where(
            ModelEvaluationCaseReview.case_type == "vision",
            ModelEvaluationCaseReview.case_id.in_(case_ids),
        )
    )
    references = {
        review.case_id: review.reference_output
        for review in review_result.scalars().all()
        if isinstance(review.reference_output, dict) and review.reference_output
    }
    for case_id in case_ids:
        if case_id in references:
            continue
        sol_run = latest_by_case_model.get((case_id, "openai:gpt-5.6-sol"))
        if sol_run and isinstance(sol_run.output, dict) and sol_run.output:
            references[case_id] = sol_run.output
    return build_vision_rankings(
        latest_by_case_model,
        references,
        objectives_by_case,
        allowed_model_keys,
    )


def _document_data(item: Dict[str, Any]) -> Dict[str, Any]:
    analysis = item.get("document_analysis") or {}
    data = analysis.get("data") or {}
    return data if isinstance(data, dict) else {}


def _document_type(item: Dict[str, Any]) -> str:
    data = _document_data(item)
    return str(data.get("document_type") or item.get("document_type") or "unknown").lower()


def classify_vision_objective(item: Dict[str, Any]) -> Optional[str]:
    """Map a stored OCR result into one benchmark objective."""
    document_type = _document_type(item)
    if document_type == "rx":
        return "rx"
    if document_type == "lien" or item.get("enhanced_lien_processing"):
        return "lien"
    return None


def _safe_current_output(item: Dict[str, Any], objective: str) -> Dict[str, Any]:
    data = _document_data(item)
    output: Dict[str, Any] = {
        "document_type": _document_type(item),
        "confidence": data.get("confidence"),
    }
    if objective == "rx":
        credentials = item.get("provider_credential_analysis") or {}
        output.update(
            {
                "patient_id": data.get("patient_id") or item.get("patient_id"),
                "provider_name": credentials.get("provider_name"),
                "provider_credentials": credentials.get("normalized_credentials"),
                "description": data.get("description"),
            }
        )
    else:
        enhanced = item.get("enhanced_lien_processing") or {}
        output.update(
            {
                "patient_id": data.get("patient_id") or item.get("patient_id"),
                "lien_type": data.get("lien_type"),
                "signature_type": data.get("LienSignatureType"),
                "barcode_found": data.get("barcode_found"),
                "total_splits": enhanced.get("total_splits"),
                "unreadable_barcode_pages": enhanced.get("unreadable_barcode_pages"),
            }
        )
    return {key: value for key, value in output.items() if value not in (None, "", [])}


def _content_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".tif", ".tiff")):
        return "image/tiff"
    return "application/octet-stream"


async def build_vision_evaluation(
    db: AsyncSession,
    *,
    examples_per_objective: int = 10,
    allowed_model_keys: Optional[set[str]] = None,
) -> Dict[str, Any]:
    rankings = await get_vision_model_rankings(db, allowed_model_keys)
    evaluated_result = await db.execute(
        select(
            ModelEvaluationRun.case_id,
            func.max(ModelEvaluationRun.created_at).label("latest_run_at"),
        )
        .where(ModelEvaluationRun.case_type == "vision")
        .group_by(ModelEvaluationRun.case_id)
    )
    evaluated_at = {case_id: latest_run_at for case_id, latest_run_at in evaluated_result.all()}
    result = await db.execute(
        select(Email)
        .where(Email.ocr_results.isnot(None))
        .order_by(Email.created_at.desc())
        .limit(3000)
    )
    selected: Dict[str, List[Dict[str, Any]]] = {key: [] for key in OBJECTIVES}

    for email in result.scalars().all():
        for index, item in enumerate(email.ocr_results or []):
            if not isinstance(item, dict) or not item.get("attachment_url"):
                continue
            objective = classify_vision_objective(item)
            if not objective:
                continue
            attachment_key = str(item.get("attachment_url"))
            filename = str(item.get("filename") or f"document-{index + 1}")
            pages = item.get("pages") or []
            example_id = f"{email.id}:{index}"
            selected[objective].append(
                {
                    "example_id": example_id,
                    "email_id": str(email.id),
                    "conversation_id": email.front_conversation_id,
                    "objective": objective,
                    "filename": filename,
                    "content_type": _content_type(filename),
                    "document_type": _document_type(item),
                    "created_at": email.created_at,
                    "page_count": len(pages),
                    "has_extracted_text": bool(
                        item.get("extracted_text") or pages or item.get("text_content")
                    ),
                    "current_output": _safe_current_output(item, objective),
                    "preview_url": f"/api/v1/model-evaluation/vision/{email.id}/{index}/content",
                    "ground_truth_status": "unreviewed",
                    "_attachment_key": attachment_key,
                }
            )

    for objective, candidates in selected.items():
        candidates.sort(
            key=lambda example: (
                example["example_id"] in evaluated_at,
                evaluated_at.get(example["example_id"])
                or example.get("created_at")
                or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        unique: List[Dict[str, Any]] = []
        seen_attachments: set[str] = set()
        for example in candidates:
            attachment_key = example.pop("_attachment_key")
            if attachment_key in seen_attachments:
                continue
            seen_attachments.add(attachment_key)
            unique.append(example)
            if len(unique) >= examples_per_objective:
                break
        selected[objective] = unique

    examples = [example for objective in OBJECTIVES for example in selected[objective]]
    case_ids = [example["example_id"] for example in examples]
    summaries: Dict[str, Dict[str, Any]] = {
        case_id: {
            "total_runs": 0,
            "evaluated_models": 0,
            "reviewed_models": 0,
            "completed_models": 0,
            "problem_models": 0,
            "preferred_model": None,
            "minimum_cost_usd": None,
            "maximum_cost_usd": None,
            "latest_run_at": None,
        }
        for case_id in case_ids
    }
    sol_baseline_cases: set[str] = set()
    if case_ids:
        run_result = await db.execute(
            select(ModelEvaluationRun)
            .where(
                ModelEvaluationRun.case_type == "vision",
                ModelEvaluationRun.case_id.in_(case_ids),
            )
            .order_by(ModelEvaluationRun.created_at.desc())
        )
        latest_by_case_model: Dict[tuple[str, str], ModelEvaluationRun] = {}
        for run in run_result.scalars().all():
            summary = summaries[run.case_id]
            summary["total_runs"] += 1
            key = (run.case_id, run.model_key)
            if key not in latest_by_case_model:
                latest_by_case_model[key] = run

        for (case_id, _), run in latest_by_case_model.items():
            summary = summaries[case_id]
            summary["evaluated_models"] += 1
            if run.human_rating:
                summary["reviewed_models"] += 1
            output_incomplete = isinstance(run.output, dict) and bool(run.output.get("parse_error"))
            if run.status == "completed" and not output_incomplete:
                summary["completed_models"] += 1
                if run.model_key == "openai:gpt-5.6-sol" and run.output:
                    sol_baseline_cases.add(case_id)
            else:
                summary["problem_models"] += 1
            if run.is_preferred:
                summary["preferred_model"] = run.model
            cost = float(run.cost_usd or 0)
            if summary["minimum_cost_usd"] is None or cost < summary["minimum_cost_usd"]:
                summary["minimum_cost_usd"] = cost
            if summary["maximum_cost_usd"] is None or cost > summary["maximum_cost_usd"]:
                summary["maximum_cost_usd"] = cost
            if summary["latest_run_at"] is None or run.created_at > summary["latest_run_at"]:
                summary["latest_run_at"] = run.created_at

        review_result = await db.execute(
            select(ModelEvaluationCaseReview).where(
                ModelEvaluationCaseReview.case_type == "vision",
                ModelEvaluationCaseReview.case_id.in_(case_ids),
            )
        )
        reviews = list(review_result.scalars().all())
        reviewed_cases = {review.case_id for review in reviews if review.reference_output}
        for example in examples:
            if example["example_id"] in reviewed_cases:
                example["ground_truth_status"] = "reviewed"
            elif example["example_id"] in sol_baseline_cases:
                example["ground_truth_status"] = "sol_baseline"
            example["evaluation_summary"] = summaries[example["example_id"]]

    return {
        "examples_per_objective": examples_per_objective,
        "generated_at": datetime.now(timezone.utc),
        "coverage": [
            {
                "objective": objective,
                "requested": examples_per_objective,
                "found": len(selected[objective]),
                **metadata,
            }
            for objective, metadata in OBJECTIVES.items()
        ],
        "examples": examples,
        "rankings": rankings,
    }


async def get_vision_document(
    db: AsyncSession,
    *,
    email_id: str,
    result_index: int,
) -> tuple[bytes, str, str]:
    try:
        email_key = UUID(email_id)
    except ValueError as exc:
        raise LookupError("Vision evaluation document not found") from exc
    email = await db.get(Email, email_key)
    if (
        not email
        or not email.ocr_results
        or result_index < 0
        or result_index >= len(email.ocr_results)
    ):
        raise LookupError("Vision evaluation document not found")
    item = email.ocr_results[result_index]
    if not isinstance(item, dict) or not item.get("attachment_url"):
        raise LookupError("Vision evaluation attachment URL not found")
    headers = {"Authorization": f"Bearer {settings.FRONT_AUTH_TOKEN}"}
    async with httpx.AsyncClient(verify=False, follow_redirects=True, timeout=60.0) as client:
        response = await client.get(item["attachment_url"], headers=headers)
        response.raise_for_status()
    filename = re.sub(r"[^A-Za-z0-9._ -]", "_", str(item.get("filename") or "document"))
    content_type = response.headers.get("content-type") or _content_type(filename)
    return response.content, content_type, filename
