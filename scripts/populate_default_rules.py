import asyncio
import logging
import os
import sys
import json

# Add the project root to the Python path to allow importing app modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.db.session import AsyncSessionLocal, engine # Added engine
from app.services.classification_rules_service import ClassificationRulesService
from app.services.classification_rule_parser import parse_default_rules, DEFAULT_RULES_FILE_PATH
# from app.db.base import Base # Commented out Base.metadata.create_all
from app.models.classification_rule import ClassificationRule # For type hinting

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PRIMARY_RULE_NAME = "PRIMARY_CLASSIFICATION_RULES"
ROOT_CATEGORY_NAME = "ROOT" # Special category for the primary rule

async def create_or_update_rule(
    rules_service: ClassificationRulesService,
    name: str,
    category: str,
    content: str,
    created_by: str = "system_populate_script"
) -> ClassificationRule:
    """Helper to create or update a classification rule. Ensures the rule is active."""
    existing_rules = await rules_service.get_rules_by_category_and_name(category, name)
    
    if existing_rules:
        rule_to_update = existing_rules[0]
        
        needs_content_update = rule_to_update.content != content
        # Check if name needs update (in case the rule was found by category but name casing differs, etc.)
        needs_name_update = rule_to_update.name != name 
        is_currently_inactive = not rule_to_update.is_active

        if needs_content_update or needs_name_update or is_currently_inactive:
            logger.info(f"Updating existing rule: Category='{category}', Name='{name}'")
            # Call the service's update_rule. It handles content, name, updated_by, version, and its own commit.
            updated_rule = await rules_service.update_rule(
                rule_id=rule_to_update.id,
                name=name,  # Pass the target name
                content=content,
                updated_by=created_by
                # No is_active here, as the service method doesn't take it.
            )
            
            # If the rule was inactive, and update_rule succeeded, we now ensure it's marked active.
            # The updated_rule object is the one refreshed from the DB after the service's commit.
            if is_currently_inactive and updated_rule and not updated_rule.is_active:
                logger.info(f"Activating rule that was updated/previously inactive: {updated_rule.name}")
                updated_rule.is_active = True
                # This change to updated_rule.is_active will be part of the session
                # and will be committed by the calling function's (e.g., main script's) final db.commit().
                # Note: The service's update_rule already committed other changes.
                # If relying on an outer commit, ensure the object is in the session correctly.
                # Re-adding to session explicitly if there's any doubt, though refresh should keep it managed.
                # rules_service.db.add(updated_rule) # Usually not needed if object came from session and was refreshed.

            return updated_rule # This is the rule object, potentially with is_active modified in memory
        else:
            logger.info(f"Rule Category='{category}', Name='{name}' is unchanged and already active. Skipping update.")
            return rule_to_update
           
    else:
        # Create new rule (will be active by default as per model)
        logger.info(f"Creating new rule: Category='{category}', Name='{name}'")
        return await rules_service.create_rule(
            name=name,
            category=category,
            content=content,
            created_by=created_by
        )

async def populate_hierarchical_rules(
    rules_service: ClassificationRulesService,
    email_categories_dict: dict,
    parent_category_name: str
):
    """Recursively populates rules based on the EMAIL_CATEGORIES structure."""
    added_count = 0
    updated_count = 0

    for child_name, sub_children in email_categories_dict.items():
        current_rule_content = ""
        is_parent_node = isinstance(sub_children, dict) or (isinstance(sub_children, list) and sub_children)

        if is_parent_node:
            if isinstance(sub_children, dict):
                children_names = list(sub_children.keys())
            else: # It's a list of strings
                children_names = sub_children
            current_rule_content = f"Rules to classify among: {', '.join(children_names)}. (To be defined by user)."
            
            rule = await create_or_update_rule(
                rules_service,
                name=child_name,
                category=parent_category_name,
                content=current_rule_content
            )
            if rule: # Check if rule was actually created or updated
                # Check if it was a create or update based on presence of existing rules (done inside create_or_update_rule logic)
                # This part is tricky because create_or_update_rule handles both.
                # We'll rely on logs from create_or_update_rule for specific create/update counts.
                pass


            # Recursive call for nested dictionaries (which represent further parent nodes)
            if isinstance(sub_children, dict):
                # The 'parent_category_name' for the next level is 'child_name'
                sub_added, sub_updated = await populate_hierarchical_rules(rules_service, sub_children, child_name)
                added_count += sub_added
                updated_count += sub_updated
        # else:
            # Leaf nodes (simple strings or empty lists) do not get their own rule *set*
            # They are the outcomes of their parent's rule set.
            # logger.debug(f"Leaf node '{child_name}' under '{parent_category_name}' will not have its own rule set record.")

    return added_count, updated_count # These counts are not accurately reflecting due to create_or_update internal logic


async def main():
    logger.info("Starting default classification rules population script.")

    # In a production setup, you'd typically use Alembic migrations.
    # We are not creating tables here anymore as it should be handled by migrations.
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    # logger.info("Database tables checked/created (if necessary via Base.metadata.create_all).")

    db = AsyncSessionLocal()
    if not db:
        logger.error("Failed to create a database session. Exiting.")
        return

    try:
        rules_service = ClassificationRulesService(db)

        # 1. Populate the Primary Classification Rule
        logger.info(f"Parsing primary rules from: {DEFAULT_RULES_FILE_PATH}")
        try:
            primary_rules_content = parse_default_rules(DEFAULT_RULES_FILE_PATH)
        except Exception as e:
            logger.error(f"Failed to parse primary rules file: {e}. Aborting script.")
            return

        await create_or_update_rule(
            rules_service,
            name=PRIMARY_RULE_NAME,
            category=ROOT_CATEGORY_NAME,
            content=primary_rules_content
        )
        
        # 2. Populate Hierarchical Rules from EMAIL_CATEGORIES (Temporarily Commented Out)
        # logger.info("Skipping hierarchical rule population for this run.")
        # email_categories_json = os.getenv("EMAIL_CATEGORIES")
        # if not email_categories_json:
        #     logger.error("EMAIL_CATEGORIES environment variable not set. Cannot populate hierarchical rules.")
        # else:
        #     try:
        #         email_categories_dict = json.loads(email_categories_json)
        #         logger.info("Successfully parsed EMAIL_CATEGORIES JSON.")
        #         
        #         await populate_hierarchical_rules(rules_service, email_categories_dict, PRIMARY_RULE_NAME)

        #     except json.JSONDecodeError as e:
        #         logger.error(f"Failed to parse EMAIL_CATEGORIES JSON: {e}")
        #     except Exception as e:
        #         logger.error(f"An unexpected error occurred during hierarchical rule population: {e}", exc_info=True)

        await db.commit()
        logger.info("Database commit successful for primary rule population.")
    except Exception as e:
        logger.error(f"An error occurred during the population script: {e}", exc_info=True)
        await db.rollback()
        logger.info("Database rollback initiated due to error.")
    finally:
        await db.close()
        logger.info("Database session closed.")

if __name__ == "__main__":
    asyncio.run(main()) 