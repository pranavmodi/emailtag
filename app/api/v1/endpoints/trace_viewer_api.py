"""API Endpoints for viewing email processing traces."""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc

from app.services.trace_service import get_conversation_traces, get_conversation_traces_async
from app.crud.sync import processing_trace as trace_crud_sync
from app.db.session import SessionLocal
from app.api.api_v1.dependencies import check_authenticated
from app.models.classification_trace import ClassificationTrace

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

@router.get("/classification-traces", response_class=HTMLResponse, name="view_classification_traces_ui")
async def view_classification_traces_ui(
    request: Request,
    conversation_id: Optional[str] = Query(None),
    is_authenticated: bool = Depends(check_authenticated)
):
    """Display the UI for viewing classification traces with collapsible prompts and responses."""
    if not is_authenticated:
        return RedirectResponse(url="/login", status_code=303)

    try:
        traces = []

        if conversation_id:
            # Get classification traces for the specific conversation
            db = SessionLocal()
            try:
                traces = db.query(ClassificationTrace).filter(
                    ClassificationTrace.front_conversation_id == conversation_id
                ).order_by(ClassificationTrace.step_order).all()

                logger.info(f"Fetched {len(traces)} classification traces for conversation {conversation_id}")
            finally:
                db.close()

        # Convert traces to dict format for template
        traces_data = []
        for trace in traces:
            trace_dict = {
                "id": str(trace.id),
                "step_name": trace.step_name,
                "step_order": trace.step_order,
                "classification_path": trace.classification_path,
                "llm_model": trace.llm_model,
                "prompt_template": trace.prompt_template,
                "full_prompt": trace.full_prompt,
                "llm_response": trace.llm_response,
                "chosen_option": trace.chosen_option,
                "email_format": trace.email_format,
                "message_count": trace.message_count,
                "started_at": trace.started_at.isoformat() if trace.started_at else None,
                "completed_at": trace.completed_at.isoformat() if trace.completed_at else None,
                "duration_ms": trace.duration_ms,
                "prompt_tokens": trace.prompt_tokens,
                "completion_tokens": trace.completion_tokens,
                "total_tokens": trace.total_tokens,
                "document_analysis": trace.document_analysis
            }
            traces_data.append(trace_dict)

        return templates.TemplateResponse(
            "classification_trace_viewer.html",
            {
                "request": request,
                "conversation_id": conversation_id or "",
                "traces": traces_data,
                "total_traces": len(traces_data),
                "total_duration": sum(t["duration_ms"] for t in traces_data if t["duration_ms"]) if traces_data else 0,
                "total_tokens": sum(t["total_tokens"] for t in traces_data if t["total_tokens"]) if traces_data else 0
            }
        )
    except Exception as e:
        logger.error(f"Error fetching classification traces for UI: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<html><body><h1>Error loading classification traces: {e}</h1></body></html>",
            status_code=500
        )


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