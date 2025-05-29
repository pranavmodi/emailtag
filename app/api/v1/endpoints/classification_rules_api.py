"""API Endpoints for managing classification rules."""

import logging
from typing import List
import os # Added for path manipulation
import asyncio # Added for to_thread
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Path
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session # Keep Session for type hinting if used elsewhere, or remove if not
from sqlalchemy.ext.asyncio import AsyncSession # Corrected import
import uuid # For rule_id type conversion

from app.db.session import get_db
from app.services.classification_rules_service import (
    ClassificationRulesService,
    get_classification_rules_service,
)
from app.models.classification_rule import ClassificationRule as ClassificationRuleModel
from app.services.classification_rule_parser import parse_default_rules, DEFAULT_RULES_FILE_PATH
from scripts.populate_default_rules import (
    PRIMARY_RULE_NAME, 
    ROOT_CATEGORY_NAME, 
    create_or_update_rule,
    populate_hierarchical_rules
)

from app.services.hierarchical_rules_service import (
    HierarchicalRulesService,
    get_hierarchical_rules_service,
)
from app.models.hierarchical_classification_rule import HierarchicalClassificationRule # For type hinting if needed

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
    # Old service, comment out or remove if no longer used by this specific endpoint
    # rules_service: ClassificationRulesService = Depends(get_classification_rules_service)
    # New service for hierarchical rules
    hierarchical_rules_service: HierarchicalRulesService = Depends(get_hierarchical_rules_service)
):
    """Display the UI for managing classification rules. Now uses hierarchical rules."""
    try:
        # Fetch hierarchical rules. Decide if you want to include full rule content on the main page.
        # For performance, if rules are very long, you might set include_rule_content=False
        # and have a separate view/edit page that loads the full content.
        # For now, let's assume we want it for the display.
        all_hier_rules = await hierarchical_rules_service.get_all_hierarchical_rules(include_rule_content=True)
        
        # The concepts of 'all_categories' and 'top_level_categories' as previously fetched
        # from the old ClassificationRulesService might need to be re-evaluated or removed
        # if they don't directly apply or are sourced differently with the new table.
        # For now, I will comment them out to avoid errors if they are not needed by the new template.
        # all_categories = await rules_service.get_all_categories()
        # top_level_categories = ["Scheduling", "Medical Records & Images", "Accounts Receivable"]

        logger.info(f"Fetched {len(all_hier_rules)} hierarchical rules for UI.")
        return templates.TemplateResponse(
            "hierarchical_rules.html", # New template name
            {
                "request": request, 
                "rules": all_hier_rules, # Pass the new rules data
                # "categories": all_categories, # Commented out
                # "top_level_categories": top_level_categories # Commented out
            }
        )
    except Exception as e:
        logger.error(f"Error fetching hierarchical rules for UI: {e}", exc_info=True)
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
    db: AsyncSession = Depends(get_db) 
):
    """Reverts all classification rules to the default set defined by classification_rules.txt and EMAIL_CATEGORIES."""
    logger.info("Attempting to revert to default classification rules structure.")
    
    from scripts.populate_default_rules import (
        PRIMARY_RULE_NAME, 
        ROOT_CATEGORY_NAME, 
        create_or_update_rule,
        populate_hierarchical_rules
    )
    from app.services.classification_rule_parser import parse_default_rules, DEFAULT_RULES_FILE_PATH
    from app.services.classification_rules_service import ClassificationRulesService
    import json 
    import os

    rules_service = ClassificationRulesService(db)

    try:
        # 0. Deactivate all existing rules first
        logger.info("Deactivating all existing rules before revert.")
        all_db_rules = await rules_service.get_all_rules(include_inactive=True)
        deactivated_count = 0
        for rule in all_db_rules:
            if rule.is_active:
                # Use the service method for deactivation if it handles versioning/updated_by correctly
                # or update directly if simpler and service method is too complex for this bulk op.
                # For now, direct update for simplicity in bulk:
                rule.is_active = False
                rule.updated_by = "system_revert_to_default_deactivation"
                # rule.version += 1 # If direct, manage version
                db.add(rule) # Re-add to session if making direct changes
                deactivated_count += 1
        
        if deactivated_count > 0:
            await db.commit() # Commit deactivations
            logger.info(f"Deactivated {deactivated_count} rules.")
        else:
            logger.info("No active rules found to deactivate.")
            # Important: if commit was not called, rollback previous (if any) uncommitted changes from session
            # or ensure session is clean. For safety, a rollback here if no commit happened.
            await db.rollback()


        # 1. Populate the Primary Classification Rule
        logger.info(f"Parsing primary rules from: {DEFAULT_RULES_FILE_PATH}")
        try:
            primary_rules_content = await asyncio.to_thread(parse_default_rules, DEFAULT_RULES_FILE_PATH)
        except Exception as e:
            logger.error(f"Failed to parse primary rules file during revert: {e}")
            back_url = request.url_for("view_classification_rules_ui")
            return HTMLResponse(content=f"<html><body><h1>Error parsing default rules file: {e}</h1><a href='{back_url}'>Back to rules</a></body></html>", status_code=500)

        primary_rule_description = "Primary rules for classifying an incoming email into one of the top-level categories: Scheduling, Medical Records & Images, or Accounts Receivable. This is the first stage of classification."

        await create_or_update_rule(
            rules_service,
            name=PRIMARY_RULE_NAME,
            category=ROOT_CATEGORY_NAME,
            content=primary_rules_content,
            description=primary_rule_description,
            created_by="system_revert_to_default"
        )
        
        # 2. Populate Hierarchical Rules from EMAIL_CATEGORIES
        email_categories_json = os.getenv("EMAIL_CATEGORIES")
        if not email_categories_json:
            logger.error("EMAIL_CATEGORIES environment variable not set. Cannot populate hierarchical rules during revert.")
            back_url = request.url_for("view_classification_rules_ui")
            return HTMLResponse(content=f"<html><body><h1>EMAIL_CATEGORIES not set. Hierarchical rules not populated.</h1><a href='{back_url}'>Back to rules</a></body></html>", status_code=500)
        else:
            try:
                email_categories_dict = json.loads(email_categories_json)
                logger.info("Successfully parsed EMAIL_CATEGORIES JSON during revert.")
                
                await populate_hierarchical_rules(rules_service, email_categories_dict, PRIMARY_RULE_NAME)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse EMAIL_CATEGORIES JSON during revert: {e}")
                back_url = request.url_for("view_classification_rules_ui")
                return HTMLResponse(content=f"<html><body><h1>Error parsing EMAIL_CATEGORIES: {e}</h1><a href='{back_url}'>Back to rules</a></body></html>", status_code=500)
            except Exception as e:
                logger.error(f"An unexpected error occurred during hierarchical rule population in revert: {e}", exc_info=True)
                back_url = request.url_for("view_classification_rules_ui")
                return HTMLResponse(content=f"<html><body><h1>Unexpected error during rule population: {e}</h1><a href='{back_url}'>Back to rules</a></body></html>", status_code=500)

        await db.commit()
        logger.info("Successfully reverted to default rules structure.")
        return RedirectResponse(url=request.url_for("view_classification_rules_ui"), status_code=303)

    except Exception as e:
        logger.error(f"Error reverting to default rules: {e}", exc_info=True)
        await db.rollback()
        back_url = request.url_for("view_classification_rules_ui")
        return HTMLResponse(content=f"<html><body><h1>Error reverting to default rules: {e}</h1><a href='{back_url}'>Back to rules</a></body></html>", status_code=500) 

# --- Endpoints for Hierarchical Rules Edit --- 

@router.get("/rules/edit_hierarchical/{rule_id}", response_class=HTMLResponse, name="edit_hierarchical_rule_ui")
async def edit_hierarchical_rule_ui_form(
    request: Request,
    rule_id: uuid.UUID = Path(..., title="The ID of the hierarchical rule to edit"),
    hierarchical_rules_service: HierarchicalRulesService = Depends(get_hierarchical_rules_service)
):
    """Display UI to edit a single hierarchical classification rule."""
    rule = await hierarchical_rules_service.get_hierarchical_rule_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail=f"Hierarchical rule with ID {rule_id} not found")
    return templates.TemplateResponse(
        "edit_hierarchical_rule.html", 
        {"request": request, "rule": rule}
    )

@router.post("/rules/update_hierarchical/{rule_id}", name="update_hierarchical_rule_form")
async def handle_update_hierarchical_rule_form(
    request: Request, 
    rule_id: uuid.UUID = Path(..., title="The ID of the hierarchical rule to update"),
    name: str = Form(...),
    rule_content: str = Form(...),
    hierarchical_rules_service: HierarchicalRulesService = Depends(get_hierarchical_rules_service)
):
    """Update an existing hierarchical rule via form submission."""
    updated_rule = await hierarchical_rules_service.update_hierarchical_rule(
        rule_id=rule_id, 
        name=name, 
        rule_content=rule_content
    )
    if not updated_rule:
        # This could happen if the service returns None (e.g., rule not found during update attempt)
        # Consider how the service signals this - raising an exception there might be cleaner.
        # For now, assume service handles logging and we show a generic error or re-raise.
        raise HTTPException(status_code=404, detail=f"Hierarchical rule with ID {rule_id} not found or failed to update.")
    
    # Redirect to the main rules UI page after updating
    # The main rules UI is still named view_classification_rules_ui, which is fine.
    return RedirectResponse(url=router.url_path_for("view_classification_rules_ui"), status_code=303)

# These old endpoints still operate on the ClassificationRulesService and old table.
# They would need to be refactored or removed if the old system is fully deprecated. 