"""API Endpoints for managing file-based classification rules."""

import logging
from typing import List, Dict, Any
import os
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Path
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.services.file_based_rules_service import get_file_based_rules_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Setup templates
templates = Jinja2Templates(directory="app/templates")


@router.get("/rules", response_class=HTMLResponse, name="view_classification_rules_ui")
async def view_rules_ui(request: Request):
    """Display the UI for managing file-based classification rules."""
    try:
        rules_service = get_file_based_rules_service()
        all_rules = rules_service.list_all_rules()
        
        logger.info(f"Fetched {len(all_rules)} file-based rules for UI.")
        return templates.TemplateResponse(
            "file_based_rules.html",
            {
                "request": request, 
                "rules": all_rules,
                "total_rules": len(all_rules),
                "rules_with_content": sum(1 for r in all_rules if r['has_content']),
                "total_chars": sum(r['content_length'] for r in all_rules)
            }
        )
    except Exception as e:
        logger.error(f"Error fetching file-based rules for UI: {e}", exc_info=True)
        return HTMLResponse(content=f"<html><body><h1>Error loading rules: {e}</h1></body></html>", status_code=500)


@router.get("/rules/api/list")
async def list_rules_api():
    """API endpoint to list all rules as JSON."""
    try:
        rules_service = get_file_based_rules_service()
        all_rules = rules_service.list_all_rules()
        
        # Convert datetime objects to strings for JSON serialization
        for rule in all_rules:
            rule['modified_time'] = rule['modified_time'].isoformat()
            
        return JSONResponse(content={
            "success": True,
            "rules": all_rules,
            "total": len(all_rules)
        })
    except Exception as e:
        logger.error(f"Error in list rules API: {e}", exc_info=True)
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)


@router.get("/rules/api/get/{rule_key}")
async def get_rule_api(rule_key: str):
    """API endpoint to get a specific rule's content."""
    try:
        rules_service = get_file_based_rules_service()
        content = rules_service.get_rule_content(rule_key)
        
        if content is None:
            return JSONResponse(content={
                "success": False,
                "error": f"Rule '{rule_key}' not found"
            }, status_code=404)
            
        return JSONResponse(content={
            "success": True,
            "rule_key": rule_key,
            "content": content,
            "length": len(content)
        })
    except Exception as e:
        logger.error(f"Error getting rule {rule_key}: {e}", exc_info=True)
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)


@router.post("/rules/api/save/{rule_key}")
async def save_rule_api(
    rule_key: str,
    request: Request
):
    """API endpoint to save rule content."""
    try:
        body = await request.json()
        content = body.get('content', '')
        
        rules_service = get_file_based_rules_service()
        success = rules_service.save_rule_content(rule_key, content)
        
        if success:
            return JSONResponse(content={
                "success": True,
                "message": f"Rule '{rule_key}' saved successfully",
                "rule_key": rule_key,
                "length": len(content)
            })
        else:
            return JSONResponse(content={
                "success": False,
                "error": f"Failed to save rule '{rule_key}'"
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"Error saving rule {rule_key}: {e}", exc_info=True)
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)


@router.post("/rules/add", name="add_classification_rule")
async def add_rule(
    request: Request,
    rule_key: str = Form(...),
    content: str = Form(...)
):
    """Add a new classification rule via form submission."""
    try:
        rules_service = get_file_based_rules_service()
        
        # Check if rule already exists
        if rules_service.rule_exists(rule_key):
            return HTMLResponse(
                content=f"<html><body><h1>Error: Rule '{rule_key}' already exists</h1>"
                f"<a href='{request.url_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", 
                status_code=400
            )
        
        success = rules_service.save_rule_content(rule_key, content)
        
        if success:
            return RedirectResponse(url=request.url_for("view_classification_rules_ui"), status_code=303)
        else:
            return HTMLResponse(
                content=f"<html><body><h1>Error: Failed to create rule '{rule_key}'</h1>"
                f"<a href='{request.url_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", 
                status_code=500
            )
            
    except Exception as e:
        logger.error(f"Error adding rule: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<html><body><h1>Error adding rule: {e}</h1>"
            f"<a href='{request.url_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", 
            status_code=500
        )


@router.post("/rules/update/{rule_key}", name="update_classification_rule")
async def update_rule_form(
    rule_key: str, 
    request: Request, 
    content: str = Form(...)
):
    """Update an existing rule via form submission."""
    try:
        rules_service = get_file_based_rules_service()
        
        # Check if rule exists
        if not rules_service.rule_exists(rule_key):
            raise HTTPException(status_code=404, detail=f"Rule '{rule_key}' not found")
        
        success = rules_service.save_rule_content(rule_key, content)
        
        if success:
            return RedirectResponse(url=request.url_for("view_classification_rules_ui"), status_code=303)
        else:
            return HTMLResponse(
                content=f"<html><body><h1>Error: Failed to update rule '{rule_key}'</h1>"
                f"<a href='{request.url_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", 
                status_code=500
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating rule {rule_key}: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<html><body><h1>Error updating rule: {e}</h1>"
            f"<a href='{request.url_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", 
            status_code=500
        )


@router.post("/rules/delete/{rule_key}", name="delete_classification_rule")
async def delete_rule_form(
    rule_key: str, 
    request: Request
):
    """Delete a rule via form submission."""
    try:
        rules_service = get_file_based_rules_service()
        
        # Check if rule exists
        if not rules_service.rule_exists(rule_key):
            raise HTTPException(status_code=404, detail=f"Rule '{rule_key}' not found")
        
        success = rules_service.delete_rule(rule_key)
        
        if success:
            return RedirectResponse(url=request.url_for("view_classification_rules_ui"), status_code=303)
        else:
            return HTMLResponse(
                content=f"<html><body><h1>Error: Failed to delete rule '{rule_key}'</h1>"
                f"<a href='{request.url_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", 
                status_code=500
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting rule {rule_key}: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<html><body><h1>Error deleting rule: {e}</h1>"
            f"<a href='{request.url_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", 
            status_code=500
        )


@router.get("/rules/edit/{rule_key}", response_class=HTMLResponse, name="edit_classification_rule_ui")
async def edit_rule_ui(
    rule_key: str,
    request: Request
):
    """Display UI to edit a single classification rule."""
    try:
        rules_service = get_file_based_rules_service()
        
        if not rules_service.rule_exists(rule_key):
            raise HTTPException(status_code=404, detail=f"Rule '{rule_key}' not found")
        
        content = rules_service.get_rule_content(rule_key) or ""
        
        # Get rule info from the list
        all_rules = rules_service.list_all_rules()
        rule_info = next((r for r in all_rules if r['rule_key'] == rule_key), None)
        
        if not rule_info:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_key}' not found")
        
        return templates.TemplateResponse(
            "edit_file_based_rule.html", 
            {
                "request": request, 
                "rule_key": rule_key,
                "content": content,
                "rule_info": rule_info
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading edit UI for rule {rule_key}: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<html><body><h1>Error loading rule: {e}</h1>"
            f"<a href='{request.url_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", 
            status_code=500
        )


@router.post("/rules/export", name="export_classification_rules")
async def export_rules(request: Request):
    """Export all rules to JSON format."""
    try:
        rules_service = get_file_based_rules_service()
        all_rules = rules_service.list_all_rules()
        
        export_data = {}
        for rule_info in all_rules:
            rule_key = rule_info['rule_key']
            content = rules_service.get_rule_content(rule_key) or ""
            export_data[rule_key] = {
                "content": content,
                "file_path": rule_info['file_path'],
                "content_length": len(content),
                "modified_time": rule_info['modified_time'].isoformat()
            }
        
        return JSONResponse(content={
            "success": True,
            "exported_rules": len(export_data),
            "rules": export_data
        })
        
    except Exception as e:
        logger.error(f"Error exporting rules: {e}", exc_info=True)
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)


@router.get("/rules/stats")
async def get_rules_stats():
    """Get statistics about the rules."""
    try:
        rules_service = get_file_based_rules_service()
        all_rules = rules_service.list_all_rules()
        
        total_rules = len(all_rules)
        rules_with_content = sum(1 for r in all_rules if r['has_content'])
        total_chars = sum(r['content_length'] for r in all_rules)
        avg_length = total_chars / total_rules if total_rules > 0 else 0
        
        return JSONResponse(content={
            "success": True,
            "stats": {
                "total_rules": total_rules,
                "rules_with_content": rules_with_content,
                "empty_rules": total_rules - rules_with_content,
                "total_characters": total_chars,
                "average_length": round(avg_length, 1)
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting rules stats: {e}", exc_info=True)
        return JSONResponse(content={
            "success": False,
            "error": str(e)
        }, status_code=500)


@router.post("/rules/revert_default", name="revert_to_default_rules")
async def revert_to_default_rules_endpoint(request: Request):
    """Reset rules to default structure by copying from classification_rules.txt."""
    try:
        from app.core.config import settings
        import shutil
        from pathlib import Path
        
        # Copy the main classification_rules.txt to ROOT.txt
        source_file = Path("/app/prompts/classification_rules.txt")
        rules_dir = Path("/app/prompts/rules")
        root_file = rules_dir / "ROOT.txt"
        
        if source_file.exists():
            # Ensure rules directory exists
            rules_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy classification_rules.txt to ROOT.txt
            shutil.copy2(source_file, root_file)
            logger.info("Copied classification_rules.txt to ROOT.txt")
            
            return RedirectResponse(url=request.url_for("view_classification_rules_ui"), status_code=303)
        else:
            return HTMLResponse(
                content=f"<html><body><h1>Error: Source file {source_file} not found</h1>"
                f"<a href='{request.url_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", 
                status_code=500
            )
            
    except Exception as e:
        logger.error(f"Error reverting to default rules: {e}", exc_info=True)
        return HTMLResponse(
            content=f"<html><body><h1>Error reverting to default rules: {e}</h1>"
            f"<a href='{request.url_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", 
            status_code=500
        )