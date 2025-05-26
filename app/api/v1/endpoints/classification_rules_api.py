"""API Endpoints for managing classification rules."""

import logging
from typing import List
import os # Added for path manipulation
import asyncio # Added for to_thread
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.classification_rules_service import (
    ClassificationRulesService,
    get_classification_rules_service,
)
from app.models.classification_rule import ClassificationRule as ClassificationRuleModel
from app.services.classification_rule_parser import parse_default_rules, DEFAULT_RULES_FILE_PATH

logger = logging.getLogger(__name__)

router = APIRouter()

# Setup templates
# Ensure you have a 'templates' directory in your project root or adjust path
# You might need to create this directory and an HTML file within it.
# For example, create a templates/classification_rules.html file
templates = Jinja2Templates(directory="app/templates")

# Schema for API responses (optional, but good practice with Pydantic)
# from pydantic import BaseModel
# class ClassificationRuleResponse(BaseModel):
#     id: str
#     category: str
#     name: str
#     content: str
#     is_active: bool
#     version: int
#     created_by: Optional[str]
#     updated_by: Optional[str]
#     class Config:
#         orm_mode = True


@router.get("/rules", response_class=HTMLResponse, name="view_classification_rules_ui")
async def view_rules_ui(
    request: Request, 
    rules_service: ClassificationRulesService = Depends(get_classification_rules_service)
):
    """Display the UI for managing classification rules."""
    try:
        all_rules = await rules_service.get_all_rules(include_inactive=True)
        all_categories = await rules_service.get_all_categories() # For a dropdown or similar
        # logger.info(f"Fetched {len(all_rules)} rules for UI.")
        return templates.TemplateResponse(
            "classification_rules.html", 
            {
                "request": request, 
                "rules": all_rules, 
                "categories": all_categories,
                "top_level_categories": ["Scheduling", "Medical Records & Images", "Accounts Receivable"] # Pass this for new rule creation
            }
        )
    except Exception as e:
        logger.error(f"Error fetching rules for UI: {e}", exc_info=True)
        # You could return an error page or a simple HTML error
        return HTMLResponse(content=f"<html><body><h1>Error loading rules: {e}</h1></body></html>", status_code=500)

@router.post("/rules/add", name="add_classification_rule")
async def add_rule(
    request: Request,
    category: str = Form(...),
    name: str = Form(...),
    content: str = Form(...),
    created_by: str = Form(None), # Or get from logged-in user
    rules_service: ClassificationRulesService = Depends(get_classification_rules_service)
):
    """Add a new classification rule via form submission."""
    try:
        await rules_service.create_rule(category, name, content, created_by)
        # Redirect to the rules UI page after adding
        # Use the route name for url_for to be robust against path changes
        return RedirectResponse(url=router.url_path_for("view_classification_rules_ui"), status_code=303)
    except Exception as e:
        logger.error(f"Error adding rule: {e}", exc_info=True)
        # Handle error, maybe show form again with error message
        # For simplicity, just redirecting back or showing a basic error
        return HTMLResponse(content=f"<html><body><h1>Error adding rule: {e}</h1><a href='{router.url_path_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", status_code=500)

@router.post("/rules/update/{rule_id}", name="update_classification_rule")
async def update_rule_form(
    rule_id: str, 
    request: Request, 
    name: str = Form(...),
    content: str = Form(...),
    updated_by: str = Form(None), # Or get from logged-in user
    rules_service: ClassificationRulesService = Depends(get_classification_rules_service)
):
    """Update an existing rule via form submission."""
    try:
        rule = await rules_service.update_rule(rule_id, name, content, updated_by)
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        return RedirectResponse(url=router.url_path_for("view_classification_rules_ui"), status_code=303)
    except HTTPException:
        raise # Re-raise HTTPExceptions to let FastAPI handle them
    except Exception as e:
        logger.error(f"Error updating rule {rule_id}: {e}", exc_info=True)
        return HTMLResponse(content=f"<html><body><h1>Error updating rule: {e}</h1><a href='{router.url_path_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", status_code=500)

@router.post("/rules/deactivate/{rule_id}", name="deactivate_classification_rule")
async def deactivate_rule_form(
    rule_id: str, 
    request: Request, 
    updated_by: str = Form(None), # Or get from logged-in user
    rules_service: ClassificationRulesService = Depends(get_classification_rules_service)
):
    """Deactivate a rule via form submission."""
    try:
        success = await rules_service.deactivate_rule(rule_id, updated_by)
        if not success:
            raise HTTPException(status_code=404, detail="Rule not found or already inactive")
        return RedirectResponse(url=router.url_path_for("view_classification_rules_ui"), status_code=303)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deactivating rule {rule_id}: {e}", exc_info=True)
        return HTMLResponse(content=f"<html><body><h1>Error deactivating rule: {e}</h1><a href='{router.url_path_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", status_code=500)

# You might want an endpoint to view/edit a single rule in a dedicated form
@router.get("/rules/edit/{rule_id}", response_class=HTMLResponse, name="edit_classification_rule_ui")
async def edit_rule_ui(
    rule_id: str,
    request: Request,
    rules_service: ClassificationRulesService = Depends(get_classification_rules_service)
):
    """Display UI to edit a single classification rule."""
    rule = await rules_service.get_rule_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return templates.TemplateResponse(
        "edit_classification_rule.html", 
        {"request": request, "rule": rule}
    )

# Add more CRUD endpoints as needed (e.g., GET rule by ID API, activate rule)

@router.post("/rules/revert_default", name="revert_to_default_rules")
async def revert_to_default_rules_endpoint(
    request: Request,
    rules_service: ClassificationRulesService = Depends(get_classification_rules_service)
):
    """Reverts all classification rules to the default set from classification_rules.txt."""
    try:
        logger.info("Attempting to revert to default classification rules.")
        # 1. Deactivate all existing rules
        all_existing_rules = await rules_service.get_all_rules(include_inactive=True)
        deactivated_count = 0
        for rule in all_existing_rules:
            if rule.is_active:
                await rules_service.deactivate_rule(rule.id, updated_by="system_revert_to_default")
                deactivated_count += 1
        logger.info(f"Deactivated {deactivated_count} active existing rules.")

        # 2. Parse default rules from the file using the new parser
        # Run the synchronous parser in a separate thread to avoid blocking the event loop
        default_rules_to_add = await asyncio.to_thread(parse_default_rules, DEFAULT_RULES_FILE_PATH)
        
        if not default_rules_to_add:
            logger.warning("No default rules found or parsed from file. No new rules will be added.")
            # It's important to inform the user if the file was empty or unparseable
            # Consider adding a flash message or similar if your frontend supports it.
            return RedirectResponse(url=router.url_path_for("view_classification_rules_ui"), status_code=303)

        # 3. Add new rules from the default set
        added_count = 0
        for rule_data in default_rules_to_add:
            try:
                # Check if a rule with the same category and name already exists (even if inactive)
                # This is a simple check; your service might have more robust ways to handle this.
                existing = await rules_service.get_rules_by_category_and_name(rule_data["category"], rule_data["name"])
                if not existing: # Only create if it doesn't exist by this exact name/category
                    await rules_service.create_rule(
                        category=rule_data["category"],
                        name=rule_data["name"],
                        content=rule_data["content"],
                        created_by=rule_data["created_by"]
                    )
                    added_count += 1
                else:
                    logger.info(f"Default rule '{rule_data['name']}' for category '{rule_data['category']}' already exists. Skipping creation.")

            except Exception as e:
                logger.error(f"Error creating default rule '{rule_data.get('name')}' for category '{rule_data.get('category')}': {e}", exc_info=True)
        
        logger.info(f"Added {added_count} new default rules.")
        # Redirect to the rules UI page
        return RedirectResponse(url=router.url_path_for("view_classification_rules_ui"), status_code=303)
    except Exception as e:
        logger.error(f"Error reverting to default rules: {e}", exc_info=True)
        return HTMLResponse(content=f"<html><body><h1>Error reverting to default rules: {e}</h1><a href='{router.url_path_for('view_classification_rules_ui')}'>Back to rules</a></body></html>", status_code=500) 