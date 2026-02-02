"""API Endpoints for viewing email processing traces."""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, distinct
import httpx

from app.services.trace_service import get_conversation_traces, get_conversation_traces_async
from app.crud.sync import processing_trace as trace_crud_sync
from app.db.session import SessionLocal
from app.api.api_v1.dependencies import check_authenticated
from app.models.classification_trace import ClassificationTrace
from app.models.processing_trace import EmailProcessingTrace
from app.models.email import Email
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Setup templates
templates = Jinja2Templates(directory="app/templates")


@router.get("/traces", response_class=HTMLResponse, name="view_traces_ui")
async def view_traces_ui(
    request: Request,
    conversation_id: Optional[str] = Query(None),
    is_authenticated: bool = Depends(check_authenticated)
):
    """Display the UI for viewing email processing traces."""
    if not is_authenticated:
        return RedirectResponse(url="/login", status_code=303)
    try:
        traces = []
        summary = {}
        
        if conversation_id:
            # Get traces for the specific conversation
            traces = get_conversation_traces(conversation_id)
            
            # Get summary data
            if traces:
                db = SessionLocal()
                try:
                    summary = trace_crud_sync.get_processing_summary(db, front_conversation_id=conversation_id)
                finally:
                    db.close()
            
            logger.info(f"Fetched {len(traces)} traces for conversation {conversation_id}")
        
        # Convert traces to dict format for template
        traces_data = []
        for trace in traces:
            trace_dict = {
                "id": str(trace.id),
                "step_name": trace.step_name,
                "step_type": trace.step_type,
                "step_order": trace.step_order,
                "status": trace.status,
                "started_at": trace.started_at.isoformat() if trace.started_at else None,
                "completed_at": trace.completed_at.isoformat() if trace.completed_at else None,
                "duration_ms": trace.duration_ms,
                "input_data": trace.input_data,
                "output_data": trace.output_data,
                "error_data": trace.error_data,
                "trace_metadata": trace.trace_metadata,
                "task_id": trace.task_id,
                "parent_trace_id": str(trace.parent_trace_id) if trace.parent_trace_id else None
            }
            traces_data.append(trace_dict)
        
        return templates.TemplateResponse(
            "trace_viewer.html",
            {
                "request": request,
                "conversation_id": conversation_id or "",
                "traces": traces_data,
                "summary": summary,
                "total_traces": len(traces_data),
                "has_errors": any(t["status"] == "failed" for t in traces_data),
                "total_duration": summary.get("total_duration_ms", 0) if summary else 0
            }
        )
    except Exception as e:
        logger.error(f"Error fetching traces for UI: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<html><body><h1>Error loading traces: {e}</h1></body></html>", 
            status_code=500
        )


@router.get("/traces/api/list")
async def list_traces_api(conversation_id: str = Query(..., description="Front conversation ID")):
    """API endpoint to get traces for a conversation as JSON."""
    try:
        traces = get_conversation_traces(conversation_id)
        
        # Convert to JSON-serializable format
        traces_data = []
        for trace in traces:
            trace_dict = {
                "id": str(trace.id),
                "front_conversation_id": trace.front_conversation_id,
                "email_id": str(trace.email_id) if trace.email_id else None,
                "step_name": trace.step_name,
                "step_type": trace.step_type,
                "step_order": trace.step_order,
                "status": trace.status,
                "started_at": trace.started_at.isoformat() if trace.started_at else None,
                "completed_at": trace.completed_at.isoformat() if trace.completed_at else None,
                "duration_ms": trace.duration_ms,
                "input_data": trace.input_data,
                "output_data": trace.output_data,
                "error_data": trace.error_data,
                "trace_metadata": trace.trace_metadata,
                "task_id": trace.task_id,
                "parent_trace_id": str(trace.parent_trace_id) if trace.parent_trace_id else None,
                "created_at": trace.created_at.isoformat() if trace.created_at else None
            }
            traces_data.append(trace_dict)
        
        return JSONResponse(content={
            "conversation_id": conversation_id,
            "traces": traces_data,
            "total_count": len(traces_data)
        })
        
    except Exception as e:
        logger.error(f"Error fetching traces via API for {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching traces: {str(e)}")


@router.get("/traces/api/summary")
async def get_trace_summary_api(conversation_id: str = Query(..., description="Front conversation ID")):
    """API endpoint to get processing summary for a conversation."""
    try:
        db = SessionLocal()
        try:
            summary = trace_crud_sync.get_processing_summary(db, front_conversation_id=conversation_id)
            
            # Convert datetime objects to ISO strings
            if summary.get("first_step_at"):
                summary["first_step_at"] = summary["first_step_at"].isoformat()
            if summary.get("last_step_at"):
                summary["last_step_at"] = summary["last_step_at"].isoformat()
            
            return JSONResponse(content={
                "conversation_id": conversation_id,
                "summary": summary
            })
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error fetching trace summary for {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching summary: {str(e)}")


@router.get("/traces/api/search")
async def search_traces_api(
    step_name: Optional[str] = Query(None, description="Step name to search for"),
    status: Optional[str] = Query(None, description="Status to filter by"),
    limit: int = Query(100, description="Maximum number of results")
):
    """API endpoint to search traces by criteria."""
    try:
        db = SessionLocal()
        try:
            if step_name:
                traces = trace_crud_sync.get_by_step_name(db, step_name=step_name, limit=limit)
            elif status == "failed":
                traces = trace_crud_sync.get_failed_traces(db, limit=limit)
            else:
                # Return recent traces if no specific criteria
                traces = []
            
            # Convert to JSON format
            traces_data = []
            for trace in traces:
                trace_dict = {
                    "id": str(trace.id),
                    "front_conversation_id": trace.front_conversation_id,
                    "step_name": trace.step_name,
                    "step_type": trace.step_type,
                    "status": trace.status,
                    "started_at": trace.started_at.isoformat() if trace.started_at else None,
                    "duration_ms": trace.duration_ms,
                    "error_data": trace.error_data if trace.status == "failed" else None
                }
                traces_data.append(trace_dict)
            
            return JSONResponse(content={
                "traces": traces_data,
                "total_count": len(traces_data),
                "search_criteria": {
                    "step_name": step_name,
                    "status": status,
                    "limit": limit
                }
            })
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Error searching traces: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error searching traces: {str(e)}")


# ==================== CLASSIFICATION TRACE ENDPOINTS ====================
# Note: The HTML UI has been moved to the Next.js frontend at /settings/classification-traces
# Only JSON API endpoints remain here.

@router.get("/classification-traces/api/list")
async def list_classification_traces_api(
    conversation_id: str = Query(..., description="Front conversation ID"),
    is_authenticated: bool = Depends(check_authenticated)
):
    """API endpoint to get classification traces for a conversation as JSON."""
    if not is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db = SessionLocal()
        try:
            traces = db.query(ClassificationTrace).filter(
                ClassificationTrace.front_conversation_id == conversation_id
            ).order_by(ClassificationTrace.step_order).all()

            # Convert to JSON-serializable format
            traces_data = []
            for trace in traces:
                trace_dict = {
                    "id": str(trace.id),
                    "front_conversation_id": trace.front_conversation_id,
                    "email_id": str(trace.email_id) if trace.email_id else None,
                    "step_name": trace.step_name,
                    "step_order": trace.step_order,
                    "classification_path": trace.classification_path,
                    "llm_model": trace.llm_model,
                    "prompt_template": trace.prompt_template,
                    "full_prompt": trace.full_prompt,
                    "llm_response": trace.llm_response,
                    "chosen_option": trace.chosen_option,
                    "conversation_summary": trace.conversation_summary,
                    "classification_reason": trace.classification_reason,
                    "email_format": trace.email_format,
                    "message_count": trace.message_count,
                    "started_at": trace.started_at.isoformat() if trace.started_at else None,
                    "completed_at": trace.completed_at.isoformat() if trace.completed_at else None,
                    "duration_ms": trace.duration_ms,
                    "prompt_tokens": trace.prompt_tokens,
                    "completion_tokens": trace.completion_tokens,
                    "total_tokens": trace.total_tokens,
                    "document_analysis": trace.document_analysis,
                    "created_at": trace.created_at.isoformat() if trace.created_at else None
                }
                traces_data.append(trace_dict)

            return JSONResponse(content={
                "conversation_id": conversation_id,
                "traces": traces_data,
                "total_count": len(traces_data),
                "total_tokens": sum(t["total_tokens"] for t in traces_data if t["total_tokens"]),
                "total_duration_ms": sum(t["duration_ms"] for t in traces_data if t["duration_ms"])
            })
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error fetching classification traces via API for {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching classification traces: {str(e)}")


@router.get("/classification-traces/api/recent-conversations")
async def list_recent_conversations_api(
    limit: int = Query(50, description="Maximum number of conversations to return"),
    is_authenticated: bool = Depends(check_authenticated)
):
    """API endpoint to get recent conversations that have traces."""
    if not is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db = SessionLocal()
        try:
            # Get recent conversations from ClassificationTrace
            classification_conversations = db.query(
                ClassificationTrace.front_conversation_id,
                func.max(ClassificationTrace.created_at).label("last_trace_at"),
                func.count(ClassificationTrace.id).label("trace_count"),
                func.sum(ClassificationTrace.total_tokens).label("total_tokens")
            ).group_by(
                ClassificationTrace.front_conversation_id
            ).order_by(
                desc("last_trace_at")
            ).limit(limit).all()

            # Get recent conversations from EmailProcessingTrace (archival)
            archival_conversations = db.query(
                EmailProcessingTrace.front_conversation_id,
                func.max(EmailProcessingTrace.created_at).label("last_trace_at"),
                func.count(EmailProcessingTrace.id).label("trace_count")
            ).filter(
                EmailProcessingTrace.step_name.like("archive_%")
            ).group_by(
                EmailProcessingTrace.front_conversation_id
            ).order_by(
                desc("last_trace_at")
            ).limit(limit).all()

            # Merge and deduplicate conversations
            conversations_map = {}

            for conv in classification_conversations:
                conv_id = conv.front_conversation_id
                if conv_id not in conversations_map:
                    conversations_map[conv_id] = {
                        "conversation_id": conv_id,
                        "last_trace_at": conv.last_trace_at,
                        "classification_traces": conv.trace_count or 0,
                        "archival_traces": 0,
                        "total_tokens": conv.total_tokens or 0
                    }
                else:
                    conversations_map[conv_id]["classification_traces"] = conv.trace_count or 0
                    conversations_map[conv_id]["total_tokens"] = conv.total_tokens or 0
                    if conv.last_trace_at and (not conversations_map[conv_id]["last_trace_at"] or conv.last_trace_at > conversations_map[conv_id]["last_trace_at"]):
                        conversations_map[conv_id]["last_trace_at"] = conv.last_trace_at

            for conv in archival_conversations:
                conv_id = conv.front_conversation_id
                if conv_id not in conversations_map:
                    conversations_map[conv_id] = {
                        "conversation_id": conv_id,
                        "last_trace_at": conv.last_trace_at,
                        "classification_traces": 0,
                        "archival_traces": conv.trace_count or 0,
                        "total_tokens": 0
                    }
                else:
                    conversations_map[conv_id]["archival_traces"] = conv.trace_count or 0
                    if conv.last_trace_at and (not conversations_map[conv_id]["last_trace_at"] or conv.last_trace_at > conversations_map[conv_id]["last_trace_at"]):
                        conversations_map[conv_id]["last_trace_at"] = conv.last_trace_at

            # Convert to list and sort by last_trace_at
            conversations_list = list(conversations_map.values())
            conversations_list.sort(key=lambda x: x["last_trace_at"] or datetime.min, reverse=True)
            conversations_list = conversations_list[:limit]

            # Convert datetime to ISO format
            for conv in conversations_list:
                if conv["last_trace_at"]:
                    conv["last_trace_at"] = conv["last_trace_at"].isoformat()

            return JSONResponse(content={
                "conversations": conversations_list,
                "total_count": len(conversations_list)
            })
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error fetching recent conversations: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching recent conversations: {str(e)}")


@router.get("/classification-traces/api/full")
async def get_full_classification_traces_api(
    conversation_id: str = Query(..., description="Front conversation ID"),
    is_authenticated: bool = Depends(check_authenticated)
):
    """API endpoint to get ALL traces (classification, archival, document processing, lien validation) for a conversation."""
    if not is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db = SessionLocal()
        try:
            # Get classification traces
            classification_traces = db.query(ClassificationTrace).filter(
                ClassificationTrace.front_conversation_id == conversation_id
            ).order_by(ClassificationTrace.step_order).all()

            # Get archival traces from EmailProcessingTrace
            archival_traces = db.query(EmailProcessingTrace).filter(
                EmailProcessingTrace.front_conversation_id == conversation_id,
                EmailProcessingTrace.step_name.like("archive_%")
            ).order_by(EmailProcessingTrace.step_order).all()

            # Get document processing results from Email.ocr_results and lien_modification_results
            document_processing_results = []
            lien_modification_results = []
            email = db.query(Email).filter(
                Email.front_conversation_id == conversation_id
            ).first()
            if email:
                if email.ocr_results:
                    document_processing_results = email.ocr_results
                if email.lien_modification_results:
                    lien_modification_results = email.lien_modification_results

            # Build unified traces list
            traces_data = []

            # Add document processing traces first (step_order 1-50)
            for idx, doc_result in enumerate(document_processing_results):
                doc_analysis = doc_result.get("document_analysis", {})
                doc_data = doc_analysis.get("data", {}) if doc_analysis.get("success") else {}
                enhanced_lien = doc_result.get("enhanced_lien_processing", {})

                trace_dict = {
                    "id": f"doc_{idx}",
                    "trace_type": "document_processing",
                    "step_name": f"Document {idx + 1}: {doc_result.get('filename', 'Unknown')}",
                    "step_order": idx + 1,
                    "classification_path": None,
                    "llm_model": doc_result.get("provider_info", {}).get("analysis_provider", "unknown"),
                    "prompt_template": None,
                    "full_prompt": None,
                    "llm_response": None,
                    "chosen_option": doc_data.get("document_type", doc_result.get("document_type", "unknown")),
                    "conversation_summary": doc_data.get("description"),
                    "classification_reason": f"Confidence: {doc_data.get('confidence', 'N/A')}",
                    "email_format": doc_result.get("detected_type", doc_result.get("document_type")),
                    "message_count": None,
                    "started_at": None,
                    "completed_at": None,
                    "duration_ms": None,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "document_analysis": {
                        "filename": doc_result.get("filename"),
                        "file_size": doc_result.get("file_size"),
                        "document_type": doc_data.get("document_type"),
                        "description": doc_data.get("description"),
                        "patient_id": doc_data.get("patient_id"),
                        "confidence": doc_data.get("confidence"),
                        "detected_type": doc_result.get("detected_type"),
                        "processing_status": doc_result.get("processing_status"),
                        "enhanced_lien_analysis": doc_data.get("enhanced_lien_analysis"),
                        "enhanced_lien_processing": enhanced_lien if enhanced_lien else None
                    },
                    "lien_validation": None,
                    "input_data": None,
                    "output_data": doc_result,
                    "error_data": None
                }
                traces_data.append(trace_dict)

            # Add lien validation traces (step_order 25-49)
            lien_trace_order = 25

            for idx, doc_result in enumerate(document_processing_results):
                enhanced_lien = doc_result.get("enhanced_lien_processing", {})
                if not enhanced_lien:
                    continue

                filename = doc_result.get("filename", f"Document {idx + 1}")

                # Signature Detection Trace
                signature_data = enhanced_lien.get("signature_detection", {})
                if signature_data:
                    sig_type = signature_data.get("lien_signature_type", "UNKNOWN")
                    patient_sig = signature_data.get("patient_signature_present", False)
                    attorney_sig = signature_data.get("attorney_signature_present", False)
                    placement_valid = signature_data.get("placement_valid", True)
                    placement_issues = signature_data.get("placement_issues", [])

                    trace_dict = {
                        "id": f"sig_{idx}",
                        "trace_type": "lien_validation",
                        "step_name": f"Signature Check: {filename}",
                        "step_order": lien_trace_order,
                        "classification_path": None,
                        "llm_model": "openai-vision",
                        "prompt_template": None,
                        "full_prompt": None,
                        "llm_response": None,
                        "chosen_option": sig_type,
                        "conversation_summary": signature_data.get("signature_analysis"),
                        "classification_reason": f"Patient: {'Y' if patient_sig else 'N'}, Attorney: {'Y' if attorney_sig else 'N'}, Placement: {'Valid' if placement_valid else 'Issues: ' + ', '.join(placement_issues)}",
                        "email_format": "signature_detection",
                        "message_count": None,
                        "started_at": None,
                        "completed_at": None,
                        "duration_ms": None,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "document_analysis": None,
                        "lien_validation": {
                            "check_type": "signature",
                            "filename": filename,
                            "patient_signature_present": patient_sig,
                            "attorney_signature_present": attorney_sig,
                            "patient_signature_inside_box": signature_data.get("patient_signature_inside_box"),
                            "attorney_signature_inside_box": signature_data.get("attorney_signature_inside_box"),
                            "lien_signature_type": sig_type,
                            "placement_valid": placement_valid,
                            "placement_issues": placement_issues,
                            "signature_analysis": signature_data.get("signature_analysis"),
                            "raw_data": signature_data
                        },
                        "input_data": None,
                        "output_data": signature_data,
                        "error_data": None
                    }
                    traces_data.append(trace_dict)
                    lien_trace_order += 1

                # Barcode Detection Trace
                barcode_data = enhanced_lien.get("barcode_detection", {})
                if barcode_data:
                    barcode_found = barcode_data.get("barcode_found", False)
                    combined = barcode_data.get("combined_data", {})
                    patient_ids = combined.get("PatientIDs", [combined.get("PatientID")]) if combined.get("PatientID") or combined.get("PatientIDs") else []
                    lien_types = combined.get("LienTypes", [])

                    trace_dict = {
                        "id": f"barcode_{idx}",
                        "trace_type": "lien_validation",
                        "step_name": f"Barcode Detection: {filename}",
                        "step_order": lien_trace_order,
                        "classification_path": None,
                        "llm_model": "pyzbar",
                        "prompt_template": None,
                        "full_prompt": None,
                        "llm_response": None,
                        "chosen_option": "Found" if barcode_found else "Not Found",
                        "conversation_summary": f"Patient IDs: {', '.join(filter(None, patient_ids)) or 'None'}, Lien Types: {', '.join(lien_types) or 'None'}",
                        "classification_reason": f"Barcode {'detected' if barcode_found else 'not detected'} in document",
                        "email_format": "barcode_detection",
                        "message_count": None,
                        "started_at": None,
                        "completed_at": None,
                        "duration_ms": None,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "document_analysis": None,
                        "lien_validation": {
                            "check_type": "barcode",
                            "filename": filename,
                            "barcode_found": barcode_found,
                            "patient_ids": patient_ids,
                            "lien_types": lien_types,
                            "referrer_id": combined.get("ReferrerID"),
                            "raw_barcode_value": barcode_data.get("raw_barcode_value"),
                            "all_barcodes": barcode_data.get("all_barcodes_parsed", []),
                            "raw_data": barcode_data
                        },
                        "input_data": None,
                        "output_data": barcode_data,
                        "error_data": None
                    }
                    traces_data.append(trace_dict)
                    lien_trace_order += 1

                # Cover Letter Detection Trace
                cover_letter_data = enhanced_lien.get("cover_letter_analysis", {})
                if cover_letter_data:
                    is_cover = cover_letter_data.get("is_cover_letter", False)
                    has_conditional = cover_letter_data.get("has_conditional_language", False)
                    conditional_phrases = cover_letter_data.get("conditional_phrases_found", [])

                    trace_dict = {
                        "id": f"cover_{idx}",
                        "trace_type": "lien_validation",
                        "step_name": f"Cover Letter Check: {filename}",
                        "step_order": lien_trace_order,
                        "classification_path": None,
                        "llm_model": "openai-vision",
                        "prompt_template": None,
                        "full_prompt": None,
                        "llm_response": None,
                        "chosen_option": cover_letter_data.get("page_classification", "LIEN_CORE"),
                        "conversation_summary": cover_letter_data.get("explanation"),
                        "classification_reason": f"Cover Letter: {'Yes' if is_cover else 'No'}, Conditional Language: {'Yes' if has_conditional else 'None'}",
                        "email_format": "cover_letter_detection",
                        "message_count": None,
                        "started_at": None,
                        "completed_at": None,
                        "duration_ms": None,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "document_analysis": None,
                        "lien_validation": {
                            "check_type": "cover_letter",
                            "filename": filename,
                            "is_cover_letter": is_cover,
                            "cover_letter_confidence": cover_letter_data.get("cover_letter_confidence"),
                            "has_conditional_language": has_conditional,
                            "conditional_language_confidence": cover_letter_data.get("conditional_language_confidence"),
                            "conditional_phrases_found": conditional_phrases,
                            "page_classification": cover_letter_data.get("page_classification"),
                            "explanation": cover_letter_data.get("explanation"),
                            "raw_data": cover_letter_data
                        },
                        "input_data": None,
                        "output_data": cover_letter_data,
                        "error_data": None
                    }
                    traces_data.append(trace_dict)
                    lien_trace_order += 1

            # Add lien modification/strikethrough traces from lien_modification_results
            for idx, mod_result in enumerate(lien_modification_results):
                filename = mod_result.get("attachment_url", "").split("/")[-1] or f"Attachment {idx + 1}"
                strikethrough_data = mod_result.get("strikethrough_data", {})

                # Document Quality / Blurry Image Detection Trace
                doc_quality = strikethrough_data.get("document_quality") or mod_result.get("document_quality")
                if doc_quality:
                    quality_explanation = strikethrough_data.get("quality_explanation", "")
                    quality_by_page = strikethrough_data.get("quality_by_page", [])

                    trace_dict = {
                        "id": f"quality_{idx}",
                        "trace_type": "lien_validation",
                        "step_name": f"Image Quality Check: {filename}",
                        "step_order": lien_trace_order,
                        "classification_path": None,
                        "llm_model": "openai-vision",
                        "prompt_template": None,
                        "full_prompt": None,
                        "llm_response": None,
                        "chosen_option": doc_quality,
                        "conversation_summary": quality_explanation,
                        "classification_reason": f"Document quality: {doc_quality}" + (f" ({len(quality_by_page)} pages analyzed)" if quality_by_page else ""),
                        "email_format": "quality_detection",
                        "message_count": None,
                        "started_at": None,
                        "completed_at": None,
                        "duration_ms": None,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "document_analysis": None,
                        "lien_validation": {
                            "check_type": "image_quality",
                            "filename": filename,
                            "document_quality": doc_quality,
                            "quality_explanation": quality_explanation,
                            "quality_by_page": quality_by_page,
                            "overall_quality": strikethrough_data.get("overall_quality", doc_quality),
                            "raw_data": {"document_quality": doc_quality, "quality_explanation": quality_explanation, "quality_by_page": quality_by_page}
                        },
                        "input_data": None,
                        "output_data": {"document_quality": doc_quality, "quality_explanation": quality_explanation, "quality_by_page": quality_by_page},
                        "error_data": None
                    }
                    traces_data.append(trace_dict)
                    lien_trace_order += 1

                # Strikethrough/Modification Detection Trace
                strikethrough_detected = strikethrough_data.get("strikethrough_detected", False) or mod_result.get("modifications_detected", False)
                strikethrough_instances = strikethrough_data.get("strikethrough_instances", [])

                if strikethrough_data or mod_result.get("modifications_detected") is not None:
                    summary = strikethrough_data.get("summary", {})
                    total_instances = summary.get("total_strikethrough_instances", len(strikethrough_instances))

                    trace_dict = {
                        "id": f"strike_{idx}",
                        "trace_type": "lien_validation",
                        "step_name": f"Modification Detection: {filename}",
                        "step_order": lien_trace_order,
                        "classification_path": None,
                        "llm_model": "openai-vision",
                        "prompt_template": None,
                        "full_prompt": None,
                        "llm_response": None,
                        "chosen_option": "Modifications Found" if strikethrough_detected else "No Modifications",
                        "conversation_summary": f"Found {total_instances} strikethrough instance(s)" if strikethrough_detected else "No strikethroughs or modifications detected",
                        "classification_reason": f"Strikethroughs: {total_instances}, Pages affected: {summary.get('pages_with_strikethrough', 0)}/{summary.get('total_pages', '?')}",
                        "email_format": "strikethrough_detection",
                        "message_count": None,
                        "started_at": None,
                        "completed_at": None,
                        "duration_ms": None,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "document_analysis": None,
                        "lien_validation": {
                            "check_type": "strikethrough",
                            "filename": filename,
                            "strikethrough_detected": strikethrough_detected,
                            "strikethrough_instances": strikethrough_instances,
                            "total_instances": total_instances,
                            "pages_with_strikethrough": summary.get("pages_with_strikethrough", 0),
                            "total_pages": summary.get("total_pages"),
                            "summary": summary,
                            "raw_data": strikethrough_data
                        },
                        "input_data": None,
                        "output_data": strikethrough_data,
                        "error_data": None
                    }
                    traces_data.append(trace_dict)
                    lien_trace_order += 1

            # Add archival traces (step_order 51-99)
            for trace in archival_traces:
                output = trace.output_data or {}
                decision = output.get("decision") or output.get("final_decision") or output.get("result") or trace.status

                trace_dict = {
                    "id": str(trace.id),
                    "trace_type": "archival",
                    "step_name": trace.step_name,
                    "step_order": trace.step_order,
                    "classification_path": None,
                    "llm_model": "archival_check",
                    "prompt_template": None,
                    "full_prompt": None,
                    "llm_response": None,
                    "chosen_option": decision,
                    "conversation_summary": output.get("summary"),
                    "classification_reason": output.get("reason") or (
                        f"Unresolved questions: {output.get('unresolved_questions')}"
                        if output.get("unresolved_questions") else None
                    ),
                    "email_format": trace.step_type,
                    "message_count": output.get("message_count"),
                    "started_at": trace.started_at.isoformat() if trace.started_at else None,
                    "completed_at": trace.completed_at.isoformat() if trace.completed_at else None,
                    "duration_ms": trace.duration_ms,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "document_analysis": None,
                    "lien_validation": None,
                    "input_data": trace.input_data,
                    "output_data": trace.output_data,
                    "error_data": trace.error_data
                }
                traces_data.append(trace_dict)

            # Add classification traces (step_order 100+)
            for trace in classification_traces:
                trace_dict = {
                    "id": str(trace.id),
                    "trace_type": "classification",
                    "step_name": trace.step_name,
                    "step_order": trace.step_order + 100,
                    "classification_path": trace.classification_path,
                    "llm_model": trace.llm_model,
                    "prompt_template": trace.prompt_template,
                    "full_prompt": trace.full_prompt,
                    "llm_response": trace.llm_response,
                    "chosen_option": trace.chosen_option,
                    "conversation_summary": trace.conversation_summary,
                    "classification_reason": trace.classification_reason,
                    "email_format": trace.email_format,
                    "message_count": trace.message_count,
                    "started_at": trace.started_at.isoformat() if trace.started_at else None,
                    "completed_at": trace.completed_at.isoformat() if trace.completed_at else None,
                    "duration_ms": trace.duration_ms,
                    "prompt_tokens": trace.prompt_tokens,
                    "completion_tokens": trace.completion_tokens,
                    "total_tokens": trace.total_tokens,
                    "document_analysis": trace.document_analysis,
                    "lien_validation": None,
                    "input_data": None,
                    "output_data": None,
                    "error_data": None
                }
                traces_data.append(trace_dict)

            # Sort by step_order
            traces_data.sort(key=lambda x: x["step_order"])

            # Calculate counts
            lien_validation_count = len([t for t in traces_data if t.get("trace_type") == "lien_validation"])

            return JSONResponse(content={
                "conversation_id": conversation_id,
                "traces": traces_data,
                "total_traces": len(traces_data),
                "document_processing_count": len(document_processing_results),
                "lien_validation_count": lien_validation_count,
                "archival_count": len(archival_traces),
                "classification_count": len(classification_traces),
                "total_duration_ms": sum(t["duration_ms"] for t in traces_data if t["duration_ms"]),
                "total_tokens": sum(t["total_tokens"] for t in traces_data if t["total_tokens"])
            })
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error fetching full traces for {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error fetching traces: {str(e)}")


@router.post("/classification-traces/api/summarize")
async def summarize_classification_traces(
    conversation_id: str = Query(..., description="Front conversation ID"),
    is_authenticated: bool = Depends(check_authenticated)
):
    """Use AI to summarize all trace data for a conversation."""
    if not is_authenticated:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        db = SessionLocal()
        try:
            # Gather trace data (reuse same logic as /full endpoint)
            classification_traces = db.query(ClassificationTrace).filter(
                ClassificationTrace.front_conversation_id == conversation_id
            ).order_by(ClassificationTrace.step_order).all()

            archival_traces = db.query(EmailProcessingTrace).filter(
                EmailProcessingTrace.front_conversation_id == conversation_id,
                EmailProcessingTrace.step_name.like("archive_%")
            ).order_by(EmailProcessingTrace.step_order).all()

            email = db.query(Email).filter(
                Email.front_conversation_id == conversation_id
            ).first()

            # Build compact trace summary (strip large fields like full_prompt)
            traces_compact = []

            # Document processing
            if email and email.ocr_results:
                for idx, doc in enumerate(email.ocr_results):
                    doc_analysis = doc.get("document_analysis", {})
                    doc_data = doc_analysis.get("data", {}) if doc_analysis.get("success") else {}
                    enhanced_lien = doc.get("enhanced_lien_processing", {})
                    traces_compact.append({
                        "type": "document_processing",
                        "step": f"Document {idx + 1}: {doc.get('filename', 'Unknown')}",
                        "document_type": doc_data.get("document_type", doc.get("document_type", "unknown")),
                        "patient_id": doc_data.get("patient_id"),
                        "confidence": doc_data.get("confidence"),
                        "description": doc_data.get("description"),
                        "processing_status": doc.get("processing_status"),
                        "signature_detection": enhanced_lien.get("signature_detection", {}).get("lien_signature_type") if enhanced_lien else None,
                        "barcode_found": enhanced_lien.get("barcode_detection", {}).get("barcode_found") if enhanced_lien else None,
                        "cover_letter": enhanced_lien.get("cover_letter_analysis", {}).get("is_cover_letter") if enhanced_lien else None,
                        "has_conditional_language": enhanced_lien.get("cover_letter_analysis", {}).get("has_conditional_language") if enhanced_lien else None,
                    })

            # Lien modification results
            if email and email.lien_modification_results:
                for idx, mod in enumerate(email.lien_modification_results):
                    strike_data = mod.get("strikethrough_data", {})
                    traces_compact.append({
                        "type": "lien_modification_check",
                        "step": f"Lien modification check: attachment {idx + 1}",
                        "strikethrough_detected": strike_data.get("strikethrough_detected", mod.get("modifications_detected", False)),
                        "document_quality": strike_data.get("document_quality") or mod.get("document_quality"),
                        "total_instances": strike_data.get("summary", {}).get("total_strikethrough_instances", 0),
                    })

            # Archival traces
            for trace in archival_traces:
                output = trace.output_data or {}
                traces_compact.append({
                    "type": "archival",
                    "step": trace.step_name,
                    "status": trace.status,
                    "decision": output.get("decision") or output.get("final_decision") or output.get("result"),
                    "reason": output.get("reason"),
                    "summary": output.get("summary"),
                    "duration_ms": trace.duration_ms,
                    "error": trace.error_data.get("error") if trace.error_data else None,
                })

            # Classification traces
            for trace in classification_traces:
                traces_compact.append({
                    "type": "classification",
                    "step": trace.step_name,
                    "classification_path": trace.classification_path,
                    "chosen_option": trace.chosen_option,
                    "classification_reason": trace.classification_reason,
                    "llm_model": trace.llm_model,
                    "duration_ms": trace.duration_ms,
                    "total_tokens": trace.total_tokens,
                    "email_format": trace.email_format,
                    "message_count": trace.message_count,
                })

            # Build email context
            email_context = {}
            if email:
                email_context = {
                    "subject": email.subject,
                    "sender": email.sender,
                    "status": email.status,
                    "has_attachments": email.has_attachments,
                    "extracted_patient_ids": email.extracted_patient_ids,
                }

            if not traces_compact and not email_context:
                return JSONResponse(content={
                    "conversation_id": conversation_id,
                    "summary": "No trace data found for this conversation."
                })

            # Build prompt
            prompt = f"""You are an expert at analyzing email processing traces for Precise Imaging's email classification system.

Given the following data for conversation {conversation_id}, provide a clear, structured summary of what happened during processing.

EMAIL METADATA:
{json.dumps(email_context, indent=2, default=str)}

PROCESSING TRACES (in order):
{json.dumps(traces_compact, indent=2, default=str)}

Please summarize:
1. **Email Overview**: What the email was about (subject, sender, apparent intent)
2. **Processing Steps**: What steps completed and their key outcomes
3. **Classification Result**: Final tags/classification path chosen, and the reasoning
4. **Document Processing**: If attachments were processed, what was found (document types, patient IDs, lien details, signatures, barcodes, modifications)
5. **Anomalies or Issues**: Any failures, errors, stuck statuses, missing steps, or unexpected results
6. **Autorespond Outcome**: If there was an autorespond decision, what was it

Keep the summary concise but thorough. Use bullet points. If a section has no relevant data, skip it."""

        finally:
            db.close()

        # Call OpenAI API
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "gpt-4o",
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt}
                    ]
                }
            ],
            "max_output_tokens": 2000,
        }

        async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                logger.error(f"OpenAI API error {response.status_code}: {response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"OpenAI API error: {response.status_code}"
                )

            result = response.json()
            # Extract text from Responses API output
            summary_text = ""
            for item in result.get("output", []):
                if item.get("type") == "message":
                    for content_block in item.get("content", []):
                        if content_block.get("type") == "output_text":
                            summary_text += content_block.get("text", "")

            if not summary_text:
                summary_text = "Unable to generate summary from the AI response."

        return JSONResponse(content={
            "conversation_id": conversation_id,
            "summary": summary_text
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error summarizing traces for {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")